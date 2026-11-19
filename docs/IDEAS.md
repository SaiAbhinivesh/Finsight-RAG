# Ideas: what to build on top of FinSight

Ways to extend the project, ranked by value. Each one can be judged the way the rest of the project was: change one thing, run the evaluation (`eval/gate.py`), keep it only if the numbers improve. Good choices for a fork, a portfolio extension or a learning exercise.

## Quality

| Idea | Why | How to measure |
| --- | --- | --- |
| Grow the golden set to 150+ questions (all FinanceBench open-source questions, more companies) | With 39 questions, one question = 2.6 points and runs vary by ±2-3 | Same scorecard, tighter confidence |
| Fix the last systematic failure (Boeing tax rate sign convention) | The reference computes the rate on a pre-tax loss; the filing reports it the other way | A targeted question + a prompt note on sign conventions |
| Claim-level citation checks | Quotes are verified to exist, not to support their sentence | An LLM entailment check per (claim, quote), compared with hand labels |
| Hybrid search on extracted key terms instead of the whole question | Hybrid failed because long questions add noisy keywords | hit@5 / MRR vs HyDE |
| A long-input reranker (e.g. bge-reranker-v2-m3) | The tested rerankers were cut off at 512 tokens | The M5 reranking ablation |
| Parent-child retrieval for tables split across chunks | Several multi-page failures are split tables | The nine hard questions in [EXPERIMENTS.md](EXPERIMENTS.md) |
| Try newer models through the gate | The gate turns a model upgrade into a measured decision | `eval/gate.py` |

## Latency and cost

| Idea | Expected effect |
| --- | --- |
| Route questions to fast or accurate mode automatically (by question type) | Accurate-mode quality at close to fast-mode average latency |
| Skip the graph's `calculate` call when the plan needs no arithmetic | One fewer reasoning-model call on fact questions |
| Run the graph's searches in parallel | Retrieval time divided by the number of searches |
| Stream the answer text, then mark citations verified when the check finishes | Perceived latency from ~25-60 s to a few seconds |
| Prompt caching (stable system prompts first) | Lower input-token cost |
| A cheaper grading model, if a sweep shows no accuracy loss | Lower cost per accurate answer |

## Scaling to thousands of filings

- Ingestion: parse with a worker pool (Docling is ~1 s per page), batch the embedding calls, keep incremental indexing, run the chunk-context step through a batch API.
- Storage: an HNSW index on the chunk embeddings; partition by company or year if needed.
- Router: stop listing every filing in the prompt; match company names against a table, then extract the year.
- Evaluation: a small subset on every pull request, the full set nightly.

## Product

- Deploy a public demo: managed Postgres with pgvector, the API and UI containers on a container host, a per-IP rate limit, the API key server-side only.
- Authentication, per-user sessions and quotas.
- Let users upload their own filings (indirect prompt injection then becomes a real risk; the safety suite's poisoned-chunk tests already cover it).
- A dashboard over `request_log`: latency percentiles, cost per day, cache hit rate.
- Turn 👎 answers (`eval/pull_feedback.py`) into new golden questions.

## Learning extensions

- GraphRAG: entities (companies, segments, executives, risks) and their relations, for relationship questions.
- Multimodal RAG over the charts in filings.
- Fine-tuning the embedding model on question-chunk pairs from the golden set.
- An MCP server exposing `search_filings` so other agents can use the index.
- A different document domain (earnings-call transcripts, legal contracts) through the same pipeline and evaluation.
