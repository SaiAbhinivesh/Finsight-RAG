"""List answers that users rated in the UI (LangSmith feedback), to review and grow the golden set.

Usage:
    uv run python eval/pull_feedback.py              # thumbs down only (default)
    uv run python eval/pull_feedback.py --all        # thumbs up and down
    uv run python eval/pull_feedback.py --days 30    # look back 30 days (default 7)
"""

import argparse
from datetime import UTC, datetime, timedelta

from langsmith import Client

from finsight.config import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="include thumbs up")
    parser.add_argument("--days", type=int, default=7, help="how far back to look")
    args = parser.parse_args()

    client = Client()
    rating = 'eq(feedback_key, "user_score")' if args.all else \
        'and(eq(feedback_key, "user_score"), eq(feedback_score, 0))'
    runs = list(client.list_runs(
        project_name=settings.langsmith_project,
        is_root=True,
        filter=rating,
        start_time=datetime.now(UTC) - timedelta(days=args.days),
    ))
    print(f"{len(runs)} rated answer(s) in the last {args.days} days "
          f"({'all ratings' if args.all else 'thumbs down only'})\n")

    for run in runs:
        inputs, outputs = run.inputs or {}, run.outputs or {}
        question = inputs.get("question") or inputs.get("input") or inputs   # graph uses "question", pipeline "input"
        answer = str(outputs.get("answer", outputs))
        for fb in client.list_feedback(run_ids=[run.id], feedback_key=["user_score"]):
            vote = "👍" if fb.score == 1 else "👎"
            print(f"{vote}  {run.name}  {run.start_time:%Y-%m-%d %H:%M}  run {run.id}")
            print(f"   Q: {question}")
            print(f"   A: {answer[:300]}{'...' if len(answer) > 300 else ''}")
            if fb.comment:
                print(f"   Comment: {fb.comment}")
            print()


if __name__ == "__main__":
    main()
