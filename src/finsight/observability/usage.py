"""Count tokens, cost and time of every LLM call in one request (a LangChain callback handler)."""

import threading
import time
from collections import defaultdict
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from finsight.observability.pricing import cost_usd


class UsageTracker(BaseCallbackHandler):
    """Use one per request: config={"callbacks": [tracker]}. LangChain calls it for every model call inside."""

    def __init__(self) -> None:
        self._lock = threading.Lock()          # graph nodes can run in worker threads
        self._starts: dict[UUID, float] = {}
        self.calls: list[dict] = []

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, **kwargs: Any) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_start(self, serialized, prompts, *, run_id: UUID, **kwargs: Any) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        seconds = time.perf_counter() - self._starts.pop(run_id, time.perf_counter())
        gen = response.generations[0][0] if response.generations and response.generations[0] else None
        msg = getattr(gen, "message", None)
        usage = getattr(msg, "usage_metadata", None) or {}
        model = (getattr(msg, "response_metadata", None) or {}).get("model_name") \
            or (response.llm_output or {}).get("model_name", "unknown")

        inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cached = (usage.get("input_token_details") or {}).get("cache_read", 0) or 0
        reasoning = (usage.get("output_token_details") or {}).get("reasoning", 0) or 0
        with self._lock:
            self.calls.append({
                "model": model, "seconds": round(seconds, 2),
                "input_tokens": inp, "output_tokens": out,
                "reasoning_tokens": reasoning, "cached_tokens": cached,
                "cost_usd": cost_usd(model, inp, out, cached),
            })

    def summary(self) -> dict:
        """Totals for the request, plus a breakdown per model."""
        by_model = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        for c in self.calls:
            m = by_model[c["model"]]
            m["calls"] += 1
            m["input_tokens"] += c["input_tokens"]
            m["output_tokens"] += c["output_tokens"]
            m["cost_usd"] += c["cost_usd"]
        return {
            "llm_calls": len(self.calls),
            "input_tokens": sum(c["input_tokens"] for c in self.calls),
            "output_tokens": sum(c["output_tokens"] for c in self.calls),
            "reasoning_tokens": sum(c["reasoning_tokens"] for c in self.calls),
            "llm_seconds": round(sum(c["seconds"] for c in self.calls), 1),
            "cost_usd": round(sum(c["cost_usd"] for c in self.calls), 6),
            "by_model": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_model.items()},
        }