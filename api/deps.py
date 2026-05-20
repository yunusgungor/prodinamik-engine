"""
FastAPI bağımlılıkları — engine singleton, auth middleware.

Engine, uygulama başlangıcında bir kez initialize edilir.
WebSocket oturumları dahil tüm istekler bu singleton'ı kullanır.
"""

from __future__ import annotations

import os
import time
import json
import logging
import traceback
from pathlib import Path
from typing import Optional, AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Engine imports
from engine import (
    AsyncEngine,
    AuthManager,
    ProdinamikConfig,
    RuntimeConfig,
    DegradationLevel,
    AIDriftDetector,
    DriftType,
    DriftSeverity,
    TrendDirection,
)
from engine.log import setup as setup_logging, get_logger
from engine.ratelimit import RateLimiter, AuthRateLimiter

logger = logging.getLogger("prodinamik.api")

# ── Global Engine Singleton ──

_engine: Optional[AsyncEngine] = None
_auth: Optional[AuthManager] = None
_limiter: Optional[RateLimiter] = None
_started_at: float = 0.0


def get_engine() -> AsyncEngine:
    """Engine singleton'ını döndürür. İlk çağrıda initialize eder."""
    global _engine, _auth, _limiter, _started_at
    if _engine is None:
        # Engine yapılandırması
        hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
        data_dir = os.path.join(hermes_home, "prodinamik")

        config = ProdinamikConfig(
            data_dir=data_dir,
        )

        runtime_config = RuntimeConfig(
            poll_interval=5.0,
            health_check_interval=60.0,
            auto_recover=True,
            enable_timeout_watcher=True,
        )

        _engine = AsyncEngine(config=config, runtime_config=runtime_config)

        # Auth manager
        auth_path = os.path.join(data_dir, "auth")
        _auth = AuthManager(base_path=auth_path)

        # Rate limiter (100 req/s, 50 burst)
        _limiter = RateLimiter(rate=100.0, burst=50.0)
        if hasattr(_engine, '_rate_limiter'):
            _engine._rate_limiter = _limiter

        _started_at = time.time()
        logger.info(f"Engine initialized (data_dir={data_dir})")

    return _engine


def get_auth() -> AuthManager:
    """Auth manager singleton."""
    get_engine()  # ensure engine is initialized
    return _auth


def get_started_at() -> float:
    return _started_at


def get_limiter() -> RateLimiter:
    """Rate limiter singleton."""
    get_engine()
    return _limiter


# ── Auth Dependency ──

security = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """API key auth dependency. Returns user info dict with 'role' key."""
    # Skip auth for health endpoint
    if request.url.path in ("/healthz", "/health", "/api/healthz", "/api/health"):
        return {"role": "admin", "name": "health-check"}

    # WebSocket auth via query param
    if not credentials and request.url.path.startswith("/ws/"):
        token = request.query_params.get("token")
        if token:
            auth = get_auth()
            result = auth.validate_key(token)
            if result and result.valid:
                return {"role": result.role or "readonly", "name": result.name or "unknown", "key_id": result.key_id or ""}
        raise HTTPException(status_code=401, detail="Unauthorized: valid token required")

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Use Authorization: Bearer pdmk_xxx",
        )

    auth = get_auth()
    result = auth.validate_key(credentials.credentials)
    if not result or not result.valid:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Rate limit check
    limiter = get_limiter()
    if limiter and result.key_id:
        allowed, wait = limiter.check(result.key_id, cost=1.0)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limited. Try again in {wait:.1f}s",
                headers={"Retry-After": str(int(wait))},
            )

    return {"role": result.role or "readonly", "name": result.name or "unknown", "key_id": result.key_id or ""}


async def require_admin(auth_info: dict = Depends(require_auth)) -> dict:
    """Require admin role."""
    if auth_info.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return auth_info


# ── WebSocket Connection Manager ──

class ConnectionManager:
    """WebSocket bağlantılarını yönetir. Kanal bazında odalar."""

    def __init__(self):
        self._connections: dict[str, list] = {}  # channel → [websocket, ...]

    async def connect(self, channel: str, websocket):
        if channel not in self._connections:
            self._connections[channel] = []
        self._connections[channel].append(websocket)
        logger.debug(f"WS connected: {channel} (total: {len(self._connections[channel])})")

    async def disconnect(self, channel: str, websocket):
        if channel in self._connections:
            self._connections[channel] = [ws for ws in self._connections[channel] if ws != websocket]
            if not self._connections[channel]:
                del self._connections[channel]

    async def broadcast(self, channel: str, message: dict):
        """Broadcast a message to all connections on a channel."""
        if channel not in self._connections:
            return
        dead = []
        for ws in self._connections[channel]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(channel, ws)

    async def broadcast_all(self, message: dict):
        """Broadcast to all channels."""
        for channel in list(self._connections.keys()):
            await self.broadcast(channel, message)


manager = ConnectionManager()


# ── Engine lifecycle helper ──

def start_engine_background():
    """Engine background tasks'ını başlatır (timeout watcher, warm agent)."""
    engine = get_engine()
    try:
        import asyncio
        import threading

        loop = asyncio.new_event_loop()

        # Setup default tasks before thread starts
        engine._agent_coordinator.setup_default_tasks(engine)

        async def _start():
            await engine.start()

        def _run_loop():
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_start())
                loop.run_forever()
            except Exception as e:
                logger.error(f"Engine background loop failed: {e}")
                logger.error(traceback.format_exc())

        thread = threading.Thread(target=_run_loop, daemon=True, name="prodinamik-engine")
        thread.start()
        logger.info("Engine background thread started")
        return thread
    except Exception as e:
        logger.warning(f"Could not start engine background thread: {e}")
        return None
