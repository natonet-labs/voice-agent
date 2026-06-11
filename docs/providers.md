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
2. In the ElevenLabs CAI agent settings, set the LLM to **Custom LLM** and
   point it at `https://<public-host>/v1/chat/completions`.
3. Pick an ElevenLabs voice for TTS.

```
Caller -> ElevenLabs CAI (STT + turns + TTS) -> this service -> Claude
```

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
