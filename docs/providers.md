# Voice Provider Integration

The agent is a provider-agnostic brain. It exposes one OpenAI-compatible
endpoint — `POST /v1/chat/completions` — that every supported provider calls as
its "custom LLM". Switching or adding a provider is configuration, not code.

## The 4 layers

| Layer | Job | Provider |
|---|---|---|
| Transport + orchestration | Call, turn-taking, barge-in, VAD | ElevenLabs CAI / Vapi / Retell |
| STT | Speech to text | Bundled by the orchestrator |
| LLM (brain) | Decide what to say, call tools | This service + Claude |
| TTS (voice) | Text to speech | ElevenLabs |

## Option A (current) — ElevenLabs Conversational AI

One vendor, uses the existing ElevenLabs account. ElevenLabs CAI handles
transport, STT, turn-taking, and TTS, and calls this service as its custom LLM.

Setup:
1. Deploy this service and expose it publicly (Tailscale Funnel — see README).
2. In the ElevenLabs CAI agent settings, set the LLM to **Custom LLM** and set
   the Server URL to the base `https://<public-host>/v1` (ElevenLabs appends
   `/chat/completions` itself — see the runbook below).
3. Pick an ElevenLabs voice for TTS.

```
Caller -> ElevenLabs CAI (STT + turns + TTS) -> this service -> Claude
```

### The custom-LLM contract (what ElevenLabs actually sends)

ElevenLabs CAI POSTs an OpenAI-style chat-completion request to the URL you
configure and reads back the reply. The body includes `messages`, `model`,
`stream`, and extras this service intentionally ignores — `temperature`,
`max_tokens`, `user_id`, `elevenlabs_extra_body`, and `tools` (the agent owns
its own sampling and tools, see `agent.py`). System messages are dropped in
favor of the agent's voice-tuned `SYSTEM_PROMPT`.

When `stream: true`, the response must be Server-Sent Events: each chunk
`data: {json}\n\n`, terminated by `data: [DONE]\n\n`, with
`Content-Type: text/event-stream`. `server.py` streams Claude's tokens as they
arrive so the provider's TTS can start speaking before the full reply is done —
the main latency lever on a live call.

### Milestone 4 — proving the text round-trip

Before touching the ElevenLabs dashboard or a public URL, prove the contract
locally by replaying the provider's exact request:

```bash
uvicorn voice_agent.server:app --port 8080      # terminal 1
python scripts/elevenlabs_sim.py "what time is it in Tokyo?"   # terminal 2
```

The simulator POSTs a streaming, ElevenLabs-shaped request (extra fields and
all), parses the SSE stream the way the provider does, and asserts the framing
(incremental deltas + `[DONE]`).

### Going live (needs an account + a public URL)

1. Run the agent: `uvicorn voice_agent.server:app --port 8080` (needs
   `ANTHROPIC_API_KEY` in `.env`).
2. Expose it over public HTTPS — `ngrok http 8080` now (copy the
   `https://….ngrok-free.app` URL), or the Tailscale Funnel once deployed
   (milestone 6, which gives a stable URL — ngrok's changes each restart).
3. In the ElevenLabs CAI agent, set LLM → **Custom LLM** and fill in:
   - **Server URL**: `https://<tunnel-host>/v1` — the base ending in `/v1`,
     *not* `/v1/chat/completions`; ElevenLabs appends that.
   - **Model ID**: any string (e.g. `voice-agent`); this server ignores it and
     uses its own configured Claude model.
   - **API key**: the UI requires a secret named `OPENAI_API_KEY` — this server
     does no auth, so any placeholder value (e.g. `unused`) works.
4. Open the agent's test chat and send a message; the reply should stream back,
   and you'll see the POST hit `/v1/chat/completions` in the uvicorn log. That
   round-trip closes milestone 4. Add a voice and call it for milestone 5+.

## Option B (future) — Vapi or Retell + ElevenLabs voice

Pick ONE orchestrator (Vapi or Retell — not both). It runs the call and STT
with best-in-class turn-taking; ElevenLabs provides the TTS voice; this service
remains the brain. No code change here — same endpoint.

```
Caller -> Vapi/Retell (STT + turns) -> this service -> Claude
                 +-----> ElevenLabs (TTS voice) <-----+
```

Setup deltas vs. Option A:
- Add the orchestrator account; set its custom-LLM URL to this same endpoint.
- Bring-your-own ElevenLabs API key for the voice (`ELEVENLABS_API_KEY`).
- Add `VAPI_API_KEY` / `RETELL_API_KEY` to the secret if calling their APIs back.

> Do not run Vapi and Retell simultaneously in one agent — they do the same
> job. Trialling all three over time is fine; the brain is portable.
