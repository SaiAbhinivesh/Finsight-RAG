# M3: Better ingestion

Completed: 2026-11-11 · Branch: `m3-ingestion`

**Goal:** fix "garbage in": readable tables, sensible chunks, less noise, and chunks that say what they are.

**Outcome:** answer score **0.231 → 0.474** (correct answers 7 → 15 of 39) and hit@5 **0.359 → 0.590**. The winning setup (Docling, 512-token chunks, exhibits removed, LLM-written context) is now FinSight's default index, `chunks_live`, kept up to date with incremental indexing.

## How it flows now

```text
scripts/parse_docling.py   PDF -> Docling (layout + table models) -> data/parsed/<doc>.json   (once, cached; ~1 s/page)

scripts/ingest.py --loader docling --drop-exhibits --context llm --incremental --table chunks_live
  docling_loader.py   cached JSON -> HybridChunker (512 tokens, headings in front) -> drop pages after SIGNATURES
  contextualize.py    gpt-4o-mini writes 1-2 sentences per chunk (cached in data/parsed/contexts/) -> prefixed to the text
  incremental.py      LangChain Indexing API: hash each chunk; embed only new/changed; delete removed
```

## Experiments (all scored with the M2 harness)

**Retrieval** (39 questions):

| Run | Change | hit@1 | hit@5 | hit@10 | MRR | same_doc@5 |
| --- | --- | --- | --- | --- | --- | --- |
| m1_baseline | PyPDF, 1000-char chunks | 0.077 | 0.359 | 0.538 | 0.208 | 0.631 |
| m3_docling | Docling, 512 tokens | 0.128 | 0.333 | 0.513 | 0.227 | 0.646 |
| m3_docling_256 | 256 tokens | 0.154 | 0.308 | 0.487 | 0.222 | 0.651 |
| m3_docling_1024 | 1024 tokens | 0.051 | 0.333 | 0.487 | 0.175 | 0.677 |
| m3_docling_noexh | 512, exhibits removed | 0.128 | 0.333 | 0.513 | 0.229 | 0.641 |
| m3_ctx_template | + metadata sentence (free) | 0.128 | 0.513 | 0.718 | 0.287 | 0.708 |
| **m3_ctx_llm** | + LLM-written context | **0.205** | **0.590** | **0.795** | **0.372** | 0.687 |

**Answers** (judge + RAGAS):

| Run | Correct | Partial | Wrong | Refused | Answer score | Faithfulness | Ctx precision | Ctx recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m1_baseline | 7 | 4 | 5 | 23 | 0.231 | 0.83 | 0.38 | 0.50 |
| m3_docling | 10 | 5 | 1 | 23 | 0.321 | 0.77 | 0.45 | 0.55 |
| m3_docling_noexh | 10 | 5 | 1 | 23 | 0.321 | 0.79 | 0.47 | 0.54 |
| **m3_ctx_llm** | **15** | **7** | 2 | **15** | **0.474** | 0.82 | **0.55** | **0.70** |

With 39 questions, one question = 0.026; differences of 1-2 questions are noise.

## What we discovered

1. **Docling improved answers, not search.** Readable tables cut wrong answers from 5 to 1, but hit@5 did not move. Our prediction ("numerical questions improve most") was wrong: numerical answer points stayed at 2.5/16.
2. **Chunk size barely matters here** (256 / 512 / 1024 within noise). 1024 ranked worst (hit@1 = 2 questions): big chunks mix topics.
3. **Removing exhibits changed nothing measurable**, because with Docling no exhibit chunk reached the top 5 (0 of 195; with PyPDF it was 4 of 195). Kept anyway: smaller, cheaper, less risk for real users.
4. **Contextual retrieval was the breakthrough.** A free metadata sentence already lifted hit@5 from 0.33 to 0.51; LLM context reached 0.59 and the best ranking. Telling each chunk its company, year, section and what it is *used for* bridges the vocabulary gap between questions ("liquidity", "capital intensive") and tables ("total current liabilities").
5. **Better retrieval turned refusals into answers** (23 → 15 refused) without more wrong answers (faithfulness 0.82).
6. **Wrong-year retrieval is still there** (same_doc@5 ≈ 0.69). Text alone doesn't fix it: M4 filters.

## Files added or changed

| File | Role |
| --- | --- |
| `src/finsight/ingestion/docling_loader.py` | Docling converter (OCR off), HybridChunker with OpenAI tokenizer, `signatures_page()`, chunk metadata incl. `pages`, `headings`, `chunk_index` |
| `scripts/parse_docling.py` | Convert all PDFs once, cache JSON, log progress |
| `src/finsight/ingestion/contextualize.py` | Template and LLM context, cached per filing, saved every 100 chunks |
| `src/finsight/indexing/incremental.py` | `index()` + `SQLRecordManager` (Postgres table `upsert_record`), `cleanup="full"`, `source_id_key="source"` |
| `scripts/ingest.py` | `--loader`, `--max-tokens`, `--drop-exhibits`, `--context`, `--incremental` |
| `src/finsight/evaluation/golden.py` | `is_gold()` accepts chunks spanning several pages |
| `notebooks/02_docling.ipynb` | Docling output vs PyPDF on the 3M capex table |
| Defaults | `build_rag_chain`, `run_answers.py`, `retrieval_metrics.py` now use `chunks_live` |

## Incremental indexing (Part D)

| Run | What changed | Result |
| --- | --- | --- |
| 1 | Fresh build | all chunks added |
| 2 | Nothing | all skipped, no embeddings |
| 3 | One filing's metadata (sector) | only that filing's chunks deleted + re-added |
| 4 | One filing removed from the manifest | only its chunks deleted (`cleanup="full"`) |

The hash covers text **and** metadata, so fixing a label in the manifest updates the stored chunks.

## Concepts learned

- **Layout-aware parsing:** vision models find headings, paragraphs, tables; tables rebuilt as rows/columns and serialised as "row, column = value".
- **Structure-aware (hybrid) chunking:** split by document structure, cut further only above a token limit; headings prefixed to each chunk.
- **Cache expensive steps:** Docling parsing (~1 s/page) and LLM contexts are saved to disk; experiments reuse them.
- **Contextual retrieval:** prepend a short, chunk-specific description before embedding.
- **Ablation:** change one thing at a time (chunk size, exhibits, context type) and measure.
- **Incremental indexing:** record manager + content hashes; cleanup modes None / incremental / full.

## Gotchas

- Docling's first run downloads its models (a few hundred MB); conversion is silent in notebooks, so run long jobs in the terminal (`parse_docling.py` logs progress). Interrupting a notebook cell shows `KeyboardInterrupt`, not a Docling error.
- Harmless warnings: `IProgress not found`, `unauthenticated requests to the HF Hub`, torch `Redirects are currently not supported in MacOs`, `MatchingPostProcessor ... cells were dropped`.
- Docling pages are 1-based; ours are 0-based.
- Some Docling table cells come out empty (e.g. header rows): an improvement, not perfect.
- 3M 2018's heading was read as `SIGNATURE S`; `signatures_page()` strips whitespace before matching.
- Run the LLM-context build with `LANGSMITH_TRACING=false` to avoid ~5,000 traces.
- `SQLRecordManager` lives in `langchain-classic` in LangChain 1.x.

## Costs

Docling: free (local), ~1 hour of laptop time once. LLM contexts: about $0.70 once (cached). Each embedding build: a few cents.

## Next

M4: better retrieval. Metadata filters (company and year extracted from the question) to fix wrong-filing results, hybrid keyword + vector search with RRF, and query rewriting.
