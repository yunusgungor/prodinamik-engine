"""
Prodinamik Engine v0.5 — Phase 4 Integration Test

Observability — 6 test:
1. Debug CLI (timeline, event, why, cost, health, budget)
2. Profile Registry (register, resolve, list, dependency graph)
3. Health Dashboard (degradation + safety + event store + cost)
4. Debug CLI edge cases (missing slug, invalid event_id)
5. Profile Registry edge cases (not found, version mismatch)
6. Cross-phase full stack (all components integrated)
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.debug_cli import DebugCLI
from engine.registry import ProfileRegistry, ProfileMetadata
from engine.event_store import EventStore, CostAwareEvent
from engine.run_manager import RunManager
from engine.cost import CostTracker, EfficiencyTracker, RunEfficiency
from engine.budget import BudgetEnforcer
from engine.degradation import DegradationManager, DegradationLevel
from engine.safety import RuntimeSafetyMonitor, EventBus
from engine.state_machine import StateMachineParser
from engine.profile import ProductProfile

YAML = """
profile: software
name: dev-cycle
version: 1.0
states:
  spec: {type: initial, max_reentries: 1}
  prototyping: {type: intermediate, max_reentries: 5}
  iteration: {type: intermediate, max_reentries: 10}
  review: {type: intermediate, max_reentries: null}
  release: {type: terminal, max_reentries: 0}
  cancelled: {type: terminal, max_reentries: 0}
transitions:
  spec -> prototyping: {}
  prototyping -> iteration: {}
  iteration -> review: {condition: "iterations >= 4"}
  iteration -> cancelled: {condition: "max_iterations_exceeded"}
  review -> release: {condition: "human_approved"}
  review -> iteration: {condition: "changes_requested"}
  review -> cancelled: {condition: "project_abandoned"}
"""


def _setup_components(tmpdir):
    """Setup all engine components for testing"""
    slug = "flux-release"
    store = EventStore(base_path=tmpdir, slug=slug)

    for i, (etype, data, cost) in enumerate([
        ("state_transition", {"from": "spec", "to": "prototyping"}, 0.0),
        ("validation", {"validator": "BuildCheck", "passed": True}, 0.01),
        ("state_transition", {"from": "prototyping", "to": "iteration"}, 0.0),
        ("validation", {"validator": "TestCase", "passed": False}, 0.35),
        ("error", {"source": "test", "message": "Coverage: 65%"}, 0.0),
        ("validation", {"validator": "Coverage", "passed": True}, 0.28),
        ("state_transition", {"from": "iteration", "to": "review"}, 0.0),
    ]):
        store.append(CostAwareEvent(
            sequence=0, run_slug=slug,
            timestamp=f"2026-05-18T{8:02d}:{i*5:02d}:00",
            event_type=etype, data=data, cost_usd=cost,
        ))

    cost = CostTracker()
    cost.record_llm("gpt-4o", 1000, 300, "validation", "BuildCheck")
    cost.record_llm("deepseek-v4-flash", 500, 150, "validation", "TestCase")

    eff = EfficiencyTracker()
    eff.add_completed(RunEfficiency(
        slug=slug, profile="software", format="release",
        total_cost=0.5, estimated=2.0, actual=2.5, source="api"))

    deg = DegradationManager(base_path=tmpdir)
    bus = EventBus()
    safety = RuntimeSafetyMonitor(event_bus=bus)
    budget = BudgetEnforcer(cost_tracker=cost, degradation_manager=deg)
    budget.configure({"soft_limit_usd": 0.05, "hard_limit_usd": 0.10})

    class SWProfile(ProductProfile):
        name, version, state_machine_yaml = "software", "1.0", YAML

    profile = SWProfile()
    profile.initialize()
    mgr = RunManager(base_path=tmpdir)
    mgr.create_run("Flux Release", profile, slug=slug)

    cli = DebugCLI(run_manager=mgr, event_store=store, cost_tracker=cost,
                    efficiency_tracker=eff, degradation_manager=deg,
                    budget_enforcer=budget, runtime_safety=safety)

    return cli, store, cost, eff, deg, budget, safety, mgr, profile


# ────────────── Test 1: Debug CLI Commands ──────────────

def test_debug_cli():
    print("═══ Test 1: Debug CLI Commands ═══")
    tmpdir = tempfile.mkdtemp()
    cli, *_ = _setup_components(tmpdir)

    # timeline
    r = cli.handle("timeline", "flux-release")
    assert "Timeline" in r
    assert "#1" in r
    assert "#7" in r
    print(f"   ✅ timeline: {len(r)} chars, 7 events shown")

    # event
    r = cli.handle("event", "flux-release", "2")
    assert "Event #2" in r
    assert "BuildCheck" in r
    assert "$0.0100" in r
    print(f"   ✅ event #2: validator=BuildCheck, cost=$0.01")

    # state
    r = cli.handle("state", "flux-release")
    assert "Run State" in r
    assert "software" in r
    assert "release" in r  # slug part
    print(f"   ✅ state: profile=software")

    # why
    r = cli.handle("why", "flux-release", "5")
    assert "5-Why Analysis" in r
    assert "Coverage" in r
    print(f"   ✅ why #5: 5-Why analysis generated")

    # cost
    r = cli.handle("cost", "flux-release")
    assert "Cost Timeline" in r
    assert "$0." in r
    print(f"   ✅ cost timeline: ${sum(e.cost_usd for e in cli.event_store.get_all()):.2f}")

    # efficiency
    r = cli.handle("efficiency", "flux-release")
    assert "Efficiency" in r
    assert "2.50x" in r
    print(f"   ✅ efficiency: 2.50x actual")

    # health
    r = cli.handle("health")
    assert "Health" in r
    assert "Degradation" in r
    assert "Event Store" in r
    assert "Runtime Safety" in r
    assert "Budget Status" in r
    print(f"   ✅ health: all 5 sections present")

    # budget
    r = cli.handle("budget", "flux-release")
    assert "Budget Status" in r
    assert "total_cost" in r
    print(f"   ✅ budget: limits displayed")


# ────────────── Test 2: Profile Registry ──────────────

def test_registry():
    print("\n═══ Test 2: Profile Registry ═══")
    reg = ProfileRegistry()

    assert len(reg.sources) == 4
    assert reg.sources["builtin"].priority == 0
    assert reg.sources["project"].priority == 200
    print(f"   ✅ Sources: {len(reg.sources)} (builtin→remote→user→project)")

    # Register
    tmpdir = tempfile.mkdtemp()
    reg.sources["user"].path = os.path.join(tmpdir, "profiles")

    meta = ProfileMetadata(
        name="software-workflow", version="1.0.0",
        description="SW lifecycle", author="Yunus",
        maturity="beta", total_runs=15, success_rate=0.87,
    )
    success, msg = reg.register("software-workflow", "1.0.0", meta)
    assert success
    print(f"   ✅ Register: {msg}")

    # Resolve
    resolved = reg.resolve("software-workflow")
    assert resolved is not None
    assert resolved.version == "1.0.0"
    assert resolved.author == "Yunus"
    print(f"   ✅ Resolve: {resolved.name}@{resolved.version}")

    # List
    profiles = reg.list_profiles()
    assert len(profiles) >= 1
    print(f"   ✅ List: {len(profiles)} profile(s)")

    # Not found
    not_found = reg.resolve("nonexistent")
    assert not_found is None
    print(f"   ✅ Not found: returns None")


# ────────────── Test 3: Health Dashboard ──────────────

def test_health_dashboard():
    print("\n═══ Test 3: Health Dashboard ═══")
    tmpdir = tempfile.mkdtemp()
    cli, store, cost, eff, deg, budget, safety, *_ = _setup_components(tmpdir)

    # Manual degrade for testing
    deg.manual_degrade(DegradationLevel.DEGRADED, "test")

    r = cli.handle("health")
    assert "Degradation" in r
    assert "degraded" in r
    assert "Event Store" in r
    assert "Runtime Safety" in r
    assert "Budget Status" in r

    # Health should mention disabled features
    assert "t2_validators" in r
    assert "remote_adapters" in r

    print(f"   ✅ Health dashboard: {len(r.split(chr(10)))} lines, "
          f"all components reporting")


# ────────────── Test 4: Debug CLI Edge Cases ──────────────

def test_debug_edges():
    print("\n═══ Test 4: Debug CLI Edge Cases ═══")
    tmpdir = tempfile.mkdtemp()
    cli, *_ = _setup_components(tmpdir)

    # Missing slug
    r = cli.handle("timeline")
    assert "Slug required" in r
    print(f"   ✅ Missing slug: error message")

    # Invalid event ID
    r = cli.handle("event", "flux-release", "abc")
    assert "Invalid" in r
    print(f"   ✅ Invalid event_id: error message")

    # Non-existent event
    r = cli.handle("event", "flux-release", "999")
    assert "not found" in r
    print(f"   ✅ Non-existent event: error message")

    # Unknown command
    r = cli.handle("nonexistent")
    assert "Debug CLI Commands" in r
    print(f"   ✅ Unknown command: shows help")


# ────────────── Test 5: Registry Edge Cases ──────────────

def test_registry_edges():
    print("\n═══ Test 5: Profile Registry Edge Cases ═══")
    reg = ProfileRegistry()

    # Version-specific resolve
    # (no profiles registered yet, so test not-found paths)
    r = reg.resolve("fake-profile", "1.0.0")
    assert r is None
    print(f"   ✅ Version-specific not found: None")

    # Dependency graph with conflicts
    tmpdir = tempfile.mkdtemp()
    reg.sources["user"].path = os.path.join(tmpdir, "p")

    reg.register("app", "1.0", ProfileMetadata(
        name="app", version="1.0", dependencies=["lib-a", "lib-b"]))
    reg.register("lib-a", "1.0", ProfileMetadata(
        name="lib-a", version="1.0", dependencies=["base"]))
    reg.register("lib-b", "1.0", ProfileMetadata(
        name="lib-b", version="1.0", dependencies=["base"]))
    reg.register("base", "1.0", ProfileMetadata(
        name="base", version="1.0"))

    graph = reg.dependency_graph("app")
    assert graph["root"] == "app"
    assert len(graph["nodes"]) >= 1
    assert graph["conflicts"] == []  # All same dependency version
    print(f"   ✅ Dep graph: {len(graph['nodes'])} nodes, "
          f"{len(graph['edges'])} edges, {len(graph['conflicts'])} conflicts")


# ────────────── Test 6: Full Stack Integration

def test_full_stack():
    print("\n═══ Test 6: Cross-Phase Full Stack ═══")
    tmpdir = tempfile.mkdtemp()
    cli, store, cost, eff, deg, budget, safety, mgr, profile = \
        _setup_components(tmpdir)

    # 1. RunManager: create another run
    mgr.create_run("Test Project", profile, slug="test-project")
    r = mgr.get_run("test-project")
    assert r is not None
    assert r.meta.state == "spec"
    print(f"   ✅ Phase 1: RunManager create+read")

    # 2. EventStore: write + read
    store.append(CostAwareEvent(
        sequence=0, run_slug="test-project",
        timestamp="2026-05-18T09:00:00",
        event_type="state_transition",
        data={"from": "spec", "to": "prototyping"},
        cost_usd=0.0))
    e = store.get(8)  # 8th event
    assert e is not None
    print(f"   ✅ Phase 2: EventStore write+read ({store.event_count} events total)")

    # 3. Cost + Efficiency
    cost.record_compute("build", 120, cores=4)
    assert cost.total_usd > 0
    eff.estimate("test-project", "software", "release", 0.3)
    assert eff.display("test-project") is not None
    print(f"   ✅ Phase 3: CostTracker + Efficiency")

    # 4. Debug CLI on new run
    r = cli.handle("summary", "test-project")
    assert "Run Summary" in r
    assert "spec" in r
    print(f"   ✅ Phase 4: Debug CLI on new run")

    # 5. Degradation
    state = {"consecutive_llm_failures": 3}
    deg.evaluate(state)
    assert deg.current_level == DegradationLevel.DEGRADED
    print(f"   ✅ Cross-phase: Degradation → DEGRADED")

    # 6. Recovery + verify with Debug CLI
    deg.manual_recover()
    r = cli.handle("health")
    assert "full" in r.lower()
    print(f"   ✅ Cross-phase: Recovery → FULL + health verified")

    print(f"   ✅ Full stack: 6 phases verified")
    print(f"   ✅ All 5 components working together")


# ────────────── Main ──────────────

def main():
    print("=" * 60)
    print("  Prodinamik Engine v0.5 — Phase 4 Integration Test")
    print("  Observability")
    print("=" * 60)

    tests = [
        ("DebugCLI", test_debug_cli),
        ("ProfileRegistry", test_registry),
        ("HealthDashboard", test_health_dashboard),
        ("DebugEdgeCases", test_debug_edges),
        ("RegistryEdgeCases", test_registry_edges),
        ("FullStack", test_full_stack),
    ]

    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ PASS — {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL — {name}: {e}")
            failed += 1
            import traceback; traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  ✅ {passed} passed, ❌ {failed} failed")
    print(f"  Total: {passed}/{passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
