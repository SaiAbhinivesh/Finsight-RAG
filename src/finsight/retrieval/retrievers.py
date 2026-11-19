"""Retrieval strategies shared by the RAG chain and the eval scripts."""

from langchain_core.runnables import RunnableLambda

from finsight.indexing.store import get_vector_store
from finsight.retrieval.filters import QueryFilters, extract_filters, to_pg_filter
from finsight.retrieval.keyword import keyword_search, rrf
from finsight.retrieval.rerank import rerank
from finsight.retrieval.rewrite import hyde

CANDIDATES = 20  # how many results each method contributes before fusion


def search(store, question: str, k: int, use_filters: bool = False,
           hybrid: bool = False, table_name: str = "chunks_live", use_hyde: bool = False,
           rerank_with: str | None = None, candidates: int = 20):
    """Return (docs, filters).

    Dense search (optionally filtered, HyDE, fused with keyword search). With rerank_with,
    fetch a bigger candidate pool first, re-score it with a cross-encoder and keep the top k.
    """
    filters: QueryFilters | None = extract_filters(question) if use_filters else None
    pg_filter = to_pg_filter(filters) if filters else None
    query = hyde(question) if use_hyde else question  # text used for vector search only

    def dense(n: int, flt):
        return store.similarity_search(query, k=n, filter=flt) if flt else store.similarity_search(query, k=n)

    pool = max(candidates, k) if rerank_with else k  # how many chunks stage 1 returns

    if hybrid:
        n = max(CANDIDATES, pool)
        docs = rrf([dense(n, pg_filter), keyword_search(table_name, question, n, filters)])[:pool]
    else:
        docs = dense(pool, pg_filter)

    if not docs and pg_filter:  # filter matched nothing: fall back to unfiltered dense search
        docs = dense(pool, None)

    if rerank_with:  # stage 2: cross-encoder reads (real question, chunk) pairs
        docs = rerank(question, docs, rerank_with, k)
    return docs[:k], filters


def build_retriever(table_name: str, k: int = 5, use_filters: bool = True, hybrid: bool = False,
                    use_hyde: bool = True, rerank_with: str | None = None, candidates: int = 20):
    """A LangChain Runnable: question -> list of Documents."""
    store = get_vector_store(table_name)
    return RunnableLambda(
        lambda q: search(store, q, k, use_filters, hybrid, table_name, use_hyde, rerank_with, candidates)[0],
        name="FinSightRetriever",
    )
