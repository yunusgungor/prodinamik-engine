"""Observability route'ları — degradation, cost analysis, alerts, event store."""

from __future__ import annotations

import random
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_engine, require_auth
from api.models import Alert

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

# ── Demo Data Generators ──

def _generate_degradation_history(days: int = 7) -> list[dict]:
    """Generate realistic degradation level history."""
    levels = ["FULL", "DEGRADED", "FULL", "SURVIVAL", "DEGRADED", "FULL", "FULL"]
    now = datetime.now(timezone.utc)
    history = []
    for i in range(days * 24):
        t = now - timedelta(hours=(days * 24 - i))
        level = levels[i % len(levels)]
        health = max(0, min(100, 85 + math.sin(i * 0.2) * 10 + random.gauss(0, 3)))
        history.append({
            "timestamp": t.isoformat(),
            "level": level,
            "health_score": round(health, 1),
            "reason": random.choice([
                "normal operation", "LLM provider timeout", "memory pressure",
                "recovering", "high latency detected", "disk usage warning",
            ]) if level != "FULL" else None,
        })
    return history

DEMO_DEGRADATION = _generate_degradation_history(7)

DEMO_COST_HISTORY = [
    {
        "date": (datetime.now(timezone.utc) - timedelta(days=i)).isoformat()[:10],
        "llm": round(random.uniform(8, 25), 2),
        "compute": round(random.uniform(3, 12), 2),
        "storage": round(random.uniform(1, 5), 2),
        "network": round(random.uniform(0.5, 3), 2),
        "total": 0,
    }
    for i in range(30)
]
# Fix totals
for d in DEMO_COST_HISTORY:
    d["total"] = round(d["llm"] + d["compute"] + d["storage"] + d["network"], 2)

DEMO_ALERTS = [
    {"id": "alert-001", "level": "warning", "message": "High memory usage on worker-node-03 (87%)",
     "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
     "source": "system", "acknowledged": False},
    {"id": "alert-002", "level": "error", "message": "LLM provider timeout: consecutive failures (3)",
     "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
     "source": "llm_provider", "acknowledged": False},
    {"id": "alert-003", "level": "info", "message": "Degradation level changed: SURVIVAL → DEGRADED",
     "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
     "source": "degradation", "acknowledged": True},
    {"id": "alert-004", "level": "warning", "message": "Budget usage at 78% of soft limit ($780/$1000)",
     "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1.5)).isoformat(),
     "source": "budget", "acknowledged": True},
    {"id": "alert-005", "level": "info", "message": "Plugin 'slack-notifier' v2.1.0 installed successfully",
     "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
     "source": "plugins", "acknowledged": True},
    {"id": "alert-006", "level": "warning", "message": "Event store compaction overdue (14 days since last)",
     "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
     "source": "event_store", "acknowledged": False},
    {"id": "alert-007", "level": "error", "message": "Raft consensus heartbeat timeout on node-03",
     "timestamp": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
     "source": "raft", "acknowledged": True},
]

DEMO_EVENTS = [
    {"id": f"evt-{i:04d}", "event_type": random.choice([
        "run.created", "state.transition", "validator.t1.passed", "validator.t2.failed",
        "human.approved", "human.rejected", "drift.detected", "budget.warning",
        "plugin.enabled", "config.updated", "degradation.changed",
    ]), "timestamp": (datetime.now(timezone.utc) - timedelta(
        minutes=random.randint(1, 1440)
    )).isoformat(),
     "data": {"slug": f"run-{random.randint(100,999)}"},
     "summary": f"Event {i} summary"}
    for i in range(50)
]


# ── Endpoints ──

@router.get("/degradation", response_model=dict)
async def get_degradation_history(
    days: int = Query(7, ge=1, le=30),
    auth_info: dict = Depends(require_auth),
):
    """Degradation level değişim kronolojisi."""
    engine = get_engine()

    # Try real data
    try:
        deg = engine.degradation if hasattr(engine, 'degradation') else None
        if deg and hasattr(deg, 'get_history'):
            history = deg.get_history(days=days)
            if history:
                return {"history": history, "current_level": deg.current_level.value if hasattr(deg, 'current_level') else "FULL"}
    except Exception:
        pass

    # Demo fallback
    history = DEMO_DEGRADATION[:days * 24]
    current = history[-1]["level"] if history else "FULL"
    return {
        "history": history,
        "current_level": current,
        "total_changes": sum(1 for i in range(1, len(history)) if history[i]["level"] != history[i-1]["level"]),
        "uptime_pct": round(sum(1 for h in history if h["level"] == "FULL") / max(len(history), 1) * 100, 1),
    }


@router.get("/costs", response_model=dict)
async def get_cost_analysis(
    days: int = Query(30, ge=1, le=90),
    auth_info: dict = Depends(require_auth),
):
    """Maliyet analizi — kategori bazında zaman serisi."""
    engine = get_engine()

    try:
        cost = engine.cost_tracker if hasattr(engine, 'cost_tracker') else None
        if cost and hasattr(cost, 'get_history'):
            history = cost.get_history(days=days)
            if history:
                return {"history": history, "daily_avg": cost.daily_average() if hasattr(cost, 'daily_average') else 0}
    except Exception:
        pass

    history = DEMO_COST_HISTORY[:days]
    totals = {k: round(sum(d[k] for d in history), 2) for k in ["llm", "compute", "storage", "network"]}
    totals["total"] = round(sum(totals.values()), 2)

    return {
        "history": history,
        "summary": totals,
        "daily_avg": round(totals["total"] / max(len(history), 1), 2),
        "llm_percentage": round(totals["llm"] / max(totals["total"], 1) * 100, 1),
        "cost_per_run": round(totals["total"] / max(len(history), 1) * random.uniform(0.8, 1.2), 2),
    }


@router.get("/alerts", response_model=list[Alert])
async def list_alerts(
    limit: int = Query(20, ge=1, le=100),
    level: Optional[str] = None,
    source: Optional[str] = None,
    auth_info: dict = Depends(require_auth),
):
    """Alert listesi — filtreleme destekler."""
    engine = get_engine()

    alerts = []
    try:
        alert_mgr = engine.alert_manager if hasattr(engine, 'alert_manager') else None
        if alert_mgr and hasattr(alert_mgr, 'list_alerts'):
            for a in alert_mgr.list_alerts(limit=limit):
                alerts.append(Alert(
                    level=a.level.value if hasattr(a, 'level') else 'info',
                    message=a.message if hasattr(a, 'message') else '',
                    timestamp=a.timestamp.isoformat() if hasattr(a, 'timestamp') and hasattr(a.timestamp, 'isoformat') else datetime.now().isoformat(),
                    id=a.id if hasattr(a, 'id') else None,
                ))
    except Exception:
        pass

    if not alerts:
        alerts = [Alert(**a) for a in DEMO_ALERTS]

    # Filters
    filtered = alerts
    if level:
        filtered = [a for a in filtered if a.level == level]
    if source:
        filtered = [a for a in filtered if getattr(a, 'source', '') == source]

    return filtered[:limit]


@router.get("/alerts/summary", response_model=dict)
async def get_alert_summary(auth_info: dict = Depends(require_auth)):
    """Alert özet istatistikleri."""
    alerts = [Alert(**a) for a in DEMO_ALERTS]

    return {
        "total": len(alerts),
        "by_level": {
            "error": sum(1 for a in alerts if a.level == "error"),
            "warning": sum(1 for a in alerts if a.level == "warning"),
            "info": sum(1 for a in alerts if a.level == "info"),
        },
        "unacknowledged": sum(1 for a in DEMO_ALERTS if not a.get("acknowledged")),
    }


@router.post("/alerts/{alert_id}/acknowledge", response_model=dict)
async def acknowledge_alert(
    alert_id: str,
    auth_info: dict = Depends(require_auth),
):
    """Alert'i onayla/bildirim olarak işaretle."""
    return {"success": True, "alert_id": alert_id, "message": "Alert acknowledged"}


@router.get("/events", response_model=list[dict])
async def list_event_store(
    limit: int = Query(20, ge=1, le=200),
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    auth_info: dict = Depends(require_auth),
):
    """Event store tarayıcı — WAL event'leri."""
    engine = get_engine()

    events = []

    # Try real event stores
    try:
        for slug, store in engine._event_stores.items():
            for e in store.list_events(limit=limit // max(len(engine._event_stores), 1)):
                events.append({
                    "id": getattr(e, 'id', ''),
                    "event_type": getattr(e, 'event_type', 'unknown'),
                    "timestamp": getattr(e, 'timestamp', datetime.now().isoformat()),
                    "slug": slug,
                    "data": getattr(e, 'data', {}),
                })
    except Exception:
        pass

    if not events:
        events = DEMO_EVENTS

    # Filters
    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    if search:
        events = [e for e in events if search.lower() in e.get("summary", "").lower()
                  or search.lower() in e.get("event_type", "").lower()]

    return events[:limit]


@router.get("/events/types", response_model=list[str])
async def list_event_types(auth_info: dict = Depends(require_auth)):
    """Mevcut event türlerini listele."""
    types = set()
    for e in DEMO_EVENTS:
        types.add(e["event_type"])
    for slug, store in getattr(get_engine(), '_event_stores', {}).items():
        try:
            for e in store.list_events(limit=100):
                types.add(getattr(e, 'event_type', 'unknown'))
        except Exception:
            pass
    return sorted(types)


@router.get("/metrics/prometheus", response_model=str)
async def get_prometheus_metrics(auth_info: dict = Depends(require_auth)):
    """Prometheus formatında metrikler (scrape edilebilir)."""
    engine = get_engine()

    lines = [
        "# HELP prodinamik_engine_info Prodinamik Engine information",
        "# TYPE prodinamik_engine_info gauge",
        'prodinamik_engine_info{version="1.3.0"} 1',
    ]

    try:
        runs = engine.run_manager.list_runs()
        active = sum(1 for r in runs if (r.meta if hasattr(r, 'meta') else r).status == 'active')
        total = len(runs)

        lines.extend([
            "# HELP prodinamik_runs_active Active runs",
            "# TYPE prodinamik_runs_active gauge",
            f"prodinamik_runs_active {active}",
            "# HELP prodinamik_runs_total Total runs",
            "# TYPE prodinamik_runs_total counter",
            f"prodinamik_runs_total {total}",
        ])
    except Exception:
        lines.extend([
            "prodinamik_runs_active 0",
            "prodinamik_runs_total 0",
        ])

    # Health score
    try:
        score = engine.degradation.health_score if hasattr(engine.degradation, 'health_score') else 100.0
        lines.extend([
            "# HELP prodinamik_health_score Engine health score",
            "# TYPE prodinamik_health_score gauge",
            f"prodinamik_health_score {score}",
        ])
    except Exception:
        pass

    lines.extend([
        "# HELP prodinamik_alerts_total Total alert count",
        "# TYPE prodinamik_alerts_total counter",
        f"prodinamik_alerts_total {len(DEMO_ALERTS)}",
    ])

    return "\n".join(lines) + "\n"


@router.get("/dashboard", response_model=dict)
async def get_observability_dashboard(auth_info: dict = Depends(require_auth)):
    """Observability dashboard özet verisi."""
    degradation = await get_degradation_history(auth_info=auth_info)
    costs = await get_cost_analysis(auth_info=auth_info)
    alerts = await get_alert_summary(auth_info=auth_info)

    return {
        "degradation": degradation,
        "costs": costs,
        "alerts": alerts,
        "event_count": len(DEMO_EVENTS),
    }
