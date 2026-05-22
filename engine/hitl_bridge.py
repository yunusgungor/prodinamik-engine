"""StateGuard HITL → Prodinamik Human Loop Bridge.

Maps StateGuard's synchronous :class:`HITLHandler` approval requests
onto Prodinamik Engine's async :class:`HumanLoopManager` escalation
queue, so that validation escalations flow through Prodinamik's
WebSocket/HTTP pipeline and reach real users.

Key mappings::

    StateGuard                   Prodinamik Engine
    ─────────────────────        ─────────────────────
    request_approval(info)  →    escalate(task, error, reason=MANUAL)
    check_approval(req_id)  →    get_pending() + auto-timeout
    resolve_approval(id, bool)   approve() / reject()
    on_timeout()                 auto_approve_timeout
    get_pending_requests()       get_pending()

Usage::

    from engine.hitl_bridge import ProdinamikHITLHandler

    hitl = ProdinamikHITLHandler(timeout_minutes=5, human_loop=loop)
    req = hitl.request_approval({"step": "tier_3", "error": "low score"})
    # ... later, user responds via Prodinamik HTTP/WS ...
    hitl.resolve_approval(req["request_id"], approved=True)
"""

from __future__ import annotations

import copy
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from engine.agent_runtime.human_loop import (
    HumanLoopManager,
    EscalationReason,
    ReviewStatus,
)


# ──────────────────────────────────────────────
# ProdinamikHITLHandler
# ──────────────────────────────────────────────


class ProdinamikHITLHandler:
    """Bridge between StateGuard's HITL and Prodinamik's Human Loop.

    Implements the same interface as StateGuard's ``HITLHandler``
    (:meth:`request_approval`, :meth:`check_approval`,
    :meth:`resolve_approval`, :meth:`on_timeout`,
    :meth:`get_pending_requests`) but delegates the actual human
    interaction to a Prodinamik :class:`HumanLoopManager`.

    This means validation escalations:
    - Flow through Prodinamik's HTTP/WS pipeline
    - Are visible in ``prodinamik dashboard``
    - Can be resolved via API/CLI calls
    - Support on_escalate / on_review callbacks
    """

    def __init__(
        self,
        timeout_minutes: int = 5,
        human_loop: HumanLoopManager | None = None,
    ) -> None:
        """Initialise the Prodinamik-backed HITL handler.

        Args:
            timeout_minutes: Minutes before automatic fail-close.
            human_loop: A Prodinamik :class:`HumanLoopManager` instance.
                        If omitted a new one is created with
                        ``auto_approve_timeout=timeout_minutes * 60``.

        Raises:
            TypeError: If *timeout_minutes* is not an int or is a bool.
            ValueError: If *timeout_minutes* is negative.
        """
        if isinstance(timeout_minutes, bool):
            raise TypeError(
                f"timeout_minutes must be an int, got bool"
            )
        if not isinstance(timeout_minutes, int):
            raise TypeError(
                f"timeout_minutes must be an int, "
                f"got {type(timeout_minutes).__name__}"
            )
        if timeout_minutes < 0:
            raise ValueError(
                f"timeout_minutes must be >= 0, got {timeout_minutes}"
            )

        self.timeout_minutes = timeout_minutes
        self._loop = human_loop or HumanLoopManager(
            auto_approve_timeout=float(timeout_minutes * 60) if timeout_minutes > 0 else None,
        )

        # Local tracking: StateGuard request_id → Prodinamik escalation_id
        self._request_map: dict[str, str] = {}
        self._reverse_map: dict[str, str] = {}

    # ── Properties ─────────────────────────────────

    @property
    def pending_count(self) -> int:
        return self._loop.pending_count

    @property
    def loop(self) -> HumanLoopManager:
        return self._loop

    # ── StateGuard-compatible API ───────────────────

    def request_approval(self, step_info: dict[str, Any]) -> dict[str, Any]:
        """Submit an approval request (sync wrapper around :meth:`HumanLoopManager.escalate`).

        Args:
            step_info: Dict with step, dimension, attempt count,
                error details.

        Returns:
            dict with keys ``request_id``, ``status``, ``timeout_at``,
            ``timeout_minutes``.
        """
        if not isinstance(step_info, dict):
            raise TypeError(
                f"step_info must be a dict, "
                f"got {type(step_info).__name__}"
            )

        # Generate a StateGuard-style request_id
        request_id = f"hitl_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}"

        # Create a minimal task-like object for HumanLoopManager
        class _TaskProxy:
            def __init__(self, info):
                self.task_id = info.get("step", "unknown")
                self.goal = info.get("error", "")[:200]
                self.context = copy.deepcopy(info)

        task = _TaskProxy(step_info)

        # Escalate into Prodinamik's human loop (fire-and-forget the async)
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            escalation_id = asyncio.run_coroutine_threadsafe(
                self._loop.escalate(
                    task=task,
                    error=step_info.get("error", "HITL approval required"),
                    reason=EscalationReason.MANUAL,
                ),
                loop,
            ).result(timeout=5)
        except (RuntimeError, Exception):
            # No running loop or timeout — create a temporary one
            escalation_id = asyncio.run(
                self._loop.escalate(
                    task=task,
                    error=step_info.get("error", "HITL approval required"),
                    reason=EscalationReason.MANUAL,
                )
            )

        # Track the mapping
        self._request_map[request_id] = escalation_id
        self._reverse_map[escalation_id] = request_id

        now = datetime.now(timezone.utc)
        timeout_dt = now + timedelta(minutes=self.timeout_minutes) if self.timeout_minutes > 0 else now

        return {
            "request_id": request_id,
            "status": "pending",
            "timeout_at": timeout_dt.isoformat(),
            "timeout_minutes": self.timeout_minutes,
        }

    def check_approval(self, request_id: str) -> dict[str, Any]:
        """Check the status of an approval request.

        Args:
            request_id: The request ID from :meth:`request_approval`.

        Returns:
            dict with keys ``request_id``, ``status``, ``approved``,
            ``reason``, ``decision_time``.

        Raises:
            KeyError: If *request_id* is not found.
        """
        if request_id not in self._request_map:
            raise KeyError(f"Approval request not found: {request_id}")

        escalation_id = self._request_map[request_id]

        # Search through resolved first, then pending
        item = None
        for resolved in self._loop._resolved:
            if resolved.id == escalation_id:
                item = resolved
                break

        if item is None:
            for pending in self._loop._queue:
                if pending.id == escalation_id:
                    item = pending
                    break

        if item is None:
            # Shouldn't happen, but handle gracefully
            return {
                "request_id": request_id,
                "status": "unknown",
                "approved": None,
                "reason": "not_found",
                "decision_time": None,
            }

        # Map status
        if item.status == ReviewStatus.PENDING:
            # Check auto-approve timeout
            if self._loop.auto_approve_timeout is not None:
                if item.age_seconds >= self._loop.auto_approve_timeout:
                    # Auto-timeout acts as reject (fail-close)
                    return {
                        "request_id": request_id,
                        "status": "decided",
                        "approved": False,
                        "reason": "timeout",
                        "decision_time": datetime.now(timezone.utc).isoformat(),
                    }
            return {
                "request_id": request_id,
                "status": "pending",
                "approved": None,
                "reason": None,
                "decision_time": None,
            }

        approved = item.status == ReviewStatus.APPROVED
        return {
            "request_id": request_id,
            "status": "decided",
            "approved": approved,
            "reason": item.feedback or ("approved" if approved else "rejected"),
            "decision_time": item.reviewed_at or datetime.now(timezone.utc).isoformat(),
        }

    def resolve_approval(
        self,
        request_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a pending approval request.

        Args:
            request_id: The request ID from :meth:`request_approval`.
            approved: True to approve, False to reject.
            reason: Optional human-readable reason.

        Returns:
            dict with keys ``request_id``, ``status``, ``approved``,
            ``reason``, ``decision_time``.

        Raises:
            KeyError: If *request_id* is not found.
            TypeError: If *approved* is not a bool.
        """
        if request_id not in self._request_map:
            raise KeyError(f"Approval request not found: {request_id}")

        if not isinstance(approved, bool):
            raise TypeError(
                f"approved must be a bool, got {type(approved).__name__}"
            )

        escalation_id = self._request_map[request_id]

        if approved:
            success = self._loop.approve(escalation_id, feedback=reason or "")
        else:
            success = self._loop.reject(escalation_id, feedback=reason or "")

        now = datetime.now(timezone.utc).isoformat()

        return {
            "request_id": request_id,
            "status": "decided",
            "approved": approved,
            "reason": reason or ("approved" if approved else "rejected"),
            "decision_time": now,
        }

    def on_timeout(self) -> dict[str, Any]:
        """Default behaviour when human does not respond in time.

        Returns:
            dict with ``approved=False`` (fail-close).
        """
        return {"approved": False, "reason": "timeout"}

    def get_pending_requests(self) -> dict[str, Any]:
        """List all pending approval requests.

        Returns:
            dict with keys ``pending`` (list) and ``count`` (int).
        """
        pending_list: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for item in self._loop.get_pending():
            if item.id not in self._reverse_map:
                continue

            request_id = self._reverse_map[item.id]

            remaining = max(0.0, self._loop.auto_approve_timeout - item.age_seconds) \
                if self._loop.auto_approve_timeout else 0.0

            pending_list.append({
                "request_id": request_id,
                "step_info": item.task_data,
                "created_at": item.created_at,
                "timeout_at": (
                    datetime.fromisoformat(item.created_at) +
                    timedelta(seconds=self._loop.auto_approve_timeout)
                ).isoformat() if self._loop.auto_approve_timeout else "",
                "remaining_seconds": remaining,
            })

        return {"pending": pending_list, "count": len(pending_list)}

    # ── Convenience helpers ────────────────────────

    def on_escalate(self, callback: Callable) -> None:
        """Register a callback invoked when a new escalation is created."""
        self._loop.on_escalate(callback)

    def on_review(self, callback: Callable) -> None:
        """Register a callback invoked when an escalation is resolved."""
        self._loop.on_review(callback)

    def stats(self) -> dict[str, Any]:
        """Return usage statistics."""
        return self._loop.stats
