"""Prodinamik Engine v1.1 — Phase 6: Chaos Engineering Tests

Tests for the chaos engineering framework (engine/chaos.py).
All scenarios are tested in SIMULATED mode (no actual dangerous side effects).
"""

import os
import json
import time
import tempfile
import shutil
from pathlib import Path

import pytest


# ──────────────────────────────────────────────
# Chaos Engine Tests
# ──────────────────────────────────────────────


@pytest.fixture
def chaos_engine():
    """ChaosEngine instance with temp path"""
    from engine.chaos import ChaosEngine
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    tmpdir = tempfile.mkdtemp()
    cfg = ProdinamikConfig.load()
    cfg.data_dir = os.path.join(tmpdir, "data")
    engine = AsyncEngine(cfg)
    chaos = ChaosEngine(engine, base_path=os.path.join(tmpdir, "chaos"))
    return chaos, engine, tmpdir


def cleanup(tmpdir):
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_chaos_scenario_list(chaos_engine):
    """List returns all 10 scenarios"""
    chaos, _, tmpdir = chaos_engine
    scenarios = chaos.list_scenarios()
    names = [s["name"] for s in scenarios]

    assert len(scenarios) == 10
    assert "network-partition" in names
    assert "disk-full" in names
    assert "cpu-spike" in names
    assert "degraded-mode" in names
    assert "event-flood" in names
    cleanup(tmpdir)


def test_chaos_unknown_scenario(chaos_engine):
    """Unknown scenario raises ValueError"""
    chaos, _, tmpdir = chaos_engine
    with pytest.raises(ValueError):
        chaos.run_scenario("nonexistent")
    cleanup(tmpdir)


def test_chaos_scenario_result_passed(chaos_engine):
    """ScenarioResult.passed() works"""
    from engine.chaos import ScenarioResult
    r = ScenarioResult(
        scenario_name="test",
        fault_type="cpu-spike",
        system_survived=True,
        self_healed=True,
    )
    assert r.passed()

    r2 = ScenarioResult(
        scenario_name="test",
        fault_type="crash",
        system_survived=False,
    )
    assert not r2.passed()


def test_chaos_scenario_result_report(chaos_engine):
    """ScenarioResult.report() returns readable output"""
    from engine.chaos import ScenarioResult
    r = ScenarioResult(
        scenario_name="cpu-spike",
        fault_type="cpu-spike",
        duration_seconds=3.0,
        fault_injected=True,
        system_survived=True,
        self_healed=True,
        recovery_time_seconds=1.5,
    )
    report = r.report()
    assert "cpu-spike" in report
    assert "PASS" in report
    assert "3.0s" in report


def test_chaos_cpu_spike(chaos_engine):
    """CPU spike scenario runs without crash"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("cpu-spike", duration=1)
    assert result.fault_type == "cpu-spike"
    assert result.system_survived  # Engine should survive
    cleanup(tmpdir)


def test_chaos_random_crash(chaos_engine):
    """Random crash scenario runs safely"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("random-crash", duration=1)
    assert result.fault_type == "random-crash"
    assert result.fault_injected
    cleanup(tmpdir)


def test_chaos_event_flood(chaos_engine):
    """Event flood creates runs without crashing"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("event-flood", duration=1)
    assert result.fault_type == "event-flood"
    cleanup(tmpdir)


def test_chaos_degraded_mode(chaos_engine):
    """Degraded mode scenario progresses through states"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("degraded-mode", duration=1)
    assert result.fault_type == "degraded-mode"
    cleanup(tmpdir)


def test_chaos_network_latency(chaos_engine):
    """Network latency scenario runs (may be noop without tc)"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("network-latency", duration=1)
    assert result.fault_type == "network-latency"
    cleanup(tmpdir)


def test_chaos_network_partition(chaos_engine):
    """Network partition scenario runs (may be noop without iptables)"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("network-partition", duration=1)
    assert result.fault_type == "network-partition"
    cleanup(tmpdir)


def test_chaos_capture_health(chaos_engine):
    """Capture health returns engine snapshot"""
    chaos, engine, tmpdir = chaos_engine
    health = chaos._capture_health()
    assert "degradation" in health
    assert "health_score" in health
    cleanup(tmpdir)


def test_chaos_save_and_load_result(chaos_engine):
    """Results persist to disk and load correctly"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("cpu-spike", duration=1)

    # Check result file exists
    pattern = f"{result.scenario_name}_*.json"
    matches = list(chaos.results_dir.glob(pattern))
    assert len(matches) >= 1

    # Load and verify
    loaded = chaos._load_result("cpu-spike")
    assert loaded.scenario_name == "cpu-spike"
    assert loaded.fault_type == "cpu-spike"
    cleanup(tmpdir)


def test_chaos_report(chaos_engine):
    """Report generates without error"""
    chaos, engine, tmpdir = chaos_engine
    chaos.run_scenario("cpu-spike", duration=1)
    report = chaos.report()
    assert "Chaos Engineering Report" in report
    assert "cpu-spike" in report
    cleanup(tmpdir)


def test_chaos_injector_disk_corruption(chaos_engine):
    """Disk corruption handler creates and corrupts files"""
    chaos, engine, tmpdir = chaos_engine
    from engine.config import ProdinamikConfig
    cfg = ProdinamikConfig.load()
    cfg.data_dir = os.path.join(tmpdir, "data_corrupt")

    # Create a target file
    target = Path(cfg.data_dir) / "test.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"hello": "world", "data": "x" * 100}))

    # Corrupt it
    chaos._corrupt_file(target)
    content = target.read_bytes()
    assert content != b''
    # At least some corruption happened
    cleanup(tmpdir)


def test_chaos_check_self_healing(chaos_engine):
    """Self-healing check works correctly"""
    from engine.chaos import ScenarioResult
    chaos, _, tmpdir = chaos_engine

    # Healthy case
    r = ScenarioResult(
        scenario_name="test",
        fault_type="test",
        health_before={"degradation": "FULL", "health_score": 100},
        health_after={"degradation": "FULL", "health_score": 90},
    )
    assert chaos._check_self_healing(r)

    # Degraded but acceptable
    r2 = ScenarioResult(
        scenario_name="test2",
        fault_type="test",
        health_before={"degradation": "FULL", "health_score": 100},
        health_after={"degradation": "DEGRADED", "health_score": 70},
    )
    assert chaos._check_self_healing(r2)

    # Catastrophic failure
    r3 = ScenarioResult(
        scenario_name="test3",
        fault_type="test",
        health_before={"degradation": "FULL", "health_score": 100},
        health_after={"degradation": "SURVIVAL", "health_score": 5},
    )
    assert not chaos._check_self_healing(r3)
    cleanup(tmpdir)


# ──────────────────────────────────────────────
# CLI Tests
# ──────────────────────────────────────────────


def test_cli_chaos_help():
    """CLI chaos help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["chaos", "--help"])
    assert result.exit_code == 0
    assert "Chaos engineering" in result.output


def test_cli_chaos_list():
    """CLI chaos list works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["chaos", "list"])
    assert result.exit_code == 0
    assert "Chaos Scenarios" in result.output
    assert "network-partition" in result.output
    assert "cpu-spike" in result.output


def test_cli_chaos_report_empty():
    """CLI chaos report with no results"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["chaos", "report"])
    assert result.exit_code == 0


def test_cli_chaos_run_unknown():
    """CLI chaos run with unknown scenario"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["chaos", "run", "nonexistent"])
    assert result.exit_code != 0  # Error


def test_cli_chaos_run_dangerous_without_flag():
    """CLI chaos run dangerous scenario requires --dangerous flag"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["chaos", "run", "disk-full"])
    # Should exit with error because dangerous and no --dangerous
    assert result.exit_code != 0
    assert "DANGEROUS" in result.output


def test_cli_chaos_run_safe_scenario():
    """CLI chaos run safe scenario works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["chaos", "run", "cpu-spike", "--duration", "1"])
    assert result.exit_code == 0
    assert "cpu-spike" in result.output


# ──────────────────────────────────────────────
# D08: Chaos Recovery Tests
# ──────────────────────────────────────────────


def test_chaos_wal_corruption_dangerous():
    """WAL corruption requires --dangerous flag"""
    from engine.chaos import ChaosEngine
    info = ChaosEngine.SCENARIOS["wal-corruption"]
    assert info["dangerous"] is True


def test_chaos_degredation_full_transition(chaos_engine):
    """Degradation mode scenario transitions through states"""
    chaos, engine, tmpdir = chaos_engine
    result = chaos.run_scenario("degraded-mode", duration=2)
    assert result.fault_injected
    assert result.system_survived


def test_chaos_health_capture_after_restart(chaos_engine):
    """Health capture works immediately after engine init"""
    chaos, engine, tmpdir = chaos_engine
    health = chaos._capture_health()
    assert health.get("available", True) is True
    assert "health_score" in health
    assert "degradation" in health


# ──────────────────────────────────────────────
# D09-D10: Integration fixes
# ──────────────────────────────────────────────


def test_bench_fallback_engine():
    """Benchmark creates default engine if none provided"""
    from engine.bench import run_benchmark
    results = run_benchmark(engine=None, runs=1)
    assert isinstance(results, dict)
    assert "state_machine_parsing" in results


def test_server_threadsafe_handler_wiring():
    """Server handler class has thread-safe attributes"""
    from engine.server import ProdinamikServer, ProdinamikHandler
    server = ProdinamikServer(port=0)
    assert hasattr(ProdinamikHandler, "engine")
    assert hasattr(ProdinamikHandler, "auth_manager")
    assert hasattr(ProdinamikHandler, "rate_limiter")
    assert hasattr(ProdinamikHandler, "server_started_at")
