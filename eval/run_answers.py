"""Run FinSight on every golden question and save answers + retrieved chunks.

Usage:
    uv run python eval/run_answers.py --run m1_baseline
    uv run python eval/run_answers.py --agent --run m7_agent   # tool-using agent
    uv run python eval/run_answers.py --graph --run m7_graph   # fixed LangGraph workflow
"""

import argparse
import json
import time

from finsight.config import ROOT_DIR
from finsight.evaluation.golden import load_golden
from finsight.generation.chain import build_rag_chain, source_label
from finsight.observability.usage import UsageTracker

RESULTS_DIR = ROOT_DIR / "eval" / "results"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="experiment name, e.g. m1_baseline")
    parser.add_argument("--table", default="chunks_live")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--filters", action=argparse.BooleanOptionalAction, default=True,
                        help="filter search by company/year from the question (--no-filters to disable)")
    parser.add_argument("--hybrid", action="store_true", help="fuse vector + keyword search with RRF")
    parser.add_argument("--hyde", action=argparse.BooleanOptionalAction, default=True,
                        help="search with a hypothetical 10-K passage (--no-hyde to disable)")
    parser.add_argument("--rerank", choices=["minilm", "bge"], default=None,
                        help="re-sort candidates with a cross-encoder (off by default)")
    parser.add_argument("--candidates", type=int, default=20, help="candidate pool size when reranking")
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v2", help="answer prompt (default v2)")
    parser.add_argument("--model", default=None, help="answer model (default: ANSWER_MODEL, gpt-5-mini)")
    parser.add_argument("--structured", action=argparse.BooleanOptionalAction, default=True,
                        help="Answer object with citations verified in code (--no-structured for free text)")
    parser.add_argument("--agent", action="store_true",
                        help="use the tool-using agent (search_filings + calculator) instead of the pipeline")
    parser.add_argument("--graph", action="store_true",
                        help="use the LangGraph workflow (plan, retrieve, grade, calculate, generate, check)")
    args = parser.parse_args()

    if args.agent:
        from finsight.agent.simple_agent import answer_with_agent
    if args.graph:
        from finsight.agent.graph import answer_with_graph

    chain = build_rag_chain(args.table, k=args.k, use_filters=args.filters, hybrid=args.hybrid,
                            use_hyde=args.hyde, rerank_with=args.rerank, candidates=args.candidates,
                            prompt=args.prompt, answer_model=args.model, structured=args.structured)
    items = load_golden()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"answers_{args.run}.jsonl"

    with out_path.open("w") as f:
        for i, item in enumerate(items, 1):
            start = time.perf_counter()
            tracker = UsageTracker()   # tokens + cost of every LLM call for this question (M9)
            config = {"run_name": f"eval:{args.run}", "tags": ["eval", args.run],
                      "metadata": {"golden_id": item["id"]}, "callbacks": [tracker]}
            try:
                if args.agent:
                    result = answer_with_agent(item["question"], model_name=args.model, config=config)
                elif args.graph:
                    result = answer_with_graph(item["question"], config=config, answer_model=args.model)
                else:
                    result = chain.invoke(item["question"], config=config)
            except Exception as e:  # one bad question should not kill a 30-minute run
                print(f"\n  ERROR on {item['id']}: {type(e).__name__}: {e}")
                result = {"answer": "I could not find this in the provided filings.", "docs": [],
                          "citations": [], "tool_calls": [], "steps": [], "n_searches": 0, "n_calculations": 0,
                          "llm_calls": 0, "stopped": f"error: {type(e).__name__}"}
            row = {
                "id": item["id"],
                "question": item["question"],
                "answer": result["answer"],
                "contexts": [d.page_content for d in result["docs"]],
                "sources": [source_label(d) for d in result["docs"]],
                "latency_s": round(time.perf_counter() - start, 2),
                "usage": {k: v for k, v in tracker.summary().items() if k != "by_model"},
            }
            if "citations" in result:
                row["citations"] = result["citations"]
            if args.agent:
                row["tool_calls"] = result["tool_calls"]
                row["n_searches"] = sum(tc["name"] == "search_filings" for tc in result["tool_calls"])
                row["n_calculations"] = sum(tc["name"] == "calculator" for tc in result["tool_calls"])
            if args.graph:
                row["steps"] = result["steps"]
                row["n_searches"] = result["n_searches"]
                row["n_calculations"] = result["n_calculations"]
                row["llm_calls"] = result["llm_calls"]
            if "stopped" in result:
                row["stopped"] = result["stopped"]
            f.write(json.dumps(row) + "\n")
            print(f"\r  answered {i}/{len(items)}", end="", flush=True)

    print(f"\nSaved {out_path}")
    rows = [json.loads(line) for line in out_path.open()]
    avg_latency = sum(r["latency_s"] for r in rows) / len(rows)
    print(f"  avg time per answer: {avg_latency:.1f}s")
    costs = [r.get("usage", {}).get("cost_usd", 0) for r in rows]
    calls = [r.get("usage", {}).get("llm_calls", 0) for r in rows]
    print(f"  avg cost per answer: ${sum(costs) / len(rows):.4f}  (total ${sum(costs):.2f})")
    print(f"  avg model calls per answer (all LLM calls, incl. router/HyDE): {sum(calls) / len(rows):.1f}")
    if args.agent or args.graph:
        print(f"  avg searches per question: {sum(r['n_searches'] for r in rows) / len(rows):.1f}")
        print(f"  avg calculator calls per question: {sum(r['n_calculations'] for r in rows) / len(rows):.1f}")
    if args.graph:
        print(f"  avg LLM calls per question: {sum(r['llm_calls'] for r in rows) / len(rows):.1f}")


if __name__ == "__main__":
    main()
