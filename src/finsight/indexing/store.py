"""Postgres + pgvector storage for chunks."""

from functools import lru_cache

import psycopg
from langchain.embeddings import init_embeddings
from langchain_postgres import Column, PGEngine, PGVectorStore

from finsight.config import settings

VECTOR_SIZE = 1536  # text-embedding-3-small

# Real SQL columns for the metadata we will filter on (M4).
# Any other metadata keys (source, start_index) go into a JSON column automatically.
METADATA_COLUMNS = [
    Column("doc_name", "TEXT"),
    Column("company", "TEXT"),
    Column("ticker", "TEXT"),
    Column("fiscal_year", "INTEGER"),
    Column("doc_type", "TEXT"),
    Column("sector", "TEXT"),
    Column("page", "INTEGER"),
]


@lru_cache
def get_engine() -> PGEngine:
    """One shared connection pool for the whole app."""
    return PGEngine.from_connection_string(url=settings.database_url)


def table_exists(table_name: str) -> bool:
    with psycopg.connect(settings.psycopg_url) as conn:
        result = conn.execute("SELECT to_regclass(%s)", (table_name,)).fetchone()[0]
    return result is not None


def create_table(table_name: str, overwrite: bool = False) -> None:
    """Create the chunks table. overwrite=True drops and recreates it (deletes all data)."""
    get_engine().init_vectorstore_table(
        table_name=table_name,
        vector_size=VECTOR_SIZE,
        metadata_columns=METADATA_COLUMNS,
        overwrite_existing=overwrite,
    )


def get_vector_store(table_name: str) -> PGVectorStore:
    """Open an existing chunks table as a LangChain vector store."""
    return PGVectorStore.create_sync(
        engine=get_engine(),
        table_name=table_name,
        embedding_service=init_embeddings(settings.embedding_model),
        metadata_columns=[c.name for c in METADATA_COLUMNS],
    )