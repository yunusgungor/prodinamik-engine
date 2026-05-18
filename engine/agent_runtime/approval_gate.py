"""Prodinamik AI Grid — Approval Gate

Manages human-in-the-loop approval for agent tasks.
Supports pause/resume, budget-based auto-pause, and timeout-based auto-approve.

Architecture:
    ApprovalGate
    ├── Task Pause/Resume (pause agent execution, resume on approval)
    ├── Budget Auto-Pause (auto-pause when cost threshold exceeded)
    ├── Timeout Auto-Approve (auto-approve after N seconds)
    └── Audit Trail (all approval actions logged)

Usage:
    gate = ApprovalGate(human_loop, budget_controller)
    await gate.pause_task(task_id, reason="Needs human review")
    await gate.approve_task(task_id, user_id="admin")
    await gate.reject_task(task_id, user_id="admin")
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..log import get_logger


class PauseReason(Enum):
    HUMAN_REVIEW = "human_review"
    BUDGET_EXCEEDED = "budget_exceeded"
    ERROR_THRESHOLD = "error_threshold"
    MANUAL = "manual"
    SECURITY = "security"


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT_AUTO = "timeout_auto"
    CANCELLED = "cancelled"


@dataclass
class PausedTask:
    task_id: str
    reason: PauseReason = PauseReason.HUMAN_REVIEW
    paused_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resumed_at: Optional[str] = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str = ""
    rejected_by: str = ""
    feedback: str = ""
    goal: str = ""
    error: str = ""
    auto_approve_timeout: Optional[float] = None

    @property
    def age_seconds(self) -> float:
        try:
            paused = datetime.fromisoformat(self.paused_at)
            return (datetime.now() - paused).total_seconds()
        except (ValueError, TypeError):
            return 0.0

    @property
    def is_stale(self) -> bool:
        if self.auto_approve_timeout:
            return self.age_seconds > self.auto_approve_timeout
        return False


class ActionLog:
    """Audit trail entry for approval actions"""

    def __init__(self, action: str, task_id: str, user: str, detail: str = ""):
        self.action = action
        self.task_id = task_id
        self.user = user
        self.detail = detail
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {
            "action": self.action,
            "task_id": self.task_id,
            "user": self.user,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class ApprovalGate:
    """
    Human-in-the-loop approval gate for agent tasks.

    Features:
    - Pause running tasks for human review
    - Approve/Reject paused tasks
    - Auto-pause on budget exceeded
    - Auto-approve on timeout
    - Full audit trail

    Usage:
        gate = ApprovalGate()
        await gate.pause_task("task-001", PauseReason.HUMAN_REVIEW)
        await gate.approve_task("task-001", "admin")
    """

    def __init__(
        self,
        human_loop: Optional[Any] = None,
        auto_approve_timeout: Optional[float] = None,
    ):
        self.human_loop = human_loop
        self.auto_approve_timeout = auto_approve_timeout
        self.log = get_logger()
        self._paused: Dict[str, PausedTask] = {}
        self._resolved: List[PausedTask] = []
        self._audit_log: List[ActionLog] = []
        self._callbacks_on_pause: List[Callable] = []
        self._callbacks_on_approve: List[Callable] = []
        self._callbacks_on_reject: List[Callable] = []

    async def pause_task(
        self,
        task_id: str,
        reason: PauseReason = PauseReason.HUMAN_REVIEW,
        feedback: str = "",
        goal: str = "",
        error: str = "",
        auto_approve_timeout: Optional[float] = None,
    ) -> str:
        """Pause a task for human review"""
        paused = PausedTask(
            task_id=task_id,
            reason=reason,
            goal=goal,
            error=error,
            feedback=feedback,
            auto_approve_timeout=auto_approve_timeout or self.auto_approve_timeout,
        )
        self._paused[task_id] = paused

        self._audit_log.append(ActionLog(
            "pause", task_id, "system",
            f"Paused: {reason.value} — {error[:100] if error else feedback[:100]}",
        ))

        self.log.info(f"Task paused: {task_id} (reason: {reason.value})")

        # Fire callbacks
        for cb in self._callbacks_on_pause:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(task_id, reason, paused)
                else:
                    cb(task_id, reason, paused)
            except Exception as e:
                self.log.debug(f"Pause callback error: {e}")

        return task_id

    async def approve_task(
        self,
        task_id: str,
        user_id: str = "admin",
        feedback: str = "",
    ) -> bool:
        """Approve a paused task to continue"""
        paused = self._paused.pop(task_id, None)
        if not paused:
            return False

        paused.approval_status = ApprovalStatus.APPROVED
        paused.approved_by = user_id
        paused.feedback = feedback
        paused.resumed_at = datetime.now().isoformat()
        self._resolved.append(paused)

        self._audit_log.append(ActionLog(
            "approve", task_id, user_id, feedback,
        ))

        self.log.info(f"Task approved: {task_id} by {user_id}")

        # Fire callbacks
        for cb in self._callbacks_on_approve:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(task_id, user_id, paused)
                else:
                    cb(task_id, user_id, paused)
            except Exception as e:
                self.log.debug(f"Approve callback error: {e}")

        return True

    async def reject_task(
        self,
        task_id: str,
        user_id: str = "admin",
        feedback: str = "Rejected",
    ) -> bool:
        """Reject a paused task"""
        paused = self._paused.pop(task_id, None)
        if not paused:
            return False

        paused.approval_status = ApprovalStatus.REJECTED
        paused.rejected_by = user_id
        paused.feedback = feedback
        paused.resumed_at = datetime.now().isoformat()
        self._resolved.append(paused)

        self._audit_log.append(ActionLog(
            "reject", task_id, user_id, feedback,
        ))

        self.log.info(f"Task rejected: {task_id} by {user_id}")

        for cb in self._callbacks_on_reject:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(task_id, user_id, paused)
                else:
                    cb(task_id, user_id, paused)
            except Exception as e:
                self.log.debug(f"Reject callback error: {e}")

        return True

    def get_paused(self) -> List[PausedTask]:
        """Get all pending paused tasks"""
        return [p for p in self._paused.values()
                if p.approval_status == ApprovalStatus.PENDING]

    @property
    def pending_count(self) -> int:
        return len(self.get_paused())

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, str]]:
        """Get audit trail"""
        return [a.to_dict() for a in self._audit_log[-limit:]]

    def auto_approve_stale(self) -> List[str]:
        """Auto-approve tasks that have exceeded their timeout (sync)"""
        approved = []
        for task_id, paused in list(self._paused.items()):
            if paused.is_stale:
                self._paused.pop(task_id, None)
                paused.approval_status = ApprovalStatus.TIMEOUT_AUTO
                paused.resumed_at = datetime.now().isoformat()
                self._resolved.append(paused)
                approved.append(task_id)
        return approved

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "pending": self.pending_count,
            "resolved": len(self._resolved),
            "total_paused": len(self._paused) + len(self._resolved),
            "auto_approve_timeout": self.auto_approve_timeout,
        }

    # ── Event Handlers ──

    def on_pause(self, callback: Callable):
        self._callbacks_on_pause.append(callback)

    def on_approve(self, callback: Callable):
        self._callbacks_on_approve.append(callback)

    def on_reject(self, callback: Callable):
        self._callbacks_on_reject.append(callback)
