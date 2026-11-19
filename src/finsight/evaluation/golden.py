"""Golden evaluation set: loading and matching helpers."""

import json

from langchain_core.documents import Document

from finsight.config import ROOT_DIR

GOLDEN_PATH = ROOT_DIR / "data" / "eval" / "golden_set.jsonl"


def load_golden(answerable_only: bool = False) -> list[dict]:
    with GOLDEN_PATH.open() as f:
        items = [json.loads(line) for line in f if line.strip()]
    if answerable_only:
        items = [i for i in items if i["answerable"]]
    return items


def is_gold(doc: Document, item: dict) -> bool:
    """Right filing AND at least one of the chunk's pages is an evidence page.

    PyPDF chunks have one page ("page"); Docling chunks can span pages ("pages", e.g. "45,46").
    """
    m = doc.metadata
    pages = {int(p) for p in str(m.get("pages", m["page"])).split(",") if p != ""}
    return m["doc_name"] == item["doc_name"] and bool(pages & set(item["evidence_pages"]))