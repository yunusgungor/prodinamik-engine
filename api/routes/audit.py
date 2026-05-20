"""Audit log route'ları."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_engine, require_auth
from api.models import AuditEntry

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntry])
async def list_audit_log(
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    auth_info: dict = Depends(require_auth),
):
    """Audit log kayıtlarını getir."""
    engine = get_engine()

    entries = []
    try:
        audit = engine.audit_log if hasattr(engine, 'audit_log') else None
        if audit:
            raw = audit.query(limit=limit, offset=offset)
            for item in raw:
                entries.append(AuditEntry(
                    id=getattr(item, 'id', None),
                    event_type=getattr(item, 'event_type', 'unknown'),
                    timestamp=getattr(item, 'timestamp', ''),
                    data=getattr(item, 'data', None),
                    summary=getattr(item, 'summary', None),
                    actor=getattr(item, 'actor', None),
                ))
    except Exception:
        pass

    return entries
