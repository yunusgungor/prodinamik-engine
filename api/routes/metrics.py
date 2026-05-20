"""Metrics route'ları — engine metrics + health."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import get_engine, get_started_at, require_auth
from api.models import EngineMetrics, Alert, HealthStatus

router = APIRouter(prefix="/api/v1", tags=["metrics"])


@router.get("/metrics", response_model=EngineMetrics)
async def get_metrics(auth_info: dict = Depends(require_auth)):
    """Engine metriklerini getir."""
    engine = get_engine()

    active = 0
    total = 0
    total_transitions = 0
    total_events = 0
    health_score = 100.0
    runs_by_state = {}
    runs_by_profile = {}

    try:
        runs = engine.run_manager.list_runs(limit=1000)
        total = len(runs)
        for r in runs:
            meta = r.meta if hasattr(r, 'meta') else r
            state = meta.state if hasattr(meta, 'state') else ''
            profile = meta.profile if hasattr(meta, 'profile') else ''
            status = meta.status if hasattr(meta, 'status') else 'active'

            if status == 'active':
                active += 1
            runs_by_state[state] = runs_by_state.get(state, 0) + 1
            runs_by_profile[profile] = runs_by_profile.get(profile, 0) + 1
    except Exception:
        pass

    # Health score from degradation manager
    try:
        health_score = engine.degradation.health_score if hasattr(engine.degradation, 'health_score') else 100.0
    except Exception:
        pass

    # Degradation level
    deg_level = "FULL"
    try:
        deg_level = engine.degradation.current_level.value if hasattr(engine.degradation, 'current_level') else "FULL"
    except Exception:
        pass

    return EngineMetrics(
        active_runs=active,
        total_runs=total,
        total_transitions=total_transitions,
        total_events=total_events,
        degradation_level=deg_level,
        uptime_seconds=time.time() - get_started_at(),
        health_score=health_score,
        runs_by_state=runs_by_state,
        runs_by_profile=runs_by_profile,
    )


@router.get("/healthz", response_model=HealthStatus, include_in_schema=True)
@router.get("/health", response_model=HealthStatus, include_in_schema=False)
async def health_check():
    """Health check endpoint."""
    engine = get_engine()
    score = 100.0
    deg_level = "FULL"
    try:
        score = engine.degradation.health_score if hasattr(engine.degradation, 'health_score') else 100.0
        deg_level = engine.degradation.current_level.value if hasattr(engine.degradation, 'current_level') else "FULL"
    except Exception:
        pass

    return HealthStatus(
        status="ok",
        version="1.3.0",
        uptime=time.time() - get_started_at(),
        degradation=deg_level,
        health_score=score,
    )
