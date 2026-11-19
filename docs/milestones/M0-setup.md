# M0: Setup and data

Completed: 2026-11-07

**Goal:** a runnable repo, a vector database, working model access, and real documents on disk, before writing any RAG code.

**Outcome:** all three smoke-test checks pass, and 11 10-K filings with 39 ground-truth questions are selected and downloadable.

## What was built

| Piece | File | What it does |
| --- | --- | --- |
| Project scaffold | `pyproject.toml`, `src/finsight/` | uv-managed Python 3.12 package with one subpackage per RAG layer (ingestion, indexing, retrieval, generation, agent, api) |
| Database | `docker-compose.yml` | Postgres 16 + pgvector on port 6024, data kept in a named volume, with a health check |
| Config | `src/finsight/config.py`, `.env.example` | Typed settings (pydantic-settings) loaded from `.env`; LangChain and LangSmith read their keys from the environment |
| Smoke test | `scripts/smoke_test.py` | Checks the chat model, embeddings and database in one run |
| Dataset exploration | `notebooks/00_explore_financebench.ipynb` | Loads FinanceBench, ranks companies by question count, writes the manifest |
| Manifest | `data/manifest.csv` | The 11 filings this project uses, with company, ticker, fiscal year, doc type and sector |
| Downloader | `scripts/download_filings.py` | Fetches the PDFs listed in the manifest; skips existing files; validates each is a real PDF |

## Steps, in order

1. Created the repo: `uv init --package --python 3.12 finsight` (uv also runs `git init`).
2. Created the folder layout and an `__init__.py` in each subpackage.
3. Added dependencies: `langchain`, `langchain-core`, `langchain-openai`, `langchain-community`, `langchain-text-splitters`, `langchain-postgres`, `psycopg[binary]`, `pypdf`, `python-dotenv`, `pydantic-settings`, `pandas`; dev: `pytest`, `ruff`, `ipykernel`.
4. Started Postgres + pgvector in Docker and ran a first vector query by hand: `SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector;` (cosine distance).
5. Wrote `config.py` and `.env`, then the smoke test.
6. Sparse-cloned FinanceBench (data files only) to `~/datasets/financebench`.
7. Explored it in a notebook, picked 6 companies, saved `data/manifest.csv`.
8. Wrote the downloader and fetched the PDFs into `data/raw/`.
9. Committed and pushed to GitHub.

## Smoke test results

| Check | Result |
| --- | --- |
| Chat model `gpt-4o-mini` | Replied "ok"; 12 input + 1 output tokens |
| Embeddings `text-embedding-3-small` | 1536 dimensions |
| Related sentences (Apple sales vs iPhone revenue) | cosine similarity 0.602 |
| Unrelated sentences (Apple sales vs a recipe) | cosine similarity -0.006 |
| Postgres | 16.15 |
| pgvector | 0.8.7 |
| Cosine distance test `[1,2,3]` vs `[1,2,4]` | 0.0085 |

## Concepts learned

- **Embedding:** a list of numbers (here 1536) that represents the meaning of a text. Texts with similar meaning get vectors pointing in similar directions.
- **Cosine similarity / distance:** how aligned two vectors are. Similarity near 1 means very similar, near 0 means unrelated. pgvector's `<=>` operator returns cosine *distance* (1 minus similarity), so smaller is closer.
- **Vector database:** a database that stores embeddings and finds the nearest ones to a query vector. pgvector adds this to ordinary Postgres, so vectors, text and metadata live in one place.
- **Golden (evaluation) set:** questions with known correct answers and the page where each answer appears. It lets every later change be measured instead of guessed. FinanceBench provides one for 10-K filings.
- **Manifest / metadata contract:** deciding the metadata fields (company, ticker, fiscal_year, doc_type, sector) up front so ingestion (M1), evaluation (M2) and filtering (M4) all agree.

## Dataset selection

From the FinanceBench open-source sample (150 questions), restricted to 10-K filings, the 6 companies below were chosen because they have the most questions per report, span 5 sectors (so retrieval must tell companies apart), and mostly have two fiscal years (so it must tell years apart). Boeing and 3M are both industrials, a deliberate hard case.

| Company | Reports | Questions | Fiscal years |
| --- | --- | --- | --- |
| AMD | 2 | 8 | 2015, 2022 |
| Boeing | 2 | 8 | 2018, 2022 |
| American Express | 1 | 7 | 2022 |
| PepsiCo | 2 | 6 | 2021, 2022 |
| 3M | 2 | 5 | 2018, 2022 |
| Verizon | 2 | 5 | 2021, 2022 |
| **Total** | **11** | **39** | |

## Gotchas noted for later

- FinanceBench evidence page numbers are **zero-indexed**. PyPDFLoader's `page` metadata is also zero-based, but people read pages starting at 1. Matters when scoring retrieval in M2.
- Fiscal years are company-specific labels (for example, a fiscal year may end in September), so `fiscal_year` is kept exactly as FinanceBench labels it.
- FinanceBench is licensed for noncommercial use, so PDFs are downloaded by script rather than committed.
- `gpt-4o-mini` is a legacy (but available and cheap) model; GPT-5-family models are reasoning models that bill hidden thinking tokens. To be compared once the M2 eval harness exists.

## Next

M1: build the naive RAG baseline (load with PyPDF, recursive chunking, embed into pgvector, retrieve top-k, answer with page citations), and record where it fails.
