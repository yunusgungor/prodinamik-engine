"""Prodinamik AI Grid — Coordinator Node

Central orchestrator that runs on the Raft Leader node.

Responsibilities:
- Task Queue management (enqueue, dequeue, priority, retry)
- Agent Registry (node registration, heartbeats, liveness)
- Scheduler (task -> node assignment with load balancing)
- Human Loop (approval gates, escalation)
- RPC server for worker communication
- Coordinator failover via Raft leader election

Architecture:
    Coordinator (Leader Node)
    ├── TaskQueue (WAL-backed priority queue)
    ├── AgentRegistry (node capabilities + heartbeats)
    ├── Scheduler (affinity + load balancing)
    ├── HumanLoop (approval gates + escalation)
    ├── Heartbeat Receiver (from worker supervisors)
    └── Task Poller (workers request tasks)

Failover:
    Raft detects leader change -> new leader initializes Coordinator
    from WAL replay. Active tasks are reassigned after TTL.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from ..log import get_logger
from .task_queue import TaskStatus


class CoordinatorStatus(Enum):
    STANDBY = "standby"       # Not the leader
    ACTIVE = "active"         # Running as coordinator
    FAILING_OVER = "failing_over"  # Transitioning
    STOPPED = "stopped"


@dataclass
class CoordinatorConfig:
    """Configuration for the Coordinator"""
    node_id: str = ""                # This node's ID
    heartbeat_ttl: float = 10.0      # Node considered dead after this
    task_poll_interval: float = 1.0  # How often workers poll for tasks
    max_task_retries: int = 3        # Max retry per task
    task_timeout: float = 600.0      # Task max execution time (10 min)
    enable_human_loop: bool = True   # Enable approval gates
    escaltion_threshold: int = 3     # Escalate after N failures
    wal_dir: str = ""                # WAL directory for task queue
    auto_reassign: bool = True       # Reassign tasks from dead nodes


class CoordinatorNode:
    """
    Central coordinator — runs on the Raft leader.

    Manages the global task queue, agent registry, scheduling,
    heartbeat processing, and human-in-the-loop escalation.

    Usage:
        coordinator = CoordinatorNode(config)
        await coordinator.start()
        # ... runs in background ...
        await coordinator.stop()
    """

    def __init__(self, config: Optional[CoordinatorConfig] = None):
        self.config = config or CoordinatorConfig()
        self.log = get_logger()

        # Status
        self.status = CoordinatorStatus.STOPPED
        self._running = False

        # Core components (lazy init)
        self.task_queue = None
        self.agent_registry = None
        self.scheduler = None
        self.human_loop = None

        # Background tasks
        self._tasks: List[asyncio.Task] = []

        # Callbacks
        self._on_task_assigned: Optional[Callable] = None
        self._on_task_completed: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None
        self._on_node_lost: Optional[Callable] = None
        self._on_escalate: Optional[Callable] = None

        # Stats
        self._tasks_assigned = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._started_at: Optional[float] = None

    async def start(self):
        """Initialize components and start background loops"""
        if self._running:
            return

        # Lazy imports
        from .task_queue import TaskQueue, Task
        from .agent_registry import AgentRegistry

        self.log.info(f"Coordinator starting on node {self.config.node_id}")
        self.status = CoordinatorStatus.ACTIVE
        self._running = True
        self._started_at = time.time()

        # Initialize core
        data_dir = self.config.wal_dir or os.environ.get("PRODINAMIK_DATA_DIR", "./data")
        wal_path = os.path.join(data_dir, "coordinator_queue.wal")
        self.task_queue = TaskQueue(wal_path=wal_path)

        self.agent_registry = AgentRegistry(heartbeat_ttl=self.config.heartbeat_ttl)

        # Lazy init scheduler and human loop
        try:
            from .scheduler import Scheduler
            self.scheduler = Scheduler(self.agent_registry, self.task_queue)
        except ImportError:
            self.log.warning("Scheduler not available — tasks will not auto-assign")
            self.scheduler = None

        if self.config.enable_human_loop:
            try:
                from .human_loop import HumanLoopManager
                self.human_loop = HumanLoopManager(
                    escalation_threshold=self.config.escaltion_threshold,
                )
            except ImportError:
                self.log.warning("HumanLoop not available — running without approval gates")
                self.human_loop = None
        else:
            self.human_loop = None

        # Background loops
        self._tasks = [
            asyncio.create_task(self._task_timeout_watcher(), name="coord-timeout"),
            asyncio.create_task(self._stale_node_cleanup(), name="coord-stale-cleanup"),
            asyncio.create_task(self._task_reassign_loop(), name="coord-reassign"),
        ]

        self.log.info(f"Coordinator active: {self.config.node_id}")

    async def stop(self):
        """Graceful shutdown"""
        self.log.info("Coordinator stopping...")
        self._running = False
        self.status = CoordinatorStatus.STOPPED

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        # Close task queue WAL
        if self.task_queue:
            await self.task_queue.close()

        self.log.info("Coordinator stopped")

    @property
    def is_active(self) -> bool:
        return self.status == CoordinatorStatus.ACTIVE and self._running

    @property
    def uptime_seconds(self) -> float:
        if self._started_at:
            return time.time() - self._started_at
        return 0.0

    # ── Task Operations ──

    async def submit_task(self, goal: str, priority: int = 2,
                          affinity: str = "", context: Dict = None,
                          tools: List[str] = None, max_steps: int = 20,
                          parent_task: str = "") -> str:
        """Submit a goal as a task to the queue. Returns task_id."""
        from .task_queue import Task

        task_id = f"task-{uuid.uuid4().hex[:12]}"

        task = Task(
            task_id=task_id,
            goal=goal,
            priority=priority,
            affinity=affinity,
            context=context or {},
            tools=tools or [],
            max_steps=max_steps,
            parent_task=parent_task,
            max_retries=self.config.max_task_retries,
        )

        await self.task_queue.enqueue(task)
        self.log.info(f"Task submitted: {task_id} (priority={priority}, affinity='{affinity}')")

        # Auto-assign if scheduler available
        if self.scheduler:
            await self.scheduler.try_assign()

        return task_id

    async def submit_goal(self, goal: str, decompose: bool = True) -> str:
        """Submit a high-level goal. Optionally decompose into subtasks."""
        # For now, submit as single task
        # Future: LLM-based goal decomposition
        return await self.submit_task(goal, priority=1)

    async def heartbeat(self, node_id: str, data: Dict[str, Any]) -> bool:
        """Process a heartbeat from a worker node"""
        if not self.agent_registry:
            return False

        registered = self.agent_registry.heartbeat(node_id, data)

        if not registered:
            # Auto-register if not found (new node)
            self.agent_registry.register_node(
                node_id=node_id,
                hostname=data.get("hostname", ""),
                capabilities=data.get("capabilities", []),
                max_workers=data.get("max_workers", 3),
            )
            registered = True

        # Check for tasks to assign
        if self.scheduler:
            await self.scheduler.try_assign()

        return registered

    async def poll_tasks(self, node_id: str, max_tasks: int = 1) -> List[Dict[str, Any]]:
        """Worker nodes call this to get new tasks"""
        if not self.task_queue or not self.agent_registry:
            return []

        node = self.agent_registry.get_node(node_id)
        if not node:
            return []

        # Find tasks matching this node's capabilities
        tasks = []
        for _ in range(min(max_tasks, max(0, node.max_workers - node.active_workers))):
            # Determine best affinity for this node
            affinity = ""
            if node.capabilities:
                affinity = node.capabilities[0]  # Primary capability

            task = self.task_queue.dequeue(affinity=affinity)
            if not task:
                # Try without affinity
                task = self.task_queue.dequeue()
            if not task:
                break

            await self.task_queue.acknowledge(task.task_id, node_id)
            self._tasks_assigned += 1

            tasks.append({
                "task_id": task.task_id,
                "goal": task.goal,
                "context": task.context,
                "tools": task.tools,
                "max_steps": task.max_steps,
                "priority": task.priority,
            })

        if tasks:
            self.log.debug(f"Assigned {len(tasks)} task(s) to {node_id}")

        return tasks

    async def report_result(self, task_id: str, node_id: str,
                            success: bool, result: Dict = None,
                            error: str = "") -> bool:
        """Worker reports task completion/failure"""
        if success:
            ok = await self.task_queue.complete(task_id, result or {})
            if ok:
                self._tasks_completed += 1
                if self._on_task_completed:
                    await self._on_task_completed(task_id, result or {})
        else:
            ok = await self.task_queue.fail(task_id, error=error, retry=True)
            if ok:
                self._tasks_failed += 1
                if self._on_task_failed:
                    await self._on_task_failed(task_id, error)

                # Escalate if exceeded threshold
                task = self.task_queue.get_task(task_id)
                if task and task.retry_count >= self.config.escaltion_threshold:
                    self.log.warning(f"Task {task_id} exceeded escalation threshold")
                    if self.human_loop:
                        await self.human_loop.escalate(task, error)
                    if self._on_escalate:
                        await self._on_escalate(task_id, error)

        return ok

    async def cancel_task(self, task_id: str) -> bool:
        return await self.task_queue.cancel(task_id)

    # ── Scheduler (delegates to scheduler module) ──

    async def schedule_task(self, task) -> Optional[str]:
        """Explicitly schedule a task to a node"""
        if self.scheduler:
            return await self.scheduler.schedule(task)
        return None

    async def try_assign(self):
        """Try to assign queued tasks to available nodes"""
        if self.scheduler:
            await self.scheduler.try_assign()

    # ── Background Loops ──

    async def _task_timeout_watcher(self):
        """Watch for timed out tasks and fail them"""
        while self._running:
            try:
                await asyncio.sleep(15)  # Check every 15s
                if not self.task_queue:
                    continue

                now = datetime.now()
                for task in self.task_queue.list_tasks(TaskStatus.RUNNING):
                    if task.assigned_at:
                        try:
                            assigned = datetime.fromisoformat(task.assigned_at)
                            elapsed = (now - assigned).total_seconds()
                            if elapsed > self.config.task_timeout:
                                self.log.warning(f"Task {task.task_id} timed out ({elapsed:.0f}s)")
                                await self.task_queue.fail(
                                    task.task_id,
                                    error=f"Timed out after {elapsed:.0f}s",
                                    retry=True,
                                )
                        except (ValueError, TypeError):
                            continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Timeout watcher error: {e}")

    async def _stale_node_cleanup(self):
        """Periodically clean up stale nodes"""
        while self._running:
            try:
                await asyncio.sleep(30)
                if self.agent_registry:
                    count = self.agent_registry.cleanup_stale_nodes()
                    if count and self._on_node_lost:
                        # Notify about each lost node
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Stale cleanup error: {e}")

    async def _task_reassign_loop(self):
        """Reassign tasks from dead nodes"""
        while self._running:
            try:
                await asyncio.sleep(20)
                if not self.config.auto_reassign or not self.task_queue:
                    continue

                for task in self.task_queue.list_tasks(TaskStatus.ASSIGNED):
                    if task.assigned_node:
                        node = self.agent_registry.get_node(task.assigned_node) if self.agent_registry else None
                        if node and not node.is_alive(self.config.heartbeat_ttl):
                            self.log.info(f"Reassigning task {task.task_id} from dead node {task.assigned_node}")
                            task.assigned_node = ""
                            await self.task_queue.fail(task.task_id, error="Node lost", retry=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Reassign error: {e}")

    # ── Event Handlers ──

    def on_task_assigned(self, callback: Callable):
        self._on_task_assigned = callback

    def on_task_completed(self, callback: Callable):
        self._on_task_completed = callback

    def on_task_failed(self, callback: Callable):
        self._on_task_failed = callback

    def on_node_lost(self, callback: Callable):
        self._on_node_lost = callback

    def on_escalate(self, callback: Callable):
        self._on_escalate = callback

    # ── Status ──

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "uptime": self.uptime_seconds,
            "tasks_assigned": self._tasks_assigned,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "queue_depth": self.task_queue.queue_depth if self.task_queue else 0,
            "active_tasks": self.task_queue.active_count if self.task_queue else 0,
            "total_tasks": self.task_queue.total_count if self.task_queue else 0,
            "nodes_alive": self.agent_registry.get_alive_count() if self.agent_registry else 0,
            "total_nodes": len(self.agent_registry.list_nodes()) if self.agent_registry else 0,
            "human_loop": self.human_loop is not None,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Detailed health check"""
        return {
            "status": "healthy" if self.is_active else "standby",
            "coordinator": self.stats,
            "task_queue": self.task_queue.stats if self.task_queue else {},
            "agent_registry": self.agent_registry.stats if self.agent_registry else {},
        }
