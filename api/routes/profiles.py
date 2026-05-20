"""Profile route'ları."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_engine, require_auth
from api.models import Profile, ProfileDetail, ProfileState, ProfileTransition

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("", response_model=list[Profile])
async def list_profiles(auth_info: dict = Depends(require_auth)):
    """Kullanılabilir profilleri listele."""
    engine = get_engine()

    profiles = []
    seen = set()

    # RunManager'dan mevcut run'ları analiz et
    try:
        runs = engine.run_manager.list_runs(limit=1000)
        profile_run_counts = {}
        for r in runs:
            meta = r.meta if hasattr(r, 'meta') else r
            pname = meta.profile if hasattr(meta, 'profile') else ''
            profile_run_counts[pname] = profile_run_counts.get(pname, 0) + 1
    except Exception:
        profile_run_counts = {}

    # Built-in profiles from engine
    built_in = [
        ("software", "Software", "Software development pipeline (spec → prototyping → iteration → review → release)"),
        ("content", "Content", "Content production pipeline (captured → ... → published → archived)"),
        ("haber", "Haber", "News verification pipeline"),
        ("devcycle", "DevCycle", "Development methodology pipeline"),
        ("research", "Research", "Research workflow pipeline"),
        ("design", "Design", "Design production pipeline"),
    ]

    for pid, name, desc in built_in:
        profiles.append(Profile(
            id=pid,
            name=name,
            description=desc,
            state_count=len(_get_profile_states(pid)),
            transition_count=len(_get_profile_transitions(pid)),
            active_runs=profile_run_counts.get(pid, 0),
        ))

    return profiles


def _get_profile_states(profile_id: str) -> list[str]:
    """Get state list for a profile."""
    states = {
        "software": ["spec", "prototyping", "iteration", "review", "release"],
        "content": ["captured", "decide_route", "idea_review", "brief_ready", "drafting", "verification", "draft_review", "approved", "published", "archived"],
        "haber": ["captured", "fact_checking", "cross_verified", "published", "correction_needed"],
        "devcycle": ["brief", "prototyping", "development", "drift_resolution", "review", "blocked"],
        "research": ["topic_selected", "literature_review", "hypothesis", "experiment_design", "paper_draft", "peer_review"],
        "design": ["brief", "research", "sketch", "wireframe", "mockup", "prototype", "review"],
    }
    return states.get(profile_id, [])


def _get_profile_transitions(profile_id: str) -> list[tuple[str, str, str]]:
    """Get (from, to, label) transitions for a profile."""
    transitions = {
        "software": [
            ("spec", "prototyping", "start"),
            ("prototyping", "iteration", "prototype_ready"),
            ("iteration", "iteration", "iterate"),
            ("iteration", "review", "done"),
            ("review", "release", "approved"),
            ("review", "iteration", "changes"),
        ],
        "content": [
            ("captured", "decide_route", "captured"),
            ("decide_route", "idea_review", "route_chosen"),
            ("idea_review", "brief_ready", "approved"),
            ("brief_ready", "drafting", "brief_approved"),
            ("drafting", "verification", "draft_done"),
            ("verification", "draft_review", "verified"),
            ("draft_review", "approved", "approved"),
            ("draft_review", "drafting", "changes"),
            ("approved", "published", "publish"),
            ("published", "archived", "archive"),
        ],
        "haber": [
            ("captured", "fact_checking", "check"),
            ("fact_checking", "cross_verified", "verified"),
            ("cross_verified", "published", "publish"),
            ("published", "correction_needed", "error_found"),
            ("correction_needed", "fact_checking", "re_check"),
        ],
    }
    raw = transitions.get(profile_id, [])
    return [ProfileTransition(from_state=f, to_state=t, label=l) for f, t, l in raw]


@router.get("/{profile_id}", response_model=ProfileDetail)
async def get_profile(
    profile_id: str,
    auth_info: dict = Depends(require_auth),
):
    """Profil detayını getir (state machine yapısı)."""
    state_names = _get_profile_states(profile_id)
    if not state_names:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

    transitions_raw = _get_profile_transitions(profile_id)

    # State types
    type_map = {
        "captured": "initial",
        "spec": "initial",
        "brief": "initial",
        "topic_selected": "initial",
        "archived": "terminal",
        "release": "terminal",
        "done": "terminal",
        "draft_review": "pause",
        "review": "pause",
        "published": "pause",
        "correction_needed": "pause",
        "peer_review": "pause",
        "blocked": "pause",
    }

    states = []
    for s in state_names:
        stype = type_map.get(s, "intermediate")
        states.append(ProfileState(name=s, type=stype))

    return ProfileDetail(
        id=profile_id,
        name=profile_id.capitalize() if profile_id != "devcycle" else "DevCycle",
        description=f"{profile_id} pipeline profile",
        state_count=len(states),
        transition_count=len(transitions_raw),
        states=states,
        transitions=transitions_raw,
    )


@router.get("/{profile_id}/states", response_model=list[ProfileState])
async def get_profile_states(
    profile_id: str,
    auth_info: dict = Depends(require_auth),
):
    """Profilin state listesini döndür."""
    state_names = _get_profile_states(profile_id)
    if not state_names:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    return [ProfileState(name=s) for s in state_names]
