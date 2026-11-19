"""Second-stage reranking with a cross-encoder (reads question + chunk together)."""

from functools import lru_cache

from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document

RERANKERS = {
    "minilm": "cross-encoder/ms-marco-MiniLM-L-6-v2",  # small, fast
    "bge": "BAAI/bge-reranker-base",                   # bigger, stronger
}


@lru_cache
def _reranker(name: str, top_n: int) -> CrossEncoderReranker:
    model = HuggingFaceCrossEncoder(model_name=RERANKERS[name])  # downloaded once, then cached
    return CrossEncoderReranker(model=model, top_n=top_n)


def rerank(question: str, docs: list[Document], name: str, top_n: int) -> list[Document]:
    """Score every (question, chunk) pair and return the top_n, best first."""
    return list(_reranker(name, top_n).compress_documents(docs, question))