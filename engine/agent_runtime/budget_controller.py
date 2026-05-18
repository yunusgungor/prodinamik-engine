"""Prodinamik AI Grid — Budget Controller

Cost-aware budget enforcement for agent tasks.
Monitors LLM/tool costs and auto-pauses agents when thresholds exceeded.

Architecture:
    BudgetController
    ├── Cost Monitor (track per-task and total costs)
    ├── Threshold Gates (soft warning, hard pause)
    ├── Auto-Pause (pause ALL agents when hard limit hit)
    └── Resume (resume after budget reset)

Usage:
    bc = BudgetController(hourly_limit=10.0, daily_limit=50.0)
    bc.record_cost("task-001", 0.05)
    if bc.is_throttled:
        await approval_gate.pause_task(...)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from ..log import get_logger


class BudgetLevel(Enum):
    NORMAL = "normal"            # Within limits
    WARNING = "warning"          # Soft threshold reached
    CRITICAL = "critical"        # Hard threshold approaching
    EXHAUSTED = "exhausted"      # All budgets exceeded


@dataclass
class BudgetThreshold:
    """Budget threshold configuration"""
    hourly_usd: float = 10.0          # Max spend per hour
    daily_usd: float = 50.0           # Max spend per day
    weekly_usd: float = 200.0         # Max spend per week
    monthly_usd: float = 500.0        # Max spend per month
    per_task_usd: float = 2.0         # Max spend per single task
    soft_ratio: float = 0.8           # Warning at 80% of limit

    def __post_init__(self):
        assert self.hourly_usd > 0, "Hourly budget must be positive"
        assert self.daily_usd > 0, "Daily budget must be positive"
        assert self.soft_ratio < 1.0, "Soft ratio must be < 1.0"


@dataclass
class TaskCostRecord:
    task_id: str
    cost_usd: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def cost_per_call(self) -> float:
        total = self.llm_calls + self.tool_calls
        return self.cost_usd / total if total > 0 else 0.0


class BudgetController:
    """
    Budget controller for agent tasks.

    Monitors costs across multiple time windows (hourly, daily, weekly, monthly)
    and enforces thresholds with soft (warning) and hard (pause) gates.

    Usage:
        bc = BudgetController(BudgetThreshold(hourly_usd=5.0, daily_usd=20.0))
        bc.record_cost("task-001", 0.15, llm_call=True)

        if bc.level == BudgetLevel.CRITICAL:
            await gate.pause_all_tasks(PauseReason.BUDGET_EXCEEDED)
    """

    def __init__(
        self,
        thresholds: Optional[BudgetThreshold] = None,
    ):
        self.thresholds = thresholds or BudgetThreshold()
        self.log = get_logger()
        self._lock = Lock()

        # Cost tracking
        self._costs: List[Dict[str, Any]] = []
        self._task_costs: Dict[str, TaskCostRecord] = {}
        self._total_cost: float = 0.0
        self._total_llm_calls: int = 0
        self._total_tool_calls: int = 0

        # Budget state
        self._level = BudgetLevel.NORMAL
        self._paused = False
        self._pause_reason: Optional[str] = None
        self._last_reset: Dict[str, float] = {}

        # Callbacks
        self._on_warning: List[Callable] = []
        self._on_critical: List[Callable] = []
        self._on_exhausted: List[Callable] = []
        self._on_recovery: List[Callable] = []

    def record_cost(
        self,
        task_id: str,
        cost_usd: float,
        llm_call: bool = False,
        tool_call: bool = False,
    ) -> None:
        """Record a cost event"""
        with self._lock:
            entry = {
                "task_id": task_id,
                "cost": cost_usd,
                "llm_call": llm_call,
                "tool_call": tool_call,
                "timestamp": time.time(),
            }
            self._costs.append(entry)
            self._total_cost += cost_usd
            if llm_call:
                self._total_llm_calls += 1
            if tool_call:
                self._total_tool_calls += 1

            # Per-task tracking
            if task_id not in self._task_costs:
                self._task_costs[task_id] = TaskCostRecord(task_id=task_id)
            tc = self._task_costs[task_id]
            tc.cost_usd += cost_usd
            if llm_call:
                tc.llm_calls += 1
            if tool_call:
                tc.tool_calls += 1

        self._evaluate_level()

    def record_llm_call(self, task_id: str, cost_usd: float) -> None:
        """Convenience: record an LLM call cost"""
        self.record_cost(task_id, cost_usd, llm_call=True)

    def record_tool_call(self, task_id: str, cost_usd: float) -> None:
        """Convenience: record a tool call cost"""
        self.record_cost(task_id, cost_usd, tool_call=True)

    def _evaluate_level(self) -> None:
        """Evaluate current budget level"""
        old_level = self._level

        # Check each time window
        now = time.time()
        hourly = self._window_cost(now - 3600, now)
        daily = self._window_cost(now - 86400, now)
        weekly = self._window_cost(now - 604800, now)
        monthly = self._window_cost(now - 2592000, now)

        per_task = max(
            (tc.cost_usd for tc in self._task_costs.values()),
            default=0.0,
        )

        # Determine level
        if hourly >= self.thresholds.hourly_usd or \
           daily >= self.thresholds.daily_usd or \
           per_task >= self.thresholds.per_task_usd:
            self._level = BudgetLevel.EXHAUSTED
            self._paused = True
            self._pause_reason = "Hard budget limit exceeded"
        elif hourly >= self.thresholds.hourly_usd * self.thresholds.soft_ratio or \
             daily >= self.thresholds.daily_usd * self.thresholds.soft_ratio:
            self._level = BudgetLevel.CRITICAL
        elif hourly >= self.thresholds.hourly_usd * self.thresholds.soft_ratio * 0.5:
            self._level = BudgetLevel.WARNING
        else:
            self._level = BudgetLevel.NORMAL
            self._paused = False
            self._pause_reason = None

        # Fire callbacks on transitions
        if self._level != old_level:
            if self._level == BudgetLevel.WARNING:
                self._fire_callbacks(self._on_warning)
            elif self._level == BudgetLevel.CRITICAL:
                self._fire_callbacks(self._on_critical)
            elif self._level == BudgetLevel.EXHAUSTED:
                self._fire_callbacks(self._on_exhausted)
            elif self._level == BudgetLevel.NORMAL and \
                 old_level in (BudgetLevel.WARNING, BudgetLevel.CRITICAL, BudgetLevel.EXHAUSTED):
                self._fire_callbacks(self._on_recovery)

    def _window_cost(self, start_ts: float, end_ts: float) -> float:
        """Sum costs within a time window"""
        return sum(
            e["cost"] for e in self._costs
            if start_ts <= e["timestamp"] <= end_ts
        )

    def _fire_callbacks(self, cbs: List[Callable]) -> None:
        for cb in cbs:
            try:
                cb(self)
            except Exception as e:
                self.log.debug(f"Budget callback error: {e}")

    # ── Query ──

    @property
    def level(self) -> BudgetLevel:
        return self._level

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_warning(self) -> bool:
        return self._level in (BudgetLevel.WARNING, BudgetLevel.CRITICAL, BudgetLevel.EXHAUSTED)

    @property
    def pause_reason(self) -> Optional[str]:
        return self._pause_reason

    def get_task_cost(self, task_id: str) -> Optional[TaskCostRecord]:
        return self._task_costs.get(task_id)

    @property
    def stats(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "level": self._level.value,
            "paused": self._paused,
            "total_cost": round(self._total_cost, 6),
            "hourly_cost": round(self._window_cost(now - 3600, now), 6),
            "daily_cost": round(self._window_cost(now - 86400, now), 6),
            "limit_hourly": self.thresholds.hourly_usd,
            "limit_daily": self.thresholds.daily_usd,
            "limit_per_task": self.thresholds.per_task_usd,
            "soft_ratio": self.thresholds.soft_ratio,
            "total_llm_calls": self._total_llm_calls,
            "total_tool_calls": self._total_tool_calls,
            "active_tasks": len(self._task_costs),
            "pause_reason": self._pause_reason,
        }

    # ── Event Handlers ──

    def on_warning(self, callback: Callable):
        self._on_warning.append(callback)

    def on_critical(self, callback: Callable):
        self._on_critical.append(callback)

    def on_exhausted(self, callback: Callable):
        self._on_exhausted.append(callback)

    def on_recovery(self, callback: Callable):
        self._on_recovery.append(callback)

    def reset(self) -> None:
        """Reset all cost tracking"""
        with self._lock:
            old_level = self._level
            self._costs.clear()
            self._task_costs.clear()
            self._total_cost = 0.0
            self._total_llm_calls = 0
            self._total_tool_calls = 0
            self._level = BudgetLevel.NORMAL
            self._paused = False
            self._pause_reason = None
        
        # Fire recovery if was in a warning/critical/exhausted state
        if old_level in (BudgetLevel.WARNING, BudgetLevel.CRITICAL, BudgetLevel.EXHAUSTED):
            self._fire_callbacks(self._on_recovery)
