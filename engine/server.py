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
    human_loop = None
    approval_gate = None
    budget_controller = None
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
            # ── Human Loop API ──
            elif path == "/api/v1/human/approvals" and self.command == "GET":
                self._api_human_approvals(auth_result)
            elif path == "/api/v1/human/audit" and self.command == "GET":
                self._api_human_audit(auth_result)
            elif path == "/api/v1/human/budget" and self.command == "GET":
                self._api_human_budget(auth_result)
            elif path == "/api/v1/human/dashboard" and self.command == "GET":
                self._api_human_dashboard(auth_result)
            elif path == "/api/v1/human/approve" and self.command == "POST":
                self._api_human_approve(auth_result)
            elif path == "/api/v1/human/reject" and self.command == "POST":
                self._api_human_reject(auth_result)
            elif path == "/api/v1/human/pause" and self.command == "POST":
                self._api_human_pause(auth_result)
            elif path == "/api/v1/human/budget/reset" and self.command == "POST":
                self._api_human_budget_reset(auth_result)
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
    # Human Loop API Methods
    # ──────────────────────────────────────

    @staticmethod
    def _run_async(coro):
        """Safely run an async coroutine from a thread-based HTTP handler.
        Each HTTP request runs in its own thread — asyncio.run() creates a
        new event loop per call, which is the correct pattern for threads."""
        import asyncio
        try:
            return asyncio.run(coro)
        except (RuntimeError, OSError):
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    def _read_json_body(self) -> dict:
        """Read and parse JSON request body"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _api_human_approvals(self, auth_result):
        """GET /api/v1/human/approvals — list pending approvals"""
        result = {
            "human_loop_pending": [],
            "approval_gate_pending": [],
        }
        if self.human_loop:
            pending = self.human_loop.get_pending()
            result["human_loop_pending"] = [
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "reason": item.reason.value,
                    "error": item.error,
                    "goal": item.goal,
                    "status": item.status.value,
                    "created_at": item.created_at,
                    "age_seconds": item.age_seconds,
                }
                for item in pending
            ]
        if self.approval_gate:
            paused = self.approval_gate.get_paused()
            result["approval_gate_pending"] = [
                {
                    "task_id": p.task_id,
                    "reason": p.reason.value,
                    "goal": p.goal,
                    "error": p.error,
                    "status": p.approval_status.value,
                    "paused_at": p.paused_at,
                    "age_seconds": p.age_seconds,
                    "is_stale": p.is_stale,
                }
                for p in paused
            ]
        result["total_pending"] = (
            len(result["human_loop_pending"])
            + len(result["approval_gate_pending"])
        )
        self._json_response(200, result)

    def _api_human_audit(self, auth_result):
        """GET /api/v1/human/audit — get approval gate audit log"""
        import urllib.parse
        params = urllib.parse.parse_qs(
            self.path.split("?")[1] if "?" in self.path else ""
        )
        limit = int(params.get("limit", [50])[0])

        entries = []
        if self.approval_gate:
            entries = self.approval_gate.get_audit_log(limit=limit)
        self._json_response(200, {
            "entries": entries,
            "count": len(entries),
        })

    def _api_human_budget(self, auth_result):
        """GET /api/v1/human/budget — get budget status"""
        if not self.budget_controller:
            self._json_response(200, {"enabled": False})
            return
        stats = self.budget_controller.stats
        stats["enabled"] = True
        # Also include task-level breakdown
        task_costs = {}
        for task_id, record in self.budget_controller._task_costs.items():
            task_costs[task_id] = {
                "cost_usd": record.cost_usd,
                "llm_calls": record.llm_calls,
                "tool_calls": record.tool_calls,
                "cost_per_call": record.cost_per_call,
            }
        stats["task_costs"] = task_costs
        self._json_response(200, stats)

    def _api_human_dashboard(self, auth_result):
        """GET /api/v1/human/dashboard — serve oversight dashboard HTML"""
        dashboard_path = Path(__file__).parent / "agent_runtime" / "templates" / "oversight_dashboard.html"
        if not dashboard_path.exists():
            self._text_response(404, "Dashboard template not found")
            return
        html = dashboard_path.read_text(encoding="utf-8")
        self._text_response(200, html, content_type="text/html; charset=utf-8")

    def _api_human_approve(self, auth_result):
        """POST /api/v1/human/approve — approve a task {task_id, user_id, feedback}"""
        data = self._read_json_body()
        task_id = data.get("task_id", "")
        user_id = data.get("user_id", auth_result.name if auth_result.name else "admin")
        feedback = data.get("feedback", "")

        if not task_id:
            self._json_response(400, {"error": "Missing required field: task_id"})
            return

        # Try approval_gate first (task-level paused tasks), then human_loop (escalation)
        approved = False
        detail = ""
        if self.approval_gate:
            result = self._run_async(
                self.approval_gate.approve_task(task_id, user_id, feedback)
            )
            if result:
                approved = True
                detail = "approval_gate"

        if not approved and self.human_loop:
            # Also try human_loop escalation queue
            hl_result = self.human_loop.approve(task_id, user_id, feedback)
            if hl_result:
                approved = True
                detail = "human_loop"

        if approved:
            self._json_response(200, {
                "status": "approved",
                "task_id": task_id,
                "approved_by": user_id,
                "source": detail,
            })
        else:
            self._json_response(404, {
                "error": "Task not found in pending queue",
                "task_id": task_id,
            })

    def _api_human_reject(self, auth_result):
        """POST /api/v1/human/reject — reject a task {task_id, user_id, feedback}"""
        data = self._read_json_body()
        task_id = data.get("task_id", "")
        user_id = data.get("user_id", auth_result.name if auth_result.name else "admin")
        feedback = data.get("feedback", "Rejected")

        if not task_id:
            self._json_response(400, {"error": "Missing required field: task_id"})
            return

        rejected = False
        detail = ""
        if self.approval_gate:
            result = self._run_async(
                self.approval_gate.reject_task(task_id, user_id, feedback)
            )
            if result:
                rejected = True
                detail = "approval_gate"

        if not rejected and self.human_loop:
            hl_result = self.human_loop.reject(task_id, user_id, feedback)
            if hl_result:
                rejected = True
                detail = "human_loop"

        if rejected:
            self._json_response(200, {
                "status": "rejected",
                "task_id": task_id,
                "rejected_by": user_id,
                "source": detail,
            })
        else:
            self._json_response(404, {
                "error": "Task not found in pending queue",
                "task_id": task_id,
            })

    def _api_human_pause(self, auth_result):
        """POST /api/v1/human/pause — pause a task {task_id, reason}"""
        data = self._read_json_body()
        task_id = data.get("task_id", "")
        reason_str = data.get("reason", "manual")

        if not task_id:
            self._json_response(400, {"error": "Missing required field: task_id"})
            return

        if not self.approval_gate:
            self._json_response(503, {"error": "Approval gate not available"})
            return

        from .approval_gate import PauseReason
        reason_map = {
            "human_review": PauseReason.HUMAN_REVIEW,
            "budget_exceeded": PauseReason.BUDGET_EXCEEDED,
            "error_threshold": PauseReason.ERROR_THRESHOLD,
            "manual": PauseReason.MANUAL,
            "security": PauseReason.SECURITY,
        }
        reason = reason_map.get(reason_str, PauseReason.MANUAL)

        result = self._run_async(
            self.approval_gate.pause_task(task_id, reason=reason)
        )

        self._json_response(200, {
            "status": "paused",
            "task_id": result,
            "reason": reason_str,
        })

    def _api_human_budget_reset(self, auth_result):
        """POST /api/v1/human/budget/reset — reset budget tracking"""
        if not self.budget_controller:
            self._json_response(503, {"error": "Budget controller not available"})
            return
        self.budget_controller.reset()
        self._json_response(200, {
            "status": "reset",
            "message": "Budget tracking has been reset",
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
        self.handler_class.human_loop = getattr(engine, 'human_loop', None) if engine else None
        self.handler_class.approval_gate = getattr(engine, 'approval_gate', None) if engine else None
        self.handler_class.budget_controller = getattr(engine, 'budget_controller', None) if engine else None

        # If human loop components not on engine, create defaults
        if engine and self.handler_class.human_loop is None:
            try:
                from .agent_runtime.human_loop import HumanLoopManager
                self.handler_class.human_loop = HumanLoopManager()
            except ImportError:
                pass
        if engine and self.handler_class.approval_gate is None:
            try:
                from .agent_runtime.approval_gate import ApprovalGate
                self.handler_class.approval_gate = ApprovalGate(
                    human_loop=self.handler_class.human_loop,
                )
            except ImportError:
                pass
        if engine and self.handler_class.budget_controller is None:
            try:
                from .agent_runtime.budget_controller import BudgetController
                self.handler_class.budget_controller = BudgetController()
            except ImportError:
                pass

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
