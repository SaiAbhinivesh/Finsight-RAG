# Getting started

How to run the full FinSight build from a fresh clone. To see it working first on 2 filings in ~20 minutes, follow the [quick tour](QUICK_TOUR.md). This guide is updated at the end of every milestone, so it always matches what the repo can do right now.

> Covers: **M0** (setup, database, data) **M1** (build the index, ask questions), **M2** (evaluation), **M3** (Docling, contextual retrieval, incremental index), **M4** (filters, HyDE, hybrid search), **M5** (reranking, new defaults) and **M6** (answer model, structured answers, chat), **M7** (agent and LangGraph workflow), **M8** (API, web UI, feedback), **M9** (costs, cache, safety, Docker) and **M10** (tests, CI, eval gate).

## 1. Prerequisites

| Tool | Why | Install |
| --- | --- | --- |
| uv | Installs Python 3.12 and all packages | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker Desktop | Runs Postgres + pgvector | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Git | Clone the repo | Preinstalled on macOS (`xcode-select --install` if not) |
| OpenAI API key | Chat model and embeddings | [platform.openai.com](https://platform.openai.com/) (about $5 of credit covers the whole project) |
| LangSmith API key | Traces every LLM call (free tier) | [smith.langchain.com](https://smith.langchain.com/) |
| Node.js 20+ | Runs the web UI (M8) | [nodejs.org](https://nodejs.org/) or `brew install node` |

Check: `uv --version` and `docker --version` both print a version.

## 2. Clone and install

```bash
git clone https://github.com/SaiAbhinivesh/finsight-rag.git finsight
cd finsight
uv sync
```

`uv sync` creates `.venv/` with Python 3.12 and installs everything in `uv.lock`, including the `finsight` package itself (in editable mode, so `import finsight` works in scripts and notebooks).

## 3. Configure secrets

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Value |
| --- | --- |
| `OPENAI_API_KEY` | Your OpenAI key |
| `LANGSMITH_API_KEY` | Your LangSmith key |
| `DATABASE_URL` | Leave the default unless you changed `docker-compose.yml` |
| `CHAT_MODEL` | `openai:gpt-4o-mini` by default: helper steps (router, HyDE, chunk context, follow-up rewriting) |
| `ANSWER_MODEL` | `openai:gpt-5-mini` by default: writes the answers |
| `EMBEDDING_MODEL` | `openai:text-embedding-3-small` by default |

`.env` is gitignored. Never commit it.

All settings are read by `src/finsight/config.py`. If a required value is missing, the app stops at startup with a clear validation error.

## 4. Start the database

```bash
docker compose up -d db
docker compose ps        # STATUS should say "healthy"
```

(`docker compose up` without `db` builds and starts the whole app: see step 10.)

This starts Postgres 16 with the pgvector extension on **localhost:6024** (6024 rather than 5432 so it does not clash with a local Postgres). Data persists in the `pgdata` Docker volume across restarts.

Enable the vector extension once:

```bash
docker exec -it finsight-db psql -U finsight -d finsight -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## 5. Download the filings

```bash
uv run python scripts/download_filings.py
```

Reads `data/manifest.csv` and downloads the 11 10-K PDFs into `data/raw/`. Re-running it skips files that already exist, and every file is checked to be a real PDF.

## 6. Run the smoke test

```bash
uv run python scripts/smoke_test.py
```

Expected output (numbers will vary slightly):

```text
=== 1. Chat model ===
Reply:   ok
=== 2. Embeddings ===
Dimensions: 1536  (expect 1536)
Related pair   (1 vs 2): ~0.60
Unrelated pair (1 vs 3): ~0.00
=== 3. Postgres + pgvector ===
pgvector: 0.8.x
All checks passed.
```

Then open LangSmith, project `finsight`, and you should see the chat call's trace.

## 7. Build the vector index (M3: current)

FinSight's default index is the table `chunks_live`.

1. Parse the PDFs with Docling once (about 1 second per page, ~1 hour on a laptop; the first run also downloads Docling's models). Results are cached in `data/parsed/`; re-running skips finished filings.

```bash
uv run python scripts/parse_docling.py
```

2. Chunk, add LLM context, embed and store, incrementally:

```bash
LANGSMITH_TRACING=false uv run python scripts/ingest.py --loader docling --drop-exhibits --context llm --table chunks_live --incremental
```

The first run writes about 5,000 short LLM contexts (gpt-4o-mini, about $0.70, 10-25 minutes, cached in `data/parsed/contexts/`) and embeds all chunks. Later runs only embed new or changed chunks and print a summary such as `{'num_added': 0, 'num_updated': 0, 'num_skipped': 5012, 'num_deleted': 0}`. Editing or removing a row in `data/manifest.csv` updates or deletes that filing's chunks.

Options: `--max-tokens` (Docling chunk size, default 512), `--context none|template|llm`, `--drop-exhibits` (skip pages after the SIGNATURES page). `--table` and `--rebuild` build experiment tables; `--loader pypdf` rebuilds the M1 baseline (`chunks_baseline`).

Check it:

```bash
docker exec -it finsight-db psql -U finsight -d finsight -c "SELECT company, fiscal_year, count(*) FROM chunks_live GROUP BY 1, 2 ORDER BY 1, 2;"
```

## 8. Ask a question

```bash
uv run python -m finsight.ask "What production rate changes is Boeing forecasting for FY2023?"
```

Uses `chunks_live` with the best setup by default: company/year filters + HyDE for retrieval, gpt-5-mini with the analyst prompt for the answer. Prints the answer with citations like `[Boeing 2022, p. 9]`, each citation's supporting quote marked `verified` or `NOT FOUND in source`, the 5 retrieved chunks and the time taken (~15 s). `--no-structured` gives a plain-text answer.

For a conversation with follow-up questions ("and in FY2021?"):

```bash
uv run python -m finsight.chat                    # prints a session id
uv run python -m finsight.chat --session <id>     # continue later
```

For questions that need several pages, filings or a calculation, use a multi-step mode:

```bash
uv run python -m finsight.ask --graph "What is the FY2022 unadjusted EBITDA % margin for PepsiCo? Use D&A from the cash flow statement."
uv run python -m finsight.ask --agent "..."       # same idea, but the LLM chooses every step
```

| Mode | How it works | Accuracy (39 questions) | Time |
| --- | --- | --- | --- |
| default (pipeline) | router + HyDE, one search, answer | 24-29 correct | ~25 s |
| `--graph` | plan, search, grade (up to 2 retries), calculator, answer, citation check; prints GRAPH STEPS | 34 correct | ~60 s |
| `--agent` | gpt-5-mini decides searches and calculations (max 6 searches); prints AGENT STEPS | 34 correct | ~65 s |

Each follow-up is rewritten into a standalone question (shown as `understood as: ...`); history is stored in the Postgres table `chat_history`. Each run appears in LangSmith (project `finsight`) as a tree: retriever, prompt, model call.

Retrieval options:

| Flag | What it does | Default |
| --- | --- | --- |
| `--no-filters` | Turn off the router; search all filings | Filters on |
| `--no-hyde` | Search with the raw question instead of a hypothetical 10-K passage | HyDE on |
| `--hybrid` | Also run Postgres keyword search and fuse with Reciprocal Rank Fusion | Off (measured worse) |
| `--rerank=minilm` / `--rerank=bge` | Fetch 20 candidates and re-sort them with a local cross-encoder | Off (measured worse) |

For `--hybrid`, create the full-text index once:

```bash
docker exec -it finsight-db psql -U finsight -d finsight -c "CREATE INDEX IF NOT EXISTS chunks_live_fts ON chunks_live USING gin (to_tsvector('english', content));"
```

The default pipeline still refuses a few multi-page calculation questions; `--graph` or `--agent` answers most of them. See the nine hard questions in [EXPERIMENTS.md](EXPERIMENTS.md).

## 9. Run the API and the web app (M8)

Two terminals, with Docker running:

```bash
# terminal 1: API on http://localhost:8000 (interactive docs at /docs)
uv run uvicorn finsight.api.main:app --reload --port 8000

# terminal 2: web UI on http://localhost:5173
cd frontend
npm install        # first time only
npm run dev
```

In the UI: pick **Fast** (one search, ~25 s) or **Accurate** (the M7 graph, ~60 s), ask a question or click an example, watch the steps arrive, click a citation chip to open the chunk with the quote highlighted, ask a follow-up, and rate the answer 👍 / 👎.

Test the API without the UI:

```bash
curl http://localhost:8000/health
curl -N -G http://localhost:8000/ask/stream \
  --data-urlencode "question=What production rate changes is Boeing forecasting for FY2023?" \
  --data-urlencode "mode=accurate"
```

User ratings are stored in LangSmith (feedback key `user_score`) on each answer's trace. List them:

```bash
uv run python eval/pull_feedback.py              # thumbs down from the last 7 days
uv run python eval/pull_feedback.py --all --days 30
```

## 10. Production features (M9): Docker, costs, cache, safety

### Run everything with Docker

Once the index exists in the database volume (step 7), the whole app starts with one command. Stop any local `uvicorn` / `npm run dev` first (same ports).

```bash
docker compose up --build        # first build takes a few minutes
docker compose ps                # db, api, ui: running / healthy
docker compose logs api          # if the API does not start
docker compose down              # stop (data stays in the pgdata volume)
```

UI on http://localhost:5173, API on http://localhost:8000/docs. The API container reads keys from `.env` at run time and reaches the database at `db:5432`. The API image contains only the serving dependencies; `uv sync` locally still installs everything (groups `ingest`, `eval`, `rerank`, `dev` in `pyproject.toml`).

### Cost and latency

Every answer records LLM calls, tokens, cost and seconds per step (shown in the UI under each answer and saved in the Postgres table `request_log`):

```bash
uv run python eval/usage_report.py              # last 7 days: p50 / p95 / max seconds, calls, tokens, cost per mode
uv run python eval/usage_report.py --days 30 --top 10
```

Prices live in `src/finsight/observability/pricing.py` (update them, with the date, when the provider changes them).

### Semantic answer cache

A repeat of an earlier question (same companies and years, similarity ≥ 0.95, same mode) returns the saved answer in ~0.1 s. Only good answers are saved; 👎 removes one; re-indexing `chunks_live` clears the cache.

```bash
uv run python -m finsight.cache.semantic_cache --stats    # what is saved, hits per answer
uv run python -m finsight.cache.semantic_cache --clear    # empty it
uv run python eval/cache_eval.py                          # threshold sweep (how 0.95 was chosen)
```

Skip the cache for one request with `?cache=false` on `/ask/stream` (or `"cache": false` on `POST /ask`).

### Safety checks

```bash
uv run python eval/safety_eval.py --run my_safety     # 16 red-team attacks (~10 min, ~$0.10); needs a new run name each time
uv run python eval/safety_eval.py --golden            # input guard on the 45 real questions: should block 0
```

## 11. Evaluate (M2)

The golden set (`data/eval/golden_set.jsonl`, 45 questions) is already in the repository, so you can run every evaluation right away. Rebuilding it with `build_golden_set.py` needs the FinanceBench question files from step 13.

```bash
uv run python eval/build_golden_set.py                      # 45 questions -> data/eval/golden_set.jsonl
uv run python eval/retrieval_metrics.py --run my_run        # search only, no LLM, ~30 s
uv run python eval/run_answers.py --run my_run              # FinSight answers all 45, ~2 min
uv run python eval/score_answers.py --run my_run            # judge + RAGAS, a few minutes, ~$0.10-0.30
```

`build_golden_set.py` should end with `Evidence page check: 0 problem(s)`. Use `--table` on the retrieval and answer scripts to evaluate another chunks table, `--no-filters` / `--no-hyde` / `--hybrid` / `--rerank minilm|bge` / `--candidates N` on both to evaluate retrieval options (the default is the current best: filters + HyDE), and `--no-ragas` on `score_answers.py` for a quick judge-only score. `retrieval_metrics.py` also prints the router's accuracy and the average seconds per question.

To test prompts or answer models without retrieval noise, re-answer from a run's saved chunks:

```bash
uv run python eval/regenerate_answers.py --from m4_filters_hyde --run my_gen_test              # default: structured, ANSWER_MODEL
uv run python eval/regenerate_answers.py --from m4_filters_hyde --no-structured --prompt v1 --model openai:gpt-4o-mini --run my_control
uv run python eval/score_answers.py --run my_gen_test
```

For structured runs, `score_answers.py` also prints citation accuracy. A full answer run takes ~20 minutes (gpt-5-mini).

To evaluate the multi-step modes (each takes 45-75 minutes for 45 questions):

```bash
uv run python eval/run_answers.py --graph --run my_graph     # also saves steps, searches, calculations, LLM calls
uv run python eval/run_answers.py --agent --run my_agent     # also saves tool calls, searches, calculations
uv run python eval/score_answers.py --run my_graph
```

If one question fails, it is saved as a refusal with a `stopped` reason and the run continues.

Results land in `eval/results/` (ignored by git, so it is empty in a fresh clone; compare your numbers with [EXPERIMENTS.md](EXPERIMENTS.md)):

| File | Contents |
| --- | --- |
| `retrieval_<run>_<time>.csv` | Per question: rank of the first correct page, hits, top 5 pages returned |
| `retrieval_summary.csv` | One line per run: averaged retrieval metrics |
| `answers_<run>.jsonl` | Per question: FinSight's answer and the 5 chunks it saw |
| `scores_<run>_<time>.csv` | Per question: verdict, judge reason, RAGAS scores |
| `answer_summary.csv` | One line per run: correct / partial / wrong / refused, RAGAS averages |

The judge model is set by `JUDGE_MODEL` in `.env` (default `openai:gpt-4.1-mini`).

## 12. Tests and CI (M10)

### Run the checks locally

```bash
uv run ruff check src eval scripts tests     # lint (explicit rules in pyproject.toml)
uv run pytest                                # 47 unit tests, a few seconds, no API key or database needed
cd frontend && npm run build && cd ..        # TypeScript check + production build
uv run python eval/gate.py --run my_gate     # the full eval gate (~30 min, ~$0.35); --skip-scorecard for ~10 min
```

`eval/gate.py` prints a pass/fail table and saves `eval/results/gate_<run>.json`; thresholds live in `eval/gate_baseline.json`.

### On GitHub

| Workflow | Runs on | What it does |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Every push to main and every PR | ruff + pytest (serving + dev dependencies only), frontend build |
| `.github/workflows/eval-gate.yml` | "Run workflow" on the Actions tab (manual by default; a commented-out block in the file runs it on pull requests) | Restores the index into a temporary Postgres, runs `eval/gate.py`, posts the table on the run's Summary page |

`ci.yml` works in your fork as soon as you push. The eval gate needs two things in **your own** repository first, because CI starts from an empty machine with no API key and no index:

1. Your OpenAI key as a repository secret (GitHub CLI: `brew install gh`, `gh auth login`):

```bash
gh secret set OPENAI_API_KEY      # paste the key when asked
```

2. Your index as a release asset. After building the index (step 7), export the `chunks_live` table (~35 MB) and attach it to a release named `ci-index-v1`:

```bash
docker exec finsight-db pg_dump -U finsight -d finsight -t chunks_live --no-owner -Fc -f /tmp/chunks_live.dump
docker cp finsight-db:/tmp/chunks_live.dump ./chunks_live.dump
gh release create ci-index-v1 chunks_live.dump --title "CI index (chunks_live)" --notes "Index used by the eval gate"
rm chunks_live.dump && docker exec finsight-db rm /tmp/chunks_live.dump
```

Then run it from the Actions tab. To run it automatically on pull requests, uncomment the `pull_request` block in the workflow (pull requests from forks never receive secrets, so keep it manual on a public repository). Optionally require the fast checks before merging: Settings → Rules → Rulesets → New branch ruleset → "Require status checks to pass" → "Python (lint + unit tests)" and "Frontend (type check + build)".

### When the index changes

Publish a new version of the index release and point the workflow at it:

```bash
docker exec finsight-db pg_dump -U finsight -d finsight -t chunks_live --no-owner -Fc -f /tmp/chunks_live.dump
docker cp finsight-db:/tmp/chunks_live.dump ./chunks_live.dump
gh release create ci-index-v2 chunks_live.dump --title "CI index (chunks_live) v2" --notes "What changed in the index"
rm chunks_live.dump && docker exec finsight-db rm /tmp/chunks_live.dump
# then set INDEX_RELEASE: ci-index-v2 in .github/workflows/eval-gate.yml
```

### When quality improves

Raise the numbers in `eval/gate_baseline.json` (keep 2-3 questions of room for run-to-run noise) and update its `_reference` line.

## 13. FinanceBench question files (needed for evaluation and the notebooks)

`notebooks/00_explore_financebench.ipynb` shows how the 11 filings were chosen from FinanceBench; `notebooks/01_explore_chunks.ipynb` shows pages, chunks and raw similarity search (needs the index from step 7). To run it, fetch the FinanceBench question files (small, no PDFs):

```bash
mkdir -p ~/datasets && cd ~/datasets
git clone --depth 1 --filter=blob:none --sparse https://github.com/patronus-ai/financebench.git
cd financebench && git sparse-checkout set data
```

Open the notebook in VS Code and select the `.venv` kernel.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ModuleNotFoundError: finsight` | Run `uv sync` from the project root |
| `ValidationError ... openai_api_key` | `.env` is missing, not in the project root, or the key name is misspelled |
| `connection refused` on port 6024 | Docker Desktop is not running, or the container is still starting (`docker compose ps`) |
| `pgvector: NOT INSTALLED` | Run the `CREATE EXTENSION` command from step 4 |
| Download shows `FAILED (... 404)` | The FinanceBench repo path changed; update `BASE_URL` in `scripts/download_filings.py` |
| `git push` asks for a password | Use the GitHub CLI: `brew install gh && gh auth login` |
| Ingest fails with `text fields cannot contain NUL (0x00) bytes` | Make sure `clean_text()` is applied in `ingestion/loaders.py`, then `ingest.py --rebuild` |
| `Table 'chunks_baseline' already exists` | Intended: use `--rebuild` to recreate it |
| `fontTools is required to fully parse...` | Harmless warning; `uv add fonttools` silences it |
| `No module named 'langchain_community.chat_models.vertexai'` when importing RAGAS | `uv add "langchain-community>=0.4,<0.4.2"` (already pinned in `pyproject.toml`) |
| `FileNotFoundError` for `financebench_open_source.jsonl` | Fetch the FinanceBench data files (step 13) |
| Docling notebook cell stops with `KeyboardInterrupt` | The cell was interrupted while converting; run `scripts/parse_docling.py` in the terminal instead |
| Docling warnings (`IProgress not found`, `unauthenticated requests to the HF Hub`, `MatchingPostProcessor ... dropped`) | Harmless |
| `ModuleNotFoundError: langchain_classic` | `uv add langchain-classic` (needed for incremental indexing) |
| `unrecognized arguments: --hybrid` (or another flag) | That script does not declare the flag yet (`parser.add_argument`) |
| `syntax error at or near "::"` in keyword search | Wrap the tsquery cast in a subquery in `keyword.py` (see M4 notes) |
| First `--rerank` run is slow | It downloads the model from Hugging Face once (minilm ~90 MB, bge ~1.1 GB) |
| Running out of disk space | Models live in `~/.cache/huggingface/hub/`; delete unused ones (`uv run hf cache delete`) |
| `Unsupported parameter: 'temperature'` | gpt-5 models reject temperature; create models with `chat_model()` in `generation/models.py` |
| A comparison follow-up ("how does that compare to FY2021?") only uses one year | The router picks one filing; ask the full question with `--graph` or `--agent` |
| `StructuredOutputValidationError ... answerable Field required` (agent) | Use `ToolStrategy(Answer, handle_errors=True)` as `response_format` in `simple_agent.py` |
| Agent answers marked `stopped: too many steps` | The step limit was hit; keep the search budget in `agent/tools.py` and `recursion_limit` 40 |
| UI shows "Connection to the API was lost" right away | Start the API (`uvicorn ... --port 8000`) and check http://localhost:8000/health |
| Browser console shows a CORS error | Open the UI at http://localhost:5173 (the only origin the API allows) |
| `npm: command not found` | Install Node.js 20+ (step 1) |
| 👍 / 👎 not visible in LangSmith | `LANGSMITH_TRACING=true` in `.env`, restart the API; traces appear a few seconds after the answer |
| The same question runs twice in the UI | `EventSource` reconnects unless closed after the answer; keep `es.close()` in `frontend/src/api.ts` |
| `docker compose up` fails with "port is already allocated" | Stop local `uvicorn` (8000) / `npm run dev` (5173), or the old container |
| API container exits: `ModuleNotFoundError` | A module the API imports is in a dependency group; move the package to the main `dependencies` in `pyproject.toml`, `uv lock`, rebuild |
| `docker compose up -d` starts more than the database | Since M9 it starts the whole app; use `docker compose up -d db` for development |
| UI says "I can only answer questions about the annual reports..." for a real question | The input guard misclassified it; run `eval/safety_eval.py --golden` and adjust `safety/guard.py` |
| An old answer keeps coming back | It is cached: `python -m finsight.cache.semantic_cache --clear`, or 👎 it |
| `safety_eval.py` says the results file already exists | Use a new `--run` name (or `--overwrite`) |
| Eval gate stops at "Add the OPENAI_API_KEY repository secret" | `gh secret set OPENAI_API_KEY` (or Settings → Secrets and variables → Actions) |
| Eval gate: `release not found` when downloading the index | Create the release (step 12) with tag `ci-index-v1` and file `chunks_live.dump`, or update `INDEX_RELEASE` |
| `zsh: command not found: gh` / `gh auth login` prompt | `brew install gh`, then `gh auth login`; answer its questions in its own prompts |
| Docker freezes or will not open | Check `df -h /`: keep ~15 GB free (clear npm, uv, Yarn caches; `docker builder prune`). Never "Clean / Purge data": it deletes the database volume |
| `gate.py` shows no progress for minutes | Normal for long steps; output streams live since `PYTHONUNBUFFERED=1` was added |
| ruff reports many style rules after an upgrade | Rules are pinned in `[tool.ruff.lint]` in `pyproject.toml`; check that section is present |
| psql prints `\d: extra argument ... ignored` | Run backslash commands and SQL separately, or use `psql -c "..."` |
