"""FinSight HTTP API.

Endpoints: /health, /filings, POST /ask, GET /ask/stream (SSE), POST /feedback
(?cache=false on /ask/stream, or "cache": false on POST /ask, skips the semantic cache)

Run:  uv run uvicorn finsight.api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

import json
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langsmith import Client
from pydantic import BaseModel, Field

from finsight.cache.semantic_cache import evict
from finsight.retrieval.filters import available_filings
from finsight.service import ask, ask_stream

app = FastAPI(title="FinSight API", version="0.8.0")

# The React dev server (Part B) runs on another port; the browser blocks it unless we allow it here
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: Literal["fast", "accurate"] = "fast"
    session_id: str | None = None
    cache: bool = True                        # False: always run the pipeline / graph (M9)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/filings")
def filings():
    """Companies and fiscal years the index covers (for the UI's examples and header)."""
    return available_filings()


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    """Run to the end and return one JSON answer."""
    return ask(req.question, req.mode, req.session_id, req.cache)


def _sse(events):
    """Format events as Server-Sent Events: 'event: <name>' + 'data: <json>' + blank line."""
    try:
        for e in events:
            yield f"event: {e['event']}\ndata: {json.dumps(e)}\n\n"
    except Exception as exc:  # send the error to the browser instead of silently closing the stream
        yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': str(exc)})}\n\n"


@app.get("/ask/stream")
def ask_stream_endpoint(question: str = Query(min_length=3, max_length=1000),
                        mode: Literal["fast", "accurate"] = "fast",
                        session_id: str | None = None,
                        cache: bool = True):
    """Live progress events, then the answer. GET so the browser's EventSource can use it."""
    return StreamingResponse(_sse(ask_stream(question, mode, session_id, cache)),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class FeedbackRequest(BaseModel):
    run_id: UUID
    score: Literal[0, 1]                      # 1 = thumbs up, 0 = thumbs down
    comment: str | None = Field(default=None, max_length=2000)


@lru_cache
def _langsmith() -> Client:
    return Client()                           # reads LANGSMITH_API_KEY from .env


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    """Attach a user's rating to the LangSmith trace of that answer (same run_id as the answer event)."""
    fb = _langsmith().create_feedback(run_id=req.run_id, key="user_score",
                                      score=req.score, comment=req.comment)
    evicted = evict(str(req.run_id)) if req.score == 0 else 0   # never serve a 👎 answer from the cache again
    return {"status": "ok", "feedback_id": str(fb.id), "evicted_from_cache": evicted}
