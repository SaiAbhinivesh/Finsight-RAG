"""Semantic answer cache: a reworded repeat of an earlier question returns the saved answer instantly.

A hit needs BOTH:
1. Entities (code): the same companies and the same years/numbers. Embeddings see "AMD revenue FY2022"
   and "AMD revenue FY2015" as nearly identical, but the answers differ.
2. Meaning (pgvector): cosine similarity of the question embeddings >= SIMILARITY_THRESHOLD.

    uv run python -m finsight.cache.semantic_cache --stats
    uv run python -m finsight.cache.semantic_cache --clear
"""

import argparse
import json
import math
import re
from functools import lru_cache

import psycopg
from langchain.embeddings import init_embeddings

from finsight.config import settings
from finsight.generation.structured import REFUSAL
from finsight.ingestion.loaders import load_manifest

SIMILARITY_THRESHOLD = 0.94   # chosen with eval/cache_eval.py
TTL_DAYS = 30
ALIASES = {"amex": "American Express", "pepsi": "PepsiCo"}

DDL = """
CREATE TABLE IF NOT EXISTS answer_cache (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    mode        text NOT NULL,
    question    text NOT NULL,
    entity_key  text NOT NULL,
    embedding   vector(1536) NOT NULL,
    answer      jsonb NOT NULL,
    run_id      uuid,
    hits        int NOT NULL DEFAULT 0,
    last_hit_at timestamptz
);
CREATE INDEX IF NOT EXISTS answer_cache_embedding ON answer_cache USING hnsw (embedding vector_cosine_ops);
"""


# ---------- check 1: entities ----------
@lru_cache
def _company_names() -> dict[str, str]:
    """Every way a question can name a company -> its name in the manifest."""
    names = dict(ALIASES)
    for row in load_manifest():
        names[row["company"].lower()] = row["company"]
        names[row["ticker"].lower()] = row["company"]
    return names


def entity_key(question: str) -> str:
    """Companies + years/numbers in a question, normalised: 'AMD FY22 revenue' -> AMD + 2022."""
    q = question.lower()
    companies = set()
    for name, company in sorted(_company_names().items(), key=lambda kv: -len(kv[0])):
        pattern = rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])"
        if re.search(pattern, q):
            companies.add(company)
            q = re.sub(pattern, " ", q)                       # so the "3" in "3M" is not read as a number
    q = re.sub(r"\bfy\s?'?(\d{2})\b", r"20\1", q)            # FY22 / FY '22 -> 2022
    numbers = sorted(set(re.findall(r"\d+(?:\.\d+)?", q)))
    return json.dumps({"companies": sorted(companies), "numbers": numbers})


# ---------- check 2: meaning ----------
@lru_cache
def _embedder():
    return init_embeddings(settings.embedding_model)


@lru_cache(maxsize=512)
def _embed(text: str) -> tuple[float, ...]:
    return tuple(_embedder().embed_query(text))


def similarity(a: str, b: str) -> float:
    """Cosine similarity of two questions (1.0 = same meaning)."""
    va, vb = _embed(a), _embed(b)
    dot = sum(x * y for x, y in zip(va, vb))
    return dot / (math.sqrt(sum(x * x for x in va)) * math.sqrt(sum(y * y for y in vb)))


def _vector(text: str) -> str:
    return "[" + ",".join(map(str, _embed(text))) + "]"


# ---------- the table ----------
@lru_cache
def _ensure_table() -> None:
    with psycopg.connect(settings.psycopg_url) as conn:
        conn.execute(DDL)


def lookup(question: str, mode: str, threshold: float = SIMILARITY_THRESHOLD) -> dict | None:
    """The saved answer for a question that means the same thing, or None. Never raises."""
    try:
        _ensure_table()
        vec = _vector(question)
        with psycopg.connect(settings.psycopg_url) as conn:
            row = conn.execute(
                """SELECT id, question, answer, 1 - (embedding <=> %s::vector) AS similarity
                   FROM answer_cache
                   WHERE mode = %s AND entity_key = %s AND created_at > now() - make_interval(days => %s)
                   ORDER BY embedding <=> %s::vector
                   LIMIT 1""",
                (vec, mode, entity_key(question), TTL_DAYS, vec),
            ).fetchone()
            if row is None or row[3] < threshold:
                return None
            conn.execute("UPDATE answer_cache SET hits = hits + 1, last_hit_at = now() WHERE id = %s", (row[0],))
        return {"answer": row[2], "matched_question": row[1], "similarity": round(float(row[3]), 4)}
    except Exception as exc:
        print(f"answer_cache: lookup failed ({exc})")
        return None


def is_cacheable(event: dict) -> bool:
    """Only answers we would stand behind: not a refusal, at least one verified citation."""
    return REFUSAL not in event["answer"] and any(c.get("verified") for c in event.get("citations", []))


def store(question: str, mode: str, event: dict) -> None:
    """Save a good answer. Never raises."""
    if not is_cacheable(event):
        return
    try:
        _ensure_table()
        saved = {k: v for k, v in event.items() if k not in ("session_id", "usage", "timings", "seconds")}
        with psycopg.connect(settings.psycopg_url) as conn:
            conn.execute(
                """INSERT INTO answer_cache (mode, question, entity_key, embedding, answer, run_id)
                   VALUES (%s, %s, %s, %s::vector, %s, %s)""",
                (mode, question, entity_key(question), _vector(question), json.dumps(saved), event.get("run_id")),
            )
    except Exception as exc:
        print(f"answer_cache: store failed ({exc})")


def evict(run_id: str) -> int:
    """Remove the answer with this run_id (called on thumbs down). Returns rows removed."""
    try:
        _ensure_table()
        with psycopg.connect(settings.psycopg_url) as conn:
            return conn.execute("DELETE FROM answer_cache WHERE run_id = %s", (run_id,)).rowcount
    except Exception as exc:
        print(f"answer_cache: evict failed ({exc})")
        return 0


def clear() -> int:
    """Empty the cache (after re-indexing the filings, answers may be stale)."""
    _ensure_table()
    with psycopg.connect(settings.psycopg_url) as conn:
        return conn.execute("DELETE FROM answer_cache").rowcount


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true", help="delete every saved answer")
    parser.add_argument("--stats", action="store_true", help="show what is saved")
    args = parser.parse_args()
    if args.clear:
        print(f"Removed {clear()} saved answers.")
    if args.stats or not args.clear:
        _ensure_table()
        with psycopg.connect(settings.psycopg_url) as conn:
            rows = conn.execute("SELECT mode, hits, left(question, 80) FROM answer_cache ORDER BY hits DESC").fetchall()
        print(f"{len(rows)} saved answers")
        for mode, hits, q in rows:
            print(f"  {hits:>3} hits  {mode:<9} {q}")