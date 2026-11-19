# M5: Reranking

Completed: 2026-11-12 · Branch: `m5-reranking`

**Goal:** fetch a bigger candidate pool, then let a cross-encoder re-sort it so the best 5 chunks reach the model.

**Outcome:** reranking **did not help** on top of filters + HyDE: both rerankers lowered hit@1, hit@5 and MRR. It stays in the code behind `--rerank` (off by default). This milestone also made filters + HyDE the default retrieval and started a one-table history of every run (now `docs/EXPERIMENTS.md`).

## How reranking fits in (when switched on)

```text
question
  -> router (filters)       which filing?                         gpt-4o-mini
  -> HyDE                   what text to search with?             gpt-4o-mini
  -> vector search          20 candidates inside that filing      Postgres + pgvector
  -> reranker               score each (real question, chunk) pair, keep the best 5   local cross-encoder
  -> answer                 gpt-4o-mini reads the 5 chunks
```

**Bi-encoder vs cross-encoder:** vector search embeds the question and each chunk separately (fast, approximate). A cross-encoder reads question and chunk together and scores relevance (slow, more precise), so it is only run on a shortlist.

## Experiments

| Run | Change | hit@1 | hit@3 | hit@5 | hit@10 | MRR |
| --- | --- | --- | --- | --- | --- | --- |
| m4_filters_hyde | M4 best (filters + HyDE) | 0.359 | 0.590 | 0.744 | 0.769 | 0.488 |
| m5_default_check | Same setup, now the default (re-run) | 0.359 | 0.641 | 0.821 | 0.821 | 0.520 |
| m5_rerank_minilm | + rerank 20 candidates with `cross-encoder/ms-marco-MiniLM-L-6-v2` | 0.205 | 0.513 | 0.641 | 0.821 | 0.404 |
| m5_rerank_bge | + rerank 20 candidates with `BAAI/bge-reranker-base` | 0.231 | 0.462 | 0.718 | 0.846 | 0.414 |

Answers were not re-scored: retrieval got worse, so there was nothing to gain.

## What we discovered

1. **The same setup gives different numbers on different runs.** Between `m4_filters_hyde` and `m5_default_check` (identical code), 12 questions changed rank and hit@5 moved 0.744 → 0.821. The router chose identically both times; the variation comes from HyDE writing a slightly different passage each run. Treat a single run as a sample; the setup's hit@5 is roughly 0.74-0.82.
2. **Reranking demoted good chunks.** Against the default run, bge moved 13 questions up and 18 down; many correct chunks fell from rank 1 to rank 4-6 (AMD liquidity, PepsiCo legal and restructuring, Boeing production rates). It did lift 3 questions from outside the top 10 into the top 3, thanks to the bigger pool.
3. **Likely causes:** (a) these rerankers read at most 512 tokens of question + chunk, and our 512-token chunks plus their context prefix plus long FinanceBench questions get truncated, often cutting off the table rows that hold the answer; (b) the models were trained on short web queries and prose, not analyst instructions and "row, column = value" tables; (c) HyDE already ranked well, and the reranker replaced that ordering with a weaker one.
4. **bge beat minilm** by about 3 questions at hit@5 (borderline noise); neither beat no reranking.
5. Not tested (chosen to stop here): `BAAI/bge-reranker-v2-m3` with a longer input limit, which would test the truncation explanation.

## Files added or changed

| File | Role |
| --- | --- |
| `src/finsight/retrieval/rerank.py` | `HuggingFaceCrossEncoder` + LangChain `CrossEncoderReranker`; models `minilm`, `bge`; loaded once per process |
| `src/finsight/retrieval/retrievers.py` | `search()` gains `rerank_with` and `candidates`: stage 1 fetches the pool, stage 2 reranks to k; `build_retriever` defaults to filters + HyDE |
| `src/finsight/generation/chain.py` | Defaults `use_filters=True`, `use_hyde=True`; `rerank_with`, `candidates` options |
| `eval/retrieval_metrics.py`, `eval/run_answers.py` | `--filters/--no-filters`, `--hyde/--no-hyde` (default on), `--rerank`, `--candidates`; retrieval metrics print average seconds per question |
| `src/finsight/ask.py` | Filters + HyDE by default; `--no-filters`, `--no-hyde`, `--hybrid`, `--rerank=minilm\|bge` |
| `docs/EXPERIMENTS.md` | One table of every run (what changed, key numbers, verdict) plus a diagram per run |

## Concepts learned

- **Two-stage retrieval:** fast, broad first stage (vector search) + slow, precise second stage (cross-encoder) on a shortlist.
- **Bi-encoder vs cross-encoder** and why cross-encoders can't search the whole corpus.
- **Local models:** sentence-transformers downloads models from Hugging Face once into `~/.cache/huggingface/hub/` and runs them on your Mac; free per call, costs time.
- **Input length limits:** a model that reads 512 tokens silently ignores the rest.
- **Run-to-run variance** from LLM steps (HyDE) and why to average runs or cache LLM outputs.
- **Default-on flags** with `argparse.BooleanOptionalAction` (`--hyde` / `--no-hyde`).

## Gotchas

- First use of a reranker downloads it (minilm ~90 MB, bge ~1.1 GB); later runs load from the local cache.
- To free disk space: `du -sh ~/.cache/huggingface/hub/* | sort -h`, then delete unused `models--...` folders or run `uv run hf cache delete`. Keep Docling's models if you will parse new filings.
- `search()` keeps `False` defaults on purpose (callers pass explicit values); `build_retriever` and `build_rag_chain` default to the best setup.

## Next

M6: grounded generation. About 13 questions already have the right page in the top 5 but are refused or only partly answered; M6 changes how the model answers (inference and simple calculations from the context, structured answers with verified citations, "none"/"no" answers, follow-ups).
