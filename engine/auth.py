"""Prodinamik Engine v1.1 — Authentication & Access Control

API key management with role-based access control (RBAC).
Supports admin, user, and readonly roles with decorator-based protection.

Usage:
    from engine.auth import AuthManager
    auth = AuthManager(base_path="./data/auth")
    key = auth.create_key("deploy-bot", role="admin")
    result = auth.validate_key(key)
    # result.valid=True, result.role="admin", result.name="deploy-bot"
"""

import os
import json
import time
import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any
from functools import wraps


# ──────────────────────────────────────────────
# Data Types
# ──────────────────────────────────────────────

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_READONLY = "readonly"
VALID_ROLES = {ROLE_ADMIN, ROLE_USER, ROLE_READONLY}

ROLE_HIERARCHY = {
    ROLE_READONLY: 0,
    ROLE_USER: 1,
    ROLE_ADMIN: 2,
}


@dataclass
class APIKey:
    """API key with metadata"""
    key_id: str
    key_hash: str          # SHA-256 hash of the raw key
    name: str
    role: str = ROLE_USER
    created_at: str = ""
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "APIKey":
        return cls(
            key_id=d["key_id"],
            key_hash=d["key_hash"],
            name=d["name"],
            role=d.get("role", ROLE_USER),
            created_at=d.get("created_at", ""),
            expires_at=d.get("expires_at"),
            last_used_at=d.get("last_used_at"),
            enabled=d.get("enabled", True),
            metadata=d.get("metadata", {}),
        )


@dataclass
class AuthResult:
    """Result of a key validation"""
    valid: bool = False
    role: str = ""
    name: str = ""
    key_id: str = ""
    error: str = ""


# ──────────────────────────────────────────────
# Auth Manager
# ──────────────────────────────────────────────


class AuthManager:
    """API key store and validation engine.

    Stores keys as JSON in base_path/keys/{key_id}.json.
    Raw keys are only shown once on creation (like GitHub tokens).
    """

    def __init__(self, base_path: str = "./data/auth"):
        self.base_path = Path(base_path)
        self.keys_dir = self.base_path / "keys"
        self._lock = threading.Lock()
        self._cache: Dict[str, APIKey] = {}

        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    # ──────────────────────────────────────
    # Key Management
    # ──────────────────────────────────────

    def create_key(self, name: str, role: str = ROLE_USER,
                   expires_in_days: Optional[int] = None,
                   metadata: dict = None) -> tuple:
        """Generate a new API key.

        Returns (key_id, raw_key) — raw_key is shown ONCE.
        """
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}. Valid: {VALID_ROLES}")

        key_id = self._generate_id(name)
        raw_key = self._generate_key()
        key_hash = self._hash_key(raw_key)

        now = datetime.now(timezone.utc).isoformat()
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now(timezone.utc) +
                         timedelta(days=expires_in_days)).isoformat()

        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            role=role,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        with self._lock:
            self._save_key(api_key)
            self._cache[key_id] = api_key

        return key_id, raw_key

    def validate_key(self, raw_key: str) -> AuthResult:
        """Validate a raw API key. Returns AuthResult."""
        if not raw_key or not raw_key.startswith("pdmk_"):
            return AuthResult(valid=False, error="Invalid key format")

        key_hash = self._hash_key(raw_key)

        with self._lock:
            for key_id, cached in self._cache.items():
                if cached.key_hash == key_hash:
                    # Check expiry
                    if cached.expires_at:
                        expires = datetime.fromisoformat(cached.expires_at)
                        if expires < datetime.now(timezone.utc):
                            return AuthResult(valid=False, error="Key expired")
                    # Check enabled
                    if not cached.enabled:
                        return AuthResult(valid=False, error="Key disabled")

                    # Update last_used
                    cached.last_used_at = datetime.now(timezone.utc).isoformat()
                    self._save_key(cached)

                    return AuthResult(
                        valid=True,
                        role=cached.role,
                        name=cached.name,
                        key_id=cached.key_id,
                    )

        return AuthResult(valid=False, error="Key not found")

    def list_keys(self) -> List[dict]:
        """List all keys (without hashes)"""
        with self._lock:
            return [
                {"key_id": k.key_id, "name": k.name, "role": k.role,
                 "created_at": k.created_at, "expires_at": k.expires_at,
                 "enabled": k.enabled, "last_used_at": k.last_used_at}
                for k in self._cache.values()
            ]

    def revoke_key(self, key_id: str) -> bool:
        """Revoke (disable) a key"""
        with self._lock:
            key = self._cache.get(key_id)
            if not key:
                return False
            key.enabled = False
            self._save_key(key)
            return True

    def get_key(self, key_id: str) -> Optional[dict]:
        """Get key info (without hash)"""
        with self._lock:
            key = self._cache.get(key_id)
            if not key:
                return None
            return {
                "key_id": key.key_id,
                "name": key.name,
                "role": key.role,
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "enabled": key.enabled,
                "last_used_at": key.last_used_at,
                "metadata": key.metadata,
            }

    # ──────────────────────────────────────
    # Authorization Decorators
    # ──────────────────────────────────────

    @staticmethod
    def require_role(min_role: str = ROLE_USER):
        """Decorator: requires minimum role level to call function.

        Usage:
            @AuthManager.require_role("admin")
            def delete_run(slug):
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract auth_result from kwargs or first arg
                auth = kwargs.get("auth_result")
                if auth is None:
                    for arg in args:
                        if isinstance(arg, AuthResult):
                            auth = arg
                            break
                if auth is None:
                    raise PermissionError("No auth_result provided")
                if not auth.valid:
                    raise PermissionError("Authentication required")
                if ROLE_HIERARCHY.get(auth.role, -1) < ROLE_HIERARCHY.get(min_role, 0):
                    raise PermissionError(
                        f"Role '{auth.role}' insufficient. Need '{min_role}'"
                    )
                return func(*args, **kwargs)
            return wrapper
        return decorator

    # ──────────────────────────────────────
    # Internal
    # ──────────────────────────────────────

    @staticmethod
    def _generate_id(name: str) -> str:
        """Generate a unique key ID"""
        name_slug = name.lower().replace(" ", "-").replace("_", "-")[:20]
        suffix = secrets.token_hex(4)
        return f"{name_slug}-{suffix}"

    @staticmethod
    def _generate_key() -> str:
        """Generate a raw API key (pdmk_ prefix)"""
        return "pdmk_" + secrets.token_hex(24)

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """SHA-256 hash of raw key"""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def _save_key(self, key: APIKey):
        """Persist key to disk"""
        key_path = self.keys_dir / f"{key.key_id}.json"
        data = key.to_dict()
        data["key_hash"] = key.key_hash
        key_path.write_text(json.dumps(data, indent=2))

    def _load_cache(self):
        """Load all keys from disk into cache"""
        if not self.keys_dir.exists():
            return
        for f in sorted(self.keys_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                key = APIKey.from_dict(data)
                self._cache[key.key_id] = key
            except (json.JSONDecodeError, KeyError):
                continue


# ──────────────────────────────────────────────
# AuthResult convenience for CLI
# ──────────────────────────────────────────────

def get_auth_from_header(headers: dict, auth_manager: AuthManager) -> AuthResult:
    """Extract and validate API key from HTTP Authorization header"""
    auth_header = headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_key = auth_header[7:]
        return auth_manager.validate_key(raw_key)
    # Also check X-API-Key header
    api_key = headers.get("X-API-Key", "")
    if api_key:
        return auth_manager.validate_key(api_key)
    return AuthResult(valid=False, error="No authentication provided")
