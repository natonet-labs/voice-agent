"""Local text REPL for the agent — milestone 1, no voice provider needed.

    pip install -e .
    voice-agent-chat
"""

import uuid

from langchain_core.messages import HumanMessage

from voice_agent.agent import agent


def main() -> None:
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    print("voice-agent local chat — type 'exit' to quit\n")
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
