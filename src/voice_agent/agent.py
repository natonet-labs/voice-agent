"""The LangGraph agent — the portable brain shared by every voice provider.

Built as an explicit StateGraph (rather than the prebuilt create_react_agent)
so the graph mechanics are visible and easy to extend.

    START -> chatbot -> (tool calls?) --yes--> tools -> chatbot
                              |
                              no
                              v
                             END

Memory has two layers:
- Short-term (per conversation): the SQLite checkpointer persists each thread's
  state, so a conversation survives a process restart.
- Long-term (cross conversation): the remember_fact / recall_facts tools persist
  facts in SQLite (see memory_store).
"""

import sqlite3
from pathlib import Path
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from voice_agent.config import settings
from voice_agent.tools import TOOLS

# Voice-tuned system prompt: replies are spoken aloud, so keep them short,
# plain, and free of markdown / lists / emoji.
SYSTEM_PROMPT = (
    "You are a concise, friendly voice assistant. "
    "Keep replies short and natural for speech — a sentence or two. "
    "Do not use markdown, bullet lists, or emoji; your words are read aloud. "
    "You can remember facts the user asks you to keep (remember_fact) and "
    "recall them later (recall_facts). Use your tools whenever they help."
)


def _build_checkpointer() -> SqliteSaver:
    path = Path(settings.agent_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def build_agent():
    """Compile and return the agent graph."""
    # Pass api_key only when set (e.g. from .env); otherwise let ChatAnthropic
    # fall back to the ANTHROPIC_API_KEY environment variable.
    model_kwargs = {"model": settings.llm_model, "temperature": 0.3}
    if settings.anthropic_api_key:
        model_kwargs["api_key"] = settings.anthropic_api_key
    model = ChatAnthropic(**model_kwargs).bind_tools(TOOLS)

    def chatbot(state: MessagesState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        return {"messages": [model.invoke(messages)]}

    def route(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "chatbot")

    # Persistent per-thread conversation state (survives restarts).
    return graph.compile(checkpointer=_build_checkpointer())


agent = build_agent()
