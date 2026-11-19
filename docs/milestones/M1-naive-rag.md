# M1: Naive RAG baseline

Completed: 2026-11-09

**Goal:** the simplest RAG pipeline that works end to end, so every later upgrade has something to beat.

**Outcome:** `uv run python -m finsight.ask "<question>"` answers with page citations. On 9 test questions: **1 correct, 2 partial, 6 wrong**. The data is there; retrieval usually misses the right page. Details in [EXPERIMENTS.md](../EXPERIMENTS.md) (nine hard questions).

## How it flows

```text
INDEXING (scripts/ingest.py, run once)

data/manifest.csv + data/raw/*.pdf
  -> ingestion/loaders.py    PyPDFLoader: one Document per page, clean text, attach metadata
  -> ingestion/chunkers.py   RecursiveCharacterTextSplitter: 1000 chars, 200 overlap
  -> indexing/store.py       OpenAI embeddings -> Postgres table chunks_baseline (pgvector)

QUERYING (python -m finsight.ask, per question)

question
  -> generation/chain.py     retriever: embed question, take 5 nearest chunks
  -> generation/prompts.py   system rules + labelled context [Company Year, p. N] + question
  -> gpt-4o-mini             answer with citations, or "I could not find this..."
  -> ask.py                  prints answer + the 5 retrieved chunks
```

## Files added

| File | Role |
| --- | --- |
| `src/finsight/ingestion/loaders.py` | Reads the manifest, loads each PDF page by page, removes NUL bytes, skips blank pages, sets metadata (doc_name, company, ticker, fiscal_year, doc_type, sector, page, source) |
| `src/finsight/ingestion/chunkers.py` | Splits pages into ~1000-character chunks with 200 overlap; records `start_index` |
| `src/finsight/indexing/store.py` | Postgres connection pool, table creation with real metadata columns, opens the table as a LangChain vector store |
| `scripts/ingest.py` | Load, chunk, estimate cost, embed and store in batches of 500; `--rebuild`, `--table`, `--chunk-size` flags |
| `src/finsight/generation/prompts.py` | Grounding rules: use only the context, cite labels, copy numbers exactly, refuse if not found |
| `src/finsight/generation/chain.py` | LCEL chain: retrieve (k=5) in parallel with the question, format labelled context, prompt, model, parse; returns question, docs and answer |
| `src/finsight/ask.py` | Command-line interface: answer, sources, timing |
| `notebooks/01_explore_chunks.ipynb` | Reading pages and chunks, finding the broken table text, raw similarity search with scores |
| `docs/EXPERIMENTS.md` | The nine hard questions, followed from this baseline through every milestone |

## Index built

10,381 chunks, about 2.21M tokens, estimated embedding cost $0.044.

| Filing | Pages | Chunks |
| --- | --- | --- |
| 3M_2018_10K | 160 | 819 |
| 3M_2022_10K | 252 | 1,258 |
| AMD_2015_10K | 215 | 1,026 |
| AMD_2022_10K | 121 | 555 |
| AMERICANEXPRESS_2022_10K | 260 | 1,108 |
| BOEING_2018_10K | 136 | 532 |
| BOEING_2022_10K | 189 | 687 |
| PEPSICO_2021_10K | 549 | 1,520 |
| PEPSICO_2022_10K | 503 | 1,583 |
| VERIZON_2021_10K | 120 | 651 |
| VERIZON_2022_10K | 124 | 642 |

Table `chunks_baseline` columns: `langchain_id`, `content`, `embedding vector(1536)` and `langchain_metadata` (langchain-postgres defaults), plus our metadata columns `doc_name`, `company`, `ticker`, `fiscal_year`, `doc_type`, `sector`, `page`. No vector index yet: every search is an exact scan of all rows.

## What we discovered

1. **The answers are in the data; retrieval misses them.** The right page reached the top 5 in only 3 of 8 answerable questions.
2. **Same topic, wrong year or company.** 3M 2018 and 2022 (and AMD 2015 and 2022) use near-identical language, so search mixes years. 3M tax tables outranked Boeing's for a Boeing question.
3. **Tables break.** PyPDF puts each table cell on its own line; a row label and its number can land in different chunks (3M capex: "Purchases of property, plant and equipment" in one chunk, "(1,577)" in the next).
4. **Wording mismatch.** Questions say "capital expenditure", "legal battles", "quick ratio"; filings say "purchases of property, plant and equipment", "legal proceedings", and never name the ratio.
5. **Exhibits add noise.** PepsiCo filings have 500+ pages and AmEx results included subsidiary lists and charters from the appendix.
6. **The strict prompt refuses rather than guesses.** Safe for finance, but it hides partial knowledge.
7. **"Correct" can depend on conventions.** Boeing's tax rate matched FinanceBench in size but not in sign (rates on pre-tax losses).

## Concepts learned

- **Document / chunk / retriever:** text plus metadata; small pieces of pages; the component that returns the most relevant chunks.
- **Two pipelines:** indexing (offline, once) and querying (online, per question).
- **Recursive splitting and overlap:** cut at paragraph, then line, then word boundaries; overlap keeps boundary sentences in both chunks.
- **Metadata columns vs JSON:** real SQL columns can be filtered and indexed; other keys go to a JSON column.
- **LCEL:** the `|` pipe syntax; `RunnableParallel` and `.assign()` keep the retrieved docs next to the answer for debugging.
- **Reading a LangSmith trace:** retriever step (which chunks), prompt (what the model saw), model call (what it said). Wrong chunks = retrieval problem; right chunks, wrong answer = generation problem.

## Gotchas

- PDF text contains NUL bytes (`\x00`) that Postgres rejects; `clean_text()` in the loader removes them.
- A failed ingest leaves a half-filled table; rebuild with `--rebuild`.
- `init_vectorstore_table` is not idempotent; `ingest.py` checks `table_exists()` first.
- In `psql`, a backslash command consumes the rest of a pasted block; run SQL with `psql -c "..."` instead.
- Pages: FinanceBench and PyPDF are zero-based; labels shown to people add 1.
- The pypdf "fontTools is required" message is a warning, not an error (`uv add fonttools` silences it).

## Next

M2: turn the 9-question failure log into a proper evaluation harness (golden set from all 39 FinanceBench questions, retrieval metrics, RAGAS), so every change from M3 on is measured automatically.
