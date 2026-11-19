"""One entry point for every interface (CLI, API, UI): ask a question in 'fast' or 'accurate' mode."""

import time
import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Literal

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from finsight.agent.graph import build_graph
from finsight.cache import semantic_cache
from finsight.generation.chain import build_rag_chain, source_label
from finsight.generation.conversation import condense, open_history
from finsight.observability.request_log import log_request
from finsight.observability.usage import UsageTracker
from finsight.safety.guard import blocked_message, check_input, leaked

Mode = Literal["fast", "accurate"]


@lru_cache
def _pipeline():
    return build_rag_chain()   # fast: router + HyDE + one search + structured answer (M6)


@lru_cache
def _graph():
    return build_graph()       # accurate: plan -> retrieve -> grade -> calculate -> generate -> check (M7)


def _source(doc: Document, n: int) -> dict:
    m = doc.metadata
    return {"n": n, "label": source_label(doc), "company": m.get("company"),
            "fiscal_year": m.get("fiscal_year"), "page": m.get("page"), "text": doc.page_content}


def ask_stream(question: str, mode: Mode = "fast", session_id: str | None = None,
               use_cache: bool = True) -> Iterator[dict]:
    """Yield {'event': 'status', ...} while working, then one {'event': 'answer', ...}."""
    start = time.perf_counter()
    run_id = str(uuid.uuid4())   # LangSmith run id: thumbs up/down attaches to it (M8)
    tracker = UsageTracker()     # tokens, cost and time of every LLM call in this request (M9)
    config = {"run_id": run_id, "run_name": f"finsight:{mode}", "tags": ["api", mode], "callbacks": [tracker]}
    timings: dict[str, float] = {}

    # Follow-ups: every question belongs to a session; condense() is skipped when there is no history yet
    history, session_id = open_history(session_id)
    t = time.perf_counter()
    standalone = condense(question, history.messages,
                          config={"callbacks": [tracker], "run_name": "finsight:condense"})
    if standalone != question:
        timings["rewrite"] = round(time.perf_counter() - t, 2)
        yield {"event": "status", "step": "rewrite", "message": f"Understood as: {standalone}"}

    # Input guard (M9 Part C): off-topic questions and prompt attacks never reach retrieval or the answer model
    t = time.perf_counter()
    decision = check_input(standalone, config={"callbacks": [tracker], "run_name": "finsight:guard"})
    timings["guard"] = round(time.perf_counter() - t, 2)
    if decision.category != "filings_question":
        yield {"event": "status", "step": "guard", "message": "This request is outside what FinSight answers"}
        message = blocked_message()
        history.add_messages([HumanMessage(content=question), AIMessage(content=message)])
        event = {"event": "answer", "answer": message, "citations": [], "sources": [], "steps": [],
                 "mode": mode, "question": standalone, "session_id": session_id, "run_id": run_id,
                 "seconds": round(time.perf_counter() - start, 1), "usage": tracker.summary(),
                 "timings": timings, "cached": False,
                 "blocked": {"category": decision.category, "reason": decision.reason}}
        log_request(event)
        yield event
        return

    # Semantic cache (M9): same companies + years AND near-identical meaning -> reuse a saved answer
    if use_cache:
        t = time.perf_counter()
        hit = semantic_cache.lookup(standalone, mode)
        timings["cache_lookup"] = round(time.perf_counter() - t, 2)
        if hit:
            yield {"event": "status", "step": "cache",
                   "message": f"Found a saved answer to: {hit['matched_question']}"}
            saved = hit["answer"]
            history.add_messages([HumanMessage(content=question), AIMessage(content=saved["answer"])])
            event = {
                **saved,                                   # answer, citations, sources, steps, run_id (original)
                "event": "answer",
                "question": standalone,
                "session_id": session_id,
                "seconds": round(time.perf_counter() - start, 1),
                "usage": tracker.summary(),                # only the follow-up rewrite, if any
                "timings": timings,
                "cached": True,
                "cache": {"matched_question": hit["matched_question"], "similarity": hit["similarity"]},
            }
            log_request(event, cached=True)
            yield event
            return

    if mode == "fast":
        yield {"event": "status", "step": "search", "message": "Picking the filing and searching it"}
        t = time.perf_counter()
        result = _pipeline().invoke(standalone, config=config)
        timings["pipeline"] = round(time.perf_counter() - t, 2)
        steps = []
    else:
        # stream_mode="updates": after each node finishes, LangGraph yields {node_name: changed_keys}
        result = {}
        t = time.perf_counter()
        for update in _graph().stream({"question": standalone}, config=config, stream_mode="updates"):
            for node, changes in update.items():
                now = time.perf_counter()
                timings[node] = round(timings.get(node, 0) + now - t, 2)   # retrieve/grade can run several times
                t = now
                before = len(result.get("steps", []))
                result.update(changes)
                new_steps = result.get("steps", [])[before:]
                for s in new_steps or [f"{node} done"]:
                    yield {"event": "status", "step": node, "message": s}
        steps = result.get("steps", [])

    # Output check (M9 Part C): the prompt canary or prompt text in an answer means a leak -> never show it
    if leaked(result["answer"]):
        result = {**result, "answer": blocked_message(), "citations": []}
        steps = steps + ["output check: possible prompt leak, answer blocked"]

    history.add_messages([HumanMessage(content=question), AIMessage(content=result["answer"])])
    event = {
        "event": "answer",
        "answer": result["answer"],
        "citations": result.get("citations", []),
        "sources": [_source(d, i) for i, d in enumerate(result["docs"], 1)],
        "steps": steps,
        "mode": mode,
        "question": standalone,
        "session_id": session_id,
        "run_id": run_id,
        "seconds": round(time.perf_counter() - start, 1),
        "usage": tracker.summary(),   # llm_calls, tokens, reasoning tokens, cost_usd, by_model
        "timings": timings,           # seconds per step (graph nodes, or the whole pipeline)
        "cached": False,
    }
    log_request(event)                # one row in Postgres table request_log
    if use_cache:
        semantic_cache.store(standalone, mode, event)   # only good answers: not refusals, >= 1 verified citation
    yield event


def ask(question: str, mode: Mode = "fast", session_id: str | None = None, use_cache: bool = True) -> dict:
    """Non-streaming version: run to the end and return the answer event."""
    for event in ask_stream(question, mode, session_id, use_cache):
        if event["event"] == "answer":
            return event
