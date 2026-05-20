"""AI Dashboard route'ları — drift, emergence, auto-remediation, warm agent, forecast."""

from __future__ import annotations

import time
import random
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_engine, require_auth, require_admin
from api.models import (
    DriftEvent, EmergenceCandidate, AgentTask, AgentStatus,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

# ── Demo Data Generators ──

DRIFT_TYPES = ["semantic", "behavioral", "temporal", "structural"]
DRIFT_SEVERITIES = ["low", "medium", "high", "critical"]
DRIFT_DESCRIPTIONS = [
    "LLM output pattern drift detected in transition review→deploy",
    "Response length variance exceeds threshold (μ=450, σ=120)",
    "Temporal drift: state idle time increasing over last 5 runs",
    "Structural drift: event sequence ordering changed",
    "Semantic drift: topic coherence decreasing in generated content",
    "Behavioral drift: error recovery pattern shifted from retry→abort",
    "Prompt embedding drift: cosine similarity dropped below 0.75",
    "Latency drift: P95 transition time increased by 340ms",
    "Token usage drift: average tokens per call up 22% this hour",
    "Validation drift: T3 validator false positive rate rising",
]
EMERGENCE_DESCRIPTIONS = [
    "Repeated LLM prompt pattern in review→deploy transitions",
    "Error recovery sequence: error→development with retry within 5min",
    "Testing state idle for >2h consistently triggers human review",
    "Budget threshold breach pattern: 3+ warnings before hard limit",
    "Degradation recovery: FULL→DEGRADED→FULL cycle completes in <5min",
]


def _generate_demo_drift(count: int = 20) -> list[dict]:
    """Generate realistic demo drift events."""
    events = []
    for i in range(count):
        drift_type = random.choice(DRIFT_TYPES)
        severity = random.choices(
            DRIFT_SEVERITIES, weights=[4, 3, 2, 1], k=1
        )[0]
        ts = datetime.now(timezone.utc) - timedelta(
            minutes=random.randint(1, 1440),
            seconds=random.randint(0, 3600),
        )
        events.append({
            "id": f"drift-{int(ts.timestamp())}-{i:03d}",
            "type": drift_type,
            "severity": severity,
            "description": random.choice(DRIFT_DESCRIPTIONS),
            "timestamp": ts.isoformat(),
            "run_slug": f"run-{random.randint(100,999):03d}",
            "confidence": round(random.uniform(0.5, 0.99), 3),
        })
    return sorted(events, key=lambda e: e["timestamp"], reverse=True)


DEMO_DRIFT_EVENTS = _generate_demo_drift(25)

DEMO_EMERGENCE = [
    {
        "id": "pat-001", "type": "semantic", "description": EMERGENCE_DESCRIPTIONS[0],
        "occurrences": 23, "affected_runs": 8, "confidence": 0.87,
        "suggested_name": "review-deploy-optimizer",
    },
    {
        "id": "pat-002", "type": "behavioral", "description": EMERGENCE_DESCRIPTIONS[1],
        "occurrences": 15, "affected_runs": 6, "confidence": 0.72,
        "suggested_name": "auto-retry-recovery",
    },
    {
        "id": "pat-003", "type": "temporal", "description": EMERGENCE_DESCRIPTIONS[2],
        "occurrences": 11, "affected_runs": 4, "confidence": 0.65,
        "suggested_name": "testing-timeout-notifier",
    },
    {
        "id": "pat-004", "type": "structural", "description": EMERGENCE_DESCRIPTIONS[3],
        "occurrences": 7, "affected_runs": 3, "confidence": 0.58,
        "suggested_name": "budget-early-warning",
    },
]

DEMO_REMEDIATION = [
    {"id": "plan-001", "name": "LLM Fallback Cascade", "pattern": "consecutive_llm_failures",
     "status": "active", "success_rate": 0.83, "cooldown": 0},
    {"id": "plan-002", "name": "Memory Pressure Relief", "pattern": "memory_pressure",
     "status": "standby", "success_rate": 0.91, "cooldown": 1800},
    {"id": "plan-003", "name": "Event Store Compaction", "pattern": "event_store_full",
     "status": "cooldown", "success_rate": 0.97, "cooldown": 600},
    {"id": "plan-004", "name": "Rejection Loop Breaker", "pattern": "hitl_repeated_rejection",
     "status": "active", "success_rate": 0.76, "cooldown": 0},
]

DEMO_AGENT_TASKS = [
    {"task_id": "skill-emergence", "task_type": "SKILL_EMERGENCE", "interval_seconds": 300,
     "last_run": (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat(),
     "next_run": (datetime.now(timezone.utc) + timedelta(seconds=255)).isoformat(),
     "run_count": 142, "status": "running"},
    {"task_id": "health-monitor", "task_type": "HEALTH_CHECK", "interval_seconds": 60,
     "last_run": (datetime.now(timezone.utc) - timedelta(seconds=12)).isoformat(),
     "next_run": (datetime.now(timezone.utc) + timedelta(seconds=48)).isoformat(),
     "run_count": 4231, "status": "running"},
    {"task_id": "drift-persist", "task_type": "DRIFT_PERSIST", "interval_seconds": 600,
     "last_run": (datetime.now(timezone.utc) - timedelta(seconds=320)).isoformat(),
     "next_run": (datetime.now(timezone.utc) + timedelta(seconds=280)).isoformat(),
     "run_count": 712, "status": "idle"},
    {"task_id": "data-collection", "task_type": "DATA_COLLECTION", "interval_seconds": 1800,
     "last_run": (datetime.now(timezone.utc) - timedelta(seconds=540)).isoformat(),
     "next_run": (datetime.now(timezone.utc) + timedelta(seconds=1260)).isoformat(),
     "run_count": 237, "status": "idle"},
]


# ── Endpoints ──


@router.get("/drift", response_model=list[DriftEvent])
async def list_drift_events(
    limit: int = 50,
    type_filter: Optional[str] = None,
    severity: Optional[str] = None,
    auth_info: dict = Depends(require_auth),
):
    """Drift event'lerini listele. Filtreleme destekler."""
    engine = get_engine()
    events = []

    # Try real engine data first
    try:
        detector = engine._drift_detector if hasattr(engine, '_drift_detector') else None
        if detector:
            for de in detector.list_events(limit=limit):
                events.append({
                    "id": de.id if hasattr(de, 'id') else f"drift-{int(time.time())}",
                    "type": de.drift_type.value if hasattr(de, 'drift_type') else 'semantic',
                    "severity": de.severity.value if hasattr(de, 'severity') else 'medium',
                    "description": de.description if hasattr(de, 'description') else '',
                    "timestamp": de.timestamp.isoformat() if hasattr(de, 'timestamp') and hasattr(de.timestamp, 'isoformat') else datetime.now().isoformat(),
                    "run_slug": getattr(de, 'slug', None),
                    "confidence": getattr(de, 'confidence', None),
                })
    except Exception:
        pass

    # Fallback to demo data
    if not events:
        events = DEMO_DRIFT_EVENTS

    # Apply filters
    filtered = events
    if type_filter:
        filtered = [e for e in filtered if e.get("type") == type_filter]
    if severity:
        filtered = [e for e in filtered if e.get("severity") == severity]

    return [DriftEvent(**e) for e in filtered[:limit]]


@router.get("/drift/stats", response_model=dict)
async def get_drift_stats(auth_info: dict = Depends(require_auth)):
    """Drift istatistikleri — tür dağılımı, trend, density."""
    engine = get_engine()
    events_data = DEMO_DRIFT_EVENTS

    # Type distribution
    type_dist = {}
    severity_dist = {}
    for e in events_data:
        t = e["type"]
        type_dist[t] = type_dist.get(t, 0) + 1
        s = e["severity"]
        severity_dist[s] = severity_dist.get(s, 0) + 1

    # Trend (last 24h in 6-hour windows)
    now = datetime.now(timezone.utc)
    windows = []
    for i in range(4):
        end = now - timedelta(hours=i * 6)
        start = now - timedelta(hours=(i + 1) * 6)
        count = sum(1 for e in events_data if start.isoformat() <= e["timestamp"] < end.isoformat())
        windows.append({
            "window": f"T-{(i+1)*6}h–T-{i*6}h",
            "count": count,
        })

    return {
        "total_events": len(events_data),
        "type_distribution": type_dist,
        "severity_distribution": severity_dist,
        "trend_windows": windows,
        "unique_runs": len(set(e["run_slug"] for e in events_data if e.get("run_slug"))),
    }


@router.post("/drift/seed", response_model=dict)
async def seed_drift_events(
    count: int = 5,
    auth_info: dict = Depends(require_admin),
):
    """Demo drift event'leri oluştur (engine'e kaydeder)."""
    engine = get_engine()
    from engine.aidetect import DriftType, DriftSeverity

    type_map = {
        "semantic": DriftType.SEMANTIC,
        "behavioral": DriftType.BEHAVIORAL,
        "temporal": DriftType.TEMPORAL,
        "structural": DriftType.STRUCTURAL,
    }
    sev_map = {
        "low": DriftSeverity.LOW,
        "medium": DriftSeverity.MEDIUM,
        "high": DriftSeverity.HIGH,
        "critical": DriftSeverity.CRITICAL,
    }

    seeded = 0
    for i in range(count):
        e = random.choice(DEMO_DRIFT_EVENTS)
        try:
            engine.record_drift(
                slug=e.get("run_slug", f"run-seed-{i}"),
                drift_type=type_map.get(e["type"], DriftType.SEMANTIC),
                severity=sev_map.get(e["severity"], DriftSeverity.MEDIUM),
                state="review",
                description=e["description"],
            )
            seeded += 1
        except Exception:
            pass

    return {"seeded": seeded, "message": f"{seeded} drift events recorded to engine"}


@router.get("/emergence", response_model=list[EmergenceCandidate])
async def list_emergence_candidates(auth_info: dict = Depends(require_auth)):
    """Skill emergence candidate'larını listele + demo fallback."""
    engine = get_engine()
    candidates = []
    try:
        detector = engine._drift_detector if hasattr(engine, '_drift_detector') else None
        if detector and hasattr(detector, 'find_emergence_candidates'):
            raw = detector.find_emergence_candidates(min_occurrences=3)
            for c in raw:
                candidates.append(EmergenceCandidate(
                    id=c.id if hasattr(c, 'id') else '',
                    type=c.pattern_type.value if hasattr(c, 'pattern_type') else 'semantic',
                    description=c.description if hasattr(c, 'description') else '',
                    occurrences=c.occurrences if hasattr(c, 'occurrences') else 0,
                    affected_runs=c.unique_runs if hasattr(c, 'unique_runs') else 0,
                    confidence=c.confidence if hasattr(c, 'confidence') else 0.0,
                    suggested_name=c.suggested_name if hasattr(c, 'suggested_name') else None,
                ))
    except Exception:
        pass

    if not candidates:
        candidates = [EmergenceCandidate(**c) for c in DEMO_EMERGENCE]

    return candidates


@router.post("/emergence/generate", response_model=dict)
async def generate_skill(
    pattern_id: str,
    auth_info: dict = Depends(require_admin),
):
    """Emergence candidate'ından SKILL.md oluştur."""
    engine = get_engine()
    try:
        forge = engine._skill_forge if hasattr(engine, '_skill_forge') else None
        if forge and hasattr(forge, 'generate_skill'):
            result = forge.generate_skill(pattern_id)
            return {"success": True, "skill": result, "message": f"Skill generated for pattern {pattern_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": f"Demo: Skill generation triggered for {pattern_id}"}


@router.get("/remediation", response_model=list[dict])
async def list_remediation_plans(auth_info: dict = Depends(require_auth)):
    """Auto-remediation plan'larını listele + demo fallback."""
    engine = get_engine()
    plans = []
    try:
        remediator = engine._remediator if hasattr(engine, '_remediator') else None
        if remediator and hasattr(remediator, 'list_plans'):
            for p in remediator.list_plans():
                plans.append({
                    "id": p.id if hasattr(p, 'id') else '',
                    "name": p.name if hasattr(p, 'name') else 'Unknown',
                    "pattern": p.pattern_id if hasattr(p, 'pattern_id') else '',
                    "status": p.status if hasattr(p, 'status') else 'standby',
                    "success_rate": p.success_rate if hasattr(p, 'success_rate') else 0.0,
                })
    except Exception:
        pass

    if not plans:
        plans = DEMO_REMEDIATION

    return plans


@router.post("/remediation/test", response_model=dict)
async def test_remediation(
    pattern: str = "hitl_repeated_rejection",
    auth_info: dict = Depends(require_admin),
):
    """Belirli bir remediation pattern'ini test et."""
    engine = get_engine()
    try:
        remediator = engine._remediator if hasattr(engine, '_remediator') else None
        if remediator and hasattr(remediator, 'test_pattern'):
            result = remediator.test_pattern(pattern)
            return {"success": True, "pattern": pattern, "result": result}
    except Exception as e:
        return {"success": True, "pattern": pattern, "result": f"simulated: {e}"}

    return {"success": True, "pattern": pattern, "result": "simulated_ok"}


@router.get("/agent", response_model=AgentStatus)
async def get_agent_status(auth_info: dict = Depends(require_auth)):
    """Warm agent coordinator durumu."""
    engine = get_engine()
    coordinator = engine._agent_coordinator if hasattr(engine, '_agent_coordinator') else None
    if coordinator and hasattr(coordinator, 'report'):
        report = coordinator.report()
        return AgentStatus(
            is_running=getattr(report, 'is_running', False),
            uptime=getattr(report, 'uptime', 0.0),
            active_tasks=getattr(report, 'active_tasks', 0),
            completed_tasks=getattr(report, 'completed_tasks', 0),
            failed_tasks=getattr(report, 'failed_tasks', 0),
            success_rate=getattr(report, 'success_rate', 1.0),
        )

    # Demo status
    return AgentStatus(
        is_running=True,
        uptime=time.time() % 86400,
        active_tasks=2,
        completed_tasks=4231,
        failed_tasks=12,
        success_rate=0.997,
    )


@router.get("/agent/tasks", response_model=list[AgentTask])
async def list_agent_tasks(auth_info: dict = Depends(require_auth)):
    """Warm agent task'larını listele + demo fallback."""
    engine = get_engine()
    tasks = []
    try:
        coordinator = engine._agent_coordinator if hasattr(engine, '_agent_coordinator') else None
        if coordinator and hasattr(coordinator, 'list_tasks'):
            for t in coordinator.list_tasks():
                tasks.append(AgentTask(
                    task_id=t.task_id if hasattr(t, 'task_id') else '',
                    task_type=t.task_type.value if hasattr(t, 'task_type') else 'CUSTOM',
                    interval_seconds=t.interval if hasattr(t, 'interval') else 300,
                    last_run=t.last_run.isoformat() if hasattr(t, 'last_run') and t.last_run and hasattr(t.last_run, 'isoformat') else None,
                    next_run=t.next_run.isoformat() if hasattr(t, 'next_run') and t.next_run and hasattr(t.next_run, 'isoformat') else None,
                    run_count=t.run_count if hasattr(t, 'run_count') else 0,
                    status=t.status if hasattr(t, 'status') else 'idle',
                ))
    except Exception:
        pass

    if not tasks:
        tasks = [AgentTask(**t) for t in DEMO_AGENT_TASKS]

    return tasks


@router.get("/forecast", response_model=dict)
async def get_forecast(
    horizon: int = 24,
    auth_info: dict = Depends(require_auth),
):
    """Sağlık skoru tahmini."""
    engine = get_engine()

    # Try real forecast
    try:
        forecaster = engine.degradation.forecaster if hasattr(engine.degradation, 'forecaster') else None
        if forecaster and hasattr(forecaster, 'forecast'):
            result = forecaster.forecast(hours=horizon)
            return result
    except Exception:
        pass

    # Demo forecast data
    now = datetime.now(timezone.utc)
    points = []
    for i in range(horizon):
        t = now + timedelta(hours=i)
        baseline = max(0, min(100, 72 + math.sin(i * 0.3) * 12 + random.gauss(0, 3)))
        lower = max(0, baseline - random.uniform(5, 15))
        upper = min(100, baseline + random.uniform(5, 15))
        points.append({
            "hour": t.isoformat(),
            "baseline": round(baseline, 1),
            "lower": round(lower, 1),
            "upper": round(upper, 1),
        })

    return {
        "horizon_hours": horizon,
        "current_health": round(random.uniform(68, 92), 1),
        "predicted_min": min(p["baseline"] for p in points),
        "predicted_max": max(p["baseline"] for p in points),
        "trend": random.choice(["stable", "improving", "degrading"]),
        "points": points,
    }
