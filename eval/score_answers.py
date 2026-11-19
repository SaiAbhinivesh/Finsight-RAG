"""Score saved answers: LLM judge (correct/partial/wrong/refused) + RAGAS metrics.

Usage:
    uv run python eval/score_answers.py --run m1_baseline
    uv run python eval/score_answers.py --run m1_baseline --no-ragas   # judge only
"""

import argparse
import asyncio
import csv
import json
from collections import Counter
from datetime import datetime
from statistics import mean

from finsight.config import ROOT_DIR, settings
from finsight.evaluation.golden import load_golden
from finsight.evaluation.judge import Verdict, build_judge

RESULTS_DIR = ROOT_DIR / "eval" / "results"
SUMMARY_PATH = RESULTS_DIR / "answer_summary.csv"
POINTS = {"correct": 1.0, "partial": 0.5, "wrong": 0.0, "refused": 0.0}


def load_answers(run: str) -> dict:
    path = RESULTS_DIR / f"answers_{run}.jsonl"
    with path.open() as f:
        return {row["id"]: row for row in map(json.loads, f) if row}


def is_refusal(answer: str) -> bool:
    return "could not find" in answer.lower()


def judge_all(items: list, answers: dict) -> list:
    """Refusals are labelled by rule; only real answers go to the LLM judge."""
    verdicts = [None] * len(items)
    to_judge = []
    for i, it in enumerate(items):
        if is_refusal(answers[it["id"]]["answer"]):
            label = "refused" if it["answerable"] else "correct"
            verdicts[i] = Verdict(verdict=label, reason="Rule: the answer is a refusal")
        else:
            to_judge.append(i)

    judge = build_judge()
    inputs = [
        {"question": items[i]["question"], "reference": items[i]["reference_answer"],
         "answer": answers[items[i]["id"]]["answer"]}
        for i in to_judge
    ]
    results = judge.batch(inputs, config={"max_concurrency": 5, "run_name": "judge"})
    for i, result in zip(to_judge, results):
        # For an unanswerable question, a refusal in other words ("no ... policy for 2030 is stated") is the
        # right outcome: the judge labels it "refused", which must count as correct here (M10 gate finding).
        if not items[i]["answerable"] and result.verdict == "refused":
            result = Verdict(verdict="correct", reason=f"Unanswerable and declined: {result.reason}")
        verdicts[i] = result
    return verdicts


async def ragas_all(items: list, answers: dict) -> list:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness

    llm = llm_factory(settings.judge_model.split(":", 1)[1], client=AsyncOpenAI())
    faithfulness = Faithfulness(llm=llm)
    precision = ContextPrecision(llm=llm)
    recall = ContextRecall(llm=llm)
    limit = asyncio.Semaphore(5)  # at most 5 metric calls at once

    async def safe(name, coro):
        async with limit:
            try:
                return round((await coro).value, 3)
            except Exception as e:
                print(f"\n  {name} failed: {type(e).__name__}: {e}")
                return None

    async def score_one(item):
        a = answers[item["id"]]
        q, ctx, ref = item["question"], a["contexts"], item["reference_answer"]
        tasks = {
            "context_precision": safe("context_precision", precision.ascore(user_input=q, reference=ref, retrieved_contexts=ctx)),
            "context_recall": safe("context_recall", recall.ascore(user_input=q, retrieved_contexts=ctx, reference=ref)),
        }
        if not is_refusal(a["answer"]):  # a refusal makes no claims, so faithfulness is undefined
            tasks["faithfulness"] = safe("faithfulness", faithfulness.ascore(user_input=q, response=a["answer"], retrieved_contexts=ctx))
        values = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), values))

    return await asyncio.gather(*(score_one(it) for it in items))


def avg(rows: list, key: str):
    vals = [r[key] for r in rows if r.get(key) not in (None, "")]
    return round(mean(vals), 3) if vals else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--no-ragas", action="store_true")
    args = parser.parse_args()

    items = load_golden()
    answers = load_answers(args.run)

    print("Judging answers...")
    verdicts = judge_all(items, answers)
    rows = [
        {
            "id": it["id"],
            "answerable": it["answerable"],
            "reasoning": it["question_reasoning"],
            "verdict": v.verdict,
            "points": POINTS[v.verdict],
            "judge_reason": v.reason,
            "answer": answers[it["id"]]["answer"][:300],
        }
        for it, v in zip(items, verdicts)
    ]

    # Citation checks (only for runs made with --structured): verified = quote found in the cited block
    has_citations = any("citations" in a for a in answers.values())
    if has_citations:
        for row in rows:
            cites = answers[row["id"]].get("citations", [])
            row["citations_total"] = len(cites)
            row["citations_verified"] = sum(c["verified"] for c in cites)

    if not args.no_ragas:
        print("Running RAGAS (answerable questions only)...")
        answerable_items = [it for it in items if it["answerable"]]
        ragas_rows = asyncio.run(ragas_all(answerable_items, answers))
        by_id = {it["id"]: r for it, r in zip(answerable_items, ragas_rows)}
        for row in rows:
            row.update(by_id.get(row["id"], {}))

    # Per-question details
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    detail_path = RESULTS_DIR / f"scores_{args.run}_{stamp}.csv"
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with detail_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    ans = [r for r in rows if r["answerable"]]
    unans = [r for r in rows if not r["answerable"]]
    counts = Counter(r["verdict"] for r in ans)
    summary = {
        "answer_score": avg(ans, "points"),
        "correct": counts["correct"],
        "partial": counts["partial"],
        "wrong": counts["wrong"],
        "refused": counts["refused"],
        "refusal_accuracy": avg(unans, "points"),
        "faithfulness": avg(ans, "faithfulness"),
        "context_precision": avg(ans, "context_precision"),
        "context_recall": avg(ans, "context_recall"),
    }

    print(f"\nRun '{args.run}': {len(ans)} answerable + {len(unans)} unanswerable questions")
    for k, v in summary.items():
        print(f"  {k:<18} {v}")

    if has_citations:
        total = sum(r["citations_total"] for r in ans)
        verified = sum(r["citations_verified"] for r in ans)
        answered = [r for r in ans if r["verdict"] != "refused"]
        backed = sum(1 for r in answered if r["citations_verified"] > 0)
        print(f"\n  citation accuracy  {verified}/{total} = {verified / total:.3f}" if total else "\n  no citations")
        print(f"  answers with >=1 verified citation: {backed}/{len(answered)} (non-refused)")

    is_new = not SUMMARY_PATH.exists()
    with SUMMARY_PATH.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["run", "date", "n_answerable"] + list(summary))
        writer.writerow([args.run, stamp, len(ans)] + list(summary.values()))

    print(f"\nDetails: {detail_path}\nSummary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()