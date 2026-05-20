"""Rate limit route'ları — token bucket istatistikleri."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_limiter, require_auth

router = APIRouter(prefix="/api/v1/ratelimit", tags=["operations"])


@router.get("/stats", response_model=dict)
async def get_rate_limit_stats(auth_info: dict = Depends(require_auth)):
    """Rate limiter istatistiklerini döndür."""
    limiter = get_limiter()
    if limiter:
        stats = limiter.stats()
        # Add per-key breakdown if admin
        if auth_info.get("role") == "admin":
            return stats
        # Non-admin: return summary only
        return {
            "rate": stats.get("rate", 100),
            "burst": stats.get("burst", 50),
            "total_allowed": stats.get("total_allowed", 0),
            "total_denied": stats.get("total_denied", 0),
        }
    return {
        "rate": 100,
        "burst": 50,
        "total_allowed": 0,
        "total_denied": 0,
    }
