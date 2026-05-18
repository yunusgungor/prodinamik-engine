#!/usr/bin/env python3
"""
Prodinamik Engine — Stress Test Script
═══════════════════════════════════════
1000 run / ~10 dk throughput test.

Usage:
    python scripts/stress_test.py              # Default: 100 runs, 5 min
    python scripts/stress_test.py --runs 1000  # Full stress: 1000 runs
    python scripts/stress_test.py --duration 300  # Time-bounded: 5 min
    python scripts/stress_test.py --quick      # Quick smoke test (10 runs)
"""

import sys
import os
import time
import json
import tempfile
import threading
import statistics
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# ── Proje root'u path'e ek ──
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.run_manager import RunManager
from engine.state_machine import StateMachineParser, StateMachine
from engine.event_store import EventStore, Event
from engine.profile import ProductProfile, Budget


# ── Minimum test profili ──
STRESS_SM_YAML = """
profile: stress
name: stress-test
version: 1.0
states:
  created:
    type: initial
    max_reentries: 1
  running:
    type: intermediate
    max_reentries: 10
  verifying:
    type: intermediate
    max_reentries: 5
  completed:
    type: terminal
    max_reentries: 0
  failed:
    type: terminal
    max_reentries: 0
  cancelled:
    type: terminal
    max_reentries: 0
transitions:
  created -> running: {}
  running -> verifying: {condition: "iterations >= 1"}
  running -> failed: {condition: "consecutive_failures >= 3"}
  verifying -> completed: {condition: "prototype_passes(spec)"}
  verifying -> running: {condition: "changes_requested"}
  running -> cancelled: {condition: "max_iterations_exceeded"}
"""


class StressProfile(ProductProfile):
    name = "stress"
    version = "1.0"
    description = "Stress testing profile"
    state_machine_yaml = STRESS_SM_YAML

    @property
    def validators(self):
        return []

    @property
    def adapters(self):
        return []

    @property
    def budget(self):
        return Budget(soft_limit_usd=100, hard_limit_usd=200)


# ── Metrics ──

class StressMetrics:
    def __init__(self):
        self.latencies: List[float] = []       # per-op latency (ms)
        self.throughput_samples: List[float] = []  # ops/sec over time
        self.errors: int = 0
        self.start_time: float = 0
        self.run_count: int = 0
        self._lock = threading.Lock()

    def record_op(self, latency_ms: float):
        with self._lock:
            self.latencies.append(latency_ms)
            self.run_count += 1

    def record_error(self):
        with self._lock:
            self.errors += 1

    def sample_throughput(self, ops_count: int):
        with self._lock:
            self.throughput_samples.append(ops_count)

    @property
    def total_time(self) -> float:
        return time.time() - self.start_time

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.99)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def throughput(self) -> float:
        elapsed = self.total_time
        return self.run_count / elapsed if elapsed > 0 else 0

    def report(self) -> dict:
        return {
            "total_runs": self.run_count,
            "total_errors": self.errors,
            "error_rate": f"{self.errors / max(self.run_count, 1) * 100:.2f}%",
            "duration_sec": round(self.total_time, 2),
            "throughput_ops_per_sec": round(self.throughput, 2),
            "latency_ms": {
                "avg": round(self.avg_latency, 3),
                "p95": round(self.p95_latency, 3),
                "p99": round(self.p99_latency, 3),
            },
        }


# ── Core Stress Test ──

def stress_create_runs(mgr: RunManager, profile, count: int,
                       batch_size: int = 50) -> StressMetrics:
    """Create N runs, measure throughput and latency"""
    metrics = StressMetrics()
    metrics.start_time = time.time()
    slug_prefix = f"stress-{int(time.time() * 1000)}"

    print(f"  📦 Creating {count} runs...")
    prev_count = 0
    last_sample = time.time()

    for i in range(count):
        slug = f"{slug_prefix}-{i:05d}"
        try:
            start = time.perf_counter()
            mgr.create_run(f"Stress run #{i}", profile, slug=slug)
            elapsed = (time.perf_counter() - start) * 1000
            metrics.record_op(elapsed)
        except Exception as e:
            metrics.record_error()
            if i < 5:
                print(f"  ⚠️  Run #{i} failed: {e}")

        # Throughput sampling every batch_size ops
        if (i + 1) % batch_size == 0:
            now = time.time()
            elapsed_batch = now - last_sample
            batch_ops = (i + 1) - prev_count
            metrics.sample_throughput(batch_ops / elapsed_batch if elapsed_batch > 0 else 0)
            ops_per_sec = batch_ops / elapsed_batch if elapsed_batch > 0 else 0
            print(f"     Batch {(i+1)//batch_size}: {i+1}/{count} runs "
                  f"({ops_per_sec:.1f} ops/sec, latency={metrics.avg_latency:.1f}ms)")
            prev_count = i + 1
            last_sample = now

    return metrics


def stress_concurrent_ops(mgr: RunManager, profile, run_slugs: List[str],
                          num_threads: int = 4) -> StressMetrics:
    """Concurrent read/write operations"""
    import random
    metrics = StressMetrics()
    metrics.start_time = time.time()

    def worker(thread_id: int):
        for slug in run_slugs[thread_id::num_threads]:
            try:
                start = time.perf_counter()
                # Simulate: read run → try transition → append event
                run = mgr.get_run(slug)
                if run and hasattr(run.meta, 'profile'):
                    try:
                        mgr.transition(slug, "running")
                    except (ValueError, KeyError):
                        pass
                elapsed = (time.perf_counter() - start) * 1000
                metrics.record_op(elapsed)
            except Exception:
                metrics.record_error()

    threads = []
    for t in range(num_threads):
        thread = threading.Thread(target=worker, args=(t,), daemon=True)
        threads.append(thread)
        thread.start()

    for t in threads:
        t.join()

    return metrics


def run_stress_test(num_runs: int = 100, duration: int = 300,
                    batch_size: int = 50, concurrent: bool = True):
    """Run full stress test suite"""
    tmpdir = tempfile.mkdtemp()
    print(f"\n{'='*60}")
    print(f"  🔥 Prodinamik Engine — Stress Test")
    print(f"  Runs: {num_runs} | Duration: {duration}s | Batch: {batch_size}")
    print(f"{'='*60}\n")

    mgr = RunManager(base_path=tmpdir)
    profile = StressProfile()
    profile.initialize()

    # ── Phase 1: Run Creation ──
    print(f"  ── Phase 1: Sequential Run Creation ──")
    create_metrics = stress_create_runs(mgr, profile, num_runs, batch_size)
    print(f"\n  ✅ Phase 1 complete: {create_metrics.run_count} runs created")

    # ── Phase 2: Concurrent Operations ──
    if concurrent and create_metrics.run_count > 0:
        print(f"\n  ── Phase 2: Concurrent Operations ──")
        slugs = [f"stress-{int(time.time() * 1000)}-{i:05d}"
                 for i in range(min(create_metrics.run_count, 100))]
        # Create additional runs for concurrent test
        for s in slugs:
            try:
                mgr.create_run(f"Concurrent run", profile, slug=s)
            except Exception:
                pass

        conc_metrics = stress_concurrent_ops(mgr, profile, slugs, num_threads=4)
        print(f"  ✅ Phase 2 complete: {conc_metrics.run_count} concurrent ops")

    # ── Final Report ──
    elapsed = time.time() - create_metrics.start_time
    print(f"\n{'='*60}")
    print(f"  📊 Stress Test Report")
    print(f"{'='*60}")
    print(f"  Duration:      {elapsed:.1f}s")
    print(f"  Total runs:    {create_metrics.run_count}")
    print(f"  Errors:        {create_metrics.errors}")
    print(f"  Error rate:    {create_metrics.errors/max(create_metrics.run_count,1)*100:.2f}%")
    print(f"  Throughput:    {create_metrics.throughput:.1f} ops/sec")
    print(f"  Latency avg:   {create_metrics.avg_latency:.2f}ms")
    print(f"  Latency p95:   {create_metrics.p95_latency:.2f}ms")
    print(f"  Latency p99:   {create_metrics.p99_latency:.2f}ms")
    print(f"{'='*60}")

    # Save report
    report_path = Path(tmpdir).parent / f"stress-report-{int(time.time())}.json"
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {"runs": num_runs, "duration": duration, "batch_size": batch_size},
        "results": create_metrics.report(),
    }
    Path(str(report_path)).write_text(json.dumps(report, indent=2))
    print(f"\n  💾 Report saved: {report_path}")

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    # Assertions
    assert create_metrics.errors == 0, f"❌ Stress test: {create_metrics.errors} errors"
    assert create_metrics.run_count == num_runs, \
        f"❌ Expected {num_runs} runs, got {create_metrics.run_count}"
    print(f"\n  ✅ Stress test PASSED — 0 errors, {create_metrics.run_count}/{num_runs} runs")

    return report


# ── CLI Entry Point ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prodinamik Engine — Stress Test")
    parser.add_argument("--runs", type=int, default=100,
                        help="Number of runs to create (default: 100)")
    parser.add_argument("--duration", type=int, default=300,
                        help="Max duration in seconds (default: 300)")
    parser.add_argument("--batch", type=int, default=50,
                        help="Batch size for throughput sampling (default: 50)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick smoke test: 10 runs, no concurrent phase")
    parser.add_argument("--no-concurrent", action="store_true",
                        help="Skip concurrent operations phase")

    args = parser.parse_args()

    if args.quick:
        args.runs = 10
        args.no_concurrent = True

    run_stress_test(
        num_runs=args.runs,
        duration=args.duration,
        batch_size=args.batch,
        concurrent=not args.no_concurrent,
    )
