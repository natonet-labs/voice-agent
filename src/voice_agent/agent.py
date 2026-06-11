"""The LangGraph agent — the portable brain shared by every voice provider.

Built as an explicit StateGraph (rather than the prebuilt create_react_agent)
so the graph mechanics are visible and easy to extend: add nodes for retrieval,
guardrails, or hand-off to a human as the project grows.

    START -> chatbot -> (tool calls?) --yes--> tools -> chatbot
                              |
                              no
                              v
                             END
"""

from datetime import datetime, timezone
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from voice_agent.config import settings


@tool
def get_current_time() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Placeholder tool that demonstrates tool-calling inside the graph.
    Replace / extend with real tools (CRM lookups, bookings, etc.).
    """
    return datetime.now(timezone.utc).isoformat()


TOOLS = [get_current_time]

# Voice-tuned system prompt: replies are spoken aloud, so keep them short,
# plain, and free of markdown / lists / emoji.
SYSTEM_PROMPT = (
    "You are a concise, friendly voice assistant. "
    "Keep replies short and natural for speech — a sentence or two. "
    "Do not use markdown, bullet lists, or emoji; your words are read aloud."
)


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

    # MemorySaver keeps per-thread state for the local CLI. The HTTP endpoint
    # is stateless per request (the provider sends full history each turn).
    return graph.compile(checkpointer=MemorySaver())


agent = build_agent()
