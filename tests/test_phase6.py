"""Prodinamik Engine v1.0 — Phase 2: Runtime Integration Tests

Tests for:
1. AsyncEngine start/stop
2. Component wiring (RunManager ↔ EventStore ↔ Cost ↔ Budget ↔ Degradation)
3. Lifecycle hooks (on_enter, on_exit, on_timeout)
4. State timeout watcher
5. Graceful shutdown
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engine.config import ProdinamikConfig
from engine.runtime import AsyncEngine, RuntimeConfig
from engine.hooks import HookRegistry
from engine.run_manager import RunStatus
from engine.degradation import DegradationLevel


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def tmp_config():
    """ProdinamikConfig pointing to a temp directory"""
    tmpdir = tempfile.mkdtemp()
    cfg = ProdinamikConfig.load()
    cfg.data_dir = os.path.join(tmpdir, ".hermes")
    cfg.log.level = "ERROR"  # Quiet tests
    return tmpdir, cfg


@pytest.fixture
def engine(tmp_config):
    """AsyncEngine instance (not started)"""
    tmpdir, cfg = tmp_config
    rt = RuntimeConfig(
        poll_interval=0.5,        # Fast timeout checks for tests
        health_check_interval=60,  # Don't trigger during tests
        enable_timeout_watcher=False,  # Disable by default
    )
    eng = AsyncEngine(cfg, rt)
    return eng


# ──────────────────────────────────────────────
# Test 1: Engine start/stop
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_engine_start_stop(engine):
    """Test basic engine lifecycle"""
    assert not engine._running

    await engine.start()
    assert engine._running
    assert len(engine._tasks) == 1  # Only health checker (timeout disabled)
    assert engine._tasks[0].get_name() == "health-checker"

    await engine.stop()
    assert not engine._running
    assert len(engine._tasks) == 0  # All cleaned up


# ──────────────────────────────────────────────
# Test 2: Component wiring
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_component_wiring(tmp_config):
    """Test that all components are wired and interact correctly"""
    tmpdir, cfg = tmp_config
    eng = AsyncEngine(cfg)
    await eng.start()

    # Create a run → should wire RunManager + EventStore + CostTracker
    run = eng.create_run("content", "Wiring Test")
    assert run is not None
    assert run.meta.slug is not None
    assert run.meta.profile == "content"
    assert run.meta.state == "captured"

    # Check EventStore was created
    store = eng._get_event_store(run.meta.slug)
    assert store is not None

    # Check run is tracked
    assert run.meta.slug in eng._state_entry_time

    # Transition → should record event
    eng._do_transition(run.meta.slug, "idea_review")
    events = store.get_all()
    assert len(events) >= 2  # created + transition

    # Cleanup
    await eng.stop()


# ──────────────────────────────────────────────
# Test 3: Lifecycle hooks
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lifecycle_hooks(engine):
    """Test on_enter / on_exit / on_timeout hooks"""
    await engine.start()

    # Track hook calls
    calls = {"on_enter": [], "on_exit": [], "on_timeout": []}

    def on_enter(run_meta, state):
        calls["on_enter"].append((run_meta.slug, state))

    def on_exit(run_meta, from_state, to_state):
        calls["on_exit"].append((run_meta.slug, from_state, to_state))

    def on_timeout(run_meta, state):
        calls["on_timeout"].append((run_meta.slug, state))

    # Register hooks for 'captured' state
    engine.hooks.register("captured", "on_enter", on_enter)
    engine.hooks.register("captured", "on_exit", on_exit)

    # Create run → on_enter should fire
    run = engine.create_run("content", "Hook Test", slug="hook-test")
    await asyncio.sleep(0.05)

    assert len(calls["on_enter"]) == 1
    assert calls["on_enter"][0] == ("hook-test", "captured")
    assert len(calls["on_exit"]) == 0  # Not yet exited

    # Transition → on_exit should fire, then on_enter for new state
    engine.hooks.register("idea_review", "on_enter", on_enter)
    await engine.transition_async("hook-test", "idea_review")
    await asyncio.sleep(0.05)

    assert len(calls["on_exit"]) == 1
    assert calls["on_exit"][0] == ("hook-test", "captured", "idea_review")
    assert len(calls["on_enter"]) == 2  # captured + idea_review

    # Register timeout hook
    engine.hooks.register("idea_review", "on_timeout", on_timeout)
    engine.hooks.trigger_sync("idea_review", "on_timeout", run.meta, "idea_review")
    assert len(calls["on_timeout"]) == 1

    # Verify stats
    stats = engine.hooks.stats
    assert stats["total_hooks"] == 4  # captured:2 (on_enter, on_exit) + idea_review:2 (on_enter, on_timeout)
    assert stats["states_with_hooks"] == 2

    await engine.stop()


# ──────────────────────────────────────────────
# Test 4: HookRegistry standalone
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hook_registry():
    """Test HookRegistry core functionality"""
    registry = HookRegistry()

    calls = []

    def sync_handler(*args):
        calls.append(("sync", args))

    async def async_handler(*args):
        calls.append(("async", args))

    # Register
    registry.register("state_a", "on_enter", sync_handler)
    registry.register("state_a", "on_enter", async_handler)
    registry.register("state_a", "on_exit", sync_handler)

    assert registry.stats["total_hooks"] == 3
    assert registry.stats["states_with_hooks"] == 1

    # Trigger sync (only sync handlers)
    registry.trigger_sync("state_a", "on_enter", "arg1")
    assert len(calls) == 1
    assert calls[0][0] == "sync"

    # Trigger async (both sync and async)
    calls.clear()
    await registry.trigger("state_a", "on_enter", "arg1")
    assert len(calls) == 2  # sync + async

    # Unregister
    registry.unregister("state_a", "on_enter", sync_handler)
    calls.clear()
    await registry.trigger("state_a", "on_enter", "arg1")
    assert len(calls) == 1  # only async remains

    # Clear
    registry.clear()
    assert registry.stats["total_hooks"] == 0

    # Invalid hook type
    with pytest.raises(ValueError):
        registry.register("x", "invalid_hook", sync_handler)


# ──────────────────────────────────────────────
# Test 5: State timeout watcher
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_watcher(tmp_config):
    """Test that timeout watcher detects expired states"""
    tmpdir, cfg = tmp_config
    rt = RuntimeConfig(
        poll_interval=0.2,       # Fast poll for test
        health_check_interval=60,
        enable_timeout_watcher=True,
    )
    eng = AsyncEngine(cfg, rt)
    await eng.start()

    # Track timeout calls
    timeout_log = []

    def on_timeout(run_meta, state):
        timeout_log.append((run_meta.slug, state))

    # Create a run in software profile (spec has timeout: 3600s)
    run = eng.create_run("software", "Timeout Test", slug="timeout-test")

    # Force entry time far in the past to trigger timeout
    eng._track_entry("timeout-test", "spec",
                      time=__import__('datetime').datetime(2020, 1, 1))

    eng.hooks.register("spec", "on_timeout", on_timeout)

    # Wait for watcher to detect the timeout (poll_interval=0.2)
    await asyncio.sleep(0.8)

    assert len(timeout_log) >= 1, "Timeout should have been detected"
    assert timeout_log[0] == ("timeout-test", "spec")

    await eng.stop()


# ──────────────────────────────────────────────
# Test 6: Graceful shutdown
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_graceful_shutdown(tmp_config):
    """Test that shutdown cleans up tasks and persists state"""
    tmpdir, cfg = tmp_config
    eng = AsyncEngine(cfg)
    await eng.start()

    # Create some runs and transitions
    run = eng.create_run("content", "Shutdown Test", slug="shutdown-test")
    eng._do_transition("shutdown-test", "idea_review")

    # Trigger budget tracking
    eng.cost_tracker.record_llm("deepseek-v4-flash", 100, 50,
                                 "validation", "TestValidator")

    # Shutdown
    await eng.stop()

    # After shutdown: no running tasks
    assert not eng._running
    assert len(eng._tasks) == 0

    # State should be persisted via WAL compaction
    wal_dir = Path(tmpdir) / ".hermes" / "wal"
    if wal_dir.exists():
        wal_files = list(wal_dir.glob("wal_*.log"))
        # After compaction, WAL entries before snapshot should be cleaned
        # but at minimum the state snapshot exists
        state_file = Path(tmpdir) / ".hermes" / "state" / "runs_state.json"
        assert state_file.exists(), "State snapshot should survive shutdown"


# ──────────────────────────────────────────────
# Test 7: Engine health snapshot
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_snapshot(engine):
    """Test engine health_snapshot property"""
    await engine.start()

    health = engine.health_snapshot
    assert "running" in health
    assert health["running"] is True
    assert "profiles" in health
    assert "content" in health["profiles"]
    assert health["degradation"] == "full"
    assert health["health_score"] >= 0.0
    assert health["active_runs"] == 0

    # Create a run
    engine.create_run("content", "Health Check")
    health = engine.health_snapshot
    assert health["active_runs"] == 1

    await engine.stop()


# ──────────────────────────────────────────────
# Test 8: Async run creation with hooks
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_run_creation(engine):
    """Test create_run_async with async hooks"""
    await engine.start()

    async_calls = []

    async def async_enter(run_meta, state):
        async_calls.append(("enter", run_meta.slug, state))

    engine.hooks.register("captured", "on_enter", async_enter)

    run = await engine.create_run_async("content", "Async Test",
                                         slug="async-test")
    await asyncio.sleep(0.05)

    assert run.meta.slug == "async-test"
    assert len(async_calls) >= 1
    assert async_calls[0] == ("enter", "async-test", "captured")

    await engine.stop()
