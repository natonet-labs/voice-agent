"""Local text REPL for the agent — milestone 1+, no voice provider needed.

    pip install -e .
    voice-agent-chat

Uses a stable thread id so the conversation persists across restarts (via the
SQLite checkpointer). Override with VOICE_AGENT_THREAD, or delete the agent db
to start fresh.
"""

import os

from langchain_core.messages import HumanMessage

from voice_agent.agent import agent


def main() -> None:
    thread_id = os.environ.get("VOICE_AGENT_THREAD", "local-cli")
    config = {"configurable": {"thread_id": thread_id}}
    print(f"voice-agent local chat — thread '{thread_id}' (history persists across restarts)")
    print("type 'exit' to quit\n")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue
        result = agent.invoke({"messages": [HumanMessage(content=user)]}, config)
        print(f"bot> {result['messages'][-1].content}\n")


if __name__ == "__main__":
    main()
