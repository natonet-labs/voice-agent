"""OpenAI-compatible custom-LLM endpoint.

ElevenLabs Conversational AI (Option A), Vapi, and Retell (Option B) all speak
the same contract: they POST an OpenAI-style chat-completion request to a URL
you own, and read back the assistant reply. Implementing that contract once
makes the agent portable across all three — switching providers is config, not
code.

Endpoints:
    POST /v1/chat/completions   the custom-LLM contract (stream + non-stream)
    GET  /health                liveness/readiness probe
    GET  /metrics               Prometheus scrape target (panda-control scrapes this)
"""

import json
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

from voice_agent.agent import agent
from voice_agent.config import settings

app = FastAPI(title="voice-agent", version="0.1.0")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

TURNS = Counter("voice_agent_turns_total", "Total chat-completion turns handled")
TURN_LATENCY = Histogram(
    "voice_agent_turn_latency_seconds",
    "End-to-end latency of a single agent turn",
)
INPUT_TOKENS = Counter("voice_agent_input_tokens_total", "Total LLM input tokens")
OUTPUT_TOKENS = Counter("voice_agent_output_tokens_total", "Total LLM output tokens")
COST_USD = Counter("voice_agent_cost_usd_total", "Estimated cumulative LLM cost in USD")

# $ per million tokens. Keyed by model so the estimate stays correct if
# settings.llm_model changes; falls back to the sonnet-4-6 rate otherwise.
_PRICE_PER_MTOK = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


def _record_usage(usage: dict | None) -> None:
    if not usage:
        return
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    INPUT_TOKENS.inc(in_tok)
    OUTPUT_TOKENS.inc(out_tok)
    price = _PRICE_PER_MTOK.get(settings.llm_model, _PRICE_PER_MTOK["claude-sonnet-4-6"])
    COST_USD.inc(in_tok / 1_000_000 * price["input"] + out_tok / 1_000_000 * price["output"])


class ChatMessage(BaseModel):
    role: str
    # ElevenLabs sends plain-text transcripts, but the OpenAI contract also
    # permits a content-parts array (multimodal). Accept both; _content_text
    # flattens to the text we care about.
    content: str | list | None = None


class ChatCompletionRequest(BaseModel):
    # Only the fields we act on are named. ElevenLabs also POSTs temperature,
    # max_tokens, user_id, elevenlabs_extra_body, and tools — pydantic ignores
    # unknown fields by default, and the agent owns its own sampling/tools, so
    # those are intentionally dropped rather than honored per-request.
    messages: list[ChatMessage]
    model: str | None = None
    stream: bool = False


def _content_text(content: str | list | None) -> str:
    """Flatten OpenAI message content (string or content-parts array) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def _to_langchain(messages: list[ChatMessage]) -> list:
    """Map OpenAI-style messages to LangChain messages.

    System messages are dropped — the agent supplies its own voice-tuned
    system prompt (see agent.SYSTEM_PROMPT).
    """
    out = []
    for m in messages:
        if m.role == "user":
            out.append(HumanMessage(content=_content_text(m.content)))
        elif m.role == "assistant":
            out.append(AIMessage(content=_content_text(m.content)))
    return out


def _new_thread() -> dict:
    # Stateless per request: the provider sends full history each turn, so we
    # use a fresh thread id and feed the whole transcript in.
    return {"configurable": {"thread_id": uuid.uuid4().hex}}


def _run_agent(messages: list[ChatMessage]) -> str:
    logger.info("turn start — %d msg(s)", len(messages))
    result = agent.invoke({"messages": _to_langchain(messages)}, _new_thread())
    tools_called = [m.name for m in result["messages"] if isinstance(m, ToolMessage) and m.name]
    if tools_called:
        logger.info("tools called: %s", tools_called)
    for msg in result["messages"]:
        if isinstance(msg, AIMessage):
            _record_usage(msg.usage_metadata)
    return result["messages"][-1].content


def _sse(cid: str, created: int, model: str, delta: dict, finish: str | None) -> str:
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _stream_agent_sse(messages: list[ChatMessage], model: str):
    """Stream the agent's reply token-by-token as OpenAI-style SSE chunks.

    Real streaming (not a single buffered chunk) lets the voice provider's TTS
    start speaking before the full reply is generated — the main latency win
    on a call. We forward only assistant text: the tool-deciding turn carries
    tool_calls with empty text, and tool results aren't AIMessageChunks, so
    both are skipped naturally.
    """
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    start = time.perf_counter()
    n_msgs = len(messages)
    logger.info("turn start — %d msg(s), stream=True", n_msgs)
    yield _sse(cid, created, model, {"role": "assistant"}, None)
    tools_called: list[str] = []
    words = 0
    try:
        for chunk, _meta in agent.stream(
            {"messages": _to_langchain(messages)}, _new_thread(), stream_mode="messages"
        ):
            if isinstance(chunk, ToolMessage) and chunk.name:
                tools_called.append(chunk.name)
            elif isinstance(chunk, AIMessageChunk):
                _record_usage(chunk.usage_metadata)
                text = _content_text(chunk.content)
                if text:
                    words += len(text.split())
                    yield _sse(cid, created, model, {"content": text}, None)
    except Exception:
        logger.exception("agent error after %d msg(s)", n_msgs)
        raise
    finally:
        elapsed = time.perf_counter() - start
        TURN_LATENCY.observe(elapsed)
        logger.info(
            "turn done — %d word(s)%s, %.3fs",
            words,
            f", tools={tools_called}" if tools_called else "",
            elapsed,
        )
    yield _sse(cid, created, model, {}, "stop")
    yield "data: [DONE]\n\n"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    model = req.model or settings.llm_model
    TURNS.inc()

    if req.stream:
        return StreamingResponse(
            _stream_agent_sse(req.messages, model), media_type="text/event-stream"
        )

    start = time.perf_counter()
    text = _run_agent(req.messages)
    elapsed = time.perf_counter() - start
    TURN_LATENCY.observe(elapsed)
    logger.info("turn done — %d word(s), %.3fs", len(text.split()), elapsed)

    return JSONResponse(
        {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }
    )
