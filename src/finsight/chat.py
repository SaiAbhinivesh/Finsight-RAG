"""Chat with FinSight in the terminal (follow-up questions supported).

Usage:
    uv run python -m finsight.chat                      # new conversation
    uv run python -m finsight.chat --session <id>       # continue an earlier one
Type 'exit' to quit.
"""

import argparse

from langchain_core.messages import AIMessage, HumanMessage

from finsight.generation.chain import build_rag_chain
from finsight.generation.conversation import condense, open_history


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default=None, help="session id to continue a conversation")
    args = parser.parse_args()

    history, session_id = open_history(args.session)
    chain = build_rag_chain()  # best setup: filters + HyDE + structured answers
    print(f"FinSight chat - session {session_id}  (type 'exit' to quit)\n")

    while True:
        message = input("You: ").strip()
        if message.lower() in {"exit", "quit"}:
            break
        if not message:
            continue

        standalone = condense(message, history.messages)
        if standalone != message:
            print(f"  (understood as: {standalone})")

        result = chain.invoke(standalone)
        print(f"\nFinSight: {result['answer']}")
        for c in result.get("citations", []):
            status = "verified" if c["verified"] else "NOT FOUND in source"
            print(f"   {c['label']} ({status})")
        print()

        # Save the user's original words and FinSight's answer for the next follow-up
        history.add_messages([HumanMessage(content=message), AIMessage(content=result["answer"])])

    print(f"Session saved. Continue with: uv run python -m finsight.chat --session {session_id}")


if __name__ == "__main__":
    main()