"""Prodinamik Engine v1.1 — Performance Benchmark Suite

Run via `prodinamik benchmark [runs]` or `python -m engine.bench`

Measures:
- State machine parsing throughput
- Run creation latency
- Transition latency
- Validator pipeline throughput
- WAL write throughput
- Event store append throughput
"""

import time
import tempfile
import statistics
from pathlib import Path
from typing import Dict, Any, Callable, List
from dataclasses import dataclass, field

from .log import get_logger

log = get_logger()


@dataclass
class BenchmarkResult:
    """Single benchmark metric"""
    name: str
    samples: List[float] = field(default_factory=list)
    unit: str = "ms"

    @property
    def avg(self) -> float:
        return statistics.mean(self.samples) if self.samples else 0.0

    @property
    def median(self) -> float:
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def min(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max(self) -> float:
        return max(self.samples) if self.samples else 0.0

    @property
    def p95(self) -> float:
        if not self.samples:
            return 0.0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * 0.95)
        return sorted_s[min(idx, len(sorted_s) - 1)]

    @property
    def stddev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0.0

    def summary(self) -> Dict[str, float]:
        return {
            "avg": round(self.avg, 3),
            "median": round(self.median, 3),
            "min": round(self.min, 3),
            "max": round(self.max, 3),
            "p95": round(self.p95, 3),
            "stddev": round(self.stddev, 3),
            "samples": len(self.samples),
        }

    def __str__(self) -> str:
        s = self.summary()
        return (f"{self.name}: avg={s['avg']}{self.unit} "
                f"p95={s['p95']}{self.unit} "
                f"min={s['min']}{self.unit} "
                f"max={s['max']}{self.unit} "
                f"(n={s['samples']})")


class Benchmark:
    """Compact benchmark runner"""

    def __init__(self, name: str, iterations: int = 5):
        self.name = name
        self.iterations = iterations
        self.results: List[BenchmarkResult] = []

    def measure(self, name: str, fn: Callable, *args, **kwargs) -> BenchmarkResult:
        """Time a function call over N iterations"""
        result = BenchmarkResult(name=name)

        # Warmup
        try:
            fn(*args, **kwargs)
        except Exception as e:
            log.debug("Benchmark '%s' warmup failed: %s", name, e)

        for i in range(self.iterations):
            start = time.perf_counter()
            try:
                fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000  # ms
            except Exception as e:
                log.warning(f"Benchmark '{name}' iteration {i} failed: {e}")
                elapsed = float('nan')

            if not (elapsed != elapsed):  # not NaN
                result.samples.append(elapsed)

        self.results.append(result)
        return result

    def report(self) -> Dict[str, Any]:
        """Return structured report"""
        return {
            "benchmark": self.name,
            "iterations": self.iterations,
            "results": {r.name: r.summary() for r in self.results},
        }

    def print(self):
        """Pretty-print results"""
        print(f"\n{'=' * 60}")
        print(f"  {self.name} ({self.iterations} iterations)")
        print(f"{'=' * 60}")
        for r in self.results:
            print(f"  {r}")
        print(f"{'=' * 60}\n")


# ──────────────────────────────────────────────
# Benchmark Suites
# ──────────────────────────────────────────────

def bench_state_machine_parsing(iterations: int = 10) -> BenchmarkResult:
    """Time state machine YAML parsing"""
    from .state_machine import StateMachineParser

    yaml_str = """
profile: bench
name: bench-profile
version: 1.0
states:
  a: {type: initial}
  b: {type: intermediate, max_reentries: 5, timeout_seconds: 3600}
  c: {type: intermediate}
  d: {type: intermediate}
  e: {type: terminal}
  f: {type: error}
transitions:
  a -> b: {}
  b -> c: {condition: "ok"}
  c -> d: {condition: "verified"}
  d -> e: {condition: "approved"}
  c -> a: {condition: "retry"}
  b -> f: {condition: "fail"}
"""
    bench = Benchmark("State Machine Parsing", iterations)
    result = bench.measure("parse_yaml", StateMachineParser.parse_string, yaml_str)
    bench.print()
    return result


def bench_run_creation(engine, iterations: int = 10) -> BenchmarkResult:
    """Time run creation"""
    bench = Benchmark("Run Creation", iterations)
    result = bench.measure(
        "create_run",
        engine.create_run, "benchmark", "bench run"
    )
    bench.print()
    return result


def bench_state_transition(engine, slug: str, iterations: int = 10) -> BenchmarkResult:
    """Time state transitions"""
    bench = Benchmark("State Transition", iterations)

    # Get states available for the profile
    run = engine.get_run(slug)
    if not run:
        return BenchmarkResult(name="state_transition")

    profile = engine._get_profile(run.meta.profile)
    states = list(profile.state_machine.config.states.keys())

    def transition_cycle():
        """Transitions through available states"""
        for s in states:
            try:
                engine._do_transition(slug, s)
            except ValueError:
                pass

    result = bench.measure("cycle_through_states", transition_cycle)
    bench.print()
    return result


def bench_event_store_append(iterations: int = 50) -> BenchmarkResult:
    """Time event store appends"""
    import tempfile
    import os
    from .event_store import EventStore, CostAwareEvent

    tmpdir = tempfile.mkdtemp()
    store = EventStore(base_path=tmpdir, slug="bench-events")

    bench = Benchmark("Event Store Append", iterations)

    def append_one():
        store.append(CostAwareEvent(
            sequence=store.event_count,
            run_slug="bench",
            timestamp="2026-05-18T08:00:00",
            event_type="state_transition",
            data={"from": "a", "to": "b"},
            cost_usd=0.001,
        ))

    result = bench.measure("append", append_one)

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    bench.print()
    return result


def bench_wal_write(iterations: int = 10) -> BenchmarkResult:
    """Time WAL write throughput"""
    import tempfile
    import os
    from .run_manager import RunManager
    from .state_machine import StateMachineParser

    tmpdir = tempfile.mkdtemp()
    mgr = RunManager(base_path=tmpdir)

    # Minimal profile — ProductProfile parses state_machine_yaml in initialize()
    from .profile import ProductProfile
    class BenchProfile(ProductProfile):
        name = "bench"
        version = "1.0"
        state_machine_yaml = """
profile: bench
name: bench
version: 1.0
states:
  created:
    type: initial
  done:
    type: terminal
    max_reentries: 0
transitions:
  created -> done: {}
"""
        @property
        def validators(self): return []
        @property
        def adapters(self): return []
        @property
        def budget(self):
            from .profile import Budget
            return Budget(soft_limit_usd=0.5, hard_limit_usd=1.0)

    profile = BenchProfile()
    profile.initialize()

    bench = Benchmark("WAL Write", iterations)

    def create_run():
        ts = int(time.time() * 1000)
        mgr.create_run(f"bench-run-{ts}", profile, slug=f"bench-wal-{ts}")

    result = bench.measure("create_run", create_run)

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    bench.print()
    return result


def bench_profile_discovery(iterations: int = 10) -> BenchmarkResult:
    """Time profile registry discovery"""
    from .registry import ProfileRegistry

    bench = Benchmark("Profile Discovery", iterations)

    def discover():
        reg = ProfileRegistry()
        reg.list_profiles()

    result = bench.measure("discover_profiles", discover)
    bench.print()
    return result


def bench_async_engine_start_stop(iterations: int = 5) -> BenchmarkResult:
    """Time async engine start/stop cycle"""
    import asyncio
    from .config import ProdinamikConfig
    from .runtime import AsyncEngine

    bench = Benchmark("Async Engine Start/Stop", iterations)

    async def start_stop():
        cfg = ProdinamikConfig.load()
        engine = AsyncEngine(cfg)
        await engine.start()
        await engine.stop()

    for i in range(iterations):
        start = time.perf_counter()
        try:
            asyncio.run(start_stop())
            elapsed = (time.perf_counter() - start) * 1000
        except Exception as e:
            log.warning(f"Async benchmark iteration {i} failed: {e}")
            elapsed = float('nan')

        if not (elapsed != elapsed):
            bench.results[0].samples.append(elapsed)

    bench.print()
    return bench.results[0]


# ──────────────────────────────────────────────
# Main Runner
# ──────────────────────────────────────────────

def run_all_benchmarks(engine=None, iterations: int = 5) -> Dict[str, Any]:
    """Run all benchmark suites"""
    results = {}

    # 1. State machine parsing
    results["state_machine_parsing"] = bench_state_machine_parsing(iterations).summary()

    # 2. Event store
    results["event_store_append"] = bench_event_store_append(iterations * 2).summary()

    # 3. WAL write
    results["wal_write"] = bench_wal_write(iterations).summary()

    # 4. Profile discovery
    results["profile_discovery"] = bench_profile_discovery(iterations).summary()

    # 5. Run creation (if engine provided)
    if engine:
        try:
            run_result = bench_run_creation(engine, iterations)
            results["run_creation"] = run_result.summary()

            # 6. State transition (if runs exist)
            runs = engine.list_runs(include_archived=False)
            if runs:
                slug = runs[0].slug
                trans_result = bench_state_transition(engine, slug, iterations)
                results["state_transition"] = trans_result.summary()
        except Exception as e:
            log.warning(f"Engine benchmarks skipped: {e}")

    return results


def run_benchmark(engine=None, runs: int = 5) -> Dict[str, Any]:
    """Entry point for CLI benchmark command"""
    print(f"🚀 Prodinamik Engine Benchmark ({runs} iterations each)")
    return run_all_benchmarks(engine, iterations=runs)


if __name__ == "__main__":
    import sys
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    print(f"Prodinamik Engine Benchmark Suite")
    print(f"Iterations: {iterations} each")
    print()

    results = run_all_benchmarks(iterations=iterations)

    print("\nSummary:")
    for name, metrics in results.items():
        print(f"  {name}: avg={metrics['avg']}ms p95={metrics['p95']}ms n={metrics['samples']}")
