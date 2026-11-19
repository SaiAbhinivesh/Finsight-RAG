# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Cursor, Copilot and others) working in this repository. Human-oriented docs live in `README.md` and `docs/`.

## What this project is

FinSight is an educational, end-to-end RAG system that answers questions about SEC 10-K filings with citations verified against the source. Python 3.12 + LangChain 1.x + LangGraph, Postgres 16 + pgvector, FastAPI (SSE) and a React + TypeScript UI. It was built in milestones M0-M10; each milestone is documented in `docs/milestones/`. Every design choice was measured: read `docs/DECISIONS.md` before changing an approach that looks "suboptimal" (hybrid search and reranking were tested and deliberately turned off).

## Setup

```bash
cp .env.example .env                 # needs OPENAI_API_KEY; set LANGSMITH_TRACING=false without a LangSmith key
docker compose up -d db              # Postgres + pgvector on localhost:6024 (container: finsight-db)
uv sync                              # all dependency groups
```

For a fast start on 2 filings, uncomment `FINSIGHT_MANIFEST=data/manifest_quicktour.csv` in `.env` and follow `docs/QUICK_TOUR.md`. The full build (11 filings) is in `docs/GETTING_STARTED.md`.

## Commands

| Task | Command | Cost |
| --- | --- | --- |
| Lint | `uv run ruff check src eval scripts tests` | free |
| Unit tests | `uv run pytest` | free, no API key or database needed |
| Frontend check | `cd frontend && npm run build` | free |
| Ask (fast / accurate) | `uv run python -m finsight.ask "..."` / `--graph "..."` | ~$0.005 / ~$0.01 |
| API | `uv run uvicorn finsight.api.main:app --reload --port 8000` | |
| UI | `cd frontend && npm run dev` (port 5173) | |
| Retrieval metrics | `uv run python eval/retrieval_metrics.py --run <name>` | ~free |
| Answer scorecard | `uv run python eval/run_answers.py --run <name>` then `eval/score_answers.py --run <name>` | ~$0.30, ~20 min |
| Safety suite | `uv run python eval/safety_eval.py --run <name>` | ~$0.10 |
| Eval gate (all checks) | `uv run python eval/gate.py --run <name>` | ~$0.35, ~30 min |

Always run lint and unit tests after a code change. **Ask the user before running anything that calls OpenAI in bulk** (scorecard, safety suite, gate, re-indexing): they cost money and take minutes. Evaluations need the full 11-filing index.

## Layout

```text
src/finsight/
  config.py          settings from .env (pydantic-settings); import `settings`, never read env vars directly
  service.py         single entry point for CLI/API/UI: guard -> cache -> fast/accurate -> output check
  ingestion/         PDF loading (PyPDF, Docling), chunking, LLM chunk context, manifest
  indexing/          pgvector store, incremental indexing (SQLRecordManager)
  retrieval/         router (company/year filters), HyDE, keyword + RRF, rerank, search()
  generation/        prompts (v1-v3), models, structured Answer + citation checks, follow-ups, chain
  agent/             tools (search_filings, calculator), ReAct agent, LangGraph workflow (graph.py)
  cache/ safety/ observability/   semantic cache, guard + checks, cost/latency tracking
  api/main.py        FastAPI: /ask, /ask/stream (SSE), /feedback, /filings
eval/                golden-set metrics, scorecard, safety suite, cache sweep, gate (+ gate_baseline.json)
scripts/             download_filings, parse_docling, ingest, smoke_test
frontend/src/        React app (App.tsx, components/, api.ts)
tests/               unit tests (dummy settings in conftest.py)
docs/                build guide, milestone notes, architecture, experiments, decisions
```

`docs/ARCHITECTURE.md` has a "where to change what" table and the life of one request.

## Conventions

- LangChain 1.x APIs: `init_chat_model`, `init_embeddings`, `create_agent`, LCEL. Create chat models with `generation.models.chat_model()` (gpt-5 models reject `temperature`). Don't use legacy `LLMChain` / `RetrievalQA` / `AgentExecutor`.
- Models come from `.env` (`CHAT_MODEL`, `ANSWER_MODEL`, `JUDGE_MODEL`, `EMBEDDING_MODEL`); prices in `observability/pricing.py`.
- Answers are structured (`generation/structured.py`: `Answer`, `Citation`) and every quote is verified in code. Keep that contract when changing generation.
- Limits for agents belong in code (tool budgets, recursion limits), not only in prompts.
- Logging, cache and guard code must never break an answer (they catch and continue on purpose).
- Ruff, line length 120; explicit rule set in `pyproject.toml`. Type hints on public functions.
- New dependencies: serving packages in `[project] dependencies`; ingestion / evaluation / reranking-only packages in the matching `[dependency-groups]` group, so the API Docker image stays small.
- Unit tests must not call OpenAI or the database.

## Changing behaviour (the project's rule)

Change one thing, then measure: retrieval changes → `eval/retrieval_metrics.py`; prompt, model or graph changes → the answer scorecard; guard or prompt-security changes → the safety suite and `safety_eval.py --golden` (the guard must block 0 of 45 real questions). Compare with `docs/EXPERIMENTS.md`; runs vary by ±2-3 questions. Record new choices in `docs/DECISIONS.md`.

## Do not

- Commit `.env`, API keys, `data/raw/`, `data/parsed/`, `*.dump` or `eval/results/` output (all gitignored; keep it that way).
- Drop or rebuild the `chunks_live` table, or run `docker compose down -v`, without asking: rebuilding the index costs ~1 hour of parsing plus API usage.
- Change `eval/gate_baseline.json` thresholds just to make a check pass.
- Edit `data/eval/golden_set.jsonl` by hand (it is generated by `eval/build_golden_set.py`).

## Gotchas

- Port 6024 (database), 8000 (API), 5173 (UI); the database container is named `finsight-db`.
- Docling parsing is ~1 s per page and downloads layout models on first run; parsed JSON is cached in `data/parsed/`.
- `FINSIGHT_MANIFEST` switches every script, the router, guard and cache to another filing list (tests always use the full list).
- Inside Docker the database host is `db:5432`; on the host it is `localhost:6024`.
- The semantic cache can return a saved answer; skip it with `?cache=false` or clear it: `uv run python -m finsight.cache.semantic_cache --clear`.
