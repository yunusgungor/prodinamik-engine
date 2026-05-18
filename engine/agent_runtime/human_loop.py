"""Prodinamik AI Grid — Human Loop Manager

Approval gates, escalation queue, and oversight dashboard backend.
Tasks that exceed escalation threshold enter the human review queue.

Usage:
    loop = HumanLoopManager()
    await loop.escalate(task, error)
    loop.approve(task_id, user_id)
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


class EscalationReason(Enum):
    MAX_RETRIES = "max_retries"
    TIMEOUT = "timeout"
    CRITICAL_ERROR = "critical_error"
    BUDGET_EXCEEDED = "budget_exceeded"
    SECURITY_VIOLATION = "security_violation"
    MANUAL = "manual"


class ReviewStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


@dataclass
class EscalatedItem:
    id: str = ""
    task_id: str = ""
    reason: EscalationReason = EscalationReason.MAX_RETRIES
    error: str = ""
    goal: str = ""
    task_data: Dict[str, Any] = field(default_factory=dict)
    status: ReviewStatus = ReviewStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_by: str = ""
    reviewed_at: Optional[str] = None
    feedback: str = ""

    @property
    def age_seconds(self) -> float:
        try:
            created = datetime.fromisoformat(self.created_at)
            return (datetime.now() - created).total_seconds()
        except (ValueError, TypeError):
            return 0.0


class HumanLoopManager:
    def __init__(
        self,
        escalation_threshold: int = 3,
        auto_approve_timeout: Optional[float] = None,  # Auto-approve after N seconds
    ):
        self.escalation_threshold = escalation_threshold
        self.auto_approve_timeout = auto_approve_timeout
        self.log = get_logger()
        self._queue: List[EscalatedItem] = []
        self._resolved: List[EscalatedItem] = []
        self._callbacks_on_escalate: List[Callable] = []
        self._callbacks_on_review: List[Callable] = []

    async def escalate(
        self, task: Any, error: str = "",
        reason: EscalationReason = EscalationReason.MAX_RETRIES,
    ) -> str:
        item = EscalatedItem(
            id=f"esc-{uuid.uuid4().hex[:8]}",
            task_id=task.task_id if hasattr(task, 'task_id') else str(task),
            reason=reason,
            error=error,
            goal=getattr(task, 'goal', ''),
            task_data=getattr(task, 'context', {}),
        )
        self._queue.append(item)
        self.log.warning(f"Escalated: {item.id} (task {item.task_id}) — {error[:100]}")
        
        for cb in self._callbacks_on_escalate:
            try:
                await cb(item) if asyncio.iscoroutinefunction(cb) else cb(item)
            except Exception as e:
                self.log.debug(f"Escalation callback error: {e}")
        
        return item.id

    def approve(self, escalation_id: str, user_id: str = "admin", feedback: str = "") -> bool:
        item = self._find_in_queue(escalation_id)
        if not item:
            return False
        item.status = ReviewStatus.APPROVED
        item.reviewed_by = user_id
        item.reviewed_at = datetime.now().isoformat()
        item.feedback = feedback
        self._queue.remove(item)
        self._resolved.append(item)
        return True

    def reject(self, escalation_id: str, user_id: str = "admin", feedback: str = "") -> bool:
        item = self._find_in_queue(escalation_id)
        if not item:
            return False
        item.status = ReviewStatus.REJECTED
        item.reviewed_by = user_id
        item.reviewed_at = datetime.now().isoformat()
        item.feedback = feedback
        self._queue.remove(item)
        self._resolved.append(item)
        return True

    def get_pending(self) -> List[EscalatedItem]:
        return [i for i in self._queue if i.status == ReviewStatus.PENDING]

    def get_resolved(self, limit: int = 20) -> List[EscalatedItem]:
        return self._resolved[-limit:]

    @property
    def pending_count(self) -> int:
        return len(self.get_pending())

    @property
    def total_escalated(self) -> int:
        return len(self._queue) + len(self._resolved)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "pending": self.pending_count,
            "total_escalated": self.total_escalated,
            "threshold": self.escalation_threshold,
        }

    def on_escalate(self, callback: Callable):
        self._callbacks_on_escalate.append(callback)
    def on_review(self, callback: Callable):
        self._callbacks_on_review.append(callback)

    def _find_in_queue(self, escalation_id: str) -> Optional[EscalatedItem]:
        for item in self._queue:
            if item.id == escalation_id:
                return item
        return None
