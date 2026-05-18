#!/usr/bin/env python3
"""
Prodinamik Engine — Memory Profiler
════════════════════════════════════
Tracemalloc ile engine operasyonlarının memory footprint'ini ölçer.

Usage:
    python scripts/memory_profile.py                   # Tüm profil senaryoları
    python scripts/memory_profile.py --quick            # Sadece temel ölçümler
    python scripts/memory_profile.py --scenario parsing  # Tek senaryo
    python scripts/memory_profile.py --compare           # Önceki run ile karşılaştır
"""

import sys
import os
import time
import json
import tracemalloc
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.run_manager import RunManager
from engine.event_store import EventStore, Event
from engine.state_machine import StateMachineParser
from engine.profile import ProductProfile, Budget


# ── Minimum profiller ──

SM_YAML_SMALL = """
profile: mem
name: mem-test
version: 1.0
states:
  a: {type: initial, max_reentries: 1}
  b: {type: intermediate, max_reentries: 5}
  c: {type: terminal, max_reentries: 0}
transitions:
  a -> b: {}
  b -> c: {}
"""

SM_YAML_LARGE = """
profile: mem
name: mem-test-large
version: 1.0
states:
  {states}
transitions:
  {transitions}
"""


def _make_large_yaml(num_states: int = 50) -> str:
    """Generate a large state machine YAML"""
    lines = [
        "profile: mem",
        "name: mem-test-large",
        "version: 1.0",
        "states:",
    ]
    for i in range(num_states):
        stype = "initial" if i == 0 else ("terminal" if i == num_states - 1 else "intermediate")
        max_r = 1 if stype == "initial" else (0 if stype == "terminal" else 5)
        lines.append(f"  s{i:03d}:")
        lines.append(f"    type: {stype}")
        lines.append(f"    max_reentries: {max_r}")

    lines.append("transitions:")
    for i in range(num_states - 1):
        lines.append(f"  s{i:03d} -> s{i+1:03d}:")
        lines.append("    type: REVERSIBLE")

    return "\n".join(lines)


class MemorySnapshot:
    """Tek bir memory ölçüm noktası"""
    def __init__(self, label: str):
        self.label = label
        self.current: int = 0       # current memory (bytes)
        self.peak: int = 0          # peak since tracemalloc start
        self.diff_from_prev: int = 0
        self.timestamp: float = time.time()

    @property
    def current_mb(self) -> float:
        return self.current / 1024 / 1024

    @property
    def peak_mb(self) -> float:
        return self.peak / 1024 / 1024

    @property
    def diff_mb(self) -> float:
        return self.diff_from_prev / 1024 / 1024

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "current_mb": round(self.current_mb, 4),
            "peak_mb": round(self.peak_mb, 4),
            "diff_mb": round(self.diff_mb, 4),
            "timestamp": self.timestamp,
        }


class MemoryProfiler:
    """Tracemalloc tabanlı memory profiler"""

    def __init__(self):
        self.snapshots: List[MemorySnapshot] = []
        self._prev_current = 0
        self.start_time: float = 0

    def __enter__(self):
        tracemalloc.start()
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        tracemalloc.stop()

    def snapshot(self, label: str):
        """Al memory snapshot at current point"""
        current, peak = tracemalloc.get_traced_memory()
        snap = MemorySnapshot(label)
        snap.current = current
        snap.peak = peak
        snap.diff_from_prev = current - self._prev_current
        self.snapshots.append(snap)
        self._prev_current = current
        return snap

    def get_top_lines(self, limit: int = 10) -> List[dict]:
        """Get top memory-consuming code lines"""
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        results = []
        for stat in top_stats[:limit]:
            frame = stat.traceback[0]
            results.append({
                "file": frame.filename,
                "line": frame.lineno,
                "size_kb": round(stat.size / 1024, 2),
                "count": stat.count,
            })
        return results

    def report(self) -> dict:
        """Generate structured report"""
        elapsed = time.time() - self.start_time
        if self.snapshots:
            first = self.snapshots[0]
            last = self.snapshots[-1]
        else:
            first = last = MemorySnapshot("none")

        return {
            "timestamp": datetime.now().isoformat(),
            "duration_sec": round(elapsed, 2),
            "base_memory_mb": first.current_mb if self.snapshots else 0,
            "peak_memory_mb": max(s.peak_mb for s in self.snapshots) if self.snapshots else 0,
            "total_allocated_mb": last.current_mb - first.current_mb if self.snapshots else 0,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "leak_indicators": self._check_leaks(),
        }

    def _check_leaks(self) -> List[str]:
        """Check for possible memory leaks"""
        indicators = []
        if len(self.snapshots) >= 2:
            diffs = [s.diff_mb for s in self.snapshots[1:] if s.diff_mb > 0]
            if diffs and len(diffs) >= 3:
                # If last 3 snapshots all show positive growth trend
                last_three = [s.diff_mb for s in self.snapshots[-3:]]
                if all(d > 0.05 for d in last_three):
                    indicators.append("⚠️  Sustained growth in last 3 snapshots — possible leak")
        return indicators

    def print(self):
        """Pretty-print results"""
        print(f"\n{'='*60}")
        print(f"  🧠 Memory Profile Report")
        print(f"{'='*60}")
        for s in self.snapshots:
            arrow = "▲" if s.diff_mb > 0 else ("▼" if s.diff_mb < 0 else "—")
            print(f"  {s.label:40s} {s.current_mb:>8.2f}MB "
                  f"(peak: {s.peak_mb:.2f}MB, {arrow}{abs(s.diff_mb):.2f}MB)")
        print(f"{'='*60}")
        peak = max(s.peak_mb for s in self.snapshots) if self.snapshots else 0
        base = self.snapshots[0].current_mb if self.snapshots else 0
        print(f"  Base memory:  {base:.2f}MB")
        print(f"  Peak memory:  {peak:.2f}MB")
        print(f"  Delta:        {peak - base:+.2f}MB")
        print(f"{'='*60}\n")


# ── Profile Scenarios ──

def profile_state_machine_parsing(profiler: MemoryProfiler):
    """Profile: state machine YAML parsing"""
    print("  📋 Scenario: State Machine Parsing")

    profiler.snapshot("Baseline")

    # Small SM
    sm = StateMachineParser.parse_string(SM_YAML_SMALL)
    profiler.snapshot("After small SM (3 states)")

    # Large SM
    large_yaml = _make_large_yaml(50)
    sm_large = StateMachineParser.parse_string(large_yaml)
    profiler.snapshot("After large SM (50 states)")

    # Multiple SMs
    for i in range(10):
        StateMachineParser.parse_string(SM_YAML_SMALL)
    profiler.snapshot("After 10x small SM parse")


def profile_run_creation(profiler: MemoryProfiler):
    """Profile: run creation and management"""
    print("  📋 Scenario: Run Creation & Management")

    tmpdir = tempfile.mkdtemp()
    mgr = RunManager(base_path=tmpdir)

    from engine.state_machine import StateMachine
    from engine.profile import ProductProfile, Budget

    class MemProfile(ProductProfile):
        name = "mem"
        version = "1.0"
        state_machine_yaml = SM_YAML_SMALL
        @property
        def validators(self): return []
        @property
        def adapters(self): return []
        @property
        def budget(self):
            return Budget(soft_limit_usd=1, hard_limit_usd=2)

    profile = MemProfile()
    profile.initialize()

    profiler.snapshot("Baseline (after init)")

    # Create 10 runs
    for i in range(10):
        mgr.create_run(f"Memory run #{i}", profile, slug=f"mem-run-{i}")
    profiler.snapshot("After 10 runs created")

    # Create 90 more (total 100)
    for i in range(10, 100):
        mgr.create_run(f"Memory run #{i}", profile, slug=f"mem-run-{i}")
    profiler.snapshot("After 100 runs created")

    # Update state for all runs
    for i in range(100):
        try:
            current = mgr.get_run(f"mem-run-{i}")
            if current and current.current_state == "a":
                mgr.update_state(f"mem-run-{i}", "b")
        except (ValueError, KeyError, AttributeError):
            pass
    profiler.snapshot("After 100 transitions")

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    profiler.snapshot("After cleanup (tmpdir removed)")


def profile_event_store(profiler: MemoryProfiler):
    """Profile: event store operations"""
    print("  📋 Scenario: Event Store Operations")

    tmpdir = tempfile.mkdtemp()
    store = EventStore(base_path=tmpdir, slug="mem-events")

    profiler.snapshot("Baseline")

    # 100 events
    for i in range(100):
        store.append(Event(
            sequence=i, run_slug="mem-run",
            timestamp="2026-01-01T00:00:00",
            event_type="state_transition",
            data={"from": "a", "to": "b"},
        ))
    profiler.snapshot("After 100 events appended")

    # 900 more events (total 1000)
    for i in range(100, 1000):
        store.append(Event(
            sequence=i, run_slug="mem-run",
            timestamp="2026-01-01T00:00:00",
            event_type="state_transition",
            data={"from": "b", "to": "c"},
        ))
    profiler.snapshot("After 1,000 events appended")

    # Query
    results = store.query(limit=500)
    profiler.snapshot("After query (500 events)")

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    profiler.snapshot("After cleanup")


def profile_top_lines(profiler: MemoryProfiler) -> List[dict]:
    """Get top memory-consuming code lines after all scenarios"""
    print("  📋 Top memory allocations (by code line):")
    top = profiler.get_top_lines(15)
    for i, t in enumerate(top, 1):
        print(f"     {i:2d}. {t['file']}:{t['line']} — {t['size_kb']:.1f}KB ({t['count']} allocs)")
    return top


def run_memory_profile(quick: bool = False):
    """Run full memory profile suite"""
    profiler = MemoryProfiler()
    top_lines = []

    with profiler:
        print(f"\n{'='*60}")
        print(f"  🧠 Prodinamik Engine — Memory Profiler")
        print(f"  Tracemalloc active")
        print(f"{'='*60}\n")

        # Scenario 1: SM Parsing
        profile_state_machine_parsing(profiler)

        # Scenario 2: Run Creation
        profile_run_creation(profiler)

        # Scenario 3: Event Store (skip if quick)
        if not quick:
            profile_event_store(profiler)

        # Top allocations
        print()
        top_lines = profile_top_lines(profiler)

    # Final report
    report = profiler.report()
    profiler.print()

    # Leak check
    if report["leak_indicators"]:
        for ind in report["leak_indicators"]:
            print(f"  {ind}")
        print()

    # Save report
    report_path = Path(f"/tmp/mem-profile-{int(time.time())}.json")
    report["top_allocations"] = top_lines
    report_path.write_text(json.dumps(report, indent=2))
    print(f"  💾 Report saved: {report_path}")

    print(f"\n  ✅ Memory profile completed (peak: {report['peak_memory_mb']:.2f}MB)")
    print()

    return report


# ── CLI ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prodinamik Engine — Memory Profiler")
    parser.add_argument("--quick", action="store_true",
                        help="Quick: skip event store profiling")
    parser.add_argument("--scenario", choices=["parsing", "runs", "events", "all"],
                        default="all", help="Specific scenario to profile")

    args = parser.parse_args()

    if args.scenario == "all":
        run_memory_profile(quick=args.quick)
    else:
        profiler = MemoryProfiler()
        with profiler:
            if args.scenario == "parsing":
                profile_state_machine_parsing(profiler)
            elif args.scenario == "runs":
                profile_run_creation(profiler)
            elif args.scenario == "events":
                profile_event_store(profiler)

            print()
            profile_top_lines(profiler)

        report = profiler.report()
        profiler.print()
        print(f"  ✅ Scenario '{args.scenario}' completed (peak: {report['peak_memory_mb']:.2f}MB)")
