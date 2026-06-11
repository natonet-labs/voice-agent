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
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

from voice_agent.agent import agent
from voice_agent.config import settings

app = FastAPI(title="voice-agent", version="0.1.0")

TURNS = Counter("voice_agent_turns_total", "Total chat-completion turns handled")
TURN_LATENCY = Histogram(
    "voice_agent_turn_latency_seconds",
    "End-to-end latency of a single agent turn",
)


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    stream: bool = False


def _to_langchain(messages: list[ChatMessage]) -> list:
    """Map OpenAI-style messages to LangChain messages.

    System messages are dropped — the agent supplies its own voice-tuned
    system prompt (see agent.SYSTEM_PROMPT).
    """
    out = []
    for m in messages:
        if m.role == "user":
            out.append(HumanMessage(content=m.content or ""))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content or ""))
    return out


def _run_agent(messages: list[ChatMessage]) -> str:
    # Stateless per request: the provider sends full history each turn, so we
    # use a fresh thread id and feed the whole transcript in.
    thread = {"configurable": {"thread_id": uuid.uuid4().hex}}
    result = agent.invoke({"messages": _to_langchain(messages)}, thread)
    return result["messages"][-1].content


def _stream_sse(text: str, model: str):
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    first = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(first)}\n\n"
    last = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(last)}\n\n"
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
    with TURN_LATENCY.time():
        text = _run_agent(req.messages)

    if req.stream:
        return StreamingResponse(_stream_sse(text, model), media_type="text/event-stream")

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
