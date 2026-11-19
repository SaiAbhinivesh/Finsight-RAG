"""Keyword search (Postgres full-text) and Reciprocal Rank Fusion."""

import json

import psycopg
from langchain_core.documents import Document
from psycopg import sql

from finsight.config import settings
from finsight.indexing.store import METADATA_COLUMNS

COLUMNS = [c.name for c in METADATA_COLUMNS]


def keyword_search(table_name: str, question: str, k: int, filters=None) -> list[Document]:
    """Rank chunks by how well their words match the question's words (OR of all terms)."""
    where = [sql.SQL("to_tsvector('english', content) @@ q")]
    params: list = [question]
    if filters and filters.company:
        where.append(sql.SQL("company = %s"))
        params.append(filters.company)
    if filters and filters.fiscal_year:
        where.append(sql.SQL("fiscal_year = %s"))
        params.append(filters.fiscal_year)
    params.append(k)

    query = sql.SQL("""
        SELECT content, {cols}, langchain_metadata,
               ts_rank_cd(to_tsvector('english', content), q) AS score
        FROM {table},
             (SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery AS q) AS terms
        WHERE {where}
        ORDER BY score DESC
        LIMIT %s
    """).format(
        cols=sql.SQL(", ").join(map(sql.Identifier, COLUMNS)),
        table=sql.Identifier(table_name),
        where=sql.SQL(" AND ").join(where),
    )

    with psycopg.connect(settings.psycopg_url) as conn:
        rows = conn.execute(query, params).fetchall()

    docs = []
    for content, *values, extra, _score in rows:
        extra = extra if isinstance(extra, dict) else json.loads(extra or "{}")
        docs.append(Document(page_content=content, metadata={**extra, **dict(zip(COLUMNS, values))}))
    return docs


def doc_key(doc: Document) -> tuple:
    m = doc.metadata
    return (m["doc_name"], m.get("chunk_index"), m["page"])


def rrf(result_lists: list[list[Document]], k_const: int = 60) -> list[Document]:
    """Reciprocal Rank Fusion: score = sum of 1 / (k_const + rank) across lists."""
    scores: dict[tuple, float] = {}
    docs: dict[tuple, Document] = {}
    for results in result_lists:
        for rank, doc in enumerate(results, 1):
            key = doc_key(doc)
            scores[key] = scores.get(key, 0.0) + 1 / (k_const + rank)
            docs.setdefault(key, doc)
    return [docs[key] for key in sorted(scores, key=scores.get, reverse=True)]