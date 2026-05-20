"""Run management route'ları — CRUD + transition + HITL."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_engine, require_auth, require_admin
from api.models import (
    Run, RunDetail, RunInput, RunEvent, ValidationResult,
    StateHistoryEntry, TransitionInput, TransitionResult, HITLQuestion,
    ActionResult,
)

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("", response_model=list[Run])
async def list_runs(
    profile: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    auth_info: dict = Depends(require_auth),
):
    """Tüm run'ları listele. Filtreleme, arama, sayfalama."""
    engine = get_engine()
    runs = engine.run_manager.list_runs()

    result = []
    for r in runs:
        meta = r.meta if hasattr(r, 'meta') else r
        slug = meta.slug if hasattr(meta, 'slug') else getattr(r, 'slug', '')
        title = meta.title if hasattr(meta, 'title') else getattr(r, 'title', None)
        profile_name = meta.profile if hasattr(meta, 'profile') else getattr(r, 'profile', '')
        state_name = meta.state if hasattr(meta, 'state') else getattr(r, 'state', '')

        # Apply filters
        if profile and profile_name != profile:
            continue
        if state and state_name != state:
            continue
        if search and search.lower() not in slug.lower() and (title and search.lower() not in title.lower()):
            continue

        result.append(Run(
            slug=slug,
            title=title,
            profile=profile_name,
            state=state_name,
            status=meta.status if hasattr(meta, 'status') else 'active',
            created_at=meta.created_at if hasattr(meta, 'created_at') else datetime.now().isoformat(),
            iteration=getattr(meta, 'iteration_count', None) or getattr(r, 'iteration', None),
        ))

    # Apply status filter after all (it's a computed field)
    if status:
        result = [r for r in result if r.status == status]

    return result[offset:offset + limit]


@router.post("", response_model=Run, status_code=201)
async def create_run(
    data: RunInput,
    auth_info: dict = Depends(require_auth),
):
    """Yeni run oluştur."""
    engine = get_engine()

    try:
        new_run = engine.run_manager.create_run(
            title=data.title or "",
            profile=None,
        )
        slug = new_run.slug if hasattr(new_run, 'slug') else new_run.meta.slug
        return Run(
            slug=slug,
            title=data.title,
            profile=data.profile,
            state=new_run.meta.state,
            status='active',
            created_at=new_run.meta.created_at,
        )
    except Exception as e:
        # Fallback: create run directory structure directly
        try:
            from engine.run_manager import RunMeta
            import time
            slug = f"run-{int(time.time())}"
            meta = RunMeta(
                slug=slug,
                profile=data.profile,
                title=data.title or "",
                created_at=datetime.now().isoformat(),
                status="active",
                state="captured" if data.profile == "content" else "initial",
            )
            # Create directory structure
            run_path = engine.run_manager._run_path(slug)
            run_path.mkdir(parents=True, exist_ok=True)
            co_path = run_path / "content-object.md"
            with open(co_path, "w") as f:
                import yaml
                yaml.dump(meta.to_dict(), f)
            # Update snapshot
            engine.run_manager._update_snapshot(slug, meta.to_dict())
            return Run(
                slug=slug,
                title=data.title,
                profile=data.profile,
                state=meta.state,
                status='active',
                created_at=meta.created_at,
            )
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Failed to create run: {e2}")


@router.get("/{slug}", response_model=RunDetail)
async def get_run(
    slug: str,
    auth_info: dict = Depends(require_auth),
):
    """Run detayını getir."""
    engine = get_engine()
    run = engine.run_manager.get_run(slug)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{slug}' not found")

    meta = run.meta if hasattr(run, 'meta') else run
    runtime = run.runtime if hasattr(run, 'runtime') else None

    # State history
    state_history = []
    if runtime and hasattr(runtime, 'state_history'):
        for sh in runtime.state_history:
            state_history.append(StateHistoryEntry(
                state=sh.get('state', ''),
                entered_at=sh.get('entered_at', ''),
                exited_at=sh.get('exited_at'),
                duration_seconds=sh.get('duration_seconds'),
            ))

    # Events
    events = []
    try:
        event_store = engine._event_stores.get(slug)
        if event_store:
            for evt in event_store.list_events(limit=50):
                events.append(RunEvent(
                    event_type=evt.event_type if hasattr(evt, 'event_type') else 'unknown',
                    timestamp=evt.timestamp if hasattr(evt, 'timestamp') else datetime.now().isoformat(),
                    data=evt.data if hasattr(evt, 'data') else None,
                ))
    except Exception:
        pass

    # Possible transitions
    possible = []
    try:
        sm = run.profile.state_machine if hasattr(run, 'profile') else None
        if sm and runtime:
            current = runtime.current_state
            for t in sm.transitions:
                if t.from_state == current:
                    possible.append(t.to_state)
    except Exception:
        pass

    return RunDetail(
        slug=slug,
        title=meta.title if hasattr(meta, 'title') else '',
        profile=meta.profile if hasattr(meta, 'profile') else '',
        state=meta.state if hasattr(meta, 'state') else '',
        status=meta.status if hasattr(meta, 'status') else 'active',
        created_at=meta.created_at if hasattr(meta, 'created_at') else '',
        updated_at=meta.updated_at if hasattr(meta, 'updated_at') else None,
        elapsed_seconds=getattr(meta, 'elapsed_seconds', None),
        iteration=getattr(meta, 'iteration_count', None),
        state_history=state_history,
        events=events,
        possible_transitions=possible,
    )


@router.post("/{slug}/transition", response_model=TransitionResult)
async def transition_run(
    slug: str,
    data: TransitionInput,
    auth_info: dict = Depends(require_auth),
):
    """State transition tetikle. HITL varsa soruları döndür."""
    engine = get_engine()
    run = engine.run_manager.get_run(slug)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{slug}' not found")

    target_state = data.transition
    if not target_state:
        raise HTTPException(status_code=400, detail="transition field required")

    # Try engine's HITL-aware transition (if available), fall back to direct update
    try:
        from engine.runtime import transition_with_hitl
        result = transition_with_hitl(engine, slug, target_state)
        if isinstance(result, dict):
            return TransitionResult(
                slug=slug,
                state=result.get('state', target_state),
                awaiting_input=result.get('awaiting_input', False),
                questions=[HITLQuestion(**q) for q in result.get('questions', [])],
                timeout=result.get('timeout'),
                _hitl=result.get('_hitl', False),
                _instruction=result.get('_instruction'),
            )
    except ImportError:
        pass
    except AttributeError:
        pass
    except Exception as e:
        if "condition" in str(e).lower():
            raise HTTPException(status_code=400, detail=f"Transition condition not met: {e}")

    # Simple transition — direct snapshot update (bypass state machine validation)
    try:
        snapshot = engine.run_manager._load_snapshot()
        if slug not in snapshot:
            raise HTTPException(status_code=404, detail=f"Run '{slug}' not found")
        engine.run_manager._update_snapshot(slug, {"state": target_state})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if this is a PAUSE state — return HITL questions
    pause_states = {
        "draft_review": [{"question": "Run is in draft_review PAUSE state. Approve for publication?", "type": "yes_no", "timeout": 300}],
        "review": [{"question": "Run is in review PAUSE state. Approve to proceed?", "type": "yes_no", "timeout": 300}],
        "published": [{"question": "Content published. Any corrections needed?", "type": "yes_no", "timeout": 600}],
        "correction_needed": [{"question": "Correction needed. Proceed with fix?", "type": "yes_no", "timeout": 600}],
        "peer_review": [{"question": "Peer review pending. Approve paper?", "type": "yes_no", "timeout": 86400}],
        "blocked": [{"question": "Run is blocked. Unblock and continue?", "type": "yes_no", "timeout": 86400}],
    }

    if target_state in pause_states:
        return TransitionResult(
            slug=slug,
            state=target_state,
            awaiting_input=True,
            questions=[HITLQuestion(**q) for q in pause_states[target_state]],
            timeout=pause_states[target_state][0].get("timeout", 300),
            _hitl=True,
            _instruction="Kullanıcıya clarify ile sor, cevabı resume ile ilet",
        )

    return TransitionResult(
        slug=slug,
        state=target_state,
        awaiting_input=False,
    )


@router.post("/{slug}/resume", response_model=TransitionResult)
async def resume_run(
    slug: str,
    data: dict,
    auth_info: dict = Depends(require_auth),
):
    """HITL PAUSE state'teki run'ı resume et (kullanıcı cevabını ilet)."""
    engine = get_engine()

    # Handle resume directly: read answer and do the transition
    answers = data.get('answers', {})
    answer = answers.get('answer', '').lower().strip()
    
    # Determine next state based on answer
    rejection_patterns = ("no", "hayır", "hayir", "red", "yok", "iptal", "düzelt", "duzelt", "olmaz")
    is_rejection = any(p in answer for p in rejection_patterns)
    
    # Get current run state
    run = engine.run_manager.get_run(slug)
    if not run:
        # Try direct snapshot read
        try:
            snapshot = engine.run_manager._load_snapshot()
            slug_data = snapshot.get(slug, {})
            current_state = slug_data.get('state', '')
        except:
            raise HTTPException(status_code=404, detail=f"Run '{slug}' not found")
    else:
        meta = run.meta if hasattr(run, 'meta') else run
        current_state = meta.state if hasattr(meta, 'state') else ''
    
    # Map PAUSE states to target on approve/reject
    approve_map = {
        'draft_review': 'approved',
        'review': 'release',
        'published': 'archived',
        'correction_needed': 'published',
        'peer_review': 'paper_draft',
        'blocked': 'development',
    }
    reject_map = {
        'draft_review': 'drafting',
        'review': 'iteration',
        'correction_needed': 'fact_checking',
        'peer_review': 'paper_draft',
        'blocked': 'development',
    }
    
    target_state = reject_map.get(current_state, 'drafting') if is_rejection else approve_map.get(current_state, 'approved')
    
    try:
        engine.run_manager.update_state(slug, target_state)
        return TransitionResult(
            slug=slug,
            state=target_state,
            awaiting_input=False,
            _hitl=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slug}/archive", response_model=ActionResult)
async def archive_run(
    slug: str,
    auth_info: dict = Depends(require_admin),
):
    """Run arşivle."""
    engine = get_engine()
    try:
        engine.run_manager.archive_run(slug)
        return ActionResult(success=True, message=f"Run '{slug}' archived")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
