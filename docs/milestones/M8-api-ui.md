# M8: API, web UI and user feedback

Completed: 2026-11-17 · Branch: `m8-api-ui`

**Goal:** turn FinSight from terminal scripts into an app: a web API anyone can call, a browser UI that shows the answer being built, clickable evidence for every citation, and user ratings that flow back into evaluation.

**Outcome:** a FastAPI backend with live progress over Server-Sent Events, a React + TypeScript UI with a **Fast / Accurate** toggle (M6 pipeline / M7 graph), follow-up conversations, a sources panel that highlights each quoted line in its chunk, and 👍 / 👎 feedback stored on the exact LangSmith trace of each answer. No evaluation runs in this milestone: answer quality is unchanged from M7 (pipeline 24-29 / 39 correct, graph 34 / 39).

## How it fits together

```text
Browser (React, localhost:5173)
  question + mode (fast / accurate) + session_id
     |  GET /ask/stream  (EventSource)
     v
FastAPI (localhost:8000)  ->  service.ask_stream()        one entry point for every interface
                                 |-- condense follow-up with Postgres chat history (M6)
                                 |-- fast:     M6 pipeline  (router + HyDE + 1 search + structured answer)
                                 |-- accurate: M7 graph, streamed node by node (stream_mode="updates")
     <-- event: status  {"step": "retrieve", "message": "search: PepsiCo 2022 - 'operating income'"}
     <-- event: status  ...
     <-- event: answer  {answer, citations, sources, steps, session_id, run_id, seconds}
  👍 / 👎 + comment
     |  POST /feedback {run_id, score, comment}
     v
LangSmith: feedback "user_score" on the trace with that run_id  ->  eval/pull_feedback.py lists the 👎 answers
```

## API

| Endpoint | What it does |
| --- | --- |
| `GET /health` | Liveness check |
| `GET /filings` | Companies and fiscal years in the index |
| `POST /ask` | `{question, mode, session_id?}` → the full answer as one JSON object |
| `GET /ask/stream` | Same inputs as query parameters; streams `status` events, then one `answer` event (or `error`) |
| `POST /feedback` | `{run_id, score: 0 or 1, comment?}` → stored as LangSmith feedback `user_score` |

Interactive docs are generated at `http://localhost:8000/docs`.

The `answer` event: `answer` (text with `[Company Year, p. N]` labels), `citations` (block number, label, quote, `verified`), `sources` (every chunk read, numbered, with full text), `steps` (graph log; empty in fast mode), `mode`, `question` (after follow-up rewriting), `session_id`, `run_id` (the LangSmith trace id), `seconds`.

## UI

- Question box with example questions and a **Fast / Accurate** toggle.
- While working: a live list of steps (plan, each search, grade, calculator, check) with a spinner.
- Answer card: citation labels as clickable chips; an Evidence list with each quote marked `verified` or `unverified`; time and number of sources read; "how this was answered" (graph steps) in accurate mode.
- Sources panel: every chunk the system read; clicking a chip or quote opens the chunk with the quote highlighted.
- Follow-ups in the same session ("Understood as: ..." shown when the question was rewritten); "New conversation" resets it.
- 👍 / 👎 under each answer; 👎 asks "What was wrong?".

## What we discovered

1. **A service layer keeps interfaces thin.** `service.ask_stream()` is the only place that knows about modes, sessions and run ids; the API only validates input and formats events, and the UI only renders them.
2. **Stream progress, not tokens, for checked answers.** The final text exists only after citations are verified, so token streaming would show unverified text. For a ~60 s accurate answer, showing each step is what keeps the wait understandable.
3. **LangGraph streams for free.** `graph.stream(..., stream_mode="updates")` yields each node's changes as it finishes; the same graph powers the eval runs and the live UI.
4. **SSE is simpler than WebSockets here.** One-way server → browser, plain HTTP, automatic reconnect (which must be stopped with `close()` after the answer, or the browser re-asks the question).
5. **Our own run id makes feedback precise.** Passing `run_id` in the config makes the LangSmith trace id known before the answer finishes, so a rating lands on the exact trace with every intermediate step.
6. **Unverified quotes need to be visible, not hidden.** In the Boeing example the model added one word ("we") to a quote; the UI shows it as `unverified`, and the sources panel shows the chunk without a highlight so the user can check it.
7. **First request after start-up is slow** (~49 s in fast mode in the first test): connections and models are set up lazily. Tracking latency and cost per request is M9.

## Files added or changed

| File | Role |
| --- | --- |
| `src/finsight/service.py` | `ask_stream()` / `ask()`: one entry point; sessions + follow-up rewriting, fast pipeline or streamed graph, LangSmith `run_id`, answer event with sources |
| `src/finsight/api/main.py` | FastAPI app: `/health`, `/filings`, `POST /ask`, `GET /ask/stream` (SSE), `POST /feedback`; CORS for the dev UI |
| `eval/pull_feedback.py` | Lists rated answers from LangSmith (👎 by default, `--all`, `--days N`) |
| `frontend/` | Vite + React + TypeScript app: `api.ts` (EventSource stream, feedback), `types.ts`, `App.tsx`, `components/` (StepList, AnswerCard, SourcePanel, Feedback), `index.css` |
| `pyproject.toml`, `uv.lock` | `fastapi`, `uvicorn[standard]` |

## Concepts learned

- **REST API with FastAPI:** typed request models (Pydantic), automatic validation and OpenAPI docs.
- **Server-Sent Events:** `text/event-stream`, `event:` + `data:` lines, `StreamingResponse` from a generator, `EventSource` in the browser.
- **CORS:** why a browser blocks calls from `localhost:5173` to `localhost:8000` unless the API allows that origin.
- **Streaming agent state:** LangGraph `stream_mode="updates"`.
- **Sessions:** a `session_id` per conversation, history in Postgres, so the API itself stays stateless.
- **Human feedback loop:** user ratings on traces (`create_feedback`), filtered back out (`list_runs` with a feedback filter) to find new failure cases for the golden set.

## Gotchas

- `EventSource` only does GET, so the stream endpoint takes query parameters; `POST /ask` exists for clients that want one JSON response.
- The browser's `error` event fires both for our server's `error` events (with data) and for lost connections (no data); `api.ts` handles both.
- Without `es.close()` after the answer, `EventSource` reconnects and asks the same question again.
- The API must be restarted (or run with `--reload`) to pick up backend changes; CORS errors in the browser console mean the UI is not on port 5173.
- `sources[].page` is the 0-based stored page; always display `label` (printed page).
- LangSmith ingests traces a few seconds after each answer; `pull_feedback.py` may show nothing for ~30 s. Feedback needs `LANGSMITH_TRACING=true`.
- `GET /ask/stream` with a very long question can exceed URL limits (we cap questions at 1000 characters).

## Next

M9: production touches: semantic cache for repeated questions, latency and cost tracking per request, prompt-injection tests, and one `docker compose up` for database + API + UI.
