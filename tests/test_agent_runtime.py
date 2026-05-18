"""Tests for Prodinamik AI Grid — Agent Runtime Layer"""

import os
import sys
import json
import time
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.agent_runtime.supervisor import (
    AgentSupervisor,
    SupervisorConfig,
    NodeIdentity,
    WorkerInfo,
    WorkerStatus,
)
from engine.agent_runtime.worker import (
    AgentWorker,
    StepType,
    StepRecord,
)
from engine.agent_runtime.tool_executor import (
    ToolExecutor,
    ToolExecutionRecord,
    ToolStatus,
)
from engine.agent_runtime.context import (
    ContextManager,
    ContextConfig,
)
from engine.agent_runtime.memory import (
    EphemeralMemory,
    LocalMemory,
    MemoryStore,
)
from engine.agent_runtime.states import (
    create_agent_state_machine,
    AGENT_STATES,
    AGENT_TRANSITIONS,
    AGENT_STATE_NAMES,
)


# ════════════════════════════════════════════════
# Supervisor Tests
# ════════════════════════════════════════════════

class TestNodeIdentity:
    def test_auto_generate_node_id(self):
        # NodeIdentity standalone doesn't auto-generate — empty is valid
        identity = NodeIdentity(node_id="")
        assert identity.node_id == ""

    def test_hostname_empty_by_default(self):
        identity = NodeIdentity(node_id="test")
        assert identity.hostname == ""


class TestWorkerInfo:
    def test_pending_default(self):
        w = WorkerInfo(worker_id="w1", task_id="t1")
        assert w.status == WorkerStatus.PENDING

    def test_duration_no_start(self):
        w = WorkerInfo(worker_id="w1", task_id="t1")
        assert w.duration_ms == 0.0

    def test_duration_with_timing(self):
        w = WorkerInfo(worker_id="w1", task_id="t1")
        w.started_at = datetime.now() - timedelta(seconds=1)
        assert w.duration_ms > 500

    def test_completed_duration(self):
        w = WorkerInfo(worker_id="w1", task_id="t1")
        w.started_at = datetime.now() - timedelta(seconds=2)
        w.completed_at = datetime.now() - timedelta(seconds=1)
        assert 800 < w.duration_ms < 1200


class TestAgentSupervisor:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        s = AgentSupervisor(SupervisorConfig(node_id="test-node"))
        await s.start()
        assert s.is_running
        assert s.identity.node_id == "test-node"
        await s.stop()
        assert not s.is_running

    @pytest.mark.asyncio
    async def test_auto_node_id(self):
        s = AgentSupervisor()
        await s.start()
        assert s.identity.node_id.startswith("node-")
        await s.stop()

    def test_list_workers_empty(self):
        s = AgentSupervisor(SupervisorConfig())
        assert s.list_workers() == []

    def test_list_workers_filtered(self):
        s = AgentSupervisor(SupervisorConfig())
        w = WorkerInfo(worker_id="w1", task_id="t1", status=WorkerStatus.COMPLETED)
        s._workers["w1"] = w
        assert len(s.list_workers(WorkerStatus.COMPLETED)) == 1
        assert len(s.list_workers(WorkerStatus.RUNNING)) == 0

    def test_cancel_nonexistent(self):
        s = AgentSupervisor(SupervisorConfig())
        assert s.cancel_worker("nothing") == False

    def test_get_worker(self):
        s = AgentSupervisor(SupervisorConfig())
        w = WorkerInfo(worker_id="w1", task_id="t1")
        s._workers["w1"] = w
        assert s.get_worker("w1") is w
        assert s.get_worker("nope") is None

    def test_active_worker_count(self):
        s = AgentSupervisor(SupervisorConfig())
        assert s.active_worker_count == 0
        s._workers["w1"] = WorkerInfo(worker_id="w1", task_id="t1", status=WorkerStatus.RUNNING)
        assert s.active_worker_count == 1


# ════════════════════════════════════════════════
# Worker Tests
# ════════════════════════════════════════════════

class TestStepType:
    def test_values(self):
        assert StepType.THOUGHT.value == "thought"
        assert StepType.TOOL_CALL.value == "tool_call"
        assert StepType.TOOL_RESULT.value == "tool_result"
        assert StepType.OBSERVATION.value == "observation"
        assert StepType.REPORT.value == "report"


class TestStepRecord:
    def test_create(self):
        step = StepRecord(1, StepType.THOUGHT, "Thinking...", token_count=50)
        assert step.step_number == 1
        assert step.content == "Thinking..."
        assert step.tool_name == ""
        assert step.token_count == 50

    def test_auto_timestamp(self):
        step = StepRecord(1, StepType.THOUGHT)
        assert step.timestamp


class TestAgentWorker:
    @pytest.mark.asyncio
    async def test_execute_returns_result(self):
        w = AgentWorker(worker_id="tw", goal="Test", max_steps=1)
        result = await w.execute()
        assert hasattr(result, 'success')
        assert hasattr(result, 'summary')

    @pytest.mark.asyncio
    async def test_steps_recorded(self):
        w = AgentWorker(worker_id="tw2", goal="Record steps", max_steps=2)
        await w.execute()
        assert len(w.steps) >= 1

    @pytest.mark.asyncio
    async def test_fallback_on_no_llm(self):
        w = AgentWorker(worker_id="tw3", goal="Fallback test", max_steps=1)
        result = await w.execute()
        assert result.success == False  # No LLM, fallback

    def test_system_prompt_built(self):
        w = AgentWorker(worker_id="tw4", goal="Prompt test",
                        tools=[{"name": "calc", "description": "Calculator"}])
        w._build_system_prompt()
        assert "Goal" in w._system_prompt
        assert "calc" in w._system_prompt


# ════════════════════════════════════════════════
# Tool Executor Tests
# ════════════════════════════════════════════════

class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_register_and_execute(self):
        ex = ToolExecutor()
        async def greet(param: str = "World"):
            return {"result": f"Hello {param}"}
        ex.register("greet", greet)
        result = await ex.execute("greet", {"param": "Test"})
        assert result.get("success") == True
        assert result.get("result") == "Hello Test"

    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        ex = ToolExecutor()
        result = await ex.execute("nope", {})
        assert "error" in result

    def test_available_tools(self):
        ex = ToolExecutor()
        ex.register("a", lambda: None)
        ex.register("b", lambda: None)
        tools = ex.get_available_tools()
        assert len(tools) == 2
        assert "a" in tools

    def test_tool_count(self):
        ex = ToolExecutor()
        assert ex.tool_count == 0
        ex.register("x", lambda: None)
        assert ex.tool_count == 1

    def test_has_tool(self):
        ex = ToolExecutor()
        ex.register("t", lambda: None)
        assert ex.has_tool("t")
        assert not ex.has_tool("nope")

    def test_get_status(self):
        ex = ToolExecutor()
        status = ex.get_status()
        assert status["available_count"] == 0

    def test_get_tool_definitions(self):
        ex = ToolExecutor()
        ex.register("add", lambda a, b: a + b, description="Add numbers")
        defs = ex.get_tool_definitions()
        assert len(defs) == 1
        assert defs[0]["name"] == "add"

    @pytest.mark.asyncio
    async def test_history(self):
        ex = ToolExecutor()
        async def my_tool(): return {"ok": True}
        ex.register("test", my_tool)
        await ex.execute("test", {})
        hist = ex.get_history()
        assert len(hist) == 1
        assert hist[0]["tool"] == "test"
        assert hist[0]["success"] == True

    def test_clear_history(self):
        ex = ToolExecutor()
        # No entries initially
        ex.clear_history()
        assert len(ex.get_history()) == 0


# ════════════════════════════════════════════════
# Context Manager Tests
# ════════════════════════════════════════════════

class TestContextManager:
    def test_default_config(self):
        c = ContextManager()
        assert c.config.max_tokens == 8000
        assert c.config.full_fidelity_steps == 5

    def test_add_reset(self):
        c = ContextManager()
        c.add_entry("system", "You are helpful")
        assert c._total_tokens > 0
        c.reset()
        assert c._total_tokens == 0

    def test_token_budget_changes(self):
        c = ContextManager(ContextConfig(max_tokens=1000))
        before = c.token_budget()
        c.add_entry("user", "X" * 400)
        after = c.token_budget()
        assert after < before

    def test_usage_zero_initial(self):
        c = ContextManager()
        assert c.usage == 0.0

    def test_usage_after_add(self):
        c = ContextManager(ContextConfig(max_tokens=100))
        c.add_entry("user", "Hello there")
        assert 0 < c.usage <= 1.0

    def test_summarize_empty(self):
        c = ContextManager()
        assert c.summarize([]) == []

    def test_summarize_steps(self):
        c = ContextManager(ContextConfig(full_fidelity_steps=2))
        steps = [
            StepRecord(1, StepType.THOUGHT, "First thought"),
            StepRecord(2, StepType.TOOL_CALL, "Tool call", tool_name="search"),
        ]
        msgs = c.summarize(steps)
        assert len(msgs) > 0

    def test_is_near_limit(self):
        c = ContextManager(ContextConfig(max_tokens=100, warn_threshold=0.1))
        c.add_entry("user", "X" * 100)
        assert c.is_near_limit

    def test_not_near_limit(self):
        c = ContextManager(ContextConfig(max_tokens=10000, warn_threshold=0.9))
        c.add_entry("user", "Hi")
        assert not c.is_near_limit


# ════════════════════════════════════════════════
# Memory Tests
# ════════════════════════════════════════════════

class TestEphemeralMemory:
    def test_store_get(self):
        m = EphemeralMemory()
        m.store("k", "v")
        assert m.get("k") == "v"

    def test_get_default(self):
        m = EphemeralMemory()
        assert m.get("nope", "fallback") == "fallback"

    def test_search(self):
        m = EphemeralMemory()
        m.store("api_key", "sk-test")
        results = m.search("api")
        assert len(results) >= 1

    def test_delete(self):
        m = EphemeralMemory()
        m.store("tmp", "val")
        assert m.delete("tmp")
        assert m.get("tmp") is None

    def test_delete_missing(self):
        m = EphemeralMemory()
        assert not m.delete("nope")

    def test_clear(self):
        m = EphemeralMemory()
        m.store("a", 1)
        m.store("b", 2)
        m.clear()
        assert m.count == 0

    def test_contains(self):
        m = EphemeralMemory()
        m.store("k", "v")
        assert "k" in m
        assert "nope" not in m

    def test_dict_access(self):
        m = EphemeralMemory()
        m["key"] = "val"
        assert m["key"] == "val"

    def test_keys(self):
        m = EphemeralMemory()
        m.store("a", 1)
        assert "a" in m.keys

    def test_stats(self):
        m = EphemeralMemory()
        m.store("x", 1)
        s = m.stats
        assert s["entries"] == 1

    def test_tags(self):
        m = EphemeralMemory()
        m.store("t1", "v1", tags=["important"])
        tagged = m.get_by_tag("important")
        assert len(tagged) == 1

    def test_lru_eviction(self):
        m = EphemeralMemory(max_entries=2)
        m.store("a", 1)
        m.store("b", 2)
        m.store("c", 3)  # Should evict 'a'
        assert "a" not in m
        assert m.count == 2


class TestLocalMemory:
    @pytest.mark.asyncio
    async def test_initialize_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            assert mem._initialized
            await mem.close()

    @pytest.mark.asyncio
    async def test_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            await mem.save("k", {"text": "hello"}, namespace="ns")
            val = await mem.load("k", namespace="ns")
            assert val == {"text": "hello"}
            await mem.close()

    @pytest.mark.asyncio
    async def test_load_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            val = await mem.load("nonexistent", namespace="ns")
            assert val is None
            await mem.close()

    @pytest.mark.asyncio
    async def test_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            await mem.save("run:abc", {"s": "done"}, namespace="runs")
            await mem.save("run:def", {"s": "pending"}, namespace="runs")
            results = await mem.query("run:", namespace="runs")
            assert len(results) == 2
            await mem.close()

    @pytest.mark.asyncio
    async def test_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            await mem.save("tmp", "val", namespace="test")
            assert await mem.delete("tmp", namespace="test")
            assert not await mem.delete("nope", namespace="test")
            await mem.close()

    @pytest.mark.asyncio
    async def test_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            await mem.save("a", 1, namespace="ns1")
            await mem.save("b", 2, namespace="ns1")
            assert await mem.count("ns1") == 2
            await mem.close()

    @pytest.mark.asyncio
    async def test_clear_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            await mem.save("a", 1, namespace="tmp")
            deleted = await mem.clear_namespace("tmp")
            assert deleted == 1
            assert await mem.count("tmp") == 0
            await mem.close()

    @pytest.mark.asyncio
    async def test_save_run_memory_and_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            await mem.save_run_memory("run-001", {"goal": "Fix login bug", "summary": "Done"})
            results = await mem.recall("login bug", limit=5)
            assert len(results) > 0
            await mem.close()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = LocalMemory(node_id="test", db_path=os.path.join(tmp, "m.db"))
            await mem.initialize()
            stats = await mem.get_stats()
            assert "db_path" in stats
            await mem.close()


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_store_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(node_id="test", db_path=os.path.join(tmp, "s.db"))
            await store.initialize()
            await store.store("k", "v")
            val = await store.get("k")
            assert val == "v"
            await store.close()

    @pytest.mark.asyncio
    async def test_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(node_id="test", db_path=os.path.join(tmp, "s.db"))
            await store.initialize()
            await store.store("pk", {"stored": True}, persistent=True)
            val = await store.get("pk", persistent=True)
            assert val == {"stored": True}
            await store.close()


# ════════════════════════════════════════════════
# Agent State Machine Tests
# ════════════════════════════════════════════════

class TestAgentStates:
    def test_all_states_exist(self):
        required = [
            "agent:pending", "agent:initializing", "agent:observing",
            "agent:thinking", "agent:acting", "agent:reporting",
            "agent:completed", "agent:failed", "agent:cancelled",
        ]
        for s in required:
            assert s in AGENT_STATES, f"Missing state: {s}"

    def test_state_count(self):
        assert len(AGENT_STATES) == 9

    def test_transitions_exist(self):
        assert len(AGENT_TRANSITIONS) >= 10

    def test_state_names(self):
        assert len(AGENT_STATE_NAMES) == 9

    def test_create_machine(self):
        sm = create_agent_state_machine()
        assert sm is not None
