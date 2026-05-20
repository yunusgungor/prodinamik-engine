# ──────────────────────────────────────────────────
# Prodinamik Engine — API Dockerfile
# FastAPI + uvicorn multi-stage build
# ──────────────────────────────────────────────────
# Build:  docker build -t prodinamik-api -f infra/docker/prodinamik-api.Dockerfile .
# Run:    docker run -d -p 8000:8000 -v prodinamik-data:/data prodinamik-api
# ──────────────────────────────────────────────────

FROM python:3.11-slim AS base

LABEL org.opencontainers.image.title="Prodinamik Engine API"
LABEL org.opencontainers.image.description="Pipeline Engine FastAPI Backend — state machines, HITL, AI Grid, Raft"
LABEL org.opencontainers.image.version="1.3.0"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# ── Stage 1: Dependencies ──
FROM base AS deps

# Build-time system packages (gcc for native extensions if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[api]"

# ── Stage 2: Test ──
FROM deps AS test

COPY engine/ engine/
COPY profiles/ profiles/
COPY adapters/ adapters/
COPY validators/ validators/
COPY api/ api/
COPY prodinamik.yaml ./
COPY tests/ tests/

RUN python -m pytest tests/ -v --tb=short -x \
    && echo "✅ All API dependency tests passed"

# ── Stage 3: Production ──
FROM base AS production

LABEL maintainer="Yunus Güngör <mail@yunusgungor.com>"

# Runtime system packages (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy source
COPY engine/ engine/
COPY profiles/ profiles/
COPY adapters/ adapters/
COPY validators/ validators/
COPY api/ api/
COPY prodinamik.yaml ./

# Default data directory (override via HERMES_HOME env)
ENV HERMES_HOME=/data
ENV PYTHONUNBUFFERED=1

# Create data directory with proper permissions
RUN mkdir -p /data/prodinamik/auth /data/prodinamik/chaos/results \
    && chmod -R 755 /data

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/healthz').status == 200 else 1)" \
    || exit 1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
