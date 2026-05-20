"""Config route'ları — engine yapılandırma."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_engine, require_admin

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("", response_model=dict)
async def get_config(auth_info: dict = Depends(require_admin)):
    """Engine yapılandırmasını getir."""
    engine = get_engine()
    config = engine.config if hasattr(engine, 'config') else None
    if not config:
        return {}
    try:
        return {
            "data_dir": getattr(config, 'data_dir', ''),
            "log_level": getattr(config, 'log_level', 'info'),
            "budget": {
                "soft_limit_usd": getattr(config.budget, 'soft_limit_usd', 1.0) if hasattr(config, 'budget') else 1.0,
                "hard_limit_usd": getattr(config.budget, 'hard_limit_usd', 5.0) if hasattr(config, 'budget') else 5.0,
            },
            "event_store": {
                "retention_days": getattr(config.event_store, 'retention_days', 90) if hasattr(config, 'event_store') else 90,
            },
            "ai": {
                "drift_detection": getattr(engine, '_drift_detector', None) is not None,
                "skill_emergence": getattr(engine, '_skill_emergence_enabled', False),
                "auto_remediation": getattr(engine, '_auto_remediation_enabled', False),
            },
        }
    except Exception:
        return {}


@router.put("", response_model=dict)
async def update_config(
    data: dict,
    auth_info: dict = Depends(require_admin),
):
    """Engine yapılandırmasını güncelle."""
    engine = get_engine()
    try:
        # AI feature toggles
        ai_config = data.get('ai', {})
        if 'drift_detection' in ai_config:
            pass  # Already enabled/disabled via engine init
        if 'skill_emergence' in ai_config:
            engine._skill_emergence_enabled = bool(ai_config['skill_emergence'])
        if 'auto_remediation' in ai_config:
            engine._auto_remediation_enabled = bool(ai_config['auto_remediation'])
        if 'warm_agent' in ai_config:
            engine._warm_agent_enabled = bool(ai_config['warm_agent'])

        return {"success": True, "message": "Config updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
