"""One row per answered request in Postgres: the data behind latency and cost reports."""

import json
from functools import lru_cache

import psycopg

from finsight.config import settings

DDL = """
CREATE TABLE IF NOT EXISTS request_log (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    run_id        uuid,
    session_id    text,
    mode          text,
    question      text,
    seconds       real,
    llm_calls     int,
    input_tokens  int,
    output_tokens int,
    cost_usd      numeric(10, 6),
    cached        boolean NOT NULL DEFAULT false,
    timings       jsonb
)
"""


@lru_cache
def _ensure_table() -> None:
    with psycopg.connect(settings.psycopg_url) as conn:
        conn.execute(DDL)


def log_request(event: dict, cached: bool = False) -> None:
    """Save one answer event. Never raises: logging must not break an answer."""
    try:
        _ensure_table()
        u = event.get("usage", {})
        with psycopg.connect(settings.psycopg_url) as conn:
            conn.execute(
                """INSERT INTO request_log (run_id, session_id, mode, question, seconds, llm_calls,
                       input_tokens, output_tokens, cost_usd, cached, timings)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (event.get("run_id"), event.get("session_id"), event.get("mode"), event.get("question"),
                 event.get("seconds"), u.get("llm_calls", 0), u.get("input_tokens", 0),
                 u.get("output_tokens", 0), u.get("cost_usd", 0), cached,
                 json.dumps(event.get("timings", {}))),
            )
    except Exception as exc:
        print(f"request_log: could not save ({exc})")