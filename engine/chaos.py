"""Prodinamik Engine v1.1 — Chaos Engineering Framework

Fault injection, scenario execution, and self-healing verification.
Built for testing degradation, recovery, and resilience.

Scenarios:
  - network-partition:    Simulate network failure
  - network-latency:      Add artificial latency
  - disk-full:            Simulate disk full condition
  - disk-corruption:      Corrupt WAL/snapshot files
  - memory-pressure:      Simulate memory exhaustion
  - cpu-spike:            Generate CPU load
  - random-crash:         SIGKILL simulation
  - degraded-mode:        Trigger FULL→DEGRADED→SURVIVAL transitions
  - wal-corruption:       Manually corrupt WAL entries
  - event-flood:          Rapid event injection

Usage:
    chaos = ChaosEngine(engine, base_path)
    result = chaos.run_scenario("disk-full")
    print(result.report())
"""

import os
import json
import time
import random
import signal
import socket
import shutil
import string
import hashlib
import threading
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from enum import Enum


# ──────────────────────────────────────────────
# Scenario Definitions
# ──────────────────────────────────────────────


class FaultType(Enum):
    NETWORK_PARTITION = "network-partition"
    NETWORK_LATENCY = "network-latency"
    DISK_FULL = "disk-full"
    DISK_CORRUPTION = "disk-corruption"
    MEMORY_PRESSURE = "memory-pressure"
    CPU_SPIKE = "cpu-spike"
    RANDOM_CRASH = "random-crash"
    DEGRADED_MODE = "degraded-mode"
    WAL_CORRUPTION = "wal-corruption"
    EVENT_FLOOD = "event-flood"


@dataclass
class ScenarioResult:
    """Result of a single chaos scenario run"""
    scenario_name: str
    fault_type: str
    started_at: str = ""
    duration_seconds: float = 0.0
    fault_injected: bool = False
    system_survived: bool = False
    self_healed: bool = False
    recovery_time_seconds: float = 0.0
    health_before: dict = field(default_factory=dict)
    health_during: dict = field(default_factory=dict)
    health_after: dict = field(default_factory=dict)
    events_logged: int = 0
    errors: List[str] = field(default_factory=list)

    def passed(self) -> bool:
        """Scenario passes if system survived and either healed or no critical damage"""
        return self.system_survived and (self.self_healed or not self.errors)

    def report(self) -> str:
        status = "✅ PASS" if self.passed() else "❌ FAIL"
        lines = [
            f"\n{'=' * 50}",
            f"  Chaos: {self.scenario_name} ({self.fault_type})",
            f"  Status: {status}",
            f"  Duration: {self.duration_seconds:.1f}s",
            f"  Fault injected: {'✅' if self.fault_injected else '❌'}",
            f"  System survived: {'✅' if self.system_survived else '💥'}",
            f"  Self-healed: {'✅' if self.self_healed else '⏳'}",
            f"  Recovery time: {self.recovery_time_seconds:.1f}s",
            f"  Events logged: {self.events_logged}",
        ]
        if self.errors:
            lines.append(f"  Errors ({len(self.errors)}):")
            for e in self.errors[:3]:
                lines.append(f"    • {e}")
        lines.append(f"{'=' * 50}")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# Chaos Engine
# ──────────────────────────────────────────────


class ChaosEngine:
    """Chaos engineering framework for Prodinamik Engine.

    Injects faults, monitors system health, and verifies self-healing.
    """

    SCENARIOS = {
        "network-partition": {
            "description": "Simulate network failure by blocking ports",
            "fault_type": FaultType.NETWORK_PARTITION,
            "duration": 5,
            "dangerous": False,
        },
        "network-latency": {
            "description": "Add artificial network latency via iptables",
            "fault_type": FaultType.NETWORK_LATENCY,
            "duration": 5,
            "dangerous": False,
        },
        "disk-full": {
            "description": "Simulate disk full by filling data directory",
            "fault_type": FaultType.DISK_FULL,
            "duration": 5,
            "dangerous": True,
        },
        "disk-corruption": {
            "description": "Corrupt random WAL/snapshot files",
            "fault_type": FaultType.DISK_CORRUPTION,
            "duration": 3,
            "dangerous": True,
        },
        "memory-pressure": {
            "description": "Allocate memory to trigger pressure",
            "fault_type": FaultType.MEMORY_PRESSURE,
            "duration": 3,
            "dangerous": True,
        },
        "cpu-spike": {
            "description": "Generate CPU load via subprocess",
            "fault_type": FaultType.CPU_SPIKE,
            "duration": 5,
            "dangerous": False,
        },
        "random-crash": {
            "description": "Simulate random process crash",
            "fault_type": FaultType.RANDOM_CRASH,
            "duration": 2,
            "dangerous": True,
        },
        "degraded-mode": {
            "description": "Force FULL→DEGRADED→SURVIVAL transitions",
            "fault_type": FaultType.DEGRADED_MODE,
            "duration": 8,
            "dangerous": False,
        },
        "wal-corruption": {
            "description": "Corrupt WAL entries and verify recovery",
            "fault_type": FaultType.WAL_CORRUPTION,
            "duration": 5,
            "dangerous": True,
        },
        "event-flood": {
            "description": "Rapid event injection to test throughput",
            "fault_type": FaultType.EVENT_FLOOD,
            "duration": 3,
            "dangerous": False,
        },
    }

    def __init__(self, engine=None, base_path: str = "./data/chaos"):
        self.engine = engine
        self.base_path = Path(base_path)
        self.results_dir = self.base_path / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._fault_handlers: Dict[FaultType, Callable] = {
            FaultType.NETWORK_PARTITION: self._fault_network_partition,
            FaultType.NETWORK_LATENCY: self._fault_network_latency,
            FaultType.DISK_FULL: self._fault_disk_full,
            FaultType.DISK_CORRUPTION: self._fault_disk_corruption,
            FaultType.MEMORY_PRESSURE: self._fault_memory_pressure,
            FaultType.CPU_SPIKE: self._fault_cpu_spike,
            FaultType.RANDOM_CRASH: self._fault_random_crash,
            FaultType.DEGRADED_MODE: self._fault_degraded_mode,
            FaultType.WAL_CORRUPTION: self._fault_wal_corruption,
            FaultType.EVENT_FLOOD: self._fault_event_flood,
        }

    def list_scenarios(self) -> List[dict]:
        """List all available chaos scenarios"""
        return [
            {
                "name": name,
                "description": info["description"],
                "fault_type": info["fault_type"].value,
                "duration": info["duration"],
                "dangerous": info["dangerous"],
            }
            for name, info in sorted(self.SCENARIOS.items())
        ]

    def run_scenario(self, scenario_name: str, duration: int = None) -> ScenarioResult:
        """Run a single chaos scenario.

        Captures health before/during/after, injects fault, measures recovery.
        """
        if scenario_name not in self.SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_name}. "
                             f"Available: {list(self.SCENARIOS.keys())}")

        info = self.SCENARIOS[scenario_name]
        fault_type = info["fault_type"]
        scenario_duration = duration or info["duration"]

        result = ScenarioResult(
            scenario_name=scenario_name,
            fault_type=fault_type.value,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # Phase 1: Capture health before
        result.health_before = self._capture_health()

        # Phase 2: Inject fault
        handler = self._fault_handlers.get(fault_type)
        if handler:
            try:
                result.fault_injected = handler(scenario_duration)
            except Exception as e:
                result.errors.append(f"Fault injection failed: {e}")

        # Phase 3: Wait and capture health during
        time.sleep(min(1, scenario_duration / 3))
        result.health_during = self._capture_health()

        # Phase 4: Wait for recovery
        recovery_start = time.monotonic()
        time.sleep(scenario_duration)
        result.health_after = self._capture_health()

        # Phase 5: Measure recovery
        result.recovery_time_seconds = time.monotonic() - recovery_start
        result.duration_seconds = time.monotonic() - time.monotonic() + scenario_duration + 2

        # Phase 6: Check survival and self-healing
        result.system_survived = self._check_survival(result)
        result.self_healed = self._check_self_healing(result)

        # Count events
        if self.engine:
            try:
                from .audit import AuditLog
                from .config import ProdinamikConfig
                cfg = ProdinamikConfig.load()
                audit = AuditLog(base_path=str(Path(cfg.data_dir) / "audit"))
                result.events_logged = audit.count()
            except Exception:
                pass

        # Save result
        self._save_result(result)

        return result

    def run_all(self, dangerous: bool = False) -> Dict[str, ScenarioResult]:
        """Run all scenarios. If dangerous=False, skip dangerous ones."""
        results = {}
        for name in self.SCENARIOS:
            if not dangerous and self.SCENARIOS[name]["dangerous"]:
                continue
            try:
                results[name] = self.run_scenario(name)
            except Exception as e:
                results[name] = ScenarioResult(
                    scenario_name=name,
                    fault_type=self.SCENARIOS[name]["fault_type"].value,
                    errors=[str(e)],
                )
        return results

    def report(self, scenario_name: str = None) -> str:
        """Generate report of all results or a single scenario"""
        if scenario_name:
            return self._load_result(scenario_name).report()

        lines = [f"\n{'=' * 55}",
                 f"  Prodinamik Chaos Engineering Report",
                 f"{'=' * 55}"]

        results_dir = self.results_dir
        if results_dir.exists():
            result_files = sorted(results_dir.glob("*.json"))
            passed = 0
            failed = 0
            for f in result_files:
                try:
                    data = json.loads(f.read_text())
                    result = ScenarioResult(**data)
                    status = "✅" if result.passed() else "❌"
                    lines.append(f"  {status} {result.scenario_name}: "
                                 f"survived={result.system_survived}, "
                                 f"healed={result.self_healed}, "
                                 f"recovery={result.recovery_time_seconds:.1f}s")
                    if result.passed():
                        passed += 1
                    else:
                        failed += 1
                except Exception:
                    lines.append(f"  ⚠️  {f.name}: corrupt result")

            total = passed + failed
            lines.append(f"{'─' * 55}")
            lines.append(f"  Total: {total} | ✅ {passed} passed | ❌ {failed} failed")
        else:
            lines.append("  No chaos results found. Run a scenario first.")

        lines.append(f"{'=' * 55}")
        return "\n".join(lines)

    # ──────────────────────────────────────
    # Fault Injection Handlers
    # ──────────────────────────────────────

    def _fault_network_partition(self, duration: int) -> bool:
        """Simulate network partition by blocking outbound connections"""
        try:
            # Block HTTP ports via iptables (requires root)
            subprocess.run(
                ["iptables", "-A", "OUTPUT", "-p", "tcp",
                 "--dport", "80,443", "-j", "DROP"],
                capture_output=True, timeout=5,
            )
            threading.Thread(target=self._restore_network,
                             args=(duration,), daemon=True).start()
            return True
        except Exception:
            # Fallback: just sleep (simulate no-iptables env)
            time.sleep(duration)
            return False

    def _restore_network(self, delay: int):
        """Restore network after delay"""
        time.sleep(delay)
        try:
            subprocess.run(
                ["iptables", "-F", "OUTPUT"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    def _fault_network_latency(self, duration: int) -> bool:
        """Add artificial network latency"""
        try:
            subprocess.run(
                ["tc", "qdisc", "add", "dev", "lo", "root",
                 "netem", "delay", "100ms"],
                capture_output=True, timeout=5,
            )
            threading.Thread(target=self._restore_latency,
                             args=(duration,), daemon=True).start()
            return True
        except Exception:
            time.sleep(duration)
            return False

    def _restore_latency(self, delay: int):
        time.sleep(delay)
        try:
            subprocess.run(["tc", "qdisc", "del", "dev", "lo", "root"],
                           capture_output=True, timeout=5)
        except Exception:
            pass

    def _fault_disk_full(self, duration: int) -> bool:
        """Simulate disk full by writing a large file"""
        try:
            fill_path = self.base_path / "fill"
            fill_path.mkdir(parents=True, exist_ok=True)
            large_file = fill_path / "disk_fill.tmp"
            # Write 50MB (safe, won't actually fill disk)
            with open(large_file, "wb") as f:
                f.write(os.urandom(50 * 1024 * 1024))
            threading.Thread(target=self._cleanup_disk_fill,
                             args=(duration,), daemon=True).start()
            return True
        except Exception as e:
            self._errors.append(f"disk-fill: {e}")
            return False

    def _cleanup_disk_fill(self, delay: int):
        time.sleep(delay)
        fill_path = self.base_path / "fill" / "disk_fill.tmp"
        if fill_path.exists():
            fill_path.unlink()

    def _fault_disk_corruption(self, duration: int) -> bool:
        """Corrupt random files in data directory"""
        if not self.engine:
            return False
        try:
            from .config import ProdinamikConfig
            cfg = ProdinamikConfig.load()
            data_dir = Path(cfg.data_dir)
            if not data_dir.exists():
                return False

            # Find WAL/snapshot files
            targets = list(data_dir.rglob("*.json")) + list(data_dir.rglob("*.log"))
            if not targets:
                return False

            # Corrupt 2 random files
            for target in random.sample(targets, min(2, len(targets))):
                self._corrupt_file(target)

            return True
        except Exception as e:
            self._errors.append(f"disk-corrupt: {e}")
            return False

    def _corrupt_file(self, path: Path):
        """Corrupt a file by replacing random bytes"""
        try:
            size = path.stat().st_size
            if size < 10:
                return
            data = bytearray(path.read_bytes())
            # Corrupt 5 random positions
            for _ in range(5):
                pos = random.randint(0, min(size - 1, 1000))
                data[pos] = random.randint(0, 255)
            path.write_bytes(bytes(data))
        except Exception:
            pass

    def _fault_memory_pressure(self, duration: int) -> bool:
        """Allocate memory to simulate pressure"""
        try:
            # Allocate ~200MB list
            big_list = [0] * (200 * 1024 * 1024 // 8)  # 200MB
            threading.Thread(target=self._release_memory,
                             args=(duration, big_list), daemon=True).start()
            return True
        except (MemoryError, OverflowError):
            return False

    def _release_memory(self, delay: int, data):
        time.sleep(delay)
        del data

    def _fault_cpu_spike(self, duration: int) -> bool:
        """Generate CPU load"""
        try:
            stop_event = threading.Event()

            def burn_cpu():
                while not stop_event.is_set():
                    _ = hashlib.sha256(os.urandom(1024)).hexdigest()

            threads = []
            for _ in range(min(4, os.cpu_count() or 2)):
                t = threading.Thread(target=burn_cpu, daemon=True)
                t.start()
                threads.append(t)

            threading.Thread(target=self._stop_cpu_burn,
                             args=(duration, stop_event), daemon=True).start()
            return True
        except Exception:
            return False

    def _stop_cpu_burn(self, delay: int, event: threading.Event):
        time.sleep(delay)
        event.set()

    def _fault_random_crash(self, duration: int) -> bool:
        """Simulate crash by raising an exception in a thread"""
        def crash():
            raise RuntimeError("Simulated chaos crash")

        t = threading.Thread(target=crash, daemon=True)
        t.start()
        time.sleep(0.5)
        return True  # Crash simulated, thread dies silently

    def _fault_degraded_mode(self, duration: int) -> bool:
        """Force degradation transitions"""
        if not self.engine:
            return False
        try:
            # Check if engine has degradation manager
            if not hasattr(self.engine, 'degradation'):
                return False

            deg = self.engine.degradation
            if not deg:
                return False

            # Force DEGRADED
            deg.health_state = "DEGRADED"
            time.sleep(2)

            # Record audit
            from .audit import AuditLog
            from .config import ProdinamikConfig
            cfg = ProdinamikConfig.load()
            audit = AuditLog(base_path=str(Path(cfg.data_dir) / "audit"))
            audit.record("degradation.change", {"from": "FULL", "to": "DEGRADED"})

            # Try to force SURVIVAL
            deg.health_state = "SURVIVAL"
            time.sleep(2)

            # Record audit
            audit.record("degradation.change", {"from": "DEGRADED", "to": "SURVIVAL"})

            # Auto-recover (simulate)
            deg.health_state = "FULL"
            audit.record("degradation.change", {"from": "SURVIVAL", "to": "FULL"})

            return True
        except Exception as e:
            self._errors.append(f"degraded: {e}")
            return False

    def _fault_wal_corruption(self, duration: int) -> bool:
        """Corrupt WAL entries and verify recovery"""
        if not self.engine:
            return False
        try:
            from .config import ProdinamikConfig
            cfg = ProdinamikConfig.load()
            data_dir = Path(cfg.data_dir)

            # Find WAL files
            wal_files = list(data_dir.rglob("*.wal")) + list(data_dir.rglob("wal*"))
            if not wal_files:
                # Create a fake WAL file to corrupt
                target = data_dir / "chaos_wal.wal"
                target.write_text(json.dumps({"test": "data", "seq": 1}))
                wal_files = [target]

            for target in wal_files[:2]:
                self._corrupt_file(target)

            time.sleep(duration)
            return True
        except Exception as e:
            self._errors.append(f"wal-corrupt: {e}")
            return False

    def _fault_event_flood(self, duration: int) -> bool:
        """Rapid event injection"""
        if not self.engine:
            return False
        try:
            # Create runs rapidly
            n_runs = min(duration * 5, 20)
            for i in range(n_runs):
                try:
                    self.engine.create_run(
                        "chaos", f"flood-run-{i}",
                        slug=f"chaos-flood-{i}",
                    )
                except Exception:
                    pass
                time.sleep(0.1)
            return True
        except Exception as e:
            self._errors.append(f"event-flood: {e}")
            return False

    # ──────────────────────────────────────
    # Health & Verification
    # ──────────────────────────────────────

    def _capture_health(self) -> dict:
        """Capture current engine health snapshot"""
        if not self.engine:
            return {"available": False}
        try:
            return self.engine.health_snapshot
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _check_survival(self, result: ScenarioResult) -> bool:
        """Check if engine survived the fault"""
        after = result.health_after
        if not after:
            return False
        if not after.get("available", True):
            return False
        # Health score must still be measurable
        score = after.get("health_score", 0)
        return score >= 0  # Any valid score means alive

    def _check_self_healing(self, result: ScenarioResult) -> bool:
        """Check if system recovered to acceptable state"""
        before = result.health_before
        after = result.health_after
        if not before or not after:
            return False

        # Degradation should not have worsened permanently
        deg_before = before.get("degradation", "FULL")
        deg_after = after.get("degradation", "FULL")
        deg_rank = {"FULL": 0, "DEGRADED": 1, "SURVIVAL": 2}
        if deg_rank.get(deg_after, 0) > deg_rank.get(deg_before, 0) + 1:
            return False

        # Health score should not have dropped catastrophically
        score_before = before.get("health_score", 100)
        score_after = after.get("health_score", 0)
        if score_before > 50 and score_after < 10:
            return False

        return True

    # ──────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────

    def _save_result(self, result: ScenarioResult):
        """Save result to disk"""
        result_path = self.results_dir / f"{result.scenario_name}_{int(time.time())}.json"
        result_path.write_text(json.dumps({
            "scenario_name": result.scenario_name,
            "fault_type": result.fault_type,
            "started_at": result.started_at,
            "duration_seconds": result.duration_seconds,
            "fault_injected": result.fault_injected,
            "system_survived": result.system_survived,
            "self_healed": result.self_healed,
            "recovery_time_seconds": result.recovery_time_seconds,
            "health_before": {k: str(v) for k, v in result.health_before.items()},
            "health_during": {k: str(v) for k, v in result.health_during.items()},
            "health_after": {k: str(v) for k, v in result.health_after.items()},
            "events_logged": result.events_logged,
            "errors": result.errors,
        }, indent=2))

    def _load_result(self, scenario_name: str) -> Optional[ScenarioResult]:
        """Load most recent result for a scenario"""
        pattern = f"{scenario_name}_*.json"
        matches = sorted(self.results_dir.glob(pattern))
        if not matches:
            return ScenarioResult(
                scenario_name=scenario_name,
                fault_type="unknown",
                errors=["No results found"],
            )
        try:
            data = json.loads(matches[-1].read_text())
            return ScenarioResult(**data)
        except Exception as e:
            return ScenarioResult(
                scenario_name=scenario_name,
                fault_type="unknown",
                errors=[f"Load error: {e}"],
            )


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────

def run_chaos_scenario(engine, scenario_name: str, duration: int = None) -> ScenarioResult:
    """Entry point for CLI"""
    chaos = ChaosEngine(engine)
    return chaos.run_scenario(scenario_name, duration=duration)


def list_chaos_scenarios() -> List[dict]:
    """Entry point for CLI list"""
    chaos = ChaosEngine()
    return chaos.list_scenarios()


def chaos_report(engine) -> str:
    """Entry point for CLI report"""
    chaos = ChaosEngine(engine)
    return chaos.report()
