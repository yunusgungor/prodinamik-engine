"""Raft/Chaos route'ları — dağıtık sistem ve kaos mühendisliği."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_engine, require_admin, require_auth
from api.models import RaftNode, ChaosScenario, ChaosResult, ActionResult

router = APIRouter(prefix="/api/v1", tags=["operations"])


# ── Raft ──

@router.get("/raft/nodes", response_model=list[RaftNode])
async def list_raft_nodes(auth_info: dict = Depends(require_admin)):
    """Raft küme düğümlerini listele."""
    engine = get_engine()
    nodes = []
    try:
        cluster = engine.raft_cluster if hasattr(engine, 'raft_cluster') else None
        if cluster and hasattr(cluster, 'list_nodes'):
            for n in cluster.list_nodes():
                nodes.append(RaftNode(
                    id=n.id if hasattr(n, 'id') else '',
                    address=n.address if hasattr(n, 'address') else '',
                    state=n.state if hasattr(n, 'state') else 'follower',
                    last_seen=n.last_seen.isoformat() if hasattr(n, 'last_seen') and n.last_seen and hasattr(n.last_seen, 'isoformat') else None,
                    log_index=n.log_index if hasattr(n, 'log_index') else 0,
                    term=n.term if hasattr(n, 'term') else 0,
                ))
    except Exception:
        pass
    return nodes


@router.get("/raft/status", response_model=dict)
async def get_raft_status(auth_info: dict = Depends(require_admin)):
    """Raft küme durumu."""
    engine = get_engine()
    try:
        cluster = engine.raft_cluster if hasattr(engine, 'raft_cluster') else None
        if cluster and hasattr(cluster, 'get_status'):
            return cluster.get_status()
    except Exception:
        pass
    return {"state": "standalone", "nodes": 0, "term": 0}


# ── Chaos ──

@router.get("/chaos/scenarios", response_model=list[ChaosScenario])
async def list_chaos_scenarios(auth_info: dict = Depends(require_admin)):
    """Kaos senaryolarını listele."""
    engine = get_engine()
    scenarios = []
    try:
        chaos = engine.chaos_engine if hasattr(engine, 'chaos_engine') else None
        if chaos is None:
            # Create standalone chaos engine
            from engine.chaos import ChaosEngine
            from engine.config import ProdinamikConfig
            cfg = ProdinamikConfig.load()
            chaos = ChaosEngine(engine=engine, base_path=str(Path(cfg.data_dir) / "chaos"))
        if chaos and hasattr(chaos, 'list_scenarios'):
            for s in chaos.list_scenarios():
                scenarios.append(ChaosScenario(
                    id=s.get('name', s.get('fault_type', '')),
                    name=s.get('name', ''),
                    description=s.get('description', ''),
                    severity=s.get('severity', 'medium'),
                    duration=s.get('duration', 30),
                ))
    except Exception:
        pass
    return scenarios


@router.post("/chaos/run", response_model=ChaosResult)
async def run_chaos_scenario(
    data: dict,
    auth_info: dict = Depends(require_admin),
):
    """Kaos senaryosu çalıştır."""
    engine = get_engine()
    scenario_id = data.get('scenario_id', data.get('scenario', ''))
    duration = data.get('duration', 30)
    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id required")

    try:
        chaos = engine.chaos_engine if hasattr(engine, 'chaos_engine') else None
        if chaos is None:
            from engine.chaos import ChaosEngine
            from engine.config import ProdinamikConfig
            cfg = ProdinamikConfig.load()
            chaos = ChaosEngine(engine=engine, base_path=str(Path(cfg.data_dir) / "chaos"))
        if chaos and hasattr(chaos, 'run_scenario'):
            result = chaos.run_scenario(scenario_id, duration=duration)
            return ChaosResult(
                scenario=scenario_id,
                outcome='success' if getattr(result, 'success', False) else 'failure',
                recovery_time_sec=getattr(result, 'recovery_time', None),
                metrics_before=getattr(result, 'metrics_before', None),
                metrics_after=getattr(result, 'metrics_after', None),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChaosResult(scenario=scenario_id, outcome='success')
