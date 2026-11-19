# Glossary: every concept in FinSight, in two lines

Each term: what it is, and where it lives in this repo. Quick revision before an interview.

## Ingestion and indexing

| Term | What it is | In FinSight |
| --- | --- | --- |
| RAG | Retrieval-Augmented Generation: fetch relevant text, then have the model answer from it | The whole project |
| Document (LangChain) | Text (`page_content`) + `metadata` dict | Every chunk |
| Chunking | Splitting documents into pieces small enough to embed and retrieve | Docling `HybridChunker`, 512 tokens (`ingestion/docling_loader.py`) |
| Chunk overlap | Repeating a few sentences between neighbouring chunks so facts at a boundary are not cut | M1 recursive splitter (200 chars) |
| Layout-aware parsing | Reading a PDF's structure (headings, tables) instead of raw text | Docling (M3) |
| Contextual retrieval | Prefixing each chunk with an LLM-written sentence saying where it comes from | `ingestion/contextualize.py`; hit@5 0.33 → 0.59 |
| Embedding | A vector of numbers representing meaning; similar texts get nearby vectors | `text-embedding-3-small`, 1536 dimensions |
| Cosine similarity | Angle-based closeness of two vectors (1 = same direction) | Vector search, cache threshold 0.95 |
| Vector store | A database that searches by vector similarity | Postgres + pgvector (`indexing/store.py`) |
| HNSW | An approximate nearest-neighbour graph index: fast vector search at scale | `answer_cache` index |
| Incremental indexing | Re-embedding only new or changed chunks | Indexing API + `SQLRecordManager` (`indexing/incremental.py`) |

## Retrieval

| Term | What it is | In FinSight |
| --- | --- | --- |
| Dense retrieval | Search by embedding similarity | Default search |
| Sparse / keyword retrieval | Search by matching words (BM25, full-text) | Postgres `tsvector` (`retrieval/keyword.py`), rejected |
| Hybrid search | Combining dense and keyword results | Tested in M4, worse here |
| RRF | Reciprocal Rank Fusion: score = Σ 1 / (60 + rank) across result lists | `keyword.rrf` (hand-written) |
| Metadata filtering / self-query | Extracting filters (company, year) from the question and searching only matching chunks | LLM router (`retrieval/filters.py`) |
| Query transformation | Rewriting the question before searching | HyDE (`retrieval/rewrite.py`), follow-up condensing |
| HyDE | Hypothetical Document Embeddings: search with a fake answer passage instead of the question | Kept (M4) |
| Bi-encoder vs cross-encoder | Embeds query and document separately (fast) vs reads them together (accurate, slow) | Embeddings vs `retrieval/rerank.py` |
| Reranking | A second, more precise scoring of the top candidates | Tested in M5, off by default |
| top-k | How many chunks the model reads | 5 |

## Generation

| Term | What it is | In FinSight |
| --- | --- | --- |
| Grounding | Answering only from the retrieved text | Prompts v1-v3 |
| Hallucination | A confident claim not supported by the sources | Prevented by quote checks and "never invent numbers" |
| Structured output | The model returns a typed object instead of free text | `Answer` / `Citation` (`generation/structured.py`) |
| Citation verification | Checking in code that each quote really appears in the cited chunk | `verify_citations` (97% verified) |
| Refusal | Declining when the answer is not in the sources | 6/6 unanswerable questions |
| Reasoning model | A model that thinks before answering (hidden reasoning tokens): slower, better at maths and judgement | gpt-5-mini |
| Conversational RAG | Rewriting a follow-up into a standalone question using chat history | `conversation.condense` |

## Agents and workflows

| Term | What it is | In FinSight |
| --- | --- | --- |
| Tool calling | The model asks to run a function and reads its result | `search_filings`, `calculator` (`agent/tools.py`) |
| ReAct agent | A loop: reason, act (call a tool), observe, repeat | `create_agent` (`agent/simple_agent.py`) |
| LangGraph | A library for stateful graphs of steps with conditional edges | `agent/graph.py` |
| Corrective RAG | Grade the retrieved chunks; if facts are missing, rewrite the query and retrieve again | plan → retrieve → grade → retry |
| Query decomposition | Splitting a question into the facts it needs, one search each | `plan` node |
| Recursion limit / budget | A hard cap on steps or tool calls so an agent cannot loop | 40 steps, 6 searches (in code) |

## Evaluation

| Term | What it is | In FinSight |
| --- | --- | --- |
| Golden set | Fixed questions with reference answers | 39 FinanceBench + 6 unanswerable (`data/eval/`) |
| hit@k | Share of questions whose evidence page is in the top k chunks | `retrieval_metrics.py` |
| Recall@k | Share of all evidence pages found in the top k | same |
| MRR | Mean Reciprocal Rank: 1 / rank of the first relevant chunk, averaged | same |
| LLM-as-judge | A (stronger, different) model grading answers against references | gpt-4.1-mini (`evaluation/judge.py`) |
| RAGAS | Library of LLM-based RAG metrics | Faithfulness, context precision, context recall |
| Faithfulness | Share of an answer's claims supported by its context | RAGAS; noisy for calculated numbers |
| Ablation | Changing one component at a time to measure its effect | Every milestone |
| Control run | Re-running an unchanged setup to measure noise | `m6_v1_control`, `m7_pipeline` |
| Red-teaming | Deliberately attacking the system to find failures | `eval/safety_eval.py` |
| Eval gate | Automated quality thresholds that block a change | `eval/gate.py` in GitHub Actions |

## Production

| Term | What it is | In FinSight |
| --- | --- | --- |
| SSE | Server-Sent Events: a one-way stream from server to browser over HTTP | `GET /ask/stream` |
| Callback handler | A LangChain hook called on every nested model call | `UsageTracker` |
| p50 / p95 latency | The median and the 95th-percentile response time | `usage_report.py` |
| Semantic cache | Reusing answers for questions with the same meaning | `answer_cache` + entity check |
| Prompt injection (direct / indirect) | Instructions hidden in the user's question / in retrieved documents | Guard, prompt v3, output check |
| Guardrails | Checks before and after the model | `safety/guard.py` |
| Canary token | A secret marker in the prompt; seeing it in output proves a leak | `prompts.CANARY` |
| Fail open / fail closed | On error, allow / block | The guard fails open |
| Tracing | Recording every step of a run for debugging | LangSmith |
| Multi-stage Docker build | Build in one image, ship only the result in a smaller one | `frontend/Dockerfile` |
| Dependency groups | Optional package sets installed only where needed | `pyproject.toml` (ingest, eval, rerank, dev) |
