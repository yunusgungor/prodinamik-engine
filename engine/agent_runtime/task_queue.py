"""Prodinamik AI Grid — WAL-Backed Task Queue

Priority + Affinity task queue with Write-Ahead Log for crash recovery.

Architecture:
    TaskQueue
    ├── Priority Queue (heapq-based, multi-level priority)
    ├── WAL (JSONL append-only log for crash recovery)
    ├── State Tracking (pending/running/completed/failed/cancelled)
    └── Task Lifecycle: queued → assigned → running → completed / failed

Usage:
    queue = TaskQueue(wal_path="./data/task_queue.wal")
    queue.enqueue(Task(goal="Run tests", priority=5))
    task = queue.dequeue()  # Highest priority first
"""

from __future__ import annotations

import asyncio
import heapq
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..log import get_logger


# ── Task Status ──

class TaskStatus(Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


# ── Task Priority ──

@dataclass(order=True)
class PrioritizedTask:
    """Heap entry: (priority, timestamp, task_id) — lower priority = higher urgency"""
    priority: int        # 0=critical, 1=high, 2=normal, 3=low
    timestamp: float     # Enqueue time (FIFO tiebreaker)
    task_id: str         # Unique task ID


# ── Task Data ──

@dataclass
class Task:
    """A task in the queue"""
    task_id: str = ""
    goal: str = ""
    priority: int = 2           # 0=critical, 1=high, 2=normal, 3=low
    affinity: str = ""          # Preferred node ID or capability tag
    context: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    max_steps: int = 20
    status: TaskStatus = TaskStatus.QUEUED
    assigned_node: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    assigned_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    parent_task: str = ""        # For subtask decomposition
    subtasks: List[str] = field(default_factory=list)
    max_retries: int = 3
    retry_count: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                               TaskStatus.CANCELLED, TaskStatus.TIMEOUT)

    @property
    def age_seconds(self) -> float:
        try:
            created = datetime.fromisoformat(self.created_at)
            return (datetime.now() - created).total_seconds()
        except (ValueError, TypeError):
            return 0.0


# ── WAL-Backed Task Queue ──

class TaskQueue:
    """
    Priority queue backed by Write-Ahead Log for crash recovery.

    - Enqueue: write WAL entry + push to heap
    - Dequeue: pop highest priority (lowest number)
    - Acknowledge: mark assigned/running
    - Complete/Fail: update status, write WAL
    - Recovery: replay WAL on startup

    Usage:
        queue = TaskQueue(wal_path="./data/task_queue.wal")
        queue.enqueue(Task(goal="Analyze data", priority=1))
        task = queue.dequeue()
        queue.acknowledge(task.task_id)
        queue.complete(task.task_id, {"summary": "Done"})
    """

    def __init__(
        self,
        wal_path: str = "",
        max_concurrent: int = 100,
    ):
        self.wal_path = wal_path or os.path.join(
            os.environ.get("PRODINAMIK_DATA_DIR", "./data"),
            "task_queue.wal",
        )
        self.max_concurrent = max_concurrent
        self.log = get_logger()

        # Heap of PrioritizedTask entries
        self._heap: List[PrioritizedTask] = []

        # Task data keyed by task_id
        self._tasks: Dict[str, Task] = {}

        # Tracking sets
        self._queued_ids: Set[str] = set()
        self._active_ids: Set[str] = set()
        self._completed_ids: Set[str] = set()

        # WAL
        self._wal_file: Optional[Any] = None
        self._wal_lock = asyncio.Lock()

        # Initialization
        self._init_wal()

    def _init_wal(self):
        """Initialize WAL: ensure directory exists, replay on startup"""
        wal_dir = os.path.dirname(self.wal_path)
        if wal_dir:
            os.makedirs(wal_dir, exist_ok=True)

        # Recover from existing WAL
        if os.path.exists(self.wal_path):
            self._replay_wal()

        # Open WAL for appending
        self._wal_file = open(self.wal_path, "a", buffering=1)  # Line-buffered

    def _replay_wal(self):
        """Replay WAL on startup to rebuild queue state"""
        recovered_count = 0
        try:
            with open(self.wal_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        action = entry.get("action")
                        data = entry.get("data", {})

                        if action == "enqueue":
                            # Filter to only Task dataclass fields
                            valid_fields = {"task_id", "goal", "priority", "affinity",
                                           "context", "tools", "max_steps", "max_retries",
                                           "retry_count", "parent_task", "status",
                                           "assigned_node", "created_at", "subtasks"}
                            clean_data = {k: v for k, v in data.items() if k in valid_fields}
                            task = Task(**clean_data)
                            self._tasks[task.task_id] = task
                            heapq.heappush(self._heap, PrioritizedTask(
                                priority=data.get("priority", 2),
                                timestamp=data.get("_timestamp", time.time()),
                                task_id=task.task_id,
                            ))
                            self._queued_ids.add(task.task_id)
                            recovered_count += 1
                        elif action == "acknowledge":
                            tid = data.get("task_id")
                            if tid in self._tasks:
                                task = self._tasks[tid]
                                task.status = TaskStatus.ASSIGNED
                                task.assigned_node = data.get("node_id", "")
                                self._queued_ids.discard(tid)
                                self._active_ids.add(tid)
                        elif action == "complete":
                            tid = data.get("task_id")
                            if tid in self._tasks:
                                task = self._tasks[tid]
                                task.status = TaskStatus.COMPLETED
                                task.result = data.get("result", {})
                                task.completed_at = data.get("completed_at")
                                self._queued_ids.discard(tid)
                                self._active_ids.discard(tid)
                                self._completed_ids.add(tid)
                        elif action == "fail":
                            tid = data.get("task_id")
                            if tid in self._tasks:
                                task = self._tasks[tid]
                                task.status = TaskStatus.FAILED
                                task.error = data.get("error")
                                task.completed_at = data.get("completed_at")
                                self._queued_ids.discard(tid)
                                self._active_ids.discard(tid)
                                self._completed_ids.add(tid)
                        elif action == "cancel":
                            tid = data.get("task_id")
                            if tid in self._tasks:
                                task = self._tasks[tid]
                                task.status = TaskStatus.CANCELLED
                                self._queued_ids.discard(tid)
                                self._active_ids.discard(tid)
                                self._completed_ids.add(tid)
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        self.log.debug(f"Skipping malformed WAL entry: {e}")
        except FileNotFoundError:
            pass

        if recovered_count:
            self.log.info(f"Recovered {recovered_count} tasks from WAL")

    async def _write_wal(self, action: str, data: Dict[str, Any]) -> None:
        """Write an entry to the WAL"""
        if not self._wal_file:
            return

        async with self._wal_lock:
            try:
                entry = json.dumps({"action": action, "data": data, "_ts": datetime.now().isoformat()})
                self._wal_file.write(entry + "\n")
                self._wal_file.flush()
                os.fsync(self._wal_file.fileno())
            except Exception as e:
                self.log.error(f"WAL write failed: {e}")

    # ── Core Operations ──

    async def enqueue(self, task: Task) -> str:
        """Add a task to the queue. Returns task_id."""
        if not task.task_id:
            task.task_id = f"task-{uuid.uuid4().hex[:12]}"

        task.status = TaskStatus.QUEUED
        task.created_at = datetime.now().isoformat()

        self._tasks[task.task_id] = task

        heap_entry = PrioritizedTask(
            priority=task.priority,
            timestamp=time.time(),
            task_id=task.task_id,
        )
        heapq.heappush(self._heap, heap_entry)
        self._queued_ids.add(task.task_id)

        # WAL
        await self._write_wal("enqueue", {
            "task_id": task.task_id,
            "goal": task.goal,
            "priority": task.priority,
            "affinity": task.affinity,
            "context": task.context,
            "tools": task.tools,
            "max_steps": task.max_steps,
            "max_retries": task.max_retries,
            "parent_task": task.parent_task,
            "_timestamp": heap_entry.timestamp,
        })

        self.log.debug(f"Task enqueued: {task.task_id} (priority={task.priority})")
        return task.task_id

    async def enqueue_batch(self, tasks: List[Task]) -> List[str]:
        """Enqueue multiple tasks at once"""
        return [await self.enqueue(t) for t in tasks]

    def dequeue(self, affinity: str = "") -> Optional[Task]:
        """
        Dequeue the highest priority task.
        Optionally filter by affinity (node capability tag).
        Returns None if no matching task.
        Also removes from the heap.
        """
        # Collect matching candidates
        candidates = []
        remaining = []

        while self._heap:
            entry = heapq.heappop(self._heap)
            task = self._tasks.get(entry.task_id)

            if task is None or task.status != TaskStatus.QUEUED:
                continue  # Stale entry

            if affinity and task.affinity and task.affinity != affinity:
                remaining.append(entry)  # Not for this node
                continue

            candidates.append((entry, task))
            break  # Found best match

        # Push back remaining
        for e in remaining:
            heapq.heappush(self._heap, e)

        if not candidates:
            return None

        entry, task = candidates[0]
        return task

    def peek(self, count: int = 5) -> List[Task]:
        """Peek at top tasks without dequeuing"""
        snapshot = []
        for entry in heapq.nsmallest(count, self._heap):
            task = self._tasks.get(entry.task_id)
            if task and task.status == TaskStatus.QUEUED:
                snapshot.append(task)
        return snapshot

    async def acknowledge(self, task_id: str, node_id: str = "") -> bool:
        """Mark a task as assigned to a node"""
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.status = TaskStatus.ASSIGNED
        task.assigned_node = node_id
        task.assigned_at = datetime.now().isoformat()

        self._queued_ids.discard(task_id)
        self._active_ids.add(task_id)

        await self._write_wal("acknowledge", {
            "task_id": task_id,
            "node_id": node_id,
        })

        return True

    async def complete(self, task_id: str, result: Dict[str, Any] = None) -> bool:
        """Mark a task as completed"""
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.status = TaskStatus.COMPLETED
        task.result = result or {}
        task.completed_at = datetime.now().isoformat()

        self._active_ids.discard(task_id)
        self._completed_ids.add(task_id)

        await self._write_wal("complete", {
            "task_id": task_id,
            "result": result or {},
            "completed_at": task.completed_at,
        })

        return True

    async def fail(self, task_id: str, error: str = "", retry: bool = True) -> bool:
        """Mark a task as failed. Optionally retry."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        if retry and task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.QUEUED
            task.assigned_node = ""
            task.assigned_at = None
            self._active_ids.discard(task_id)
            self._queued_ids.add(task_id)
            # Re-push to heap
            heapq.heappush(self._heap, PrioritizedTask(
                priority=task.priority,
                timestamp=time.time(),
                task_id=task_id,
            ))
            await self._write_wal("enqueue", {
                "task_id": task_id, "goal": task.goal,
                "priority": task.priority, "affinity": task.affinity,
                "_timestamp": time.time(), "retry": True,
            })
            self.log.info(f"Task {task_id} requeued (retry {task.retry_count}/{task.max_retries})")
        else:
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.now().isoformat()
            self._active_ids.discard(task_id)
            self._completed_ids.add(task_id)
            await self._write_wal("fail", {
                "task_id": task_id, "error": error,
                "completed_at": task.completed_at,
            })

        return True

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task"""
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.status = TaskStatus.CANCELLED
        self._queued_ids.discard(task_id)
        self._active_ids.discard(task_id)
        self._completed_ids.add(task_id)

        await self._write_wal("cancel", {"task_id": task_id})
        return True

    async def cancel_all(self, status_filter: Optional[TaskStatus] = None) -> int:
        """Cancel all tasks (optionally filtered by status)"""
        count = 0
        for tid, task in list(self._tasks.items()):
            if status_filter and task.status != status_filter:
                continue
            if not task.is_terminal:
                await self.cancel(tid)
                count += 1
        return count

    # ── Query ──

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: (t.priority, t.created_at), reverse=False)
        return tasks[:limit]

    def list_active(self) -> List[Task]:
        return self.list_tasks(TaskStatus.RUNNING)

    def list_queued(self) -> List[Task]:
        return self.list_tasks(TaskStatus.QUEUED)

    @property
    def queue_depth(self) -> int:
        return len(self._queued_ids)

    @property
    def active_count(self) -> int:
        return len(self._active_ids)

    @property
    def total_count(self) -> int:
        return len(self._tasks)

    @property
    def stats(self) -> Dict[str, Any]:
        status_counts = {}
        for t in self._tasks.values():
            status_counts[t.status.value] = status_counts.get(t.status.value, 0) + 1
        return {
            "queue_depth": self.queue_depth,
            "active": self.active_count,
            "total": self.total_count,
            "by_status": status_counts,
            "wal_path": self.wal_path,
            "max_concurrent": self.max_concurrent,
        }

    async def close(self):
        """Close WAL file"""
        if self._wal_file:
            self._wal_file.close()
            self._wal_file = None
        # Compact WAL: keep only non-terminal tasks
        await self._compact_wal()

    async def _compact_wal(self):
        """Compact WAL: remove completed/failed/cancelled entries, keep pending+active"""
        active_entries = []
        for task in self._tasks.values():
            if task.status in (TaskStatus.QUEUED, TaskStatus.ASSIGNED, TaskStatus.RUNNING):
                active_entries.append(task)

        if not active_entries:
            # Truncate WAL if nothing active
            try:
                open(self.wal_path, "w").close()  # Empty file
            except Exception:
                pass
            return

        # Rewrite WAL with only active tasks
        try:
            tmp_path = self.wal_path + ".tmp"
            with open(tmp_path, "w") as f:
                for task in active_entries:
                    entry = json.dumps({
                        "action": "enqueue",
                        "data": {"task_id": task.task_id, "goal": task.goal,
                                "priority": task.priority, "affinity": task.affinity,
                                "context": task.context, "tools": task.tools,
                                "max_steps": task.max_steps, "max_retries": task.max_retries,
                                "retry_count": task.retry_count, "parent_task": task.parent_task,},
                        "_ts": datetime.now().isoformat(),
                    })
                    f.write(entry + "\n")
            os.replace(tmp_path, self.wal_path)
        except Exception as e:
            self.log.warning(f"WAL compaction failed: {e}")
