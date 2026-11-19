"""Retrieval metrics for a chunks table. No LLM calls: fast and almost free.

Usage:
    uv run python eval/retrieval_metrics.py
    uv run python eval/retrieval_metrics.py --table chunks_r500 --run r500
    uv run python eval/retrieval_metrics.py --run my_run                 # default: filters + HyDE
    uv run python eval/retrieval_metrics.py --no-hyde --run filters_only
    uv run python eval/retrieval_metrics.py --no-filters --no-hyde --run plain_dense
    uv run python eval/retrieval_metrics.py --hybrid --run with_keyword_search
"""

import argparse
import csv
import time
from collections import defaultdict
from datetime import datetime
from statistics import mean

from finsight.config import ROOT_DIR
from finsight.evaluation.golden import is_gold, load_golden
from finsight.indexing.store import get_vector_store
from finsight.retrieval.retrievers import search

KS = (1, 3, 5, 10)
METRICS = [f"hit@{k}" for k in KS] + ["recall@5", "mrr", "same_doc@5"]
RESULTS_DIR = ROOT_DIR / "eval" / "results"
SUMMARY_PATH = RESULTS_DIR / "retrieval_summary.csv"


def score_item(item: dict, docs: list) -> dict:
    gold_ranks = [rank for rank, d in enumerate(docs, 1) if is_gold(d, item)]
    first = gold_ranks[0] if gold_ranks else None
    pages_found = {d.metadata["page"] for d in docs[:5] if is_gold(d, item)}

    row = {"id": item["id"], "reasoning": simple_type(item["question_reasoning"]), "first_gold_rank": first or ""}
    for k in KS:
        row[f"hit@{k}"] = int(first is not None and first <= k)
    row["recall@5"] = len(pages_found) / len(item["evidence_pages"])
    row["mrr"] = 1 / first if first else 0.0
    row["same_doc@5"] = sum(d.metadata["doc_name"] == item["doc_name"] for d in docs[:5]) / 5
    row["top5"] = "; ".join(f"{d.metadata['doc_name']} p{d.metadata['page'] + 1}" for d in docs[:5])
    return row

def simple_type(label: str) -> str:
    """Collapse FinanceBench's combined labels into 3 groups + unknown."""
    label = label.lower()
    if "numerical" in label:
        return "numerical"
    if "logical" in label:
        return "logical"
    if "extraction" in label:
        return "extraction"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="chunks_live")
    parser.add_argument("--run", default=None, help="name for this experiment (default: table name)")
    parser.add_argument("--filters", action=argparse.BooleanOptionalAction, default=True,
                        help="filter search by company/year from the question (--no-filters to disable)")
    parser.add_argument("--hybrid", action="store_true", help="fuse vector + keyword search with RRF")
    parser.add_argument("--hyde", action=argparse.BooleanOptionalAction, default=True,
                        help="search with a hypothetical 10-K passage (--no-hyde to disable)")
    parser.add_argument("--rerank", choices=["minilm", "bge"], default=None,
                        help="re-sort candidates with a cross-encoder (off by default)")
    parser.add_argument("--candidates", type=int, default=20, help="candidate pool size when reranking")
    args = parser.parse_args()
    run = args.run or args.table

    store = get_vector_store(args.table)
    items = load_golden(answerable_only=True)

    rows = []
    start = time.perf_counter()
    for i, item in enumerate(items, 1):
        docs, filters = search(store, item["question"], max(KS), args.filters, args.hybrid, args.table, args.hyde,
                               args.rerank, args.candidates)
        row = score_item(item, docs)
        if filters is not None:
            row["filter_company"] = filters.company
            row["filter_year"] = filters.fiscal_year
            row["filter_ok"] = int(filters.company == item["company"] and filters.fiscal_year == item["fiscal_year"])
        rows.append(row)
        print(f"\r  scored {i}/{len(items)}", end="", flush=True)
    seconds_per_q = (time.perf_counter() - start) / len(items)
    print()

    # Per-question details (open in VS Code or Excel to see each failure)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    detail_path = RESULTS_DIR / f"retrieval_{run}_{stamp}.csv"
    with detail_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    summary = {m: round(mean(r[m] for r in rows), 3) for m in METRICS}
    print(f"\nRun '{run}' on table '{args.table}' ({len(rows)} questions)")
    for m, v in summary.items():
        print(f"  {m:<11} {v:.3f}")

    print(f"\n  avg time per question: {seconds_per_q:.2f}s")

    if args.filters:
        print(f"\nfilter accuracy: {mean(r['filter_ok'] for r in rows):.3f} (company AND year both right)")

    by_type = defaultdict(list)
    for r in rows:
        by_type[r["reasoning"]].append(r["hit@5"])
    print("\nhit@5 by reasoning type:")
    for t, hits in sorted(by_type.items()):
        print(f"  {t:<28} {mean(hits):.2f}  (n={len(hits)})")

    # Append one line per run, so experiments accumulate in one file
    is_new = not SUMMARY_PATH.exists()
    with SUMMARY_PATH.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["run", "table", "date", "n"] + METRICS)
        writer.writerow([run, args.table, stamp, len(rows)] + [summary[m] for m in METRICS])

    print(f"\nDetails: {detail_path}\nSummary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()