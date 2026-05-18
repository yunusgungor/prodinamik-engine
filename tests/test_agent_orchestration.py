"""Tests for Prodinamik AI Grid — Phase 2: Orchestration Layer"""

import os
import sys
import json
import time
import pytest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.agent_runtime.task_queue import (
    TaskQueue, Task, TaskStatus, PrioritizedTask,
)
from engine.agent_runtime.agent_registry import (
    AgentRegistry, NodeInfo, CapabilityQuery,
)
from engine.agent_runtime.scheduler import Scheduler
from engine.agent_runtime.human_loop import (
    HumanLoopManager, EscalatedItem, EscalationReason, ReviewStatus,
)
from engine.agent_runtime.global_memory import (
    GlobalMemory, CRDTEntry,
)


# ════════════════════════════════════════════════
# Task Queue Tests
# ════════════════════════════════════════════════

class TestTask:
    def test_task_defaults(self):
        t = Task(goal="test", task_id="auto-test")
        assert t.task_id == "auto-test"
        assert t.status == TaskStatus.QUEUED
        assert t.priority == 2
        assert t.max_retries == 3
        assert t.retry_count == 0
        assert t.task_id != ""

    def test_task_terminal(self):
        t = Task(goal="test", status=TaskStatus.COMPLETED)
        assert t.is_terminal
        t2 = Task(goal="test", status=TaskStatus.QUEUED)
        assert not t2.is_terminal

    def test_task_age(self):
        t = Task(goal="test")
        assert t.age_seconds >= 0.0


class TestTaskQueue:
    @pytest.fixture
    def tmp_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield os.path.join(tmp, "queue.wal")

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        tid = await q.enqueue(Task(goal="hello"))
        assert tid.startswith("task-")
        assert q.queue_depth == 1

        task = q.dequeue()
        assert task is not None
        assert task.goal == "hello"
        # Must acknowledge to remove from queue
        await q.acknowledge(tid, "node-1")
        assert q.queue_depth == 0
        await q.close()

    @pytest.mark.asyncio
    async def test_priority_ordering(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        await q.enqueue(Task(goal="low", priority=3))
        await q.enqueue(Task(goal="high", priority=0))
        await q.enqueue(Task(goal="normal", priority=2))

        t1 = q.dequeue()
        assert t1.goal == "high"
        t2 = q.dequeue()
        assert t2.goal == "normal"
        t3 = q.dequeue()
        assert t3.goal == "low"
        await q.close()

    @pytest.mark.asyncio
    async def test_dequeue_empty(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        assert q.dequeue() is None
        await q.close()

    @pytest.mark.asyncio
    async def test_acknowledge(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        tid = await q.enqueue(Task(goal="test"))
        assert await q.acknowledge(tid, "node-1")
        task = q.get_task(tid)
        assert task.status == TaskStatus.ASSIGNED
        assert task.assigned_node == "node-1"
        await q.close()

    @pytest.mark.asyncio
    async def test_complete(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        tid = await q.enqueue(Task(goal="test"))
        assert await q.complete(tid, {"result": "ok"})
        task = q.get_task(tid)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == {"result": "ok"}
        await q.close()

    @pytest.mark.asyncio
    async def test_fail_no_retry(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        tid = await q.enqueue(Task(goal="test", max_retries=0))
        assert await q.fail(tid, "error happened", retry=False)
        task = q.get_task(tid)
        assert task.status == TaskStatus.FAILED
        await q.close()

    @pytest.mark.asyncio
    async def test_auto_retry(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        tid = await q.enqueue(Task(goal="test", max_retries=2))
        assert await q.fail(tid, "temporary error", retry=True)
        task = q.get_task(tid)
        assert task.status == TaskStatus.QUEUED  # Re-queued
        assert task.retry_count == 1
        await q.close()

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        tid = await q.enqueue(Task(goal="test"))
        assert await q.cancel(tid)
        task = q.get_task(tid)
        assert task.status == TaskStatus.CANCELLED
        await q.close()

    @pytest.mark.asyncio
    async def test_peek(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        await q.enqueue(Task(goal="a", priority=1))
        await q.enqueue(Task(goal="b", priority=2))
        top = q.peek(1)
        assert len(top) == 1
        assert top[0].goal == "a"
        assert q.queue_depth == 2
        await q.close()

    @pytest.mark.asyncio
    async def test_list_tasks(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        await q.enqueue(Task(goal="a"))
        await q.enqueue(Task(goal="b"))
        all_tasks = q.list_tasks()
        assert len(all_tasks) == 2
        await q.close()

    @pytest.mark.asyncio
    async def test_stats(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        stats = q.stats
        assert stats["queue_depth"] >= 0
        assert stats["max_concurrent"] == 100
        await q.close()

    @pytest.mark.asyncio
    async def test_batch_enqueue(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        ids = await q.enqueue_batch([
            Task(goal="a"), Task(goal="b"), Task(goal="c"),
        ])
        assert len(ids) == 3
        assert q.total_count == 3
        await q.close()

    @pytest.mark.asyncio
    async def test_cancel_all_queued(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        await q.enqueue(Task(goal="a"))
        await q.enqueue(Task(goal="b"))
        cancelled = await q.cancel_all(status_filter=TaskStatus.QUEUED)
        assert cancelled == 2
        await q.close()

    @pytest.mark.asyncio
    async def test_wal_persistence(self, tmp_wal):
        q = TaskQueue(wal_path=tmp_wal)
        await q.enqueue(Task(goal="persist-test"))
        await q.close()

        q2 = TaskQueue(wal_path=tmp_wal)
        assert q2.total_count >= 1
        task = q2.dequeue()
        assert task is not None
        assert task.goal == "persist-test"
        await q2.close()


# ════════════════════════════════════════════════
# Agent Registry Tests
# ════════════════════════════════════════════════

class TestNodeInfo:
    def test_available_slots(self):
        n = NodeInfo(node_id="n1", max_workers=5, active_workers=2)
        assert n.available_slots == 3

    def test_load_ratio(self):
        n = NodeInfo(node_id="n1", max_workers=4, active_workers=2)
        assert n.load_ratio == 0.5

    def test_is_alive_no_heartbeat(self):
        n = NodeInfo(node_id="n1")
        assert not n.is_alive()


class TestAgentRegistry:
    def test_register_and_get(self):
        r = AgentRegistry()
        r.register_node("node-1", hostname="host1", capabilities=["llm", "search"])
        node = r.get_node("node-1")
        assert node is not None
        assert node.hostname == "host1"
        assert "llm" in node.capabilities

    def test_list_nodes(self):
        r = AgentRegistry()
        r.register_node("n1")
        r.register_node("n2")
        assert len(r.list_nodes()) == 2

    def test_unregister(self):
        r = AgentRegistry()
        r.register_node("n1")
        assert r.unregister_node("n1")
        assert not r.unregister_node("nonexistent")
        assert len(r.list_nodes()) == 0

    def test_heartbeat(self):
        r = AgentRegistry()
        r.register_node("n1")
        assert r.heartbeat("n1", {"active_workers": 2})
        node = r.get_node("n1")
        assert node.active_workers == 2
        assert node.last_heartbeat is not None

    def test_heartbeat_unregistered(self):
        r = AgentRegistry()
        assert not r.heartbeat("unknown")

    def test_find_by_capability(self):
        r = AgentRegistry(heartbeat_ttl=60)
        r.register_node("n1", capabilities=["llm"], max_workers=3)
        r.register_node("n2", capabilities=["search"], max_workers=3)
        # Send heartbeats so nodes are alive
        r.heartbeat("n1")
        r.heartbeat("n2")

        results = r.find_by_capability("llm")
        assert len(results) == 1
        assert results[0].node_id == "n1"

    def test_find_best_node(self):
        r = AgentRegistry(heartbeat_ttl=60)
        r.register_node("n1", capabilities=["llm"], max_workers=3)
        r.heartbeat("n1")
        best = r.find_best_node()
        assert best == "n1"

    def test_find_best_node_none_available(self):
        r = AgentRegistry()
        assert r.find_best_node() is None

    def test_mark_unhealthy(self):
        r = AgentRegistry()
        r.register_node("n1")
        r.mark_unhealthy("n1", "disk full")
        node = r.get_node("n1")
        assert not node.is_healthy
        assert node.last_error == "disk full"

    def test_cleanup_stale(self):
        r = AgentRegistry(heartbeat_ttl=0.01)
        r.register_node("n1")
        r.heartbeat("n1")  # Send heartbeat first
        time.sleep(0.05)
        cleaned = r.cleanup_stale_nodes()
        assert cleaned >= 1

    def test_stats(self):
        r = AgentRegistry()
        r.register_node("n1")
        r.register_node("n2")
        r.heartbeat("n1")
        stats = r.stats
        assert stats["total_nodes"] == 2
        assert stats["alive"] >= 1


# ════════════════════════════════════════════════
# Scheduler Tests
# ════════════════════════════════════════════════

class TestScheduler:
    @pytest.mark.asyncio
    async def test_schedule_no_nodes(self):
        registry = AgentRegistry()
        queue = TaskQueue(wal_path="/tmp/test_sched_queue.wal")
        scheduler = Scheduler(registry, queue)

        tid = await queue.enqueue(Task(goal="test"))
        task = queue.get_task(tid)
        # No nodes registered - schedule returns None (not raises)
        node = await scheduler.schedule(task)
        assert node is None

        await queue.close()
        try: os.remove("/tmp/test_sched_queue.wal")
        except: pass

    @pytest.mark.asyncio
    async def test_stats(self):
        registry = AgentRegistry()
        queue = TaskQueue(wal_path="/tmp/test_sched_stats.wal")
        scheduler = Scheduler(registry, queue)
        stats = scheduler.stats
        assert stats["total_scheduled"] == 0
        assert stats["failed_assignments"] == 0
        await queue.close()
        try: os.remove("/tmp/test_sched_stats.wal")
        except: pass

    @pytest.mark.asyncio
    async def test_get_node_for_task(self):
        registry = AgentRegistry()
        queue = TaskQueue(wal_path="/tmp/test_sched_get.wal")
        scheduler = Scheduler(registry, queue)
        assert scheduler.get_node_for_task("nonexistent") is None
        await queue.close()
        try: os.remove("/tmp/test_sched_get.wal")
        except: pass


# ════════════════════════════════════════════════
# Human Loop Tests
# ════════════════════════════════════════════════

class MockTask:
    def __init__(self):
        self.task_id = "task-mock-001"
        self.goal = "Test goal for escalation"
        self.context = {"source": "test"}


class TestHumanLoop:
    def test_escalate_and_pending(self):
        loop = HumanLoopManager()
        task = MockTask()

        import asyncio
        async def _test():
            eid = await loop.escalate(task, "something went wrong")
            assert eid.startswith("esc-")
            assert loop.pending_count == 1
            assert loop.total_escalated == 1

        asyncio.run(_test())

    def test_approve(self):
        loop = HumanLoopManager()
        task = MockTask()

        import asyncio
        async def _test():
            eid = await loop.escalate(task, "error")
            assert loop.approve(eid, "admin", "looks good")
            assert loop.pending_count == 0
            assert len(loop.get_resolved()) == 1

        asyncio.run(_test())

    def test_reject(self):
        loop = HumanLoopManager()
        task = MockTask()

        import asyncio
        async def _test():
            eid = await loop.escalate(task, "error")
            assert loop.reject(eid, "admin", "not needed")
            assert loop.pending_count == 0

        asyncio.run(_test())

    def test_approve_nonexistent(self):
        loop = HumanLoopManager()
        assert not loop.approve("nope")

    def test_reject_nonexistent(self):
        loop = HumanLoopManager()
        assert not loop.reject("nope")

    def test_stats(self):
        loop = HumanLoopManager(escalation_threshold=5)
        stats = loop.stats
        assert stats["threshold"] == 5
        assert stats["pending"] == 0

    def test_get_pending(self):
        loop = HumanLoopManager()
        assert loop.get_pending() == []


# ════════════════════════════════════════════════
# Global Memory Tests
# ════════════════════════════════════════════════

class TestCRDTEntry:
    def test_merge_lww(self):
        a = CRDTEntry(key="k", value="old", timestamp=100.0, node_id="n1")
        b = CRDTEntry(key="k", value="new", timestamp=200.0, node_id="n2")
        merged = a.merge_with(b)
        assert merged.value == "new"
        assert merged.node_id == "n2"


class TestGlobalMemory:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        gm = GlobalMemory()
        await gm.set("greeting", "hello", namespace="test")
        val = await gm.get("greeting", namespace="test")
        assert val == "hello"

    @pytest.mark.asyncio
    async def test_get_missing(self):
        gm = GlobalMemory()
        val = await gm.get("nope", namespace="test")
        assert val is None

    @pytest.mark.asyncio
    async def test_delete(self):
        gm = GlobalMemory()
        await gm.set("temp", "value", namespace="test")
        assert await gm.delete("temp", namespace="test")
        assert await gm.get("temp", namespace="test") is None

    @pytest.mark.asyncio
    async def test_delete_missing(self):
        gm = GlobalMemory()
        assert not await gm.delete("nope", namespace="test")

    @pytest.mark.asyncio
    async def test_list_namespace(self):
        gm = GlobalMemory()
        await gm.set("a", 1, namespace="ns")
        await gm.set("b", 2, namespace="ns")
        items = await gm.list_namespace("ns")
        assert len(items) == 2
        assert items["a"] == 1

    @pytest.mark.asyncio
    async def test_list_namespaces(self):
        gm = GlobalMemory()
        await gm.set("k1", "v1", namespace="ns1")
        await gm.set("k2", "v2", namespace="ns2")
        nss = await gm.list_namespaces()
        assert "ns1" in nss
        assert "ns2" in nss

    @pytest.mark.asyncio
    async def test_clear_namespace(self):
        gm = GlobalMemory()
        await gm.set("a", 1, namespace="tmp")
        await gm.set("b", 2, namespace="tmp")
        count = await gm.clear_namespace("tmp")
        assert count == 2

    @pytest.mark.asyncio
    async def test_lww_overwrite(self):
        gm = GlobalMemory()
        await gm.set("k", "first", namespace="t")
        # Simulate second write with later timestamp
        await gm.set("k", "second", namespace="t")
        val = await gm.get("k", namespace="t")
        assert val == "second"

    @pytest.mark.asyncio
    async def test_merge(self):
        gm = GlobalMemory()
        entries = [
            CRDTEntry(key="a", value=1, timestamp=100, node_id="n1", namespace="ns"),
            CRDTEntry(key="b", value=2, timestamp=200, node_id="n2", namespace="ns"),
        ]
        merged = await gm.merge(entries)
        assert merged == 2
        assert await gm.get("a", namespace="ns") == 1

    @pytest.mark.asyncio
    async def test_get_changes_since(self):
        gm = GlobalMemory()
        await gm.set("a", 1, namespace="ns", node_id="n1")
        await gm.set("b", 2, namespace="ns", node_id="n2")
        changes = await gm.get_changes_since("n1", since_timestamp=0)
        assert len(changes) >= 1

    @pytest.mark.asyncio
    async def test_sync_snapshot(self):
        gm = GlobalMemory()
        await gm.set("k", "v", namespace="ns")
        snap = await gm.sync_snapshot()
        assert "ns" in snap
        assert len(snap["ns"]) == 1
        assert snap["ns"][0]["value"] == "v"

    @pytest.mark.asyncio
    async def test_stats(self):
        gm = GlobalMemory()
        await gm.set("k", "v", namespace="ns")
        await gm.get("k", namespace="ns")
        stats = await gm.get_stats()
        assert stats["total_active"] >= 1
        assert stats["total_writes"] >= 1
        assert stats["total_reads"] >= 1
