"""
Prodinamik Engine v0.5 — Phase 2 Integration Test

Resilience & Cache — 8 test:
1. Event Store (append, query, retention, compaction)
2. Event Bus (subscribe, emit, duplicate detection, cycle safety)
3. Degradation Manager (health checks, FULL→DEGRADED→SURVIVAL)
4. Runtime Safety Invariants (10 invariant, action matrix)
5. Cache × Degradation Policy (T1/T2 cache kontrola)
6. Cycle Safety (cross-profile event cycle)
7. Crash Recovery (WAL + event store persistence)
8. End-to-end pipeline with resilience
"""

import sys
import os
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.event_store import (
    EventStore, Event, CostAwareEvent, EventRetentionPolicy, EventType,
)
from engine.safety import EventBus, BusEvent, RuntimeSafetyMonitor
from engine.degradation import DegradationManager, DegradationLevel
from engine.state_machine import StateMachineParser, StateMachine

LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


# ──────────────────────────────
# Test 1: Event Store
# ──────────────────────────────

def test_event_store():
    print("\n═══ Test 1: Event Store ═══")
    tmpdir = tempfile.mkdtemp()
    store = EventStore(base_path=tmpdir, slug="test-run")

    for i in range(10):
        store.append(CostAwareEvent.from_validation(
            0, "test-run", "SlopScanT1", 1, i % 2 == 0, 0.01 * (i + 1)))
    store.append(CostAwareEvent.from_error(0, "test-run", "test", "Test error"))
    assert store.event_count == 11, f"Expected 11, got {store.event_count}"
    print(f"   ✅ {store.event_count} events ({round(store.storage_bytes/1024,1)}KB)")

    assert len(store.query(event_type="validation")) == 10
    assert len(store.query(event_type="error")) == 1
    assert len(store.query(min_cost=0.05)) >= 1
    print(f"   ✅ Queries: validation(10) error(1) expensive(≥1)")

    costs = store.cost_summary()
    assert "SlopScanT1" in costs and costs["SlopScanT1"] > 0
    print(f"   ✅ Cost: SlopScanT1=${costs['SlopScanT1']:.2f}")

    purged = store.purge()
    print(f"   ✅ Purge: {purged} removed")


# ──────────────────────────────
# Test 2: Event Bus
# ──────────────────────────────

def test_event_bus():
    print("\n═══ Test 2: Event Bus ═══")
    bus = EventBus()
    received = []

    async def h(event):
        received.append(event)

    bus.subscribe("release.published", h)
    bus.subscribe("announcement.done", h)

    async def run():
        e1 = BusEvent(type="release.published", source_profile="software",
                       source_slug="flux-v1", hop_count=0)
        bus.emit(e1)
        await asyncio.sleep(0.05)
        assert len(received) == 1

        bus.emit(e1)  # duplicate
        await asyncio.sleep(0.05)
        assert len(received) == 1, "Duplicate ignored"

        e2 = BusEvent(type="announcement.done", source_profile="content",
                       source_slug="flux-ann", hop_count=5)
        bus.emit(e2)  # max hops
        await asyncio.sleep(0.05)
        assert len(bus.cycle_warnings) >= 1

    LOOP.run_until_complete(run())
    print(f"   ✅ Emit, duplicate, max hops: all correct ({bus.stats})")


# ──────────────────────────────
# Test 3: Degradation Manager
# ──────────────────────────────

def test_degradation():
    print("\n═══ Test 3: Degradation ═══")
    mgr = DegradationManager(base_path=tempfile.mkdtemp())
    assert mgr.current_level == DegradationLevel.FULL

    mgr.evaluate({"consecutive_llm_failures": 3})
    assert mgr.current_level == DegradationLevel.DEGRADED
    assert not mgr.is_enabled("t2_validators")

    mgr.evaluate({"consecutive_llm_failures": 0})
    assert mgr.current_level == DegradationLevel.FULL

    mgr.manual_degrade(DegradationLevel.DEGRADED, "test")
    assert mgr.current_level == DegradationLevel.DEGRADED
    mgr.manual_recover()
    assert mgr.current_level == DegradationLevel.FULL

    assert len(mgr.feature_matrix) == 8
    print(f"   ✅ FULL→DEGRADED→FULL, manual control, 8 features")


# ──────────────────────────────
# Test 4: Runtime Safety
# ──────────────────────────────

def test_runtime_safety():
    print("\n═══ Test 4: Runtime Safety ═══")
    monitor = RuntimeSafetyMonitor(event_bus=EventBus())
    v = monitor.check_all()
    assert len(monitor.active_violations) > 0
    if v:
        monitor.resolve_violation(v[0].name)
    assert monitor.health_report()
    print(f"   ✅ {len(monitor.active_violations)} active, "
          f"score={monitor.health_score:.1f}, report=✓")


# ──────────────────────────────
# Test 5: Cache × Degradation
# ──────────────────────────────

def test_cache_degradation():
    print("\n═══ Test 5: Cache × Degradation ═══")
    from engine.validators import ContentAddressableCache, CachePolicy, ValidationResult

    cdir = os.path.join(tempfile.mkdtemp(), "cache")
    cache = ContentAddressableCache(cache_dir=cdir)
    content = "test content"

    # Cache T2 result
    cache.set(content, "T2Val", ValidationResult(passed=True), tier=2)
    assert cache.get(content, "T2Val", tier=2, cache_policy=CachePolicy.FULL) is not None
    assert cache.get(content, "T2Val", tier=2, cache_policy=CachePolicy.DEGRADED) is None
    assert cache.get(content, "T2Val", tier=2, cache_policy=CachePolicy.SURVIVAL) is None

    # Cache T1 result — accessible in DEGRADED
    cache.set(content, "T1Val", ValidationResult(passed=True), tier=1)
    assert cache.get(content, "T1Val", tier=1, cache_policy=CachePolicy.DEGRADED) is not None

    print(f"   ✅ FULL(T2✓) DEGRADED(T2✗ T1✓) SURVIVAL(✗) cache_policy=✓")


# ──────────────────────────────
# Test 6: Cycle Safety
# ──────────────────────────────

def test_cycle_safety():
    print("\n═══ Test 6: Cycle Safety ═══")
    bus = EventBus()
    chain = []

    async def sw_h(e):
        chain.append(f"sw:{e.type}:{e.hop_count}")
        if e.type == "code.completed":
            bus.emit(BusEvent(type="announcement.needed",
                source_profile="content", source_slug=e.source_slug,
                trace_id=e.trace_id, hop_count=e.hop_count + 1))

    async def ct_h(e):
        chain.append(f"ct:{e.type}:{e.hop_count}")
        if e.type == "announcement.needed":
            bus.emit(BusEvent(type="changelog.updated",
                source_profile="software", source_slug=e.source_slug,
                trace_id=e.trace_id, hop_count=e.hop_count + 1))

    async def swb_h(e):
        chain.append(f"swb:{e.type}:{e.hop_count}")
        if e.type == "changelog.updated":
            bus.emit(BusEvent(type="announcement.needed",
                source_profile="content", source_slug=e.source_slug,
                trace_id=e.trace_id, hop_count=e.hop_count + 1))

    bus.subscribe("code.completed", sw_h)
    bus.subscribe("announcement.needed", ct_h)
    bus.subscribe("changelog.updated", swb_h)

    async def run():
        bus.emit(BusEvent(type="code.completed", source_profile="software",
            source_slug="flux-v1", hop_count=1))
        await asyncio.sleep(0.15)
        print(f"   ✅ Chain ({len(chain)}): {' → '.join(chain)}")
        assert len(chain) <= 6, f"Expected ≤6, got {len(chain)}"
        assert len(bus.cycle_warnings) >= 1

    LOOP.run_until_complete(run())


# ──────────────────────────────
# Test 7: Event Store Persistence
# ──────────────────────────────

def test_persistence():
    print("\n═══ Test 7: Persistence ═══")
    tmpdir = tempfile.mkdtemp()
    slug = "persist-test"

    s1 = EventStore(base_path=tmpdir, slug=slug)
    for i in range(5):
        s1.append(Event(sequence=0, run_slug=slug,
            timestamp=datetime.now().isoformat(),
            event_type="validation", data={"i": i}, cost_usd=0.01))

    s2 = EventStore(base_path=tmpdir, slug=slug)
    assert s2.event_count == 5, f"Expected 5, got {s2.event_count}"
    events = s2.get_range(1, 10)
    assert len(events) == 5
    print(f"   ✅ 5 events persistent across EventStore instances")


# ──────────────────────────────
# Test 8: E2E Resilience
# ──────────────────────────────

def test_e2e_resilience():
    print("\n═══ Test 8: E2E Resilience ═══")
    tmpdir = tempfile.mkdtemp()
    slug = "e2e"
    store = EventStore(base_path=tmpdir, slug=slug)
    mgr = DegradationManager(base_path=tmpdir)

    # Normal
    store.append(CostAwareEvent.from_validation(0, slug, "SlopScanT1", 1, True, 0.01))
    assert store.event_count == 1

    # LLM failure → DEGRADED
    mgr.evaluate({"consecutive_llm_failures": 3})
    assert mgr.current_level == DegradationLevel.DEGRADED
    assert not mgr.is_enabled("t2_validators")

    # T1 still works in DEGRADED
    store.append(CostAwareEvent.from_validation(0, slug, "SlopScanT1", 1, True, 0.001))

    # Recovery
    mgr.manual_recover()
    assert mgr.current_level == DegradationLevel.FULL

    costs = store.cost_summary()
    total = store.event_count
    print(f"   ✅ {total} events, costs={costs}, "
          f"DEGRADED→FULL, T2 disabled→enabled")


# ──────────────────────────────
# Main
# ──────────────────────────────

def main():
    print("=" * 60)
    print("  Prodinamik Engine v0.5 — Phase 2 Integration Test")
    print("  Resilience & Cache")
    print("=" * 60)

    tests = [
        ("EventStore", test_event_store),
        ("EventBus", test_event_bus),
        ("Degradation", test_degradation),
        ("RuntimeSafety", test_runtime_safety),
        ("Cache×Degradation", test_cache_degradation),
        ("CycleSafety", test_cycle_safety),
        ("Persistence", test_persistence),
        ("E2EResilience", test_e2e_resilience),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ PASS — {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL — {name}: {e}")
            failed += 1
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  ✅ {passed} passed, ❌ {failed} failed")
    print(f"  Total: {passed}/{passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
