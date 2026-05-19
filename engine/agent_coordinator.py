"""Prodinamik Engine v1.3 — Warm Agent Coordinator

Background agent processes that run asynchronously:
  1. Periodic skill emergence checks (C2)
  2. Health degradation monitoring
  3. Data collection and drift persistence to disk
  4. Scheduled maintenance tasks

Architecture:
    WarmAgentCoordinator
        ├── TaskQueue (background tasks)
        ├── SkillRefresher (periodic emergence check)
        ├── HealthMonitor (periodic health check + logging)
        └── DataCollector (periodic data aggregation + snapshot)

All tasks are asyncio-based, run in the background, and report
status via an event bus. The coordinator supports start/stop/report.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .log import get_logger


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class AgentTaskType(str, Enum):
    SKILL_EMERGENCE = "skill_emergence"       # Periodic emergence scan
    HEALTH_CHECK = "health_check"             # Periodic health check
    DRIFT_PERSIST = "drift_persist"           # Persist drift data to disk
    DATA_COLLECTION = "data_collection"       # Periodic data aggregation
    MAINTENANCE = "maintenance"               # Cleanup / compaction
    CUSTOM = "custom"                         # User-defined


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class AgentTask:
    """A background agent task"""
    task_id: str
    task_type: AgentTaskType
    description: str
    interval_seconds: float  # How often to run
    handler: Optional[Callable] = None       # async () -> dict
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    run_count: int = 0
    success_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_due(self) -> bool:
        if self.next_run is None:
            return True
        return datetime.now() >= self.next_run

    @property
    def success_rate(self) -> float:
        if self.run_count == 0:
            return 0.0
        return self.success_count / self.run_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "description": self.description,
            "interval_s": self.interval_seconds,
            "status": self.status.value,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 2),
            "error": self.error,
            "result": self.result,
        }


@dataclass
class CoordinatorReport:
    """Snapshot of coordinator state"""
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    tasks: List[Dict[str, Any]]
    uptime_seconds: float
    is_running: bool
    data_dir: str
    last_persist: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_tasks": self.active_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "uptime_s": round(self.uptime_seconds, 1),
            "is_running": self.is_running,
            "tasks": self.tasks,
            "data_dir": self.data_dir,
            "last_persist": self.last_persist,
        }


# ──────────────────────────────────────────────
# Warm Agent Coordinator
# ──────────────────────────────────────────────


class WarmAgentCoordinator:
    """Manages background agent tasks for the Prodinamik Engine.

    Creates, schedules, monitors, and reports on background tasks.
    Runs as part of the AsyncEngine's background task group.

    Usage:
        coordinator = WarmAgentCoordinator(data_dir="/tmp/prodinamik")
        task = coordinator.add_task("skill-check", AgentTaskType.SKILL_EMERGENCE,
                                     interval_seconds=300, handler=my_handler)
        await coordinator.start()
        # ... engine runs ...
        report = coordinator.report()
        await coordinator.stop()
    """

    def __init__(self, data_dir: str = "~/.hermes/prodinamik/warm-agent",
                 engine_ref: Optional[Any] = None):
        self.data_dir = os.path.expanduser(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

        self.log = get_logger()
        self._engine = engine_ref
        self._tasks: Dict[str, AgentTask] = {}
        self._running = False
        self._started_at: Optional[datetime] = None
        self._main_loop_task: Optional[asyncio.Task] = None

        # Metrics
        self._total_executions = 0
        self._total_failures = 0
        self._execution_history: List[Dict[str, Any]] = []

    @property
    def uptime(self) -> float:
        if not self._started_at:
            return 0.0
        return (datetime.now() - self._started_at).total_seconds()

    # ── Task Management ────────────────────────

    def add_task(self, task_id: str, task_type: AgentTaskType,
                 description: str, interval_seconds: float,
                 handler: Optional[Callable] = None) -> AgentTask:
        """Register a new background agent task"""
        now = datetime.now()
        task = AgentTask(
            task_id=task_id,
            task_type=task_type,
            description=description,
            interval_seconds=interval_seconds,
            handler=handler,
            status=AgentTaskStatus.PENDING,
            next_run=now,  # Run immediately on first tick
        )
        self._tasks[task_id] = task
        self.log.info(f"Agent task added: {task_id} (every {interval_seconds}s)")
        return task

    def remove_task(self, task_id: str) -> bool:
        """Remove a background task"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self.log.info(f"Agent task removed: {task_id}")
            return True
        return False

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[AgentTaskStatus] = None) -> List[AgentTask]:
        if status:
            return [t for t in self._tasks.values() if t.status == status]
        return list(self._tasks.values())

    # ── Default Task Factory ───────────────────

    def setup_default_tasks(self, engine: Any) -> None:
        """Register default background tasks for the engine.

        Call during AsyncEngine.start() to auto-wire common tasks.
        """
        self._engine = engine

        # 1. Skill emergence check (every 5 minutes)
        async def _skill_check():
            try:
                if hasattr(engine, 'check_emergence'):
                    return {"skills": engine.check_emergence(), "source": "warm-agent"}
                return {"skills": [], "source": "warm-agent"}
            except Exception as e:
                return {"error": str(e), "source": "warm-agent"}

        self.add_task(
            task_id="skill-emergence",
            task_type=AgentTaskType.SKILL_EMERGENCE,
            description="Periodic skill emergence scan (C2)",
            interval_seconds=300,
            handler=_skill_check,
        )

        # 2. Health check (every 60 seconds)
        async def _health_check():
            try:
                health = engine.health_snapshot if hasattr(engine, 'health_snapshot') else {}
                return {
                    "health_score": health.get("health_score", 0),
                    "degradation": health.get("degradation", "unknown"),
                    "active_runs": health.get("active_runs", 0),
                    "source": "warm-agent",
                }
            except Exception as e:
                return {"error": str(e), "source": "warm-agent"}

        self.add_task(
            task_id="health-monitor",
            task_type=AgentTaskType.HEALTH_CHECK,
            description="Periodic engine health monitoring",
            interval_seconds=60,
            handler=_health_check,
        )

        # 3. Drift persist (every 10 minutes)
        async def _drift_persist():
            try:
                if not hasattr(engine, '_drift_detector'):
                    return {"persisted": False, "source": "warm-agent"}
                
                detector = engine._drift_detector
                report = detector.generate_report()
                
                persist_path = os.path.join(self.data_dir, f"drift-snapshot.json")
                with open(persist_path, "w") as f:
                    json.dump(report, f, indent=2, default=str)
                
                return {
                    "persisted": True,
                    "path": persist_path,
                    "total_events": report.get("total_events", 0),
                    "source": "warm-agent",
                }
            except Exception as e:
                return {"error": str(e), "source": "warm-agent"}

        self.add_task(
            task_id="drift-persist",
            task_type=AgentTaskType.DRIFT_PERSIST,
            description="Periodic drift data persistence",
            interval_seconds=600,
            handler=_drift_persist,
        )

        # 4. Data collection (every 30 minutes)
        async def _data_collection():
            try:
                runs = engine.list_runs() if hasattr(engine, 'list_runs') else []
                profiles = engine.list_profiles() if hasattr(engine, 'list_profiles') else []
                
                collection = {
                    "timestamp": datetime.now().isoformat(),
                    "total_runs": len(runs),
                    "profiles": profiles,
                    "runs_by_profile": dict(
                        defaultdict(int, {
                            p: sum(1 for r in runs if r.profile == p)
                            for p in profiles
                        })
                    ),
                    "source": "warm-agent",
                }
                
                collect_path = os.path.join(self.data_dir, f"data-snapshot.json")
                with open(collect_path, "w") as f:
                    json.dump(collection, f, indent=2, default=str)
                
                return collection
            except Exception as e:
                return {"error": str(e), "source": "warm-agent"}

        self.add_task(
            task_id="data-collection",
            task_type=AgentTaskType.DATA_COLLECTION,
            description="Periodic data aggregation and snapshot",
            interval_seconds=1800,
            handler=_data_collection,
        )

        self.log.info(f"Default tasks setup: {len(self._tasks)} tasks registered")

    # ── Lifecycle ──────────────────────────────

    async def start(self) -> None:
        """Start the coordinator's main loop"""
        if self._running:
            self.log.warning("WarmAgentCoordinator already running")
            return

        self._running = True
        self._started_at = datetime.now()
        self._main_loop_task = asyncio.create_task(
            self._main_loop(), name="warm-agent-coordinator"
        )
        self.log.info(f"WarmAgentCoordinator started with {len(self._tasks)} tasks")

    async def stop(self) -> None:
        """Gracefully stop the coordinator"""
        self._running = False
        if self._main_loop_task:
            self._main_loop_task.cancel()
            try:
                await self._main_loop_task
            except asyncio.CancelledError:
                pass
            self._main_loop_task = None
        self.log.info("WarmAgentCoordinator stopped")

    async def _main_loop(self) -> None:
        """Main coordinator loop — checks due tasks and runs them"""
        while self._running:
            try:
                await self._tick()
                await asyncio.sleep(5.0)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Coordinator main loop error: {e}")
                await asyncio.sleep(10.0)  # Back off on error

    async def _tick(self) -> None:
        """One tick: run all due tasks"""
        for task in self._tasks.values():
            if task.is_due and task.handler:
                await self._run_task(task)

    async def _run_task(self, task: AgentTask) -> None:
        """Execute a single task"""
        task.status = AgentTaskStatus.RUNNING
        task.run_count += 1
        task.last_run = datetime.now()
        task.next_run = task.last_run + timedelta(seconds=task.interval_seconds)

        try:
            result = task.handler()
            if asyncio.iscoroutine(result):
                result = await result
            task.result = result
            task.status = AgentTaskStatus.COMPLETED
            task.success_count += 1
            self._total_executions += 1
            self.log.debug(f"Agent task completed: {task.task_id}")
        except Exception as e:
            task.status = AgentTaskStatus.FAILED
            task.error = str(e)
            self._total_failures += 1
            self._total_executions += 1
            self.log.warning(f"Agent task failed: {task.task_id}: {e}")

        # Trim execution history
        self._execution_history.append({
            "task_id": task.task_id,
            "status": task.status.value,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-500:]

    # ── Reporting ──────────────────────────────

    def report(self) -> CoordinatorReport:
        """Get coordinator snapshot"""
        active = sum(1 for t in self._tasks.values()
                     if t.status == AgentTaskStatus.RUNNING)
        completed = sum(1 for t in self._tasks.values()
                        if t.status == AgentTaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values()
                     if t.status == AgentTaskStatus.FAILED)

        return CoordinatorReport(
            active_tasks=active,
            completed_tasks=completed,
            failed_tasks=failed,
            tasks=[t.to_dict() for t in self._tasks.values()],
            uptime_seconds=self.uptime,
            is_running=self._running,
            data_dir=self.data_dir,
            last_persist=self._execution_history[-1]["timestamp"]
            if self._execution_history else None,
        )

    @property
    def metrics(self) -> Dict[str, Any]:
        """Quick metrics for dashboard"""
        report = self.report()
        return {
            "total_executions": self._total_executions,
            "total_failures": self._total_failures,
            "success_rate": (
                (self._total_executions - self._total_failures)
                / max(self._total_executions, 1)
            ),
            "active_tasks": report.active_tasks,
            "task_count": len(self._tasks),
            "uptime_s": round(report.uptime_seconds, 1),
        }
