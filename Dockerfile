# FinSight API image: only what serving needs (no Docling, RAGAS or PyTorch).
# Build and run with docker compose (see docker-compose.yml), or:
#   docker build -t finsight-api .
FROM python:3.12-slim

# uv (the same tool used locally) copied from its official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Dependencies first, in their own layer: rebuilt only when pyproject.toml or uv.lock change.
#    --no-default-groups: main dependencies only (no dev, ingest, eval or rerank groups).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-default-groups --no-install-project

# 2. The application code and the filings list (available_filings() reads data/manifest.csv)
COPY src ./src
COPY data/manifest*.csv ./data/
RUN uv sync --frozen --no-default-groups

ENV PATH="/app/.venv/bin:$PATH"

# Run as a normal user, not root
RUN useradd --create-home finsight && chown -R finsight /app
USER finsight

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "finsight.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
