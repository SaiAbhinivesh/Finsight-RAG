"""Ask FinSight a question from the terminal.

Usage:
    uv run python -m finsight.ask "What was 3M's capital expenditure in FY2018?"
    (default retrieval: company/year filters + HyDE)
    uv run python -m finsight.ask --no-hyde "..."        # filters only
    uv run python -m finsight.ask --no-filters "..."     # search all filings
    uv run python -m finsight.ask --hybrid "..."         # + keyword search fused with RRF
    uv run python -m finsight.ask --rerank=bge "..."     # re-sort 20 candidates with a cross-encoder (minilm or bge)
    (default answer: structured, with citations checked against the source)
    uv run python -m finsight.ask --no-structured "..."  # free-text answer instead
    uv run python -m finsight.ask --agent "..."          # tool-using agent (searches + calculator)
    uv run python -m finsight.ask --graph "..."          # LangGraph workflow (plan, retrieve, grade, ...)
"""

import sys
import time

from finsight.generation.chain import build_rag_chain, source_label


def main() -> None:
    args = sys.argv[1:]
    use_filters = "--no-filters" not in args
    hybrid = "--hybrid" in args
    use_hyde = "--no-hyde" not in args
    rerank_with = next((a.split("=", 1)[1] for a in args if a.startswith("--rerank=")), None)
    structured = "--no-structured" not in args
    use_agent = "--agent" in args
    use_graph = "--graph" in args
    flags = ("--filters", "--no-filters", "--hyde", "--no-hyde", "--hybrid", "--structured", "--no-structured",
             "--agent", "--graph")
    question = " ".join(a for a in args if a not in flags and not a.startswith("--rerank=")) or input("Question: ")

    start = time.perf_counter()
    if use_agent:
        from finsight.agent.simple_agent import answer_with_agent
        result = answer_with_agent(question)
    elif use_graph:
        from finsight.agent.graph import answer_with_graph
        result = answer_with_graph(question)
    else:
        result = build_rag_chain(use_filters=use_filters, hybrid=hybrid, use_hyde=use_hyde,
                                 rerank_with=rerank_with, structured=structured).invoke(question)
    elapsed = time.perf_counter() - start

    print("\nANSWER")
    print(result["answer"])

    if result.get("citations"):
        print("\nCITATIONS")
        for c in result["citations"]:
            status = "verified" if c["verified"] else "NOT FOUND in source"
            print(f"[{c['source']}] {c['label']} ({status}): \"{c['quote']}\"")

    if result.get("tool_calls"):
        print("\nAGENT STEPS")
        for n, tc in enumerate(result["tool_calls"], 1):
            a = tc["args"]
            if tc["name"] == "search_filings":
                print(f"{n}. search_filings: {a.get('company')} {a.get('fiscal_year')} - \"{a.get('query')}\"")
            else:
                print(f"{n}. {tc['name']}: {a.get('expression', a)}")

    if result.get("steps"):
        print("\nGRAPH STEPS")
        for n, step in enumerate(result["steps"], 1):
            print(f"{n}. {step}")
        print(f"LLM calls: {result['llm_calls']}")

    print("\nRETRIEVED CHUNKS")
    for i, doc in enumerate(result["docs"], 1):
        snippet = doc.page_content[:100].replace("\n", " ")
        print(f"{i}. {source_label(doc)} {snippet}...")

    print(f"\n({elapsed:.1f}s)")


if __name__ == "__main__":
    main()