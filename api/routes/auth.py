"""Auth route'ları — API key yönetimi."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_auth, require_auth, require_admin
from api.models import APIKeyInfo, APIKeyCreate, APIKeyCreated

router = APIRouter(prefix="/api/v1/auth", tags=["security"])


@router.get("/me", response_model=dict)
async def get_current_auth(auth_info: dict = Depends(require_auth)):
    """Mevcut auth bilgisini döndür — login doğrulaması için kullanılır."""
    return {
        "role": auth_info.get("role", "readonly"),
        "name": auth_info.get("name", "unknown"),
        "key_id": auth_info.get("key_id", ""),
    }


@router.get("/keys", response_model=list[APIKeyInfo])
async def list_api_keys(auth_info: dict = Depends(require_admin)):
    """Tüm API key'leri listele (sadece admin)."""
    auth = get_auth()
    keys = []
    try:
        for k in auth.list_keys():
            keys.append(APIKeyInfo(
                id=k.get('key_id', k.get('id', '')),
                name=k.get('name', ''),
                role=k.get('role', 'user'),
                created_at=k.get('created_at', ''),
                expires_at=k.get('expires_at', None),
                last_used=k.get('last_used_at', None),
                enabled=k.get('enabled', True),
            ))
    except Exception:
        pass
    return keys


@router.post("/keys", response_model=APIKeyCreated, status_code=201)
async def create_api_key(
    data: APIKeyCreate,
    auth_info: dict = Depends(require_admin),
):
    """Yeni API key oluştur."""
    auth = get_auth()
    try:
        key_id, raw_key = auth.create_key(name=data.name, role=data.role, expires_in_days=data.expires_in_days)
        return APIKeyCreated(
            id=key_id,
            name=data.name,
            role=data.role,
            key=raw_key,
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=(datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)).isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/keys/{key_id}", response_model=dict)
async def revoke_api_key(
    key_id: str,
    auth_info: dict = Depends(require_admin),
):
    """API key iptal et."""
    auth = get_auth()
    try:
        auth.revoke_key(key_id)
        return {"success": True, "message": f"Key '{key_id}' revoked"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
