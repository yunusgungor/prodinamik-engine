"""Prodinamik AI Grid — Agent Supervisor

Warm Agent pattern: lightweight supervisor always runs on each node.
Heartbeat → Coordinator, Task Listener, Worker Pool management.

Architecture:
    Supervisor (always on)
    ├── Heartbeat (TTL 3s → Coordinator)
    ├── Event Listener (agent tasks from event bus)
    ├── Health Monitor (worker status, memory, cpu)
    └── Worker Pool (spawn/manage/restart workers)
"""

from __future__ import annotations

import asyncio
import os
import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path

from ..log import get_logger


# ── Agent Node Identity ──

@dataclass
class NodeIdentity:
    """Identity of this worker node"""
    node_id: str
    hostname: str = ""
    pid: int = field(default_factory=os.getpid)
    version: str = "1.0.0"
    started_at: datetime = field(default_factory=datetime.now)
    capabilities: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()


# ── Worker Status ──

class WorkerStatus(Enum):
    PENDING = "pending"        # Queued, not yet started
    RUNNING = "running"        # Actively executing
    COMPLETED = "completed"    # Finished successfully
    FAILED = "failed"          # Finished with error
    CANCELLED = "cancelled"    # Cancelled by user/system
    CRASHED = "crashed"        # Unexpected termination


@dataclass
class WorkerInfo:
    """Metadata about a running/queued worker"""
    worker_id: str
    task_id: str
    status: WorkerStatus = WorkerStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    goal: str = ""
    error: Optional[str] = None
    progress: float = 0.0  # 0.0 → 1.0

    @property
    def duration_ms(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds() * 1000


# ── Supervisor Configuration ──

@dataclass
class SupervisorConfig:
    """Configuration for the Agent Supervisor"""
    node_id: str = ""  # Auto-generated if empty
    heartbeat_interval: float = 3.0      # Seconds between heartbeats
    task_poll_interval: float = 1.0      # Task queue check interval
    max_workers: int = 3                 # Max concurrent workers
    worker_timeout: float = 300.0        # Max worker execution time
    worker_restart_delay: float = 1.0    # Delay before restart on crash
    heartbeat_ttl: float = 10.0          # Coordinator considers node dead after this
    enable_auto_recovery: bool = True    # Auto-restart failed workers


# ── Agent Supervisor ──

class AgentSupervisor:
    """
    Warm Agent Supervisor — always runs on each node.

    Responsibilities:
    - Maintain node identity and capabilities
    - Send periodic heartbeats to Coordinator
    - Listen for incoming task assignments
    - Spawn/manage/monitor worker instances (pool max 3)
    - Detect worker crashes → auto-restart
    - Report health to Coordinator

    Usage:
        supervisor = AgentSupervisor(config, coordinator_client)
        await supervisor.start()
        # runs in background...
        await supervisor.stop()
    """

    def __init__(
        self,
        config: Optional[SupervisorConfig] = None,
        coordinator_client: Optional[Any] = None,  # Coordinator RPC client
        node_identity: Optional[NodeIdentity] = None,
    ):
        self.config = config or SupervisorConfig()
        self.coordinator = coordinator_client
        self.log = get_logger()

        # Node identity
        self.identity = node_identity or NodeIdentity(
            node_id=self.config.node_id or self._generate_node_id(),
            hostname=self._get_hostname(),
        )

        # Worker pool
        self._workers: Dict[str, WorkerInfo] = {}
        self._worker_tasks: Dict[str, asyncio.Task] = {}
        self._worker_semaphore = asyncio.Semaphore(self.config.max_workers)

        # Runtime
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._heartbeat_count: int = 0
        self._last_health_report: Dict[str, Any] = {}

        # Callbacks
        self._on_task_received: Optional[Callable] = None
        self._on_worker_completed: Optional[Callable] = None
        self._on_worker_failed: Optional[Callable] = None

    # ── Node Identity ──

    def _generate_node_id(self) -> str:
        import uuid
        return f"node-{uuid.uuid4().hex[:12]}"

    def _get_hostname(self) -> str:
        try:
            import socket
            return socket.gethostname()
        except Exception:
            return "unknown"

    # ── Lifecycle ──

    async def start(self):
        """Start the supervisor: heartbeat, task listener, health monitor"""
        self.log.info(
            f"AgentSupervisor starting: {self.identity.node_id} "
            f"on {self.identity.hostname} "
            f"(max_workers={self.config.max_workers})"
        )
        self._running = True

        # Background tasks
        self._tasks = [
            asyncio.create_task(self._heartbeat_loop(), name=f"hb-{self.identity.node_id}"),
            asyncio.create_task(self._task_listener_loop(), name=f"tl-{self.identity.node_id}"),
            asyncio.create_task(self._health_monitor_loop(), name=f"hm-{self.identity.node_id}"),
            asyncio.create_task(self._worker_cleanup_loop(), name=f"wc-{self.identity.node_id}"),
        ]

        self.log.info("AgentSupervisor started")

    async def stop(self):
        """Graceful shutdown: cancel workers, stop heartbeat"""
        self.log.info("AgentSupervisor stopping...")
        self._running = False

        # Cancel all workers
        for worker_id, task in self._worker_tasks.items():
            task.cancel()
            if worker_id in self._workers:
                self._workers[worker_id].status = WorkerStatus.CANCELLED

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks.values(), return_exceptions=True)
            self._worker_tasks.clear()

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        self.log.info("AgentSupervisor stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Worker Pool Management ──

    async def spawn_worker(
        self,
        task_id: str,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        provider_id: Optional[str] = None,
        max_steps: int = 20,
    ) -> str:
        """Spawn a new worker for a task. Returns worker_id."""

        async with self._worker_semaphore:
            worker_id = f"w-{task_id[:8]}-{len(self._workers)}"

            worker_info = WorkerInfo(
                worker_id=worker_id,
                task_id=task_id,
                status=WorkerStatus.PENDING,
                goal=goal,
            )
            self._workers[worker_id] = worker_info

            # Create the worker task (will be started when semaphore available)
            worker_task = asyncio.create_task(
                self._run_worker(
                    worker_id=worker_id,
                    goal=goal,
                    context=context or {},
                    tools=tools or [],
                    provider_id=provider_id,
                    max_steps=max_steps,
                ),
                name=f"worker-{worker_id}",
            )
            self._worker_tasks[worker_id] = worker_task

            self.log.info(f"Spawned worker {worker_id} for task {task_id}: {goal[:60]}")
            return worker_id

    async def _run_worker(
        self,
        worker_id: str,
        goal: str,
        context: Dict[str, Any],
        tools: List[Dict[str, Any]],
        provider_id: Optional[str],
        max_steps: int,
    ):
        """Execute a worker task"""
        worker = self._workers.get(worker_id)
        if not worker:
            return

        worker.status = WorkerStatus.RUNNING
        worker.started_at = datetime.now()

        try:
            # TODO: Actual worker logic will be in worker.py
            # For now, this is the placeholder that the full Loop Engine will drive
            from ..agent_base import AgentResult

            # Notify task received
            if self._on_task_received:
                await self._on_task_received(worker_id, goal)

            # The actual execution happens via agent_runtime.worker.AgentWorker
            # which is imported dynamically to avoid circular deps
            result = await self._execute_with_timeout(
                worker_id, goal, context, tools, provider_id, max_steps
            )

            worker.status = WorkerStatus.COMPLETED if result.success else WorkerStatus.FAILED
            worker.progress = 1.0
            worker.error = result.error

            if result.success and self._on_worker_completed:
                await self._on_worker_completed(worker_id, result)
            elif not result.success and self._on_worker_failed:
                await self._on_worker_failed(worker_id, result)

            self.log.info(f"Worker {worker_id} {'completed' if result.success else 'failed'}")

        except asyncio.CancelledError:
            worker.status = WorkerStatus.CANCELLED
            self.log.info(f"Worker {worker_id} cancelled")
        except Exception as e:
            worker.status = WorkerStatus.CRASHED
            worker.error = str(e)
            self.log.error(f"Worker {worker_id} crashed: {e}")

            # Auto-recovery
            if self.config.enable_auto_recovery:
                self.log.info(f"Auto-restarting worker {worker_id}...")
                await asyncio.sleep(self.config.worker_restart_delay)
                asyncio.create_task(
                    self._run_worker(worker_id, goal, context, tools, provider_id, max_steps)
                )
        finally:
            worker.completed_at = datetime.now()

    async def _execute_with_timeout(self, worker_id, goal, context, tools, provider_id, max_steps):
        """Execute worker with timeout protection"""
        # Dynamic import to avoid circular dependency
        from .worker import AgentWorker

        # Get LLM provider
        llm_provider = None
        if provider_id:
            try:
                from ..llm_registry import LLMProviderRegistry
                registry = LLMProviderRegistry.get_instance()
                llm_provider = registry.get(provider_id)
            except Exception as e:
                self.log.warning(f"LLM provider {provider_id} not available: {e}")

        worker = AgentWorker(
            worker_id=worker_id,
            goal=goal,
            context=context,
            tools=tools,
            llm_provider=llm_provider,
            max_steps=max_steps,
            timeout=self.config.worker_timeout,
        )

        # Run with timeout
        try:
            result = await asyncio.wait_for(
                worker.execute(),
                timeout=self.config.worker_timeout,
            )
            return result
        except asyncio.TimeoutError:
            from ..agent_base import AgentResult
            self.log.warning(f"Worker {worker_id} timed out after {self.config.worker_timeout}s")
            return AgentResult(
                success=False,
                summary=f"Worker timed out after {self.config.worker_timeout}s",
                error=f"Timeout: {self.config.worker_timeout}s exceeded",
            )

    def cancel_worker(self, worker_id: str) -> bool:
        """Cancel a running worker"""
        if worker_id in self._worker_tasks:
            self._worker_tasks[worker_id].cancel()
            if worker_id in self._workers:
                self._workers[worker_id].status = WorkerStatus.CANCELLED
            return True
        return False

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get worker status"""
        return self._workers.get(worker_id)

    def list_workers(self, status: Optional[WorkerStatus] = None) -> List[WorkerInfo]:
        """List workers, optionally filtered by status"""
        workers = list(self._workers.values())
        if status:
            workers = [w for w in workers if w.status == status]
        return workers

    @property
    def active_worker_count(self) -> int:
        return sum(1 for w in self._workers.values() if w.status == WorkerStatus.RUNNING)

    @property
    def worker_slots_available(self) -> int:
        return self.config.max_workers - self.active_worker_count

    # ── Background Loops ──

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to Coordinator"""
        while self._running:
            try:
                await self._send_heartbeat()
                self._heartbeat_count += 1
                await asyncio.sleep(self.config.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.warning(f"Heartbeat error: {e}")
                await asyncio.sleep(self.config.heartbeat_interval)

    async def _send_heartbeat(self):
        """Compose and send heartbeat payload"""
        if not self.coordinator:
            # No coordinator connected — store locally
            return

        heartbeat = {
            "node_id": self.identity.node_id,
            "hostname": self.identity.hostname,
            "uptime_seconds": self.identity.uptime_seconds,
            "active_workers": self.active_worker_count,
            "max_workers": self.config.max_workers,
            "worker_slots_available": self.worker_slots_available,
            "workers": [
                {"worker_id": w.worker_id, "task_id": w.task_id,
                 "status": w.status.value, "progress": w.progress}
                for w in self._workers.values()
            ],
            "timestamp": datetime.now().isoformat(),
            "health": self._last_health_report,
        }

        try:
            await self.coordinator.heartbeat(heartbeat)
        except Exception as e:
            self.log.debug(f"Heartbeat send failed (coordinator may be down): {e}")

    async def _task_listener_loop(self):
        """Listen for incoming task assignments from Coordinator"""
        while self._running:
            try:
                if self.coordinator:
                    tasks = await self.coordinator.poll_tasks(
                        node_id=self.identity.node_id,
                        max_tasks=self.worker_slots_available,
                    )
                    for task in tasks:
                        await self.spawn_worker(
                            task_id=task.get("task_id", "unknown"),
                            goal=task.get("goal", ""),
                            context=task.get("context", {}),
                            tools=task.get("tools", []),
                            provider_id=task.get("provider_id"),
                            max_steps=task.get("max_steps", 20),
                        )
                await asyncio.sleep(self.config.task_poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.debug(f"Task listener error: {e}")
                await asyncio.sleep(self.config.task_poll_interval * 2)

    async def _health_monitor_loop(self):
        """Monitor worker health and system resources"""
        while self._running:
            try:
                report = await self._collect_health()
                self._last_health_report = report
                await asyncio.sleep(self.config.heartbeat_interval * 2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.debug(f"Health monitor error: {e}")
                await asyncio.sleep(5)

    async def _collect_health(self) -> Dict[str, Any]:
        """Collect health metrics for this node"""
        health: Dict[str, Any] = {
            "status": "healthy",
            "workers": {
                "active": self.active_worker_count,
                "total": len(self._workers),
                "max": self.config.max_workers,
            },
        }

        # System metrics (optional psutil integration)
        try:
            import psutil
            process = psutil.Process()
            health["cpu_percent"] = process.cpu_percent(interval=0.1)
            health["memory_mb"] = process.memory_info().rss / 1024 / 1024
            health["memory_percent"] = process.memory_percent()
        except ImportError:
            # psutil not installed — skip system metrics
            health["cpu_percent"] = 0.0
            health["memory_mb"] = 0.0

        # Check for stale/crashed workers
        crashed = [w for w in self._workers.values() if w.status == WorkerStatus.CRASHED]
        if len(crashed) > 3:
            health["status"] = "degraded"
            health["degradation_reason"] = f"{len(crashed)} crashed workers"

        return health

    async def _worker_cleanup_loop(self):
        """Periodically clean up completed/failed workers from the pool"""
        while self._running:
            try:
                await asyncio.sleep(30)  # Every 30s
                completed_ids = [
                    wid for wid, w in self._workers.items()
                    if w.status in (WorkerStatus.COMPLETED, WorkerStatus.FAILED, WorkerStatus.CANCELLED)
                    and w.completed_at
                    and (datetime.now() - w.completed_at).total_seconds() > 60  # 1 min retention
                ]
                for wid in completed_ids:
                    self._workers.pop(wid, None)
                    self._worker_tasks.pop(wid, None)

                if completed_ids:
                    self.log.debug(f"Cleaned up {len(completed_ids)} completed workers")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.debug(f"Worker cleanup error: {e}")

    # ── Event Handlers ──

    def on_task_received(self, callback: Callable):
        """Register callback when a task is received"""
        self._on_task_received = callback

    def on_worker_completed(self, callback: Callable):
        """Register callback when a worker completes successfully"""
        self._on_worker_completed = callback

    def on_worker_failed(self, callback: Callable):
        """Register callback when a worker fails"""
        self._on_worker_failed = callback
