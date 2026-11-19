# M10: Tests, CI and the evaluation gate

Completed: 2026-11-18 · Branch: `m10-ci`

**Goal:** make quality automatic. Every pull request is checked by unit tests and a linter; every pull request that touches the RAG code also runs the real evaluation (guard, safety suite, scorecard) on a fresh machine and fails if quality drops. Then finish the repo for readers: README, licence.

**Outcome:** 47 unit tests and lint on every PR (~2 min, free), and an **eval gate** that rebuilds the database from a release asset and checks 6 thresholds in ~30 min for ~$0.35. First CI run (`ci_1`): **all 6 checks passed** (27/39 correct, 3 wrong, 100% refusals, 97.4% citations verified, 16/16 attacks, 0/45 real questions blocked). Writing the tests and running the gate found **4 bugs**: two in the app, two in our own evaluation.

## The two workflows

```text
.github/workflows/ci.yml          every push to main and every PR, no secrets, ~2 min
  Python    uv sync (serving + dev only) -> ruff check -> pytest
  Frontend  npm ci -> npm run build (TypeScript check + Vite build)

.github/workflows/eval-gate.yml   PRs that change src/, eval/, pyproject.toml, uv.lock, data/manifest.csv,
                                   data/eval/ or the workflow; or "Run workflow" on the Actions tab
  Postgres + pgvector service container (port 6024)
  -> download chunks_live.dump from the GitHub release ci-index-v1 (35 MB, 5,013 chunks)
  -> restore it with the same pgvector image (pg_restore version = server version)
  -> eval/gate.py --run ci_<run number>  (OPENAI_API_KEY from a repository secret, LangSmith tracing off)
  -> results table on the run's Summary page, results files as a downloadable artifact
```

## The gate (`eval/gate.py`)

| Check | How | Threshold (`eval/gate_baseline.json`) | Why this number |
| --- | --- | --- | --- |
| Real questions blocked by the guard | `safety_eval.py --golden` | 0 | Any blocked real question is a bug |
| Attacks handled | `safety_eval.py` (16 attacks) | ≥ 15 | Final M9 run was 16/16; one-run noise allowed |
| Correct answers (fast mode) | `run_answers.py` + `score_answers.py --no-ragas` | ≥ 21 / 39 | Reference 25; runs vary by ±2-3 |
| Wrong answers | same | ≤ 9 / 39 | Reference 6 |
| Unanswerable questions declined | same | 100% | Never answer what is not in the filings |
| Citations verified | from the answers file | ≥ 90% | Reference 95% |

RAGAS is skipped in the gate (judge only): faster, cheaper, and its faithfulness score was the noisiest metric in M7. Thresholds are absolute numbers with room for run-to-run noise; raise them as the system improves.

## Gate runs

| Run | Where | Guard | Safety | Correct | Wrong | Refusals | Citations | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gate_local` | Mac | 0 | 16/16 | 27/39 | 3 | 83% | 93.8% | **Failed**: scorer bug (below) |
| `gate_local` (re-scored after the fix) | Mac | — | — | 28/39 | 3 | 100% | 93.8% | Passes |
| `ci_1` | GitHub Actions | 0 | 16/16 | 27/39 | 3 | 100% | 97.4% | **Passed**, 29 min 28 s |

## Bugs found

| Bug | Found by | Fix |
| --- | --- | --- |
| The calculator accepted `9 ** 9 ** 9`: a model (or an injected prompt) could freeze the agent | Writing the calculator tests | Exponents capped at 100; booleans are not numbers |
| The fabrication check matched numbers as text: an invented "151" counted as grounded because "11,512" contains it | Writing the safety tests | Whole-number comparison; check moved to `src/finsight/safety/checks.py` |
| An unanswerable question declined in other words ("no dividend policy for 2030 is stated") was labelled "refused" by the judge and counted as a failure | The first local gate run (refusals 83%) | `score_answers.py`: for unanswerable questions, a judge "refused" counts as correct |
| `gate.py` showed no progress for minutes | Running the gate | Child scripts run with `PYTHONUNBUFFERED=1` |

## What we discovered

1. **Tests find bugs that evaluations don't.** The scorecard never sends `9 ** 9 ** 9`, and no golden answer happens to contain a number hidden inside another; unit tests aim straight at edge cases.
2. **A gate is only as good as its scorer.** Its first run failed on a correct answer. Like the judge in M2 and the safety checks in M9, the measuring code needed the same scrutiny as the product.
3. **Separate cheap checks from expensive ones.** Lint and unit tests run on every change for free; the LLM evaluation runs only when RAG code changes, and a new push cancels the old run.
4. **CI needs its data, not just its code.** Rebuilding the index in CI would mean an hour of parsing and re-embedding; a 35 MB table export attached to a release restores in seconds. When the index changes, upload `ci-index-v2` and bump one line.
5. **Pin your tools' behaviour.** A newer ruff turned on many style rules by default (41 findings); an explicit rule set makes lint results independent of the installed version.
6. **Operations are part of the project.** Docker froze with 5.8 GB of free disk; clearing package caches (npm, uv, Yarn) brought it to 24 GB. Keep ~15 GB free when building images.

## Files added or changed

| File | Role |
| --- | --- |
| `tests/conftest.py`, `tests/test_*.py` | 47 unit tests: citations, calculator, cache keys, safety checks, pricing, RRF; dummy settings so no `.env` is needed |
| `src/finsight/safety/checks.py` | `ungrounded_numbers()` (moved from the safety suite, whole-number matching) |
| `src/finsight/agent/tools.py` | Calculator: exponent cap, booleans rejected |
| `eval/gate.py`, `eval/gate_baseline.json` | The gate and its thresholds |
| `eval/score_answers.py` | Unanswerable + judge "refused" = correct |
| `eval/safety_eval.py` | Uses `safety.checks`; refuses to overwrite a run (`--overwrite`) |
| `.github/workflows/ci.yml`, `.github/workflows/eval-gate.yml` | The two workflows |
| `pyproject.toml` | pytest and ruff settings (explicit lint rules) |
| `.gitignore` | `*.dump` |
| `README.md`, `LICENSE` | Final README (pitch, demo, architecture diagram, results, lessons), MIT licence |

## Concepts learned

- **Unit tests vs evaluations:** deterministic code gets exact tests; model behaviour gets scored samples with thresholds.
- **Continuous integration:** workflows, jobs, triggers (`paths`, `workflow_dispatch`), caching, service containers, secrets, artifacts, job summaries, concurrency groups.
- **Evaluation gates:** regression thresholds with noise margins, cost-aware triggering, failing on any check.
- **Test fixtures** and isolating tests from secrets and networks.
- **Branch protection (rulesets):** required status checks before merging.

## Gotchas

- The gate needs the repository secret `OPENAI_API_KEY`; without it the job stops at the first step with a message.
- Pull requests from forks don't receive secrets, so the gate can't run there.
- The release tag and file name must match the workflow: `ci-index-v1`, `chunks_live.dump`.
- `gh auth login` asks questions interactively: answer in its prompts, not as shell commands (typing `HTTPS` at the prompt line created an empty file named `HTTPS`).
- Required status checks: require only the two fast checks for every PR; the eval gate doesn't run on docs-only PRs, so making it required would leave those PRs waiting.
- Gate costs add up: ~$0.35 per run; pushes to a PR cancel the previous run.

## Next

The plan is complete. Possible extensions: a public deploy (managed Postgres + a container host), a larger golden set, tracking the gate's numbers over time, and trying newer models through the same gate.
