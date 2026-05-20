"""
Prodinamik Engine — FastAPI Web API

Ana uygulama. Tüm route'ları + WebSocket'leri register eder.
Engine'i başlatır ve background task'ları yönetir.

Kullanım:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Engine path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.deps import get_engine, start_engine_background, get_started_at
from api.routes import (
    runs, profiles, audit, metrics, human,
    auth, plugins, ai, raft_chaos, config, observability, ratelimit,
)
from api.ws import handlers as ws_handlers
from fastapi.responses import RedirectResponse

logger = logging.getLogger("prodinamik.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama başlangıcında engine'i başlat, kapanışta temizle."""
    logger.info("Starting Prodinamik Engine API...")

    # Engine singleton'ını initialize et
    try:
        engine = get_engine()
        logger.info(f"Engine initialized (v{engine.config.version if hasattr(engine.config, 'version') else '1.3.0'})")
    except Exception as e:
        logger.warning(f"Engine initialization warning (will work in mock mode): {e}")

    # Background thread'de engine'i başlat (timeout watcher, warm agent)
    start_engine_background()

    yield

    # Shutdown
    logger.info("Shutting down Prodinamik Engine API...")
    try:
        engine = get_engine()
        if engine._running:
            import asyncio
            await engine.stop()
    except Exception:
        pass


# ── FastAPI App ──

app = FastAPI(
    title="Prodinamik Engine API",
    description="""
    Prodinamik Engine — Product-Agnostic Pipeline Engine.
    
    State machine, multi-tier validation, event sourcing, Raft consensus,
    plugin ecosystem, AI-native features, and HITL (Human-In-The-Loop).
    
    ## Authentication
    API keys with `Authorization: Bearer pdmk_xxx` header.
    Roles: admin, user, readonly.
    """,
    version="1.3.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    license_info={
        "name": "MIT",
    },
    contact={
        "name": "Yunus Güngör",
        "email": "mail@yunusgungor.com",
    },
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handler ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "path": request.url.path},
    )


# ── Register Routes ──

app.include_router(runs.router)
app.include_router(profiles.router)
app.include_router(audit.router)
app.include_router(metrics.router)
app.include_router(human.router)
app.include_router(auth.router)
app.include_router(plugins.router)
app.include_router(ai.router)
app.include_router(raft_chaos.router)
app.include_router(config.router)
app.include_router(observability.router)
app.include_router(ratelimit.router)

# WebSocket handlers
app.include_router(ws_handlers.router)

# Legacy /api/healthz → /api/v1/healthz redirect
@app.get("/api/healthz", include_in_schema=False)
async def legacy_healthz():
    return RedirectResponse(url="/api/v1/healthz")


# ── Root endpoint ──

@app.get("/")
async def root():
    return {
        "name": "Prodinamik Engine API",
        "version": "1.3.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/healthz",
    }


@app.get("/api")
async def api_root():
    return {
        "api": "v1",
        "endpoints": {
            "health": "/api/healthz",
            "metrics": "/api/v1/metrics",
            "runs": "/api/v1/runs",
            "profiles": "/api/v1/profiles",
            "audit": "/api/v1/audit",
            "human": "/api/v1/human/*",
            "auth": "/api/v1/auth/*",
            "plugins": "/api/v1/plugins",
            "ai": "/api/v1/ai/*",
            "raft": "/api/v1/raft/*",
            "chaos": "/api/v1/chaos/*",
            "config": "/api/v1/config",
        },
        "websockets": {
            "run_events": "/ws/runs/{slug}",
            "human": "/ws/human",
            "metrics": "/ws/metrics",
            "events": "/ws/events",
        },
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PRODINAMIK_PORT", "8000"))
    host = os.environ.get("PRODINAMIK_HOST", "0.0.0.0")
    uvicorn.run("api.main:app", host=host, port=port, reload=True, log_level="info")
