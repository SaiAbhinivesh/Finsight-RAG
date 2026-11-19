"""Incremental indexing: only embed new/changed chunks, delete removed ones."""

from langchain_classic.indexes import SQLRecordManager
from langchain_core.documents import Document
from langchain_core.indexing import index

from finsight.config import settings
from finsight.indexing.store import create_table, get_vector_store, table_exists


def index_documents(docs: list[Document], table_name: str) -> dict:
    if not table_exists(table_name):
        create_table(table_name)
    store = get_vector_store(table_name)

    # Remembers a hash of every chunk in this table (stored in Postgres, table 'upsert_record')
    record_manager = SQLRecordManager(namespace=f"finsight/{table_name}", db_url=settings.database_url)
    record_manager.create_schema()  # no-op if it already exists

    return index(
        docs,
        record_manager,
        store,
        cleanup="full",          # anything not in this run gets deleted
        source_id_key="source",  # which metadata key says which file a chunk came from
        batch_size=500,
    )