# FinSight web UI

React + TypeScript (Vite) front end for the FinSight API. Built in M8; see [docs/milestones/M8-api-ui.md](../docs/milestones/M8-api-ui.md).

```bash
npm install
npm run dev        # http://localhost:5173 (expects the API on http://localhost:8000)
```

Set `VITE_API_URL` to point at another API address.

| File | Role |
| --- | --- |
| `src/api.ts` | `getFilings()`, `streamAsk()` (EventSource over `GET /ask/stream`), `sendFeedback()` |
| `src/types.ts` | Shapes of the API events |
| `src/App.tsx` | Conversation state, question box, Fast / Accurate toggle, follow-ups |
| `src/components/StepList.tsx` | Live steps while working; "how this was answered" afterwards |
| `src/components/AnswerCard.tsx` | Answer with clickable citation chips, evidence list, feedback |
| `src/components/SourcePanel.tsx` | Chunks the answer was based on, with the quote highlighted |
| `src/components/Feedback.tsx` | 👍 / 👎 + comment, sent to LangSmith through the API |
