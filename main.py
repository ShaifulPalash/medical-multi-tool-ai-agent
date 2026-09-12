"""
Run this file to chat with the Medical Multi-Tool Agent from your terminal.

USAGE:
    python main.py
    python main.py "How many patients have a glucose level over 140?"

Make sure you've already run, in order:
    1. python scripts/download_and_inspect.py
    2. python scripts/build_databases.py
and that your .env file has a valid GOOGLE_API_KEY (see .env.example).
"""

import sys

from dotenv import load_dotenv

load_dotenv()  # must run before importing agent.main_agent, which constructs an LLM

from agent.main_agent import ask, build_agent, final_answer_text  # noqa: E402


def print_tool_trace(result: dict) -> None:
    """Prints which tool(s) the agent decided to call, for transparency."""
    for msg in result["messages"]:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                print(f"  [tool call] {call['name']}({call['args']})")


def main():
    agent = build_agent()

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = ask(agent, question)
        print_tool_trace(result)
        print("\nAnswer:", final_answer_text(result))
        return

    print("Medical Multi-Tool Agent — type 'exit' to quit.\n")
    while True:
        question = input("You: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue

        result = ask(agent, question)
        print_tool_trace(result)
        print("Agent:", final_answer_text(result), "\n")


if __name__ == "__main__":
    main()
