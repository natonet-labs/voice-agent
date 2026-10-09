# LangGraph / LangChain Architecture

How `agent.py` and `server.py` fit together — the graph, the tool-routing
mechanism, and the two memory layers.

## 1. The StateGraph (`agent.py`)

```mermaid
flowchart TD
    START([START]) --> chatbot

    chatbot["chatbot node\n- prepend SYSTEM_PROMPT\n- model.invoke(messages)\n- model is bound to TOOLS"]

    chatbot --> route{"route(): last message\nhas tool_calls?"}

    route -- "yes" --> tools["tools node = ToolNode(TOOLS)\n- look up each tool_call by name\n- invoke(args)\n- wrap result in ToolMessage"]
    route -- "no" --> END([END])

    tools -- "loop back" --> chatbot
```

- **State** = `MessagesState`, basically `{"messages": [...]}`. Each node
  returns new messages and LangGraph appends them via the `add_messages`
  reducer — nodes never manage the full list themselves.
- **`chatbot`** always prepends the fixed `SYSTEM_PROMPT`, then calls Claude
  (`ChatAnthropic(...).bind_tools(TOOLS)`).
- **`route`** is a pure yes/no gate: does the latest `AIMessage` carry
  `tool_calls`? It does *not* decide which tool — only whether to detour
  through `tools` at all.
- **`tools` = `ToolNode(TOOLS)`** does the actual dispatch (see §2).
- **`tools -> chatbot`** loops back so Claude can see tool results and either
  call another tool or produce a final text reply.

## 2. How Claude picks a tool (`tools.py`)

```mermaid
sequenceDiagram
    participant C as chatbot node
    participant M as ChatAnthropic (bound to TOOLS)
    participant T as ToolNode

    Note over M: bind_tools(TOOLS) sent every call:<br/>get_current_time, get_time_in_timezone,<br/>calculate, remember_fact, recall_facts<br/>(schemas auto-built from each<br/>@tool function's signature/docstring)

    C->>M: invoke([SystemMessage, ...history])
    M-->>C: AIMessage(tool_calls=[<br/>{name:"calculate",<br/> args:{expression:"0.15*80"},<br/> id:"toolu_01"}])

    C->>T: route() -> "tools" (tool_calls present)

    Note over T: ToolNode built a {name: fn} map<br/>from TOOLS at construction time

    T->>T: lookup "calculate" -> calculate()
    T->>T: calculate(expression="0.15*80") -> "12.0"
    T-->>C: ToolMessage(content="12.0",<br/>tool_call_id="toolu_01")

    C->>M: invoke([..., ToolMessage])
    M-->>C: AIMessage("15% of 80 is 12.")
    Note over C: route() -> END (no tool_calls)
```

Adding tool #6 = write an `@tool` function in `tools.py` and append it to
`TOOLS`. Nothing in `agent.py` changes — `bind_tools`, `ToolNode`, and
`route()` are all generic over the list.

## 3. Two memory layers

```mermaid
flowchart LR
    subgraph "Short-term (per HTTP request / thread)"
        CP["SqliteSaver checkpointer\nkeyed by thread_id\n(agent.py)"]
    end

    subgraph "Long-term (cross-conversation, global)"
        FS["facts table in SQLite\n(memory_store.py)"]
    end

    chatbot1["chatbot / tools nodes"] <-->|"state['messages']\nper thread_id"| CP
    chatbot1 -->|"remember_fact(...)"| FS
    chatbot1 -->|"recall_facts()"| FS
```

- **Checkpointer**: full message history per `thread_id`. In `chat.py` (local
  REPL) the thread is stable, so it really persists a conversation across
  restarts.
- **`memory_store`**: a separate `facts` table, written/read only via the
  `remember_fact` / `recall_facts` tools. Global, not scoped per thread.

## 4. End-to-end request (ElevenLabs -> Claude -> ElevenLabs)

```mermaid
sequenceDiagram
    participant E as ElevenLabs CAI
    participant S as server.py\n(/v1/chat/completions)
    participant A as agent (StateGraph)
    participant C as Claude API\n(ANTHROPIC_API_KEY)
    participant P as Prometheus/Grafana

    E->>S: POST /v1/chat/completions\n{messages: [...full transcript], stream:true}
    Note over S: _to_langchain(): map OpenAI roles\n-> HumanMessage/AIMessage\n(system messages dropped)
    Note over S: _new_thread(): fresh thread_id\nper HTTP request

    S->>A: agent.stream({"messages": [...]}, thread_id)

    loop chatbot <-> tools (as needed)
        A->>C: model.invoke(messages)
        C-->>A: AIMessageChunk (text or tool_calls)
        opt tool_calls present
            A->>A: ToolNode executes matching tool
        end
    end

    A-->>S: AIMessageChunk stream (final text)
    S->>S: _record_usage(chunk.usage_metadata)\n-> INPUT_TOKENS / OUTPUT_TOKENS / COST_USD
    S-->>E: SSE: data: {delta: {content: "..."}}\n... data: [DONE]

    S->>P: GET /metrics scraped by ServiceMonitor
    P->>P: Grafana dashboard:\nlatency, turns/min, tokens, cost
```

Key point: from `server.py`'s perspective, **every request is stateless** —
the provider resends the full transcript each turn, so the only thing that
truly persists across separate HTTP calls is `memory_store`'s `facts` table
(via `remember_fact`/`recall_facts`). The checkpointer's per-thread state is
created fresh each request and never reused.
