"""Human Loop route'ları — approvals, budget, HITL dashboard."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_engine, require_auth, require_admin
from api.models import (
    ApprovalTask, ApprovalAction, PauseInput, ActionResult,
    BudgetStatus, HumanDashboard, AuditEntry,
)

router = APIRouter(prefix="/api/v1/human", tags=["human"])


@router.get("/approvals", response_model=list[ApprovalTask])
async def list_approvals(auth_info: dict = Depends(require_auth)):
    """Bekleyen onayları listele."""
    engine = get_engine()
    tasks = []

    # PAUSE state'teki run'ları HITL bekleme olarak göster
    try:
        runs = engine.run_manager.list_runs(limit=500)
        for r in runs:
            meta = r.meta if hasattr(r, 'meta') else r
            status = getattr(meta, 'status', '')
            state = getattr(meta, 'state', '')
            slug = getattr(meta, 'slug', '')

            if status == 'active' and state in ('draft_review', 'review', 'published',
                                                  'correction_needed', 'peer_review', 'blocked'):
                tasks.append(ApprovalTask(
                    task_id=f"hitl-{slug}",
                    description=f"Run '{slug}' PAUSE state'te: {state}. İnsan onayı bekliyor.",
                    created_at=getattr(meta, 'updated_at', getattr(meta, 'created_at', '')),
                    run_slug=slug,
                    priority="medium",
                ))
    except Exception:
        pass

    return tasks


@router.post("/approve", response_model=ActionResult)
async def approve_task(
    data: ApprovalAction,
    auth_info: dict = Depends(require_auth),
):
    """Görevi onayla (human_approved)."""
    engine = get_engine()

    # Extract slug from task ID
    if data.task_id.startswith('hitl-'):
        slug = data.task_id[5:]
        try:
            engine.run_manager.update_state(slug, _get_approved_state(slug, engine))
            return ActionResult(success=True, message=f"Run '{slug}' approved")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail=f"Task '{data.task_id}' not found")


@router.post("/reject", response_model=ActionResult)
async def reject_task(
    data: ApprovalAction,
    auth_info: dict = Depends(require_auth),
):
    """Görevi reddet (changes_requested)."""
    engine = get_engine()

    if data.task_id.startswith('hitl-'):
        slug = data.task_id[5:]
        try:
            engine.run_manager.update_state(slug, _get_rejected_state(slug, engine))
            return ActionResult(success=True, message=f"Run '{slug}' changes requested")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail=f"Task '{data.task_id}' not found")


@router.post("/pause", response_model=ActionResult)
async def pause_task(
    data: PauseInput,
    auth_info: dict = Depends(require_admin),
):
    """Görevi duraklat."""
    if data.task_id.startswith('hitl-'):
        slug = data.task_id[5:]
        engine = get_engine()
        try:
            engine.run_manager.update_state(slug, 'paused')
            return ActionResult(success=True, message=f"Run '{slug}' paused")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail=f"Task '{data.task_id}' not found")


@router.get("/budget", response_model=BudgetStatus)
async def get_budget(auth_info: dict = Depends(require_auth)):
    """Bütçe durumunu getir."""
    engine = get_engine()
    try:
        budget = engine.budget
        return BudgetStatus(
            total_cost_usd=budget.total_cost if hasattr(budget, 'total_cost') else 0.0,
            budget_usage_ratio=budget.usage_ratio if hasattr(budget, 'usage_ratio') else 0.0,
            soft_limit_usd=budget.soft_limit if hasattr(budget, 'soft_limit') else 1000.0,
            hard_limit_usd=budget.hard_limit if hasattr(budget, 'hard_limit') else 1500.0,
            llm_calls=budget.llm_calls if hasattr(budget, 'llm_calls') else 0,
        )
    except Exception:
        return BudgetStatus()


@router.post("/budget/reset", response_model=ActionResult)
async def reset_budget(auth_info: dict = Depends(require_admin)):
    """Bütçe sayaçlarını sıfırla."""
    engine = get_engine()
    try:
        engine.budget.reset()
        return ActionResult(success=True, message="Budget reset successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_model=HumanDashboard)
async def get_human_dashboard(auth_info: dict = Depends(require_auth)):
    """İnsan gözetim dashboard verisi."""
    engine = get_engine()
    approvals = await list_approvals(auth_info)
    budget = await get_budget(auth_info)

    return HumanDashboard(
        pending_approvals=len(approvals),
        active_runs_human=len(approvals),
        budget_status=budget,
    )


def _get_approved_state(slug: str, engine) -> str:
    """Onay sonrası gidilecek state."""
    run = engine.run_manager.get_run(slug)
    if not run:
        return 'approved'
    meta = run.meta if hasattr(run, 'meta') else run
    state = getattr(meta, 'state', '')
    mapping = {
        'draft_review': 'approved',
        'review': 'release',
        'published': 'archived',
        'correction_needed': 'published',
        'peer_review': 'paper_draft',
        'blocked': 'development',
    }
    return mapping.get(state, 'approved')


def _get_rejected_state(slug: str, engine) -> str:
    """Red sonrası gidilecek state."""
    run = engine.run_manager.get_run(slug)
    if not run:
        return 'drafting'
    meta = run.meta if hasattr(run, 'meta') else run
    state = getattr(meta, 'state', '')
    mapping = {
        'draft_review': 'drafting',
        'review': 'iteration',
        'peer_review': 'paper_draft',
        'blocked': 'development',
    }
    return mapping.get(state, 'drafting')
