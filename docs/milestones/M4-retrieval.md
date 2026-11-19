# M4: Better retrieval

Completed: 2026-11-12 · Branch: `m4-retrieval`

**Goal:** find the right chunks: the right filing (company + year) and the right page within it.

**Outcome:** with metadata filters + HyDE, the right page reaches the model's top 5 for **29 of 39** questions (hit@5 0.744, up from 0.590 in M3 and 0.359 in M1), every retrieved chunk comes from the right filing (same_doc@5 = 1.0), and **18 of 39** answers are correct (answer score 0.526). Hybrid keyword search was tried and **rejected**: it made results worse on this data.

## How retrieval works now

```text
question
  -> filters.py   gpt-4o-mini picks {company, fiscal_year} from the filings that exist (+ code guardrails)
  -> rewrite.py   gpt-4o-mini writes a hypothetical 10-K passage answering the question (HyDE)
  -> retrievers.py  vector search with the HyDE passage, only inside that filing
                    (falls back to unfiltered search if the filter finds nothing)
  -> 5 chunks -> prompt -> gpt-4o-mini -> answer        (unchanged)
```

Each technique is a flag: `--filters`, `--hyde`, `--hybrid` on `ask.py`, `run_answers.py` and `retrieval_metrics.py`. Best configuration: `--filters --hyde`.

## Experiments

**Retrieval** (39 questions, table `chunks_live`):

| Run | Change | hit@1 | hit@3 | hit@5 | hit@10 | recall@5 | MRR | same_doc@5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m3_live_check | M3 best, no filters | 0.205 | 0.462 | 0.590 | 0.795 | 0.538 | 0.372 | 0.687 |
| m4_filters | + metadata filters (first prompt) | 0.154 | 0.564 | 0.641 | 0.769 | 0.611 | 0.357 | 0.923 |
| m4_filters_v2 | + fixed router prompt | 0.205 | 0.615 | 0.718 | 0.846 | 0.675 | 0.415 | 1.000 |
| m4_filters_hybrid | + keyword search (RRF) | 0.205 | 0.487 | 0.615 | 0.821 | 0.577 | 0.381 | 1.000 |
| **m4_filters_hyde** | **+ HyDE** | **0.359** | 0.590 | **0.744** | 0.769 | **0.714** | **0.488** | **1.000** |

**Answers** (judge + RAGAS):

| Run | Correct | Partial | Wrong | Refused | Answer score | Faithfulness | Ctx precision | Ctx recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m3_ctx_llm (M3 best) | 15 | 7 | 2 | 15 | 0.474 | 0.82 | 0.55 | 0.70 |
| m4_filters | 14 | 7 | 3 | 15 | 0.449 | 0.83 | 0.59 | 0.68 |
| m4_filters_v2 | 17 | 5 | 3 | 14 | 0.500 | 0.83 | 0.64 | 0.74 |
| m4_filters_hybrid | 15 | 4 | 5 | 15 | 0.436 | 0.83 | 0.52 | 0.69 |
| **m4_filters_hyde** | **18** | 5 | 4 | **12** | **0.526** | 0.81 | 0.61 | **0.77** |

One question = 0.026; differences of 1-2 questions are noise.

## What we discovered

1. **Filters solved the wrong-filing problem** (same_doc@5 0.69 → 1.0) once the router prompt was right.
2. **A true rule without a priority misleads an LLM.** The first router prompt said "a 2022 filing also reports 2021"; the model over-applied it and sent three FY2021 questions to 2022 filings (filter accuracy 36/39). Stating the default ("match the year asked") and the exceptions (comparisons, forecasts) fixed all three (39/39).
3. **Filtering is all-or-nothing:** a wrong year means the right page cannot appear at all, so router accuracy matters more than anything else in this setup.
4. **Hybrid search hurt here.** FinanceBench questions are long and instruction-heavy, so keyword matches are noisy; RRF weights both lists equally and pulled good vector results down; contextual retrieval had already put the key terms into chunk text. Kept behind `--hybrid`, off by default.
5. **HyDE helped most on ranking** (hit@1 0.205 → 0.359, MRR 0.415 → 0.488): a 10-K-style passage sits much closer to real filing text than an instruction-heavy question does.
6. **The bottleneck has moved to generation.** Many questions now have the right page in the top 5 but are refused or only partly answered (multi-page calculations, ratios, "no"/"none" answers, the strict refusal prompt). That is M6 and M7's job.

## Files added or changed

| File | Role |
| --- | --- |
| `src/finsight/retrieval/filters.py` | Router: `QueryFilters` structured output, available filings from the manifest, guardrails, `to_pg_filter()` |
| `src/finsight/retrieval/keyword.py` | Postgres full-text keyword search (OR of terms, `ts_rank_cd`), `rrf()` |
| `src/finsight/retrieval/rewrite.py` | HyDE: hypothetical 10-K passage for search only |
| `src/finsight/retrieval/retrievers.py` | One shared `search()` (filters, hybrid, HyDE, fallback) and `build_retriever()` |
| `src/finsight/generation/chain.py` | Uses `build_retriever`; `use_filters`, `hybrid`, `use_hyde` options |
| `src/finsight/ask.py`, `eval/run_answers.py`, `eval/retrieval_metrics.py` | `--filters`, `--hybrid`, `--hyde` flags; retrieval metrics report router accuracy (`filter_ok`) |
| Postgres | GIN index `chunks_live_fts` on `to_tsvector('english', content)` for keyword search |

## Concepts learned

- **Self-query / metadata filtering:** an LLM turns the question into structured filters; code validates them; search runs inside the filter.
- **Measuring the router separately** (filter accuracy) from the search it controls.
- **Keyword (full-text) search:** tsvector / tsquery, stemming, stopwords, OR vs AND matching, GIN index.
- **Reciprocal Rank Fusion:** combine ranked lists by 1 / (60 + rank); rank-based, so different score scales don't matter.
- **HyDE:** search with a generated answer-like passage; never show it to the answering model.
- **Negative results are results:** hybrid search is widely recommended, but measured on this data it lost; keep the evidence, keep the flag, turn it off.

## Gotchas

- `SELECT ... FROM table, func(...)::type AS q` is a Postgres syntax error; wrap the cast in a subquery: `(SELECT func(...)::type AS q) AS terms`.
- `plainto_tsquery` ANDs every word; long questions then match nothing. Replace `&` with `|` for OR matching.
- The GIN index expression must match the query expression exactly (`to_tsvector('english', content)`) or Postgres won't use it.
- New CLI options need `parser.add_argument`; `unrecognized arguments: --hybrid` means the flag isn't declared in that script yet.
- Each technique adds an LLM call per question (router, HyDE): slightly slower and costlier per answer.

## Next

M5: reranking with a cross-encoder (re-sort more candidates so the best 5 reach the model). Then M6, where the biggest remaining gains are: answers for questions whose evidence is already retrieved.
