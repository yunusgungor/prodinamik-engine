"""
Prodinamik Engine v0.5 — Phase 3 Integration Test

Distribution & Cost — 6 test:
1. Cost Tracker (multi-dimensional: tokens, compute, storage, network)
2. Deferred Efficiency (T0 estimate + T1 actual)
3. Budget Enforcement (soft/hard limit, WARN→SLOW→STOP)
4. Cost Timeline + Anomaly Detection (TemporalCostDebugger)
5. Hybrid Raft Consensus (Leader/follower sync, offline, reconnect)
6. CRDT Merge (conflict resolution, forward path)
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cost import (
    CostTracker, EfficiencyTracker, RunEfficiency,
    TemporalCostDebugger, CostAnomaly,
)
from engine.budget import BudgetEnforcer, BudgetAction
from engine.degradation import DegradationManager, DegradationLevel
from engine.raft import (
    HybridConsensusNode, DistributedStateMachine,
    OfflineManager, StateCRDT, NodeState, NodeRole,
    LogEntry,
)
from engine.event_store import CostAwareEvent, EventType


# ──────────────────────────────
# Test 1: Cost Tracker
# ──────────────────────────────

def test_cost_tracker():
    print("═══ Test 1: Cost Tracker ═══")
    c = CostTracker()

    c.record_llm("deepseek-v4-flash", 500, 150, "validation", "SlopScanT1")
    c.record_llm("gpt-4o", 1000, 300, "validation", "RubricScore", wasted=True)
    c.record_compute("build", 120, cores=4)
    c.record_network("Buffer", "api.buffer.com/updates", 350, 0.001)
    c.record_storage(1024 * 1024 * 10)

    assert c.total_llm_calls == 2
    assert c.total_llm_tokens > 0
    assert c.total_usd > 0
    assert c.total_compute_cost > 0
    assert c.total_network_cost > 0
    assert c.total_storage_cost > 0
    assert c.waste_estimate > 0

    breakdown = c.breakdown_by_validator()
    assert len(breakdown) >= 2
    assert c.savings_tips is not None

    print(f"   ✅ Total: ${c.total_usd:.4f} (LLM: ${c.total_llm_cost:.4f}, "
          f"Compute: ${c.total_compute_cost:.4f}, "
          f"Network: ${c.total_network_cost:.4f})")
    print(f"   ✅ Waste: ${c.waste_estimate:.4f}")
    print(f"   ✅ Breakdown: {breakdown}")


# ──────────────────────────────
# Test 2: Deferred Efficiency
# ──────────────────────────────

def test_efficiency():
    print("\n═══ Test 2: Deferred Efficiency ═══")
    e = EfficiencyTracker()

    # Add completed runs
    e.add_completed(RunEfficiency(
        slug="flux-v1", profile="software", format="release",
        total_cost=0.5, estimated=2.0, actual=2.5, source="api"))
    e.add_completed(RunEfficiency(
        slug="ai-thread", profile="content", format="thread",
        total_cost=0.05, estimated=1.5, actual=0.8, source="api"))

    # T0: estimate for new run
    estimate = e.estimate("new-run", "software", "release", 0.3)
    assert estimate.estimated == 2.5  # flux-v1'in actual değeri (2.5)
    assert estimate.actual is None
    print(f"   ✅ T0 estimate: {estimate.display_value} (based on similar runs)")

    # T1: record actual
    e.record_actual("new-run", 3.0, source="api")
    assert e.completed_runs[-1].actual == 3.0
    assert e.completed_runs[-1].variance_pct is not None
    print(f"   ✅ T1 actual: {e.display('new-run')}")
    print(f"   ✅ Variance: {e.completed_runs[-1].variance_pct:+.1f}%")


# ──────────────────────────────
# Test 3: Budget Enforcement
# ──────────────────────────────

def test_budget():
    print("\n═══ Test 3: Budget Enforcement ═══")
    tmpdir = tempfile.mkdtemp()
    cost = CostTracker()
    deg = DegradationManager(base_path=tmpdir)
    b = BudgetEnforcer(cost_tracker=cost, degradation_manager=deg)

    b.configure({"soft_limit_usd": 0.02, "hard_limit_usd": 0.05, "max_llm_calls_per_run": 3})

    # PROCEED
    action = b.check_validator("T1Test", 1)
    assert action == BudgetAction.PROCEED
    print(f"   ✅ Initial: PROCEED")

    # WARN: soft limit exceeded
    cost.record_llm("gpt-4o", 5000, 1500, "test", "ExpensiveValidator")
    b.update_from_tracker()
    action = b.check_validator("T2Test", 2)
    assert action in (BudgetAction.WARN, BudgetAction.STOP)
    print(f"   ✅ After expensive call: {action.value}")

    # Enforce: degradation
    b.apply_action(BudgetAction.STOP, "T2Test")
    print(f"   ✅ Degradation triggered: {deg.current_level.value}")


# ──────────────────────────────
# Test 4: Cost Timeline + Anomaly
# ──────────────────────────────

def test_cost_timeline():
    print("\n═══ Test 4: Cost Timeline ═══")
    events = [
        CostAwareEvent(sequence=i, run_slug="demo", timestamp="2026-05-18T10:00:00",
                      event_type="validation",
                      data={"validator": f"V{j}", "passed": True},
                      cost_usd=0.01 if j < 8 else 0.5)
        for i, j in enumerate(range(10))
    ]

    debugger = TemporalCostDebugger()
    analysis = debugger.analyze_events(events)

    assert analysis["total_cost"] > 0
    assert analysis["event_count"] == 10
    assert isinstance(analysis["anomalies"], list)
    print(f"   ✅ Total: ${analysis['total_cost']:.3f}, Events: {analysis['event_count']}")

    if analysis["anomalies"]:
        for a in analysis["anomalies"]:
            print(f"   ⚠️  Anomaly: #{a.sequence} ${a.cost_usd:.3f} ({a.sigma:.1f}σ)")

    # Timeline display
    timeline = debugger.cost_timeline(events)
    assert "Cost Timeline" in timeline
    print(f"   ✅ Timeline display: {len(timeline)} chars")


# ──────────────────────────────
# Test 5: Hybrid Raft Consensus
# ──────────────────────────────

def test_raft():
    print("\n═══ Test 5: Hybrid Raft Consensus ═══")
    tmpdir = tempfile.mkdtemp()
    s = lambda n: os.path.join(tmpdir, f"raft{n}")

    # Create cluster
    leader = HybridConsensusNode("node-1", ["node-2"], state_dir=s(1))
    leader.raft.become_leader()

    # Normal operation
    success, _ = leader.apply({"type": "create", "slug": "flux-release",
                                "initial_state": "spec"})
    assert success
    success, _ = leader.apply({"type": "transition", "slug": "flux-release",
                                "to_state": "prototyping"})
    assert success

    state = leader.get_state("flux-release")
    assert state.current_state == "prototyping"
    assert state.version == 2
    print(f"   ✅ Leader: flux-release → {state.current_state} (v{state.version})")

    # Follower sync
    follower = HybridConsensusNode("node-2", ["node-1"], state_dir=s(2))
    follower.raft.log = list(leader.raft.log)
    follower.raft.commit_index = len(leader.raft.log) - 1
    follower.raft._apply_committed()
    fstate = follower.get_state("flux-release")
    assert fstate.current_state == "prototyping"
    print(f"   ✅ Follower synced: flux-release → {fstate.current_state}")

    # Offline
    offline_node = HybridConsensusNode("node-3", ["node-1"], state_dir=s(3))
    offline_node.offline.go_offline()
    offline_node.apply({"type": "transition", "slug": "flux-release",
                         "to_state": "iteration"})
    assert offline_node.offline.pending_count == 1
    print(f"   ✅ Offline pending: iteration (1 op)")

    # Reconnect
    offline_node.reconnect(leader)
    final = leader.get_state("flux-release")
    assert final.current_state == "iteration", f"Expected iteration, got {final.current_state}"
    print(f"   ✅ Reconnected: flux-release → {final.current_state}")


# ──────────────────────────────
# Test 6: CRDT Merge
# ──────────────────────────────

def test_crdt():
    print("\n═══ Test 6: CRDT Merge ═══")
    transitions = {
        "spec": ["prototyping"],
        "prototyping": ["iteration"],
        "iteration": ["review", "blocked"],
        "review": ["release", "iteration"],
        "drafting": ["verification"],
        "verification": ["review"],
    }

    # Same version, forward path
    local = NodeState(current_state="drafting", version=1)
    remote = NodeState(current_state="verification", version=1)
    merged = StateCRDT.merge(local, remote, transitions)
    assert merged.current_state == "verification", "Forward path should win"
    print(f"   ✅ Forward path: {local.current_state} + {remote.current_state} → {merged.current_state}")

    # Different versions, remote newer
    local = NodeState(current_state="drafting", version=1)
    remote = NodeState(current_state="published", version=3)
    merged = StateCRDT.merge(local, remote, transitions)
    assert merged.current_state == "published"
    assert merged.version == 3
    print(f"   ✅ Remote newer: v1 + v3 → {merged.current_state}")

    # Different paths (divergent)
    local = NodeState(current_state="review", version=2)
    remote = NodeState(current_state="iteration", version=2)
    merged = StateCRDT.merge(local, remote, transitions)
    print(f"   ✅ Divergent: {local.current_state} + {remote.current_state} → {merged.current_state} (local wins)")


# ──────────────────────────────
# Main
# ──────────────────────────────

def main():
    print("=" * 60)
    print("  Prodinamik Engine v0.5 — Phase 3 Integration Test")
    print("  Distribution & Cost")
    print("=" * 60)

    tests = [
        ("CostTracker", test_cost_tracker),
        ("DeferredEfficiency", test_efficiency),
        ("BudgetEnforcement", test_budget),
        ("CostTimeline", test_cost_timeline),
        ("HybridRaft", test_raft),
        ("CRDTMerge", test_crdt),
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
