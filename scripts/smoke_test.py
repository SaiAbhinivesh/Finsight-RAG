"""M0 smoke test: checks the chat model, embeddings, and Postgres + pgvector.

Run from the project root:
    docker compose up -d
    uv run python scripts/smoke_test.py
"""

import numpy as np
import psycopg
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings

from finsight.config import settings


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity: 1.0 = same direction, ~0 = unrelated."""
    a, b = np.array(a), np.array(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def check_chat_model() -> None:
    print("\n=== 1. Chat model ===")
    model = init_chat_model(settings.chat_model)
    response = model.invoke("Reply with just: ok")
    print(f"Model:   {settings.chat_model}")
    print(f"Reply:   {response.content}")
    # Token counts: you will use these later for cost tracking (M9)
    print(f"Usage:   {response.usage_metadata}")


def check_embeddings() -> None:
    print("\n=== 2. Embeddings ===")
    embeddings = init_embeddings(settings.embedding_model)

    vector = embeddings.embed_query("Apple net sales")
    print(f"Model:      {settings.embedding_model}")
    print(f"Dimensions: {len(vector)}  (expect 1536)")
    print(f"First 5:    {[round(x, 4) for x in vector[:5]]}")

    # Build intuition: related sentences should score higher than unrelated ones
    sentences = [
        "Apple's total net sales increased in fiscal 2023.",
        "Revenue from iPhone and services grew year over year.",
        "The recipe calls for two cups of flour and an egg.",
    ]
    v1, v2, v3 = embeddings.embed_documents(sentences)
    print(f"Related pair   (1 vs 2): {cosine(v1, v2):.3f}")
    print(f"Unrelated pair (1 vs 3): {cosine(v1, v3):.3f}")


def check_database() -> None:
    print("\n=== 3. Postgres + pgvector ===")
    with psycopg.connect(settings.psycopg_url) as conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        print(f"Postgres: {version.split(',')[0]}")

        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        print(f"pgvector: {row[0] if row else 'NOT INSTALLED - run CREATE EXTENSION vector;'}")

        distance = conn.execute(
            "SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector"
        ).fetchone()[0]
        print(f"Cosine distance test: {distance:.4f}")


if __name__ == "__main__":
    check_chat_model()
    check_embeddings()
    check_database()
    print("\nAll checks passed. Look for the chat trace in LangSmith -> project 'finsight'.")