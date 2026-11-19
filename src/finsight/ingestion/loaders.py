"""Load 10-K PDFs into LangChain Documents with FinSight metadata."""

import csv
import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from finsight.config import ROOT_DIR

# Which filings the project uses. FINSIGHT_MANIFEST (in .env) switches to another list, e.g. the 2-filing
# quick tour: data/manifest_quicktour.csv. Relative paths are relative to the project root.
MANIFEST_PATH = ROOT_DIR / os.environ.get("FINSIGHT_MANIFEST", "data/manifest.csv")
RAW_DIR = ROOT_DIR / "data" / "raw"


def load_manifest() -> list[dict]:
    """Read data/manifest.csv. fiscal_year becomes an int so we can filter on it later."""
    with MANIFEST_PATH.open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["fiscal_year"] = int(row["fiscal_year"])
    return rows

def clean_text(text: str) -> str:
    """Remove characters that PDF extraction leaves behind and Postgres rejects."""
    return text.replace("\x00", "")

def load_filing(row: dict) -> list[Document]:
    """Load one 10-K: one Document per page, with our metadata schema attached."""
    path = RAW_DIR / f"{row['doc_name']}.pdf"
    pages = PyPDFLoader(str(path)).load()

    documents = []
    for page in pages:
        page.page_content = clean_text(page.page_content)
        if not page.page_content.strip():
            continue  # skip blank pages (cover pages, separators)

        page.metadata = {
            "doc_name": row["doc_name"],
            "company": row["company"],
            "ticker": row["ticker"],
            "fiscal_year": row["fiscal_year"],
            "doc_type": row["doc_type"],
            "sector": row["sector"],
            "page": page.metadata["page"],  # zero-based, same as FinanceBench
            "source": path.name,
        }
        documents.append(page)
    return documents