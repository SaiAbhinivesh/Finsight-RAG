# Quick tour: FinSight running in about 20 minutes

The full build indexes 11 filings (about an hour of PDF parsing). This tour indexes just **2 filings, AMD 2022 and Verizon 2022**, so you can see the whole system working (fast and accurate answers, verified citations, the web UI) in one sitting, for about $0.20 of OpenAI usage. Everything you build here carries over to the full build.

## What you need

| Tool | Check | Install |
| --- | --- | --- |
| Docker Desktop (running) | `docker --version` | [docker.com](https://www.docker.com/products/docker-desktop/) |
| uv | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js 20+ (only for the UI without Docker) | `node --version` | [nodejs.org](https://nodejs.org/) |
| An OpenAI API key | | [platform.openai.com](https://platform.openai.com/) |
| ~5 GB free disk | `df -h` | Docker needs room |

## 1. Clone and configure (2 min)

```bash
git clone https://github.com/SaiAbhinivesh/finsight-rag.git finsight && cd finsight
cp .env.example .env
```

Edit `.env`: paste your key after `OPENAI_API_KEY=`, set `LANGSMITH_TRACING=false` (unless you have a LangSmith key), and **uncomment the last line** so only the two tour filings are used:

```bash
FINSIGHT_MANIFEST=data/manifest_quicktour.csv
```

## 2. Database and dependencies (3 min)

```bash
docker compose up -d db                       # Postgres + pgvector on localhost:6024
docker exec -it finsight-db psql -U finsight -d finsight -c "CREATE EXTENSION IF NOT EXISTS vector;"
uv sync                                       # Python 3.12 + all packages (first time takes a few minutes)
uv run python scripts/smoke_test.py           # model, embeddings and database all reachable
```

## 3. Build the index for 2 filings (10 min, ~$0.15)

```bash
uv run python scripts/download_filings.py     # 2 PDFs into data/raw/
uv run python scripts/parse_docling.py        # Docling layout + table parsing, ~1 s per page (~245 pages)
LANGSMITH_TRACING=false uv run python scripts/ingest.py --loader docling --drop-exhibits --context llm --table chunks_live --incremental
```

What happens: Docling turns each PDF into structured JSON (cached in `data/parsed/`), the chunker cuts it into 512-token pieces, gpt-4o-mini writes one sentence of context per chunk ("This chunk is from AMD's FY2022 10-K, consolidated balance sheet..."), and each chunk is embedded into the `chunks_live` table. The first Docling run downloads its layout models once.

## 4. Ask questions in the terminal (5 min)

```bash
# fast mode: router -> HyDE -> one search -> structured answer with verified quotes (~25 s)
uv run python -m finsight.ask "Did AMD report customer concentration in FY22?"

# accurate mode: plan -> search each fact -> grade (retry) -> calculator -> answer (~60 s)
uv run python -m finsight.ask --graph "Does Verizon have a reasonably healthy liquidity profile based on its quick ratio for FY 2022?"
uv run python -m finsight.ask --graph "Does AMD have a reasonably healthy liquidity profile based on its quick ratio for FY22?"

# not in the filings: should be declined
uv run python -m finsight.ask "What is Verizon's dividend policy for 2030?"

# a conversation with follow-ups
uv run python -m finsight.chat
```

What to expect (exact wording varies between runs):

| Question | Expected answer |
| --- | --- |
| AMD customer concentration | Yes: one customer was about 16% of FY2022 net revenue (and ~18% of accounts receivable), with page citations marked "verified" |
| Verizon quick ratio (accurate) | About 0.54, so not a healthy liquidity profile by this measure; the GRAPH STEPS show the balance-sheet searches and the calculator |
| AMD quick ratio (accurate) | About 1.57, a reasonably healthy profile |
| Verizon 2030 dividend policy | Declined: no such policy is stated in the filings |

Fast mode may answer the quick-ratio questions only partly ("current liabilities not in the retrieved chunks"); that is exactly the gap accurate mode closes, and the comparison is the core lesson of [M7](milestones/M7-agents.md).

## 5. The web app (5 min)

Either everything in Docker:

```bash
docker compose up --build                     # UI http://localhost:5173 · API http://localhost:8000/docs
```

or the API and UI locally, in two terminals:

```bash
uv run uvicorn finsight.api.main:app --reload --port 8000
cd frontend && npm install && npm run dev     # http://localhost:5173
```

Pick Fast or Accurate, click an example or type a question, watch the steps appear, click a citation chip to open the source chunk with the quote highlighted, ask a follow-up, and try an off-topic question to see the input guard decline it. Each answer shows its LLM calls, tokens and cost. Compare with the screenshots in the [README](../README.md#demo).

## 6. Run the tests (1 min)

```bash
uv run pytest                                 # 47 unit tests, no API calls
uv run ruff check src eval scripts tests
```

## Going further

**Full build (all 11 filings):** remove (or comment out) the `FINSIGHT_MANIFEST` line in `.env`, then run the same three commands from step 3. Downloading and parsing skip the files you already have, and incremental indexing adds only the new filings. Restart the API or `docker compose up --build` afterwards.

**Evaluation** (retrieval metrics, answer scorecard, safety suite, the eval gate) needs the full build, because the 45 test questions cover all 11 filings: see [GETTING_STARTED.md](GETTING_STARTED.md), steps 10-12, and compare your numbers with [EXPERIMENTS.md](EXPERIMENTS.md).

**Understand what you just ran:** [ARCHITECTURE.md](ARCHITECTURE.md) follows one question through the code; the [build guide](BUILD_GUIDE.md) and [milestone notes](milestones/) explain how each piece was built and why.

## If something goes wrong

| Problem | Fix |
| --- | --- |
| `connection refused` on port 6024 | Docker Desktop is not running, or the database is still starting: `docker compose ps` |
| `ValidationError ... openai_api_key` | `.env` is missing or the key line is empty |
| Answers mention 3M, Boeing or other companies, or questions about them get "could not find" | Expected in the tour: only AMD 2022 and Verizon 2022 are indexed |
| `parse_docling.py` seems stuck on the first file | It is downloading Docling's models (once); parsing itself is ~1 s per page |
| Docker freezes or won't start | Free disk space (keep ~15 GB free); never use Docker Desktop's "Clean / Purge data" (it deletes the database) |
