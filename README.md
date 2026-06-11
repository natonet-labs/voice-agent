# Voice Agent

![Status](https://img.shields.io/badge/Status-In%20Progress-yellow)
![Phase](https://img.shields.io/badge/Phase-1%20Bootstrap-blue)
![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C)
![FastAPI](https://img.shields.io/badge/Serving-FastAPI-009688?logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757)
![Deploy](https://img.shields.io/badge/Deploy-K3s%20(panda--worker)-326CE5?logo=kubernetes&logoColor=white)

## Project Overview

A LangChain / LangGraph agent that acts as the brain behind an AI voice
assistant. The voice SaaS provider handles the phone/web call, transcription,
turn-taking, and speech; this service owns the reasoning — state, tools, memory,
and routing — and is exposed to the provider as an OpenAI-compatible "custom
LLM" endpoint.

It is the application-layer companion to the `bare-metal-mlops-sandbox` cluster:
that project built the bare-metal K3s infrastructure; this one runs a real
workload on it. The agent deploys as a containerized service on `panda-worker`,
served from the cluster's local Docker registry and observed by its
Prometheus / Grafana stack.

## Architecture

```
   Caller
     |
     v
  ElevenLabs Conversational AI        (Option A: transport + STT + TTS)
     |  custom-LLM HTTPS
     |  (exposed via Tailscale Funnel)
     v
  panda-worker (K3s, containerized)
     |  FastAPI + LangGraph agent  ---> Claude API (LLM)
     |  /metrics  --> Prometheus / Grafana (panda-control)
     v
  reply spoken back to the caller
```

The provider front end is swappable — ElevenLabs now (Option A), Vapi or Retell
later (Option B) — because all three call the same `/v1/chat/completions`
contract. See [docs/providers.md](docs/providers.md).

## Stack

- **Orchestration:** LangGraph (explicit `StateGraph`)
- **LLM:** Claude (via `langchain-anthropic`)
- **Serving:** FastAPI + Uvicorn, OpenAI-compatible custom-LLM endpoint
- **Voice (Option A):** ElevenLabs Conversational AI
- **Deploy:** Docker image to the cluster's local registry, runs on `panda-worker`
- **Observability:** Prometheus `/metrics`, scraped by `panda-control`

## Quickstart (local, no voice provider)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env        # set ANTHROPIC_API_KEY
voice-agent-chat            # text REPL against the LangGraph agent
```

Run the HTTP endpoint locally:

```bash
uvicorn voice_agent.server:app --reload --port 8080
curl -s localhost:8080/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"hello"}]}' | jq
```

## Roadmap

| # | Milestone | Status |
|---|---|---|
| 1 | LangGraph agent + local text REPL | Done |
| 2 | Tools and persistent memory (checkpointer) | Done |
| 3 | OpenAI-compatible custom-LLM endpoint (FastAPI) | Done |
| 4 | Connect ElevenLabs Conversational AI, text round-trip | Upcoming |
| 5 | Containerize and deploy to panda-worker via local registry | Upcoming |
| 6 | Tailscale Funnel exposes the webhook to the provider cloud | Upcoming |
| 7 | Turn latency / token-cost metrics in Grafana | Upcoming |
| 8 | Option B: front with Vapi or Retell (config-only) | Future |

## Layout

```
src/voice_agent/
  agent.py        LangGraph StateGraph + persistent SQLite checkpointer
  tools.py        agent tools (time, timezone, calculator, remember/recall)
  memory_store.py SQLite-backed long-term facts (cross-conversation memory)
  server.py       FastAPI OpenAI-compatible endpoint + /health + /metrics
  chat.py         local text REPL (stable thread, persists across restarts)
  config.py       env-driven settings
deploy/k8s/       Deployment (pinned to panda-worker) + Service + Secret example
docs/             provider integration notes
data/             local SQLite state (gitignored)
```
