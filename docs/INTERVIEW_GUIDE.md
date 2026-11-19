# Interview guide: RAG questions, answered with real numbers

If you are preparing for AI-engineering interviews, a working project you can explain end to end is worth more than any list of definitions. This guide shows how to talk about a RAG system like FinSight: the questions interviewers ask, answers grounded in measurements from this repo, and case studies of things that went wrong and how they were fixed.

If you build or fork this project, replace the numbers with your own runs (see [EXPERIMENTS.md](EXPERIMENTS.md) for the reference numbers).

## Describing the project

**In 30 seconds.** FinSight answers questions about companies' annual reports and cites the exact page, with every quote verified against the source. It was built in 11 milestones with LangChain and LangGraph, measuring each change on a FinanceBench test set: correct answers went from 7 to 34 out of 39. It has a streaming web UI, cost tracking, prompt-injection defences and a CI gate that re-evaluates every change.

**In 2 minutes.** 10-K filings are hard for RAG: 100+ pages, dense tables, the same vocabulary in every company's report. Start with a naive pipeline (PyPDF, fixed chunks, top-5 vector search) and build the evaluation harness *before* optimising: 39 FinanceBench questions with evidence pages, 6 unanswerable ones, retrieval metrics, an LLM judge and RAGAS. Then change one layer at a time:

1. Ingestion: Docling keeps tables intact; contextual retrieval (an LLM sentence per chunk saying which company, year and section) takes hit@5 from 0.33 to 0.59.
2. Retrieval: an LLM router restricts search to the right filing; HyDE improves ranking. Hybrid keyword search and cross-encoder reranking were *worse* on this data.
3. Generation: a reasoning model with an analyst prompt and structured output; code verifies every quote (97% verified).
4. Multi-step: a LangGraph workflow that plans the facts it needs, retries missing ones and calculates in code: 34/39.
5. Production: cost per answer (~half a cent), a semantic cache, guardrails tested by a 16-attack red-team suite, Docker, and a GitHub Actions evaluation gate.

## Reference numbers

| What | Number |
| --- | --- |
| Test set | 39 FinanceBench questions + 6 unanswerable, 11 filings, 6 companies, ~5,000 chunks |
| Correct answers | 7 (naive) → 15 (ingestion) → 18 (retrieval) → 29 (generation) → **34** (LangGraph); fast mode 25-28 |
| Retrieval hit@5 | 0.36 → 0.59 (contextual retrieval) → 0.72 (router) → 0.74-0.82 (HyDE) |
| Rejected | hybrid search 0.72 → 0.62 · rerankers 0.82 → 0.64 / 0.72 |
| Citations verified in code | 97% |
| Unanswerable questions declined | 6/6 |
| Safety | 12/16 → 16/16 attacks handled; 0/45 real questions blocked |
| Cost / latency | fast ~$0.005, 25-30 s · accurate ~60 s · cache hit 0.1 s · guard decline $0.0001 |
| Run-to-run noise | ±2-3 questions |

## Case studies from the build

Each one is a good answer to "tell me about a hard problem you solved". The pattern: what happened, how it was diagnosed, what changed, the measured result.

**1. The router that picked the wrong year.** Adding company/year filters should have helped every question, but three FY2021 questions got worse. The router prompt said "a 2022 filing also covers 2021", so it picked the newer filing. Measuring the router on its own (36/39) exposed it; a priority rule (use the year asked unless comparing or forecasting) gave 39/39 and hit@5 0.64 → 0.72. *Evaluate components separately, not only end to end.*

**2. The agent that wouldn't stop.** A ReAct agent scored worse than the fixed pipeline: 8 "refusals". The traces showed they were not refusals: the agent kept searching until the step limit killed it, despite "max 6 searches" in its prompt. Moving the budget into the tool ("Search limit reached. Answer now or refuse.") took it from 27 to 34 correct with the same model and prompt. *Prompts are suggestions; limits belong in code.*

**3. When best practices lost.** Hybrid search and cross-encoder reranking are standard advice. Here hybrid dropped hit@5 from 0.72 to 0.62 (long, instruction-heavy questions make keyword matches noisy) and both rerankers ranked worse (512-token input limits, table text). They stay behind flags, documented. *Measure on your data; "what didn't work" is a result.*

**4. The gate that caught its own scorer.** The CI evaluation gate's first run failed: refusal accuracy 83%. The system had correctly answered "no dividend policy for 2030 is stated", but the judge labelled it "refused" and the scorer only accepted "correct". Unit tests found two more evaluation-side bugs: the agent's calculator accepted `9**9**9` (a denial of service via prompt injection), and the fabrication check matched numbers as substrings. *Evaluation code needs the same scrutiny as the product.*

**5. Safety without losing accuracy.** A 16-attack suite was written first (direct and indirect injection, off-topic, investment advice, fabrication, secrets): baseline 12/16, including a projection built on an invented "$100 billion" base with real-looking citations. An input guard, prompt rules and a canary-based leak check gave 16/16; testing the guard on all 45 real questions found it blocking 3 speculative ones, so it was narrowed; the scorecard confirmed no accuracy loss. *Every guard needs a false-positive test.*

## Questions and answers

**How do you evaluate a RAG system?** Separately for retrieval and generation. Retrieval: hit@k, recall@k and MRR against known evidence pages, cheap and deterministic. Generation: an LLM judge against reference answers (a different, stronger model; refusals labelled by rule), RAGAS faithfulness and context metrics, and code checks such as exact-quote verification. Add unanswerable questions for refusal accuracy, control runs for noise, and a red-team suite for safety.

**How do you prevent hallucinations?** Retrieve from the right document, answer only from context, never invent numbers, return structured output with a quote per claim, verify each quote in code, compute arithmetic with a tool, and refuse when an "answerable" answer has no verified quote.

**Why did contextual retrieval help so much?** A balance-sheet chunk says "Total current liabilities 6,000" but not which company or year, and every 10-K looks alike. Prefixing "This chunk is from AMD's FY2022 10-K, balance sheet..." puts the missing identity into the embedding.

**Why Postgres + pgvector rather than a dedicated vector database?** One database for vectors, metadata filters (real columns), full-text search, chat history, logs and the cache. Fast at this size; HNSW indexes scale it much further.

**What is HyDE, and when does it help?** The model writes a hypothetical answer passage and you search with it, because document-style text is closer in embedding space to the real documents than a question is. Here it improved ranking (MRR 0.42 → 0.49) at the cost of an extra call and some run-to-run variance.

**Agent or workflow?** Both reached 34/39. The agent is flexible but needed code-enforced budgets and makes a variable number of calls. The LangGraph workflow has a fixed path (4-6 calls), logs every step and had the best citation accuracy, so it is the "accurate" mode; simple questions go to the fast pipeline.

**How do you control cost and latency?** Measure first: a callback handler records tokens (including reasoning tokens), cost and time for every model call in a request, logged per request, reported as p50/p95. Use cheap models for helper steps and the reasoning model only where it changes answers; cache repeats; decline off-topic questions before retrieval.

**What is risky about a semantic cache?** Embeddings measure topic, not facts: "AMD revenue FY2022" and "FY2015" are almost the same vector. Require the same companies and years in code, then a high similarity threshold chosen by a sweep with zero false hits. In finance that means it mostly serves near-exact repeats.

**How do you defend against prompt injection?** Layers: an input guard for off-topic and attack messages, a prompt that treats retrieved text as data (indirect injection is the RAG-specific risk), and an output check with a canary token. Test with a suite that includes poisoned chunks inserted among real ones.

**How would you scale to thousands of documents?** Parallel parsing workers, batch embeddings, an HNSW index, metadata filters as the first cut (they matter more as the corpus grows), a router that matches company names against a table instead of listing every filing in its prompt, and the same evaluation gate on a larger test set. See [IDEAS.md](IDEAS.md).

**What would you do differently?** Build the evaluation harness even earlier with more questions (39 means ±2-3 noise), log costs from day one, and unit-test evaluation code as soon as it exists.

**What are the limitations?** A small corpus and test set; English 10-Ks only; ~60 s for accurate answers; quote verification proves a quote exists, not that it supports the claim; one systematic failure remains (a sign-convention disagreement with FinanceBench on Boeing's tax rate).
