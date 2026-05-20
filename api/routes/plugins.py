"""Plugin route'ları."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_engine, require_auth, require_admin
from api.models import Plugin, MarketplacePlugin, ActionResult

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


@router.get("", response_model=list[Plugin])
async def list_plugins(auth_info: dict = Depends(require_auth)):
    """Yüklü plugin'leri listele."""
    engine = get_engine()
    plugins = []
    try:
        registry = engine.plugin_registry if hasattr(engine, 'plugin_registry') else None
        if registry:
            for p in registry.list_plugins():
                plugins.append(Plugin(
                    id=p.id if hasattr(p, 'id') else '',
                    name=p.name if hasattr(p, 'name') else '',
                    version=p.version if hasattr(p, 'version') else '0.0.0',
                    type=p.plugin_type.value if hasattr(p, 'plugin_type') else 'INTEGRATION',
                    status=p.status.value if hasattr(p, 'status') else 'disabled',
                    description=p.description if hasattr(p, 'description') else None,
                    author=p.author if hasattr(p, 'author') else None,
                    dependencies=p.dependencies if hasattr(p, 'dependencies') else [],
                ))
    except Exception:
        pass
    return plugins


@router.get("/marketplace", response_model=list[MarketplacePlugin])
async def list_marketplace(auth_info: dict = Depends(require_auth)):
    """Plugin market-place listesi."""
    return [
        MarketplacePlugin(id="jira-adapter", name="Jira Adapter", version="2.3.0",
                          type="ADAPTER", rating=4.7, downloads=1247,
                          description="Jira issue tracking integration for software pipelines"),
        MarketplacePlugin(id="github-actions-hook", name="GitHub Actions Hook", version="1.1.0",
                          type="HOOK", rating=4.5, downloads=893,
                          description="Trigger GitHub Actions on state transitions"),
        MarketplacePlugin(id="llama-llm", name="Ollama LLM Provider", version="0.8.0",
                          type="LLM_PROVIDER", rating=4.2, downloads=421,
                          description="Local Ollama model provider"),
        MarketplacePlugin(id="datadog-metrics", name="Datadog Metrics", version="1.5.1",
                          type="INTEGRATION", rating=4.6, downloads=734,
                          description="Export engine metrics to Datadog"),
    ]


@router.post("/{plugin_id}/enable", response_model=ActionResult)
async def enable_plugin(
    plugin_id: str,
    auth_info: dict = Depends(require_admin),
):
    """Plugin'i etkinleştir."""
    engine = get_engine()
    try:
        registry = engine.plugin_registry if hasattr(engine, 'plugin_registry') else None
        if registry:
            registry.enable_plugin(plugin_id)
        return ActionResult(success=True, message=f"Plugin '{plugin_id}' enabled")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_id}/disable", response_model=ActionResult)
async def disable_plugin(
    plugin_id: str,
    auth_info: dict = Depends(require_admin),
):
    """Plugin'i devre dışı bırak."""
    engine = get_engine()
    try:
        registry = engine.plugin_registry if hasattr(engine, 'plugin_registry') else None
        if registry:
            registry.disable_plugin(plugin_id)
        return ActionResult(success=True, message=f"Plugin '{plugin_id}' disabled")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
