"""Shared test setup. Runs before any test module is imported.

Settings() requires an OpenAI key and a database URL. In CI there is no .env, so dummy values are set
here; the unit tests never call OpenAI or connect to the database. Real values in a local .env win
(setdefault does not overwrite them), and tracing is switched off so tests never send traces.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-used")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["FINSIGHT_MANIFEST"] = "data/manifest.csv"   # tests expect all 11 filings, even during the quick tour

import pytest
from langchain_core.documents import Document


@pytest.fixture
def make_doc():
    """Build a chunk Document with the metadata the pipeline expects."""
    def _make(text="text", company="AMD", fiscal_year=2022, page=10, chunk_index=0, doc_name=None):
        return Document(page_content=text, metadata={
            "company": company, "fiscal_year": fiscal_year, "page": page, "chunk_index": chunk_index,
            "doc_name": doc_name or f"{company.upper()}_{fiscal_year}_10K"})
    return _make
