"""Prodinamik Engine v1.1 — HTTP Server

Built-in HTTP server with:
- /metrics      → Prometheus format metrics
- /healthz      → Health check endpoint
- /api/v1/*     → RESTful API (authenticated)
- Rate limiting + authentication middleware

Usage:
    from engine.server import ProdinamikServer
    server = ProdinamikServer(engine, port=8080)
    server.start()  # background thread
"""

import os
import json
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any
from pathlib import Path


class ProdinamikHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Prodinamik Engine"""

    # Class-level references set by server
    engine = None
    auth_manager = None
    rate_limiter = None
    server_started_at = 0.0

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/healthz" or path == "/health":
            self._handle_health()
        elif path == "/metrics":
            self._handle_metrics()
        elif path.startswith("/api/v1/"):
            self._handle_api(path)
        else:
            self._json_response(404, {"error": "Not found", "path": path})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path.startswith("/api/v1/"):
            self._handle_api(path)
        else:
            self._json_response(404, {"error": "Not found", "path": path})

    # ──────────────────────────────────────
    # Handlers
    # ──────────────────────────────────────

    def _handle_health(self):
        """Health check endpoint"""
        health = {}
        if self.engine:
            try:
                health = self.engine.health_snapshot
            except Exception:
                health = {"error": "engine unavailable"}

        health["server_uptime"] = int(time.time() - self.server_started_at)
        health["timestamp"] = datetime.now().isoformat()
        health["status"] = "ok" if health.get("health_score", 0) > 0 else "degraded"

        self._json_response(200, health)

    def _handle_metrics(self):
        """Prometheus metrics endpoint"""
        if not self.engine:
            self._text_response(503, "Engine unavailable")
            return

        try:
            from .metrics import metrics, EngineMetrics
            em = EngineMetrics(self.engine)
            em.poll()
            output = metrics.render_prometheus()
            self._text_response(200, output, content_type="text/plain; version=0.0.4")
        except Exception as e:
            self._text_response(500, f"Error: {e}")

    def _handle_api(self, path: str):
        """Authenticated API handler"""
        # Authentication
        from .auth import get_auth_from_header, AuthResult
        auth_result = get_auth_from_header(self.headers, self.auth_manager)

        if not auth_result.valid:
            self._json_response(401, {
                "error": "Unauthorized",
                "detail": auth_result.error,
            })
            return

        # Rate limiting
        if self.rate_limiter:
            allowed, wait = self.rate_limiter.check(auth_result.key_id)
            if not allowed:
                self.send_response(429)
                self.send_header("Retry-After", str(int(wait) + 1))
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Rate limited",
                    "retry_after_seconds": round(wait, 1),
                }).encode())
                return

        # Route
        try:
            if path == "/api/v1/runs":
                self._api_list_runs(auth_result)
            elif path.startswith("/api/v1/runs/") and self.command == "GET":
                slug = path.split("/api/v1/runs/")[1]
                self._api_get_run(slug, auth_result)
            elif path == "/api/v1/health":
                self._handle_health()
            elif path == "/api/v1/profiles":
                self._api_list_profiles(auth_result)
            elif path == "/api/v1/audit":
                self._api_audit_query(auth_result)
            elif path == "/api/v1/metrics":
                self._handle_metrics()
            else:
                self._json_response(404, {"error": f"API endpoint not found: {path}"})
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    # ──────────────────────────────────────
    # API Methods
    # ──────────────────────────────────────

    def _api_list_runs(self, auth_result):
        if not self.engine:
            self._json_response(503, {"error": "Engine unavailable"})
            return
        runs = self.engine.list_runs(include_archived=False)
        self._json_response(200, {
            "runs": [
                {"slug": r.slug, "profile": r.profile, "state": r.state,
                 "title": r.title, "status": r.status}
                for r in runs
            ],
            "count": len(runs),
        })

    def _api_get_run(self, slug: str, auth_result):
        if not self.engine:
            self._json_response(503, {"error": "Engine unavailable"})
            return
        run = self.engine.get_run(slug)
        if not run:
            self._json_response(404, {"error": f"Run '{slug}' not found"})
            return
        elapsed = None
        try:
            elapsed = self.engine.run_manager.get_state_elapsed(slug)
        except Exception:
            pass
        self._json_response(200, {
            "slug": run.meta.slug,
            "profile": run.meta.profile,
            "state": run.meta.state,
            "title": run.meta.title,
            "status": run.meta.status,
            "version": run.meta.version,
            "created_at": run.meta.created_at,
            "updated_at": run.meta.updated_at,
            "elapsed_seconds": elapsed,
        })

    def _api_list_profiles(self, auth_result):
        if not self.engine:
            self._json_response(503, {"error": "Engine unavailable"})
            return
        health = self.engine.health_snapshot
        self._json_response(200, {
            "profiles": health.get("profiles", []),
        })

    def _api_audit_query(self, auth_result):
        from .audit import AuditLog
        from .config import ProdinamikConfig
        cfg = ProdinamikConfig.load()
        audit_dir = Path(cfg.data_dir) / "audit"
        log = AuditLog(base_path=str(audit_dir))

        import urllib.parse
        params = urllib.parse.parse_qs(self.path.split("?")[1] if "?" in self.path else "")
        since = params.get("since", [None])[0]
        event_type = params.get("type", [None])[0]
        limit = int(params.get("limit", [20])[0])

        results = log.query(since=since, event_type=event_type, limit=limit)
        self._json_response(200, {
            "entries": [e.to_dict() for e in results],
            "count": len(results),
        })

    # ──────────────────────────────────────
    # Response Helpers
    # ──────────────────────────────────────

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, default=str)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())

    def _text_response(self, status: int, text: str, content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(text.encode())

    def log_message(self, format, *args):
        """Suppress default HTTP log (use engine logger instead)"""
        from .log import get_logger
        get_logger().debug(f"HTTP: {args[0]} {args[1]} {args[2]}")


# ──────────────────────────────────────────────
# Server
# ──────────────────────────────────────────────


class ProdinamikServer:
    """HTTP server for Prodinamik Engine.

    Runs in a background thread. Supports start/stop lifecycle.
    """

    def __init__(self, engine=None, host: str = "127.0.0.1",
                 port: int = 8080, auth_manager=None, rate_limiter=None):
        self.engine = engine
        self.host = host
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Auth + rate limit
        from .auth import AuthManager
        from .ratelimit import RateLimiter
        self.auth_manager = auth_manager or AuthManager()
        self.rate_limiter = rate_limiter or RateLimiter(rate=20, burst=40)

        # Wire handler
        self.handler_class = ProdinamikHandler
        self.handler_class.engine = self.engine
        self.handler_class.auth_manager = self.auth_manager
        self.handler_class.rate_limiter = self.rate_limiter
        self.handler_class.server_started_at = time.time()

    def start(self):
        """Start HTTP server in background thread"""
        if self._running:
            return

        self._server = HTTPServer((self.host, self.port), self.handler_class)
        self._thread = threading.Thread(target=self._serve, daemon=True,
                                         name="prodinamik-http")
        self._running = True
        self._thread.start()

        from .log import get_logger
        get_logger().info(f"HTTP server started on http://{self.host}:{self.port}")

    def start_blocking(self):
        """Start HTTP server in foreground (blocking)"""
        self._server = HTTPServer((self.host, self.port), self.handler_class)
        from .log import get_logger
        get_logger().info(f"HTTP server started on http://{self.host}:{self.port} (blocking)")
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop HTTP server"""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        from .log import get_logger
        get_logger().info("HTTP server stopped")

    def _serve(self):
        """Background thread target"""
        if self._server:
            self._server.serve_forever()

    @property
    def is_running(self) -> bool:
        return self._running and self._thread and self._thread.is_alive()

    def __repr__(self) -> str:
        return (f"ProdinamikServer(host={self.host}, port={self.port}, "
                f"running={self.is_running})")
