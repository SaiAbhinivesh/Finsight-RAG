"""Build the vector index: load PDFs -> chunk -> embed -> store in Postgres.

Usage:
    uv run python scripts/ingest.py                 # build 'chunks_baseline' if it doesn't exist
    uv run python scripts/ingest.py --rebuild       # drop and rebuild
    uv run python scripts/ingest.py --chunk-size 500 --table chunks_r500
    uv run python scripts/ingest.py --loader docling --table chunks_docling   # needs scripts/parse_docling.py first
    uv run python scripts/ingest.py --loader docling --drop-exhibits --context llm --table chunks_live --incremental
"""

import argparse
import time
import uuid

from finsight.indexing.incremental import index_documents
from finsight.indexing.store import create_table, get_vector_store, table_exists
from finsight.ingestion.chunkers import split_documents
from finsight.ingestion.contextualize import add_context
from finsight.ingestion.docling_loader import load_filing_docling
from finsight.ingestion.loaders import load_filing, load_manifest

EMBED_PRICE_PER_M_TOKENS = 0.02  # text-embedding-3-small, USD


def chunk_id(chunk) -> str:
    """Same chunk -> same id every run (handy for debugging and later dedup)."""
    m = chunk.metadata
    # PyPDF chunks have start_index; Docling chunks have chunk_index
    key = f"{m['doc_name']}|{m['page']}|{m.get('start_index', m.get('chunk_index'))}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="chunks_baseline")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=200)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--loader", choices=["pypdf", "docling"], default="pypdf")
    parser.add_argument("--max-tokens", type=int, default=512, help="Docling chunk size limit (tokens)")
    parser.add_argument("--drop-exhibits", action="store_true", help="Docling: skip pages after SIGNATURES")
    parser.add_argument("--context", choices=["none", "template", "llm"], default="none",
                        help="Docling only: prefix each chunk with context before embedding")
    parser.add_argument("--incremental", action="store_true",
                        help="only embed new/changed chunks (LangChain Indexing API)")
    args = parser.parse_args()

    if table_exists(args.table) and not args.rebuild and not args.incremental:
        print(f"Table '{args.table}' already exists. Use --rebuild to recreate it.")
        return

    # 1. Load + chunk
    all_chunks = []
    for row in load_manifest():
        if args.loader == "docling":
            chunks = load_filing_docling(row, args.max_tokens, args.drop_exhibits)
            if args.context != "none":
                chunks = add_context(chunks, args.context, cache_name=f"{row['doc_name']}_{args.max_tokens}")
                print(f"    e.g. {chunks[len(chunks) // 2].metadata['context'][:160]}")
            print(f"{row['doc_name']:<28} -> {len(chunks):>5} chunks")
        else:
            pages = load_filing(row)
            chunks = split_documents(pages, args.chunk_size, args.chunk_overlap)
            print(f"{row['doc_name']:<28} {len(pages):>4} pages -> {len(chunks):>5} chunks")
        all_chunks.extend(chunks)

    total_chars = sum(len(c.page_content) for c in all_chunks)
    est_tokens = total_chars / 4  # rough rule: ~4 characters per token
    print(f"\nTotal: {len(all_chunks)} chunks, ~{est_tokens / 1e6:.2f}M tokens, "
          f"est. embedding cost ${est_tokens / 1e6 * EMBED_PRICE_PER_M_TOKENS:.3f}")

    if args.incremental:
        start = time.perf_counter()
        result = index_documents(all_chunks, args.table)
        print(f"\n{result}  ({time.perf_counter() - start:.0f}s) -> table '{args.table}'")
        if args.table == "chunks_live" and (result.get("num_added") or result.get("num_deleted")):
            from finsight.cache.semantic_cache import clear  # saved answers may now be stale (M9)
            print(f"Index changed: cleared {clear()} saved answers from the semantic cache")
        return

    # 2. Create table + embed + store, in batches
    create_table(args.table, overwrite=args.rebuild)
    store = get_vector_store(args.table)

    start = time.perf_counter()
    batch_size = 500
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        store.add_documents(batch, ids=[chunk_id(c) for c in batch])
        print(f"  indexed {min(i + batch_size, len(all_chunks))}/{len(all_chunks)}")

    print(f"\nDone in {time.perf_counter() - start:.0f}s -> table '{args.table}'")
    if args.table == "chunks_live":
        from finsight.cache.semantic_cache import clear  # rebuilt index: saved answers may be stale (M9)
        print(f"Cleared {clear()} saved answers from the semantic cache")


if __name__ == "__main__":
    main()