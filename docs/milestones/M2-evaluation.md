# M2: Evaluation harness

Completed: 2026-11-10 · Branch: `m2-evaluation`

**Goal:** replace hand-checking with an automatic scorecard, so every change from M3 on is measured the same way.

**Outcome:** three commands score any pipeline on 45 questions (39 FinanceBench + 6 unanswerable). Baseline: the right page reaches the top 5 for **36%** of questions, and **7 of 39** answers are correct.

## How it flows

```text
eval/build_golden_set.py   FinanceBench + 6 hand-written questions -> data/eval/golden_set.jsonl
                           (also checks every evidence page against our PDFs: 0 problems)

eval/retrieval_metrics.py  golden questions -> vector search (top 10) -> page-based scores
                           -> retrieval_<run>_<time>.csv + one line in retrieval_summary.csv     (no LLM)

eval/run_answers.py        golden questions -> FinSight chain -> answers_<run>.jsonl
                           (saves each answer + the 5 chunks it saw)

eval/score_answers.py      answers_<run>.jsonl -> refusal rule + LLM judge + RAGAS
                           -> scores_<run>_<time>.csv + one line in answer_summary.csv
```

## Files added

| File | Role |
| --- | --- |
| `src/finsight/evaluation/golden.py` | `load_golden()`; `is_gold()` = right filing AND an evidence page |
| `src/finsight/evaluation/judge.py` | LLM judge (gpt-4.1-mini) returning a structured `Verdict`: correct / partial / wrong / refused + reason |
| `eval/build_golden_set.py` | Builds the golden set and verifies evidence pages |
| `eval/retrieval_metrics.py` | hit@1/3/5/10, recall@5, MRR, same_doc@5, breakdown by reasoning type |
| `eval/run_answers.py` | Runs FinSight on all questions; tags LangSmith traces with the run name |
| `eval/score_answers.py` | Judge + RAGAS (faithfulness, context precision, context recall), summary line |
| `data/eval/golden_set.jsonl` | 45 questions: question, reference answer, filing, evidence pages (zero-based), type |
| `eval/results/` | Per-question CSVs, saved answers, and the two summary files (experiment history) |

## Baseline results (run `m1_baseline`)

**Retrieval** (39 answerable questions, no LLM):

| hit@1 | hit@3 | hit@5 | hit@10 | recall@5 | MRR | same_doc@5 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.077 | 0.256 | 0.359 | 0.538 | 0.346 | 0.208 | 0.631 |

**Answers** (judge + RAGAS):

| Correct | Partial | Wrong | Refused | Answer score | Refusal accuracy | Faithfulness | Context precision | Context recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | 4 | 5 | 23 | 0.231 | 1.0 (6/6) | 0.833 | 0.384 | 0.500 |

Answer score: correct = 1, partial = 0.5, otherwise 0, averaged over the 39 answerable questions.

## What we discovered

1. **Retrieval is the bottleneck.** 64% of questions never get the right page into the 5 chunks the model reads; 46% are not even in the top 10.
2. **7 more questions are "almost found"** (rank 6 to 10): reranking (M5) should recover some.
3. **About 2 of every 5 chunks come from the wrong filing** (same_doc@5 = 0.63), e.g. Verizon 2021 p. 77 returned for a Verizon 2022 p. 77 question. Metadata filters (M4) target this.
4. **The system mostly refuses rather than invents** (23 refused vs 5 wrong). Faithfulness 0.83 when it does answer.
5. **Some failures are generation, not retrieval:** context recall was 1.0 for three failed questions (3M PP&E refused; AMD segment misread; PepsiCo restructuring $29M vs $411M). These are M6's job.
6. **Page-based metrics undercount:** a fact can appear on several pages (3M capex on p. 46 and p. 60) while the golden set lists one. Context recall (0.50) is higher than hit@5 (0.36) for this reason; we track both.

## The judge bug (and why we check the judge)

The first run labelled **8 refusals as "wrong"** (the judge reasoned "the information was available, so refusing is wrong") and 2 refusals as "correct" (for questions whose true answer is "none"/"no"). Fix: refusals are now labelled by a simple rule before the judge sees anything; only real answers go to the LLM. Lesson: never ask an LLM what a rule can decide, and always spot-check the judge against your own verdicts.

## Concepts learned

- **Golden set:** fixed questions + reference answers + evidence pages; never changes between experiments.
- **Retrieval vs generation metrics:** hit@k, recall@k, MRR (page-based, no LLM) vs judge verdicts and RAGAS (LLM-based).
- **MRR:** 1 / rank of the first correct result, averaged; rewards ranking the right page high.
- **LLM-as-judge:** a different, stronger model grades answers; structured output (`with_structured_output`) forces one of four labels; known biases (self-preference, leniency, rule-bending).
- **RAGAS:** faithfulness (claims supported by context), context precision (relevant chunks ranked first), context recall (reference facts present in context).
- **Separate generation from scoring:** answers are saved once and can be re-scored cheaply.
- **Experiment history:** each run appends one line to the summary CSVs.

## Gotchas

- RAGAS 0.4.3 imports `langchain_community.chat_models.vertexai`, removed in langchain-community 0.4.2. Pinned `langchain-community>=0.4,<0.4.2`.
- RAGAS's current (collections) API is async; `score_answers.py` uses `asyncio` with a semaphore of 5 to avoid rate limits.
- Faithfulness is undefined for refusals (no claims), so it is skipped for them.
- FinanceBench reasoning labels are combined with "OR"; `simple_type()` groups them into extraction / numerical / logical / unknown. Groups are small, so differences of ±0.15 are noise.
- The judge is not perfectly deterministic: small run-to-run changes in verdicts are expected.

## Costs

Retrieval metrics: under $0.01. Answers: about $0.01. Judge + RAGAS: about $0.10 to $0.30 per run.

## Next

M3: better ingestion (Docling layout-aware parsing, chunking experiments, contextual retrieval). Prediction to check: the **numerical** questions (table-heavy) should improve most.
