# CLAUDE.md

Instructions for Claude Code in this repository. The shared agent guidance lives in AGENTS.md and is imported below, so both files stay in sync.

@AGENTS.md

## Claude-specific notes

- Before a multi-step change, read the relevant milestone note in `docs/milestones/` and the matching rows in `docs/DECISIONS.md`.
- Prefer small, verified steps: edit, run `uv run ruff check src eval scripts tests` and `uv run pytest`, then summarise what changed.
- Ask before any command that spends OpenAI credits in bulk or deletes data (see "Do not" in AGENTS.md).
