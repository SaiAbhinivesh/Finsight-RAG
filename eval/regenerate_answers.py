"""Re-generate answers from the chunks saved in an earlier run (retrieval held fixed).

Use it to compare prompts or answer models without retrieval noise.

Usage:
    uv run python eval/regenerate_answers.py --from m4_filters_hyde --no-structured --prompt v1 --model openai:gpt-4o-mini --run m6_v1_control
    uv run python eval/regenerate_answers.py --from m4_filters_hyde --no-structured --prompt v2 --model openai:gpt-4o-mini --run m6_v2
    uv run python eval/regenerate_answers.py --from m4_filters_hyde --no-structured --prompt v2 --run m6_v2_gpt5mini
    uv run python eval/regenerate_answers.py --from m4_filters_hyde --run m6_v2_structured   # default: structured, ANSWER_MODEL
"""

import argparse
import json
import time

from langchain_core.output_parsers import StrOutputParser

from finsight.config import ROOT_DIR, settings
from finsight.generation.models import chat_model
from finsight.generation.prompts import PROMPTS
from finsight.generation.structured import (
    STRUCTURED_PROMPT,
    Answer,
    format_numbered,
    render,
    verify_citations,
)

RESULTS_DIR = ROOT_DIR / "eval" / "results"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_run", required=True, help="run whose saved chunks to reuse")
    parser.add_argument("--run", required=True, help="name for this experiment")
    parser.add_argument("--prompt", choices=list(PROMPTS), default="v2")
    parser.add_argument("--model", default=None, help="answer model, e.g. openai:gpt-4o-mini (default: ANSWER_MODEL)")
    parser.add_argument("--structured", action=argparse.BooleanOptionalAction, default=True,
                        help="Answer object with citations verified in code (--no-structured: free text with --prompt)")
    args = parser.parse_args()

    model_name = args.model or settings.answer_model
    model = chat_model(model_name)
    if args.structured:
        chain = STRUCTURED_PROMPT | model.with_structured_output(Answer)
    else:
        chain = PROMPTS[args.prompt] | model | StrOutputParser()

    with (RESULTS_DIR / f"answers_{args.from_run}.jsonl").open() as f:
        saved = [json.loads(line) for line in f if line.strip()]

    out_path = RESULTS_DIR / f"answers_{args.run}.jsonl"
    with out_path.open("w") as f:
        for i, row in enumerate(saved, 1):
            texts, labels = row["contexts"], row["sources"]
            if args.structured:
                context = format_numbered(texts, labels)  # [1] label + text, [2] ...
            else:
                # Rebuild the context exactly as the chain formats it: label, newline, chunk text
                context = "\n\n---\n\n".join(f"{src}\n{text}" for src, text in zip(labels, texts))
            start = time.perf_counter()
            result = chain.invoke(
                {"context": context, "question": row["question"]},
                config={"run_name": f"eval:{args.run}", "tags": ["eval", args.run]},
            )
            new = {**row, "latency_s": round(time.perf_counter() - start, 2)}
            if args.structured:
                new["answer"] = render(result, labels)
                new["citations"] = verify_citations(result, texts, labels)
            else:
                new["answer"] = result
            f.write(json.dumps(new) + "\n")
            print(f"\r  answered {i}/{len(saved)}", end="", flush=True)

    mode = "structured" if args.structured else f"prompt {args.prompt}"
    print(f"\nSaved {out_path}  ({mode}, model {model_name}, chunks from {args.from_run})")


if __name__ == "__main__":
    main()