# FinSight documentation

Everything you need to understand, run, rebuild or extend FinSight. Numbers in these docs come from the reference build; your runs will differ by a few questions.

## Start here

| If you want to... | Read |
| --- | --- |
| See it working in ~20 minutes (2 filings) | [QUICK_TOUR.md](QUICK_TOUR.md) |
| Run the full project from a fresh clone | [GETTING_STARTED.md](GETTING_STARTED.md) |
| Build it yourself, milestone by milestone | [BUILD_GUIDE.md](BUILD_GUIDE.md), then each milestone's notes |
| Understand how a request flows through the code | [ARCHITECTURE.md](ARCHITECTURE.md) |
| See what each experiment changed and the results to expect | [EXPERIMENTS.md](EXPERIMENTS.md) |
| Know why each technical choice was made | [DECISIONS.md](DECISIONS.md) |
| Revise RAG concepts quickly | [GLOSSARY.md](GLOSSARY.md) |
| Prepare for interviews | [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) |
| Extend the project or pick a contribution | [IDEAS.md](IDEAS.md) |

## Milestone notes

Each note covers the goal, how it was built, the results, what was learned, the files involved and the gotchas.

| Milestone | Notes |
| --- | --- |
| M0: Setup and data | [M0-setup.md](milestones/M0-setup.md) |
| M1: Naive RAG baseline | [M1-naive-rag.md](milestones/M1-naive-rag.md) |
| M2: Evaluation harness | [M2-evaluation.md](milestones/M2-evaluation.md) |
| M3: Better ingestion | [M3-ingestion.md](milestones/M3-ingestion.md) |
| M4: Better retrieval | [M4-retrieval.md](milestones/M4-retrieval.md) |
| M5: Reranking | [M5-reranking.md](milestones/M5-reranking.md) |
| M6: Grounded generation | [M6-generation.md](milestones/M6-generation.md) |
| M7: Agentic RAG | [M7-agents.md](milestones/M7-agents.md) |
| M8: API, web UI and feedback | [M8-api-ui.md](milestones/M8-api-ui.md) |
| M9: Production touches | [M9-production.md](milestones/M9-production.md) |
| M10: Tests, CI and the evaluation gate | [M10-ci.md](milestones/M10-ci.md) |

## Keeping the docs current

If you change the pipeline, keep the same habit the project was built with: run the evaluation, then update the milestone note (or add a new one), add the run to [EXPERIMENTS.md](EXPERIMENTS.md), record the decision in [DECISIONS.md](DECISIONS.md), and adjust [GETTING_STARTED.md](GETTING_STARTED.md) if a command changed.
