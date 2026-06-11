"""Simulate an ElevenLabs Conversational AI custom-LLM request — milestone 4.

ElevenLabs CAI calls your server with an OpenAI-style chat-completion request
and reads back a streamed reply. This script replays that exact contract
against a running endpoint so you can prove the text round-trip locally,
before wiring up the ElevenLabs dashboard and a public tunnel.

    uvicorn voice_agent.server:app --port 8080     # in one terminal
    python scripts/elevenlabs_sim.py "what time is it in Tokyo?"

It POSTs with stream=true plus the extra fields ElevenLabs includes
(temperature, max_tokens, user_id, elevenlabs_extra_body), parses the SSE
stream the way the provider does, and checks the framing: assistant deltas
arrive incrementally and the stream ends with `data: [DONE]`.
"""

import json
import sys

import httpx

URL = "http://localhost:8080/v1/chat/completions"


def main() -> int:
    prompt = " ".join(sys.argv[1:]) or "Hi, what can you do?"
    # The body ElevenLabs CAI sends (see docs/providers.md). The server names
    # only messages/model/stream and ignores the rest — sending them here
    # proves the endpoint tolerates the real provider payload.
    body = {
        "model": "voice-agent",
        "stream": True,
        "temperature": 0.5,
        "max_tokens": 512,
        "user_id": "sim-caller-001",
        "elevenlabs_extra_body": {"conversation_id": "sim"},
        "messages": [{"role": "user", "content": prompt}],
    }

    print(f"you> {prompt}")
    print("bot> ", end="", flush=True)

    text, chunks, saw_done = "", 0, False
    with httpx.stream("POST", URL, json=body, timeout=60.0) as resp:
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" not in ctype:
            print(f"\n[FAIL] expected text/event-stream, got {ctype!r}")
            return 1
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[len("data: ") :]
            if data == "[DONE]":
                saw_done = True
                break
            delta = json.loads(data)["choices"][0]["delta"]
            piece = delta.get("content", "")
            if piece:
                text += piece
                chunks += 1
                print(piece, end="", flush=True)
    print()

    ok = saw_done and text.strip()
    streamed = chunks > 1  # >1 content chunk ⇒ genuinely incremental, not buffered
    print(f"\n[{'OK' if ok else 'FAIL'}] {chunks} content chunk(s), "
          f"[DONE]={'yes' if saw_done else 'NO'}, "
          f"{'incremental' if streamed else 'single-chunk'} streaming")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
