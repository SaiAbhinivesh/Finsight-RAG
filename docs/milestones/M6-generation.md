# M6: Grounded generation

Completed: 2026-11-13 · Branch: `m6-generation`

**Goal:** turn retrieved evidence into correct, checkable answers: calculate and judge when the evidence allows, refuse only when it doesn't, cite sources that code can verify, and handle follow-up questions.

**Outcome:** with retrieval held fixed, correct answers went **20 → 29 of 39** (answer score 0.577 → 0.769), wrong answers stayed low (3), the 6 unanswerable questions are still refused, and **97% of citations (140/144) are verified by code** against the source text. New default answer setup: v2 analyst prompt + `gpt-5-mini` + structured output. Follow-ups work via a condense step and Postgres chat history.

## How answering works now

```text
(chat only) follow-up + history -> condense (gpt-4o-mini) -> standalone question
question -> router + HyDE + vector search (M4, unchanged) -> 5 chunks
  -> number the chunks [1]..[5]                                   code
  -> gpt-5-mini returns Answer {answer, answerable, citations}    LLM (ANSWER_MODEL)
  -> verify each citation: is the quote really in that chunk?     code
  -> render [n] as [Company Year, p. N]                           code
```

## Experiments (retrieval held fixed: all runs reuse the chunks saved in `m4_filters_hyde`)

| Run | Prompt | Answer model | Output | Correct | Partial | Wrong | Refused | Answer score | Faithfulness | Time / answer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m4_filters_hyde (original) | v1 strict | gpt-4o-mini | text | 18 | 5 | 4 | 12 | 0.526 | 0.81 | — |
| m6_v1_control | v1 strict | gpt-4o-mini | text | 20 | 5 | 3 | 11 | 0.577 | 0.84 | 2.3 s |
| m6_v2 | v2 analyst | gpt-4o-mini | text | 21 | 7 | 8 | 3 | 0.628 | 0.81 | 2.0 s |
| m6_v2_gpt5mini | v2 analyst | gpt-5-mini | text | 27 | 5 | 4 | 3 | 0.756 | 0.89 | 12.9 s |
| **m6_v2_structured** | v2 analyst | gpt-5-mini | **Answer + citations** | **29** | 2 | 3 | 5 | **0.769** | 0.89 | ~13 s |

Citation accuracy (structured run): 140/144 citations verified; 34/34 non-refused answers have at least one verified citation.

## What we discovered

1. **Hold retrieval fixed to test generation.** Reusing saved chunks removed HyDE's run-to-run noise; the control (same prompt, same model, same chunks) moved 18 → 20 correct, so generation noise is about ±2 questions.
2. **A permissive prompt on a small model is a bad trade.** v2 on gpt-4o-mini cut refusals 11 → 3 but raised wrong answers 3 → 8 for only +1 correct: it attempted calculations and judgements it could not do reliably.
3. **Prompt + reasoning model is the win.** v2 on gpt-5-mini: +7 correct over the control with no rise in wrong answers and the best faithfulness. The prompt decides whether the model tries; the model decides whether it gets it right.
4. **Cost of quality:** gpt-5-mini answers take ~13 s vs ~2 s and cost more (it pays for hidden reasoning tokens). Router, HyDE and condense stay on gpt-4o-mini.
5. **Structured output didn't hurt quality** (29 vs 27 correct, within noise) and made answers checkable. Refusals rose 3 → 5: having to quote evidence makes the model slightly more cautious.
6. **Unverified citations were near-misses** (two table cells stitched into one quote, small formatting differences), not invented facts; the strict word-for-word check flags them on purpose.
7. **Remaining failures:** multi-page calculations where one input isn't in the 5 chunks (PepsiCo EBITDA, quick ratios), "none" answers (AmEx securities), and convention disagreements (Boeing tax-rate sign). Cross-page and cross-filing work is M7's job.

## Files added or changed

| File | Role |
| --- | --- |
| `src/finsight/generation/prompts.py` | `RAG_PROMPT_V2` (analyst rules: combine blocks, calculate with formula, judge, state absences, partial answers, refuse only when nothing is relevant); `PROMPTS` lookup |
| `src/finsight/generation/models.py` | `chat_model()`: temperature 0 except for gpt-5 models (which reject it) |
| `src/finsight/generation/structured.py` | `Answer` / `Citation` models, `STRUCTURED_PROMPT`, `format_numbered()`, `verify_citations()`, `render()` |
| `src/finsight/generation/conversation.py` | `condense()` follow-ups into standalone questions; `open_history()` with `PostgresChatMessageHistory` (table `chat_history`) |
| `src/finsight/generation/chain.py` | Answers with `ANSWER_MODEL`, prompt v2, structured by default (`structured=False` for free text) |
| `src/finsight/chat.py` | Interactive chat with follow-ups and resumable sessions |
| `src/finsight/ask.py` | Structured by default (prints verified / NOT FOUND citations); `--no-structured` |
| `src/finsight/config.py`, `.env.example` | New `ANSWER_MODEL` (default `openai:gpt-5-mini`) |
| `eval/regenerate_answers.py` | Re-answer from a saved run's chunks: `--prompt`, `--model`, `--structured/--no-structured` |
| `eval/run_answers.py` | `--prompt`, `--model`, `--structured/--no-structured`; saves citations |
| `eval/score_answers.py` | Citation accuracy when an answers file has citations |

## Concepts learned

- **Grounded generation:** answer only from retrieved evidence, but use it fully (combine, calculate, judge).
- **Ablation with a control group:** freeze retrieval, change one generation component, compare against an unchanged re-run.
- **Reasoning models** (think before answering): better at multi-step maths and judgement; slower and costlier.
- **Structured output** (`with_structured_output` + Pydantic) for the product itself, not just evaluation.
- **Verifiable citations:** exact-quote checks in code; citation accuracy as a free, deterministic metric.
- **Conversational RAG:** condense the follow-up with chat history (`MessagesPlaceholder`), then run the normal pipeline; persist history per session.

## Gotchas

- gpt-5 models reject `temperature`; `chat_model()` handles it.
- Our refusal rule labels any answer containing "could not find" as refused, so the v2 prompt tells the model not to use the refusal sentence in partial answers.
- `regenerate_answers.py` now defaults to `ANSWER_MODEL` and structured output; earlier free-text runs need `--no-structured --model ...` to reproduce.
- Full evaluation runs take ~10 minutes now (~13 s per answer with gpt-5-mini).
- Comparisons across years or companies ("how does that compare to FY2021?") get rewritten correctly, but the router still picks one filing: that needs M7's agent.

## Next

M7: agentic RAG with LangGraph: let the system decide which filings to search, search more than once, and use a calculator tool for cross-page and cross-company questions.
