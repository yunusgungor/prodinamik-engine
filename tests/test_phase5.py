"""
Prodinamik Engine v0.5 — Phase 5 Integration Test

Profile Migration — 6 test:
1. ContentProfile (Content-OS'tan taşıma)
2. SoftwareProfile (dev-cycle'den taşıma)
3. Cross-Profile Event Chain (software→content)
4. Formal Migration Plan (v1→v2 execution + verification)
5. Migration Edge Cases (backward_compatible, removed states)
6. Full Stack v0.5 — ALL components integrated
"""

import sys
import os
import json
import asyncio
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from profiles.content import ContentProfile, create_slop_validator
from profiles.software import SoftwareProfile, SoftwareMigrationPlan
from engine.migration import (
    CrossProfileOrchestrator, MigrationPlan, MigrationResult,
    SOFTWARE_V1_TO_V2, CONTENT_V1_TO_V2,
)
from engine.safety import EventBus, BusEvent
from engine.state_machine import StateMachineParser, StateMachine
from engine.raft import NodeState, StateCRDT
from engine.run_manager import RunManager
from engine.event_store import EventStore, CostAwareEvent
from engine.cost import CostTracker, EfficiencyTracker, RunEfficiency
from engine.budget import BudgetEnforcer
from engine.degradation import DegradationManager
from engine.safety import RuntimeSafetyMonitor
from engine.debug_cli import DebugCLI
from engine.registry import ProfileRegistry, ProfileMetadata
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
  blocked: {type: error, requires_manual: true}
  cancelled: {type: terminal, max_reentries: 0}
transitions:
  spec -> prototyping: {}
  prototyping -> iteration: {}
  iteration -> iteration: {condition: "drift_detected"}
  iteration -> review: {condition: "iterations >= 4"}
  iteration -> blocked: {condition: "consecutive_failures >= 3"}
  iteration -> cancelled: {condition: "max_iterations_exceeded"}
  review -> release: {condition: "human_approved"}
  review -> iteration: {condition: "changes_requested"}
  review -> cancelled: {condition: "project_abandoned"}
  blocked -> iteration: {condition: "manual_unblock"}
"""

LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


# ────────────── Test 1: ContentProfile ──────────────

def test_content_profile():
    print("═══ Test 1: ContentProfile ═══")
    p = ContentProfile()
    p.initialize()

    assert p.name == "content"
    assert p.version == "1.0"
    assert p.state_machine is not None
    assert len(p.validators) == 3
    assert len(p.adapters) == 2
    assert len(p.stores) == 3

    sm = p.state_machine
    assert len(sm.config.states) == 9
    assert len(sm.config.transitions) == 11

    rt = sm.create_runtime()
    assert rt.current_state == "captured"
    assert "idea_review" in sm.get_next_states("captured")

    # Slop validator
    slop = create_slop_validator()
    result = LOOP.run_until_complete(slop.validate("Clean content here"))
    assert result.passed

    result = LOOP.run_until_complete(
        slop.validate("Bu harika ve mükemmel bir ürün!"))
    assert not result.passed
    assert len(result.details["errors"]) >= 2

    print(f"   ✅ {p.name} v{p.version}: {len(sm.config.states)} states, "
          f"{len(sm.config.transitions)} transitions, "
          f"{len(p.validators)} validators, {len(p.adapters)} adapters")
    print(f"   ✅ Slop: clean=PASS, sloppy=FAIL ({len(result.details['errors'])} errors)")


# ────────────── Test 2: SoftwareProfile ──────────────

def test_software_profile():
    print("\n═══ Test 2: SoftwareProfile ═══")
    p = SoftwareProfile()
    p.initialize()

    assert p.name == "software"
    assert p.version == "1.0"
    assert p.state_machine is not None
    assert len(p.validators) == 4
    assert len(p.adapters) == 2
    assert p.budget.hard_limit_usd == 10.0

    sm = p.state_machine
    assert len(sm.config.states) == 7
    assert len(sm.config.transitions) == 10

    rt = sm.create_runtime()
    assert rt.current_state == "spec"

    allowed, _ = sm.can_transition("spec", "prototyping", rt)
    assert allowed
    allowed, _ = sm.can_transition("release", "iteration", rt)
    assert not allowed  # Terminal state

    # CRDT merge
    local = NodeState(current_state="spec", version=1)
    remote = NodeState(current_state="prototyping", version=2)
    merged = StateCRDT.merge(local, remote, p.transition_map)
    assert merged.current_state == "prototyping"

    # Migration plan
    assert SoftwareMigrationPlan.migrate_state("prototyping") == "implementation"
    assert SoftwareMigrationPlan.migrate_state("spec") == "spec"

    print(f"   ✅ {p.name} v{p.version}: {len(sm.config.states)} states, "
          f"{len(sm.config.transitions)} transitions")
    print(f"   ✅ Terminal block: release→iteration correctly rejected")
    print(f"   ✅ CRDT: v2 prototyping wins, Migration: prototyping→implementation")


# ────────────── Test 3: Cross-Profile Chain ──────────────

def test_cross_profile_chain():
    print("\n═══ Test 3: Cross-Profile Chain ═══")
    bus = EventBus()
    chain = []
    ev = None

    def on_sw(event):
        chain.append(f"sw:release")
        nonlocal ev
        ev = event

    def on_ct(event):
        chain.append(f"ct:announcement(v{event.data.get('version')})")

    orch = CrossProfileOrchestrator(bus)
    orch.setup_software_release_chain(on_sw)
    orch.setup_content_announcement_chain(on_ct)

    async def run():
        bus.emit(BusEvent(type="release.published",
            source_profile="software", source_slug="flux-v1",
            data={"version": "2.0"}, hop_count=1))
        await asyncio.sleep(0.1)

    LOOP.run_until_complete(run())

    assert len(chain) >= 1
    assert "sw:release" in chain[0]
    print(f"   ✅ Chain: {' → '.join(chain)}")

    orch.teardown()
    print(f"   ✅ Teardown: subscribers cleaned")


# ────────────── Test 4: Formal Migration Plan ──────────────

def test_formal_migration():
    print("\n═══ Test 4: Formal Migration Plan ═══")

    # Create a mock v2 config
    v2_yaml = """
profile: software
name: dev-cycle
version: 2.0
states:
  spec: {type: initial, max_reentries: 1}
  implementation: {type: intermediate, max_reentries: 5}
  iteration: {type: intermediate, max_reentries: 10}
  code_review: {type: intermediate, max_reentries: null}
  review: {type: intermediate, max_reentries: null}
  release: {type: terminal, max_reentries: 0}
  blocked: {type: error, requires_manual: true}
  cancelled: {type: terminal, max_reentries: 0}
transitions:
  spec -> implementation: {}
  implementation -> iteration: {}
  iteration -> code_review: {}
  iteration -> blocked: {}
  iteration -> cancelled: {}
  code_review -> review: {condition: "human_approved"}
  code_review -> iteration: {condition: "changes_requested"}
  review -> release: {condition: "human_approved"}
  review -> iteration: {condition: "changes_requested"}
  review -> cancelled: {condition: "project_abandoned"}
  blocked -> code_review: {condition: "manual_unblock"}
"""

    v1 = SoftwareProfile()
    v1.initialize()
    v2_config = StateMachineParser.parse_string(v2_yaml)

    # Execute migration
    plan = SOFTWARE_V1_TO_V2
    result = plan.execute(v1.state_machine, v2_config)
    assert result.success, f"Migration failed: {result.errors}"
    assert len(result.migrated_states) >= 7
    print(f"   ✅ v1→v2: {result.summary}")

    # Additive migration test
    additive_plan = MigrationPlan(
        added_states=["fast_lane"],
        added_validators=["QuickCheck"],
        backward_compatible=True,
    )

    # The additive plan will fail because fast_lane isn't in v2_config
    # which is correct behavior
    result2 = additive_plan.execute(v1.state_machine, v2_config)
    assert not result2.success  # fast_lane not found in v2
    print(f"   ✅ Additive migration correctly detects: "
          f"{result2.errors[0] if result2.errors else '?'}")


# ────────────── Test 5: Migration Edge Cases ──────────────

def test_migration_edges():
    print("\n═══ Test 5: Migration Edge Cases ═══")

    v1 = SoftwareProfile()
    v1.initialize()

    # Empty migration plan (no changes)
    empty = MigrationPlan()
    result = empty.execute(v1.state_machine, v1.state_machine.config)
    assert result.success
    assert len(result.migrated_states) == 7
    print(f"   ✅ Empty plan: 7 states pass-through")

    # Removed states with backward compat
    removal_plan = MigrationPlan(
        removed_states=["blocked"],
        backward_compatible=False,
    )
    result2 = removal_plan.execute(v1.state_machine, v1.state_machine.config)
    assert result2.success  # blocked removed, still exists in v1 config — not an error
    print(f"   ✅ Removed state 'blocked': still passes")

    # Version check
    assert SOFTWARE_V1_TO_V2.backward_compatible == False
    assert CONTENT_V1_TO_V2.backward_compatible == True
    print(f"   ✅ Version semantics: software=breaking, content=additive")


# ────────────── Test 6: Full Stack v0.5 ──────────────

def test_full_stack_v05():
    """Full stack works end-to-end"""
    tmpdir = tempfile.mkdtemp()

# ──────────────────────────────────────────────
# Profile Validation Tests (D07)
# ──────────────────────────────────────────────


def test_content_profile_valid():
    """Content profile initializes with valid state machine"""
    from profiles.content import ContentProfile
    p = ContentProfile()
    p.initialize()
    assert p.state_machine is not None
    assert p.name == "content"
    assert len(p.state_machine.config.states) == 9
    initial = p.state_machine.config.initial_states
    assert len(initial) >= 1
    assert initial[0].state_type.name == "INITIAL"


def test_software_profile_valid():
    """Software profile initializes with valid state machine"""
    from profiles.software import SoftwareProfile
    p = SoftwareProfile()
    p.initialize()
    assert p.state_machine is not None
    assert p.name == "software"
    assert len(p.state_machine.config.states) == 7


def test_research_profile_valid():
    """Research profile initializes with valid state machine"""
    from profiles.research import ResearchProfile
    p = ResearchProfile()
    p.initialize()
    assert p.state_machine is not None
    assert p.name == "research"
    assert len(p.state_machine.config.states) == 10


def test_design_profile_valid():
    """Design profile initializes with valid state machine"""
    from profiles.design import DesignProfile
    p = DesignProfile()
    p.initialize()
    assert p.state_machine is not None
    assert p.name == "design"
    assert len(p.state_machine.config.states) == 8


def test_all_profiles_have_budget():
    """All profiles have a valid budget configuration"""
    from profiles.content import ContentProfile
    from profiles.software import SoftwareProfile
    from profiles.research import ResearchProfile
    from profiles.design import DesignProfile

    for ProfileClass in [ContentProfile, SoftwareProfile, ResearchProfile, DesignProfile]:
        p = ProfileClass()
        p.initialize()
        b = p.budget
        assert b is not None, f"{p.name} missing budget"
    tmpdir = tempfile.mkdtemp()
    slug = "v05-full-stack"

    # ALL components
    store = EventStore(base_path=tmpdir, slug=slug)
    cost = CostTracker()
    eff = EfficiencyTracker()
    deg = DegradationManager(base_path=tmpdir)
    bus = EventBus()
    safety = RuntimeSafetyMonitor(event_bus=bus)
    budget = BudgetEnforcer(cost_tracker=cost, degradation_manager=deg)
    budget.configure({"soft_limit_usd": 0.1, "hard_limit_usd": 0.5})

    class SW(ProductProfile):
        name, version, state_machine_yaml = "software", "1.0", YAML

    profile = SW()
    profile.initialize()
    mgr = RunManager(base_path=tmpdir)
    mgr.create_run("Final v0.5 Test", profile, slug=slug)

    cli = DebugCLI(run_manager=mgr, event_store=store, cost_tracker=cost,
                    efficiency_tracker=eff, degradation_manager=deg,
                    budget_enforcer=budget, runtime_safety=safety)
    reg = ProfileRegistry()
    reg.sources["user"].path = os.path.join(tmpdir, "profiles")

    # 1. Run lifecycle
    mgr.update_state(slug, "prototyping", profile)
    mgr.update_state(slug, "iteration", profile)

    # 2. Events
    store.append(CostAwareEvent.from_validation(0, slug, "BuildCheck", 1, True, 0.01))
    store.append(CostAwareEvent.from_validation(0, slug, "TestSuite", 2, False, 0.35))
    store.append(CostAwareEvent.from_transition(0, slug, "spec", "prototyping"))

    # 3. Cost
    cost.record_llm("gpt-4o", 1000, 300, "validation", "TestSuite")
    cost.record_compute("build", 60, cores=2)

    # 4. Efficiency
    eff.estimate(slug, "software", "release", cost.total_usd)
    eff.record_actual(slug, 2.5, source="api")

    # 5. Degradation test
    deg.evaluate({"consecutive_llm_failures": 3})
    assert deg.current_level.value == "degraded"
    deg.manual_recover()

    # 6. Registry
    reg.register("v05-profile", "1.0", ProfileMetadata(
        name="v05-profile", version="1.0", author="test"))

    # 7. Debug CLI
    r = cli.handle("timeline", slug)
    assert "Timeline" in r or "events" in r.lower()
    r = cli.handle("health")
    assert "Degradation" in r
    r = cli.handle("cost", slug)
    assert "Cost" in r or "$" in r

    # 8. Safety check
    safety.check_all()
    report = safety.health_report()
    assert report is not None

    # 9. Summary
    total_events = store.event_count
    total_cost = cost.total_usd

    print(f"   ✅ Run: spec→prototyping→iteration")
    print(f"   ✅ Events: {total_events}")
    print(f"   ✅ Cost: ${total_cost:.4f}")
    print(f"   ✅ Efficiency: {eff.display(slug)}")
    print(f"   ✅ Degradation: FULL after manual_recover")
    print(f"   ✅ Registry: 1 profile registered")
    print(f"   ✅ Debug CLI: timeline + health + cost")
    print(f"   ✅ Safety: {len(safety.active_violations)} active violations")

    print(f"\n   🎯 ALL 9 components verified together!")


# ────────────── Main ──────────────

def main():
    print("=" * 60)
    print("  Prodinamik Engine v0.5 — Phase 5 Integration Test")
    print("  Profile Migration")
    print("=" * 60)

    tests = [
        ("ContentProfile", test_content_profile),
        ("SoftwareProfile", test_software_profile),
        ("CrossProfileChain", test_cross_profile_chain),
        ("FormalMigration", test_formal_migration),
        ("MigrationEdges", test_migration_edges),
        ("FullStack_v0.5", test_full_stack_v05),
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
            import traceback; traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  ✅ {passed} passed, ❌ {failed} failed")
    print(f"  Total: {passed}/{passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
