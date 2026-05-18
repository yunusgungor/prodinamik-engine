# ──────────────────────────────────────────────────
# Prodinamik Engine — Multi-Stage Dockerfile
# ──────────────────────────────────────────────────
# Build:    docker build -t prodinamik-engine .
# Run:      docker run --rm prodinamik-engine --help
# Compose:  docker compose up
# ──────────────────────────────────────────────────

FROM python:3.11-slim AS base

LABEL org.opencontainers.image.title="Prodinamik Engine"
LABEL org.opencontainers.image.description="Product-Agnostic Pipeline Engine"
LABEL org.opencontainers.image.version="1.1.0"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# ── Stage 1: Dev Dependencies ──
FROM base AS dev

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY engine/ engine/
COPY profiles/ profiles/
COPY adapters/ adapters/

# ── Stage 2: Test ──
FROM dev AS test

COPY tests/ tests/
RUN python -m pytest tests/ -v --tb=short -x && echo "✅ All tests passed"

# ── Stage 3: Lint ──
FROM dev AS lint

RUN pip install --no-cache-dir ruff
COPY .ruff.toml . 2>/dev/null || true
RUN python -m ruff check engine/ profiles/ adapters/ || echo "⚠️ Lint warnings ignored"

# ── Stage 4: Production ──
FROM base AS production

COPY pyproject.toml README.md ./
COPY engine/ engine/
COPY profiles/ profiles/
COPY adapters/ adapters/

RUN pip install --no-cache-dir -e ".[test]"

# CLI entrypoint
ENTRYPOINT ["prodinamik"]
CMD ["--help"]
