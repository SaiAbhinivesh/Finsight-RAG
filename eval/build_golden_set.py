"""Build data/eval/golden_set.jsonl.

- All FinanceBench questions about our 11 filings (answer + evidence pages)
- Hand-written questions the filings cannot answer (tests refusals)
Also checks that every evidence page really contains its evidence text,
so we know page numbers line up with our PDFs before trusting any metric.

Usage:
    uv run python eval/build_golden_set.py
"""

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from finsight.evaluation.golden import GOLDEN_PATH
from finsight.ingestion.loaders import RAW_DIR, load_manifest

FB_QUESTIONS = Path.home() / "datasets" / "financebench" / "data" / "financebench_open_source.jsonl"

UNANSWERABLE = [
    {"question": "What is Verizon's dividend policy for 2030?", "company": "Verizon"},
    {"question": "What was 3M's total revenue in fiscal year 2025?", "company": "3M"},
    {"question": "What was PepsiCo's net revenue in 2024?", "company": "PepsiCo"},
    {"question": "Who will be Boeing's CEO in 2028?", "company": "Boeing"},
    {"question": "What price did AMD pay to acquire Intel?", "company": "AMD"},
    {"question": "When will American Express launch its own cryptocurrency exchange?", "company": "American Express"},
]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", text.lower()))


def evidence_overlap(reader: PdfReader, page: int, evidence_text: str) -> float:
    """Share of the evidence's words that appear on that PDF page (1.0 = all found)."""
    if page >= len(reader.pages):
        return 0.0
    ev = words(evidence_text)
    if not ev:
        return 1.0
    return len(ev & words(reader.pages[page].extract_text() or "")) / len(ev)


def clean(value, default="unknown"):
    return default if pd.isna(value) else str(value)


def main() -> None:
    manifest = {row["doc_name"]: row for row in load_manifest()}
    questions = pd.read_json(FB_QUESTIONS, lines=True)
    questions = questions[questions["doc_name"].isin(manifest)]

    items, problems, readers = [], [], {}
    for _, r in questions.iterrows():
        doc = manifest[r["doc_name"]]
        reader = readers.setdefault(r["doc_name"], PdfReader(RAW_DIR / f"{r['doc_name']}.pdf"))

        # Sanity check: does the evidence text really sit on that page?
        for ev in r["evidence"]:
            page = int(ev["evidence_page_num"])
            score = evidence_overlap(reader, page, ev["evidence_text"])
            if score < 0.6:
                problems.append(f"{r['financebench_id']} {r['doc_name']} p{page + 1}: overlap {score:.2f}")

        items.append({
            "id": str(r["financebench_id"]),
            "question": r["question"],
            "reference_answer": str(r["answer"]),
            "question_type": clean(r.get("question_type")),
            "question_reasoning": clean(r.get("question_reasoning")),
            "company": doc["company"],
            "fiscal_year": doc["fiscal_year"],
            "doc_name": r["doc_name"],
            "evidence_pages": sorted({int(ev["evidence_page_num"]) for ev in r["evidence"]}),  # zero-based
            "answerable": True,
            "source": "financebench",
        })

    for i, u in enumerate(UNANSWERABLE, 1):
        items.append({
            "id": f"unanswerable_{i}",
            "question": u["question"],
            "reference_answer": "I could not find this in the provided filings.",
            "question_type": "unanswerable",
            "question_reasoning": "refusal",
            "company": u["company"],
            "fiscal_year": None,
            "doc_name": None,
            "evidence_pages": [],
            "answerable": False,
            "source": "handwritten",
        })

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN_PATH.open("w") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")

    answerable = [i for i in items if i["answerable"]]
    print(f"Wrote {len(items)} questions to {GOLDEN_PATH}")
    print(f"  answerable: {len(answerable)}, unanswerable: {len(items) - len(answerable)}")
    print("  by reasoning type:", dict(Counter(i["question_reasoning"] for i in answerable)))
    print(f"\nEvidence page check: {len(problems)} problem(s)")
    for p in problems:
        print("  ", p)


if __name__ == "__main__":
    main()