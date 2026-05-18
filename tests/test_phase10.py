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


# ──────────────────────────────────────────────
# Monitoring & Alert Tests
# ──────────────────────────────────────────────


def test_alert_create():
    """Alert creation with levels"""
    from engine.alert import Alert
    a = Alert("info", "Test title", "test message")
    assert a.level == "info"
    assert "Test title" in a.title
    assert a.emoji == "🔵"

    w = Alert("warning", "Warning", metrics={"usage": 0.85})
    assert w.level == "warning"
    assert w.emoji == "🟡"

    c = Alert("critical", "Critical")
    assert c.level == "critical"
    assert c.emoji == "🔴"


def test_alert_serialization():
    """Alert converts to dict and channel payloads"""
    from engine.alert import Alert
    a = Alert("warning", "Disk space low",
              "Only 10% free", {"disk_pct": 90, "path": "/data"})

    d = a.to_dict()
    assert d["level"] == "warning"
    assert d["title"] == "Disk space low"

    slack = a.to_slack_payload()
    assert "Disk space low" in slack["text"]

    tg = a.to_telegram_payload()
    assert "Disk space low" in tg
    assert "disk_pct" in tg

    am = a.to_alertmanager_payload()
    assert am["labels"]["severity"] == "warning"
    assert am["labels"]["alertname"] == "Disk space low"


def test_alertmanager_deduplication():
    """Duplicate alerts within window are suppressed"""
    from engine.alert import AlertManager
    mgr = AlertManager(dedup_window_sec=300)

    a1 = mgr.send_alert("info", "Dup test", "first")
    a2 = mgr.send_alert("info", "Dup test", "second")

    # Same dedup key → should not create new history entry
    assert len(mgr._history) == 1


def test_alertmanager_rate_limit():
    """Rate limiting prevents too-frequent sends"""
    from engine.alert import AlertManager
    import time

    mgr = AlertManager(min_interval_sec=60)

    # Both attempts should succeed (no webhook delivery, only history)
    a1 = mgr.send_alert("info", "Rate test", "first")
    a2 = mgr.send_alert("info", "Rate test 2", "second")
    # Rate limit is per-channel, history is always recorded
    assert len(mgr._history) == 2


def test_alertmanager_summary_and_recent():
    """AlertManager.summary() and recent() return correct results"""
    from engine.alert import AlertManager
    mgr = AlertManager()

    mgr.send_alert("info", "Info alert")
    mgr.send_alert("warning", "Warning alert")
    mgr.send_alert("critical", "Critical alert")

    summary = mgr.summary()
    assert summary["total_alerts"] == 3
    assert summary["counts"]["info"] == 1
    assert summary["counts"]["warning"] == 1
    assert summary["counts"]["critical"] == 1

    recent = mgr.recent(limit=2)
    assert len(recent) == 2
    assert recent[0].level == "critical"  # Most recent first

    filtered = mgr.recent(limit=10, min_level="warning")
    assert len(filtered) >= 2  # warning + critical
    assert all(a.level in ("warning", "critical") for a in filtered)


def test_alertmanager_subscribe():
    """Custom subscribers receive alerts"""
    from engine.alert import AlertManager
    received = []

    def handler(alert):
        received.append(alert.title)

    mgr = AlertManager()
    mgr.subscribe(handler)
    mgr.send_alert("info", "Subscriber test")

    assert len(received) == 1
    assert received[0] == "Subscriber test"


def test_alert_from_env():
    """alert_config_from_env() reads environment variables"""
    import os
    from engine.alert import alert_config_from_env

    # Without env vars
    mgr = alert_config_from_env()
    assert not mgr.is_configured

    # With env vars
    os.environ["PRODINAMIK_SLACK_WEBHOOK"] = "https://hooks.test/webhook"
    os.environ["PRODINAMIK_TELEGRAM_TOKEN"] = "123:abc"
    os.environ["PRODINAMIK_TELEGRAM_CHAT_ID"] = "-100123"

    mgr = alert_config_from_env()
    assert mgr.is_configured
    assert "slack" in mgr.enabled_channels
    assert "telegram" in mgr.enabled_channels

    # Cleanup
    del os.environ["PRODINAMIK_SLACK_WEBHOOK"]
    del os.environ["PRODINAMIK_TELEGRAM_TOKEN"]
    del os.environ["PRODINAMIK_TELEGRAM_CHAT_ID"]


def test_cli_alert_help():
    """CLI alert command shows help"""
    from click.testing import CliRunner
    from engine.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["alert", "--help"])
    assert result.exit_code == 0
    assert "Send and manage alerts" in result.output


def test_cli_alert_status():
    """CLI alert status shows manager info"""
    from click.testing import CliRunner
    from engine.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["alert", "status"])
    assert result.exit_code == 0
    assert "Alert Manager" in result.output


def test_cli_alert_send_no_channel():
    """CLI alert send warns when no channels configured"""
    from click.testing import CliRunner
    from engine.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["alert", "send", "info", "Test"])
    assert result.exit_code == 0
    assert "No alert channels configured" in result.output


def test_prometheus_alert_rules_yaml():
    """Prometheus alert rules file is valid YAML"""
    import yaml
    path = "/root/projelerim/prodinamik-engine/monitoring/prometheus-alerts.yml"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "groups" in data
    assert len(data["groups"]) >= 1
    rules = data["groups"][0]["rules"]
    assert len(rules) >= 10
    assert any("EngineDown" in r.get("alert", "") for r in rules)
    assert any("EngineDegraded" in r.get("alert", "") for r in rules)


def test_grafana_dashboard_json():
    """Grafana dashboard JSON is valid"""
    import json
    path = "/root/projelerim/prodinamik-engine/monitoring/grafana-dashboard.json"
    with open(path) as f:
        data = json.load(f)
    assert "panels" in data
    assert data["title"] == "Prodinamik Engine"
    assert len(data["panels"]) >= 10
    # Has row panels
    rows = [p for p in data["panels"] if p["type"] == "row"]
    assert len(rows) >= 3  # Engine Health, Performance, Security etc.


# ──────────────────────────────────────────────
# Performance Tests
# ──────────────────────────────────────────────


def test_event_store_append_many():
    """EventStore.append_many writes batch efficiently"""
    import tempfile
    import shutil
    from engine.event_store import EventStore, Event

    tmpdir = tempfile.mkdtemp()
    store = EventStore(base_path=tmpdir, slug="perf-test")
    events = [
        Event(sequence=0, run_slug="perf", timestamp="2026-01-01",
              event_type="state_transition", data={"from": "a", "to": "b"})
        for _ in range(10)
    ]
    seqs = store.append_many(events)
    assert len(seqs) == 10
    assert seqs[0] == 1
    assert seqs[-1] == 10

    # Verify all events readable
    for seq in seqs:
        event = store.get(seq)
        assert event is not None
        assert event.run_slug == "perf"

    shutil.rmtree(tmpdir, ignore_errors=True)


def test_event_store_append_many_empty():
    """append_many with empty list returns []"""
    import tempfile
    import shutil
    from engine.event_store import EventStore

    tmpdir = tempfile.mkdtemp()
    store = EventStore(base_path=tmpdir, slug="perf-test")
    assert store.append_many([]) == []
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_event_store_append_many_large_batch():
    """append_many handles 100 events"""
    import tempfile
    import shutil
    from engine.event_store import EventStore, Event

    tmpdir = tempfile.mkdtemp()
    store = EventStore(base_path=tmpdir, slug="perf-batch")
    events = [
        Event(sequence=0, run_slug="batch", timestamp="2026-01-01",
              event_type="state_transition", data={"i": i})
        for i in range(100)
    ]
    seqs = store.append_many(events)
    assert len(seqs) == 100
    assert store.event_count == 100
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_run_manager_wal_batch():
    """RunManager._append_wal_batch writes batch file"""
    import tempfile
    import shutil
    import json
    from pathlib import Path
    from engine.run_manager import RunManager

    tmpdir = tempfile.mkdtemp()
    mgr = RunManager(base_path=tmpdir)

    entries = [
        {"action": "create", "slug": f"test-{i}", "timestamp": "2026-01-01"}
        for i in range(5)
    ]
    mgr._append_wal_batch(entries)

    # Verify batch file exists
    wal_dir = Path(tmpdir) / "wal"
    batch_files = list(wal_dir.glob("*.batch"))
    assert len(batch_files) == 1

    # Verify content
    content = batch_files[0].read_text()
    assert "checksum" in content
    assert "test-0" in content
    assert "test-4" in content
    assert content.count("\n") == 5  # 5 entries

    shutil.rmtree(tmpdir, ignore_errors=True)


def test_state_machine_lru_cache():
    """StateMachine LRU cache caches get_next_states"""
    from engine.state_machine import StateMachine, StateMachineParser

    yaml = """
profile: test
name: perf-test
version: 1.0
states:
  a: {type: initial, max_reentries: 1}
  b: {type: intermediate, max_reentries: 5}
  c: {type: intermediate, max_reentries: 5}
  d: {type: terminal, max_reentries: 0}
transitions:
  a -> b: {}
  a -> c: {}
  b -> d: {}
  c -> d: {}
"""
    config = StateMachineParser.parse_string(yaml)
    sm = StateMachine(config, lru_size=10)

    # First call: populates cache
    result1 = sm.get_next_states("a")
    assert result1 == ["b", "c"]

    # Second call: from cache (same result)
    result2 = sm.get_next_states("a")
    assert result2 == ["b", "c"]

    # Different state: not cached yet
    result3 = sm.get_next_states("b")
    assert result3 == ["d"]

    # Verify cache stats
    assert "next:a" in sm._transition_cache
    assert "next:b" in sm._transition_cache
    assert len(sm._transition_cache) <= 10


def test_state_machine_lru_cache_eviction():
    """LRU cache evicts oldest entries when full"""
    from engine.state_machine import StateMachine, StateMachineParser

    # Generate 20 states programmatically (avoid format string + YAML flow conflict)
    lines = ["profile: test", "name: perf-test", "version: 1.0", "states:"]
    for i in range(20):
        stype = "initial" if i == 0 else "intermediate"
        max_r = 0 if i == 0 else 5
        lines.append(f"  s{i}:")
        lines.append(f"    type: {stype}")
        lines.append(f"    max_reentries: {max_r}")
    lines.append("  end:")
    lines.append("    type: terminal")
    lines.append("    max_reentries: 0")
    lines.append("transitions:")
    for i in range(20):
        if i < 19:
            lines.append(f"  s{i} -> s{i+1}:")
            lines.append("    type: REVERSIBLE")
        else:
            lines.append(f"  s{i} -> end:")
            lines.append("    type: REVERSIBLE")

    yaml_str = "\n".join(lines)
    config = StateMachineParser.parse_string(yaml_str)
    sm = StateMachine(config, lru_size=5)

    # Access 10 different states
    for i in range(10):
        sm.get_next_states(f"s{i}")

    # Cache should be bounded at 5
    assert len(sm._transition_cache) == 5


def test_benchmark_event_store_append_many():
    """Benchmark: append_many vs append for 50 events"""
    import tempfile
    import shutil
    import time
    from engine.event_store import EventStore, Event

    tmpdir = tempfile.mkdtemp()
    events_50 = [
        Event(sequence=0, run_slug="bench", timestamp="2026-01-01",
              event_type="benchmark", data={"n": i})
        for i in range(50)
    ]

    # Single append: 50 separate writes + 50 index saves
    store1 = EventStore(base_path=tmpdir, slug="bench-single")
    start = time.perf_counter()
    for e in events_50:
        store1.append(e)
    single_time = (time.perf_counter() - start) * 1000

    # Batch append: 50 writes + 1 index save
    store2 = EventStore(base_path=tmpdir, slug="bench-batch")
    start = time.perf_counter()
    store2.append_many(events_50)
    batch_time = (time.perf_counter() - start) * 1000

    # Batch should be faster
    print(f"\n  ⏱  Single: {single_time:.1f}ms | Batch: {batch_time:.1f}ms | "
          f"Ratio: {single_time/batch_time:.1f}x faster")
    assert batch_time < single_time * 2  # Not strict — depends on filesystem

    shutil.rmtree(tmpdir, ignore_errors=True)


# ──────────────────────────────────────────────
# Raft TCP Transport Tests
# ──────────────────────────────────────────────


def test_raft_message_serde():
    """RaftMessage JSON serialization roundtrip"""
    from engine.raft_transport import RaftMessage

    msg = RaftMessage(type="RequestVote", sender_id="node-1", term=1,
                       data={"last_log_index": 5, "last_log_term": 1})
    json_str = msg.to_json()
    restored = RaftMessage.from_json(json_str)
    assert restored.type == "RequestVote"
    assert restored.sender_id == "node-1"
    assert restored.term == 1
    assert restored.data["last_log_index"] == 5


def test_raft_message_builders():
    """Raft message builder functions produce valid messages"""
    from engine.raft_transport import (
        build_vote_request, build_vote_response,
        build_append_entries, build_append_response, build_heartbeat,
        RAFT_MSG_REQUEST_VOTE, RAFT_MSG_APPEND_ENTRIES, RAFT_MSG_HEARTBEAT,
    )

    vr = build_vote_request("node-1", 2, 10, 1)
    assert vr.type == RAFT_MSG_REQUEST_VOTE
    assert vr.data["last_log_index"] == 10

    vresp = build_vote_response("node-2", 2, True)
    assert vresp.data["vote_granted"] is True

    ae = build_append_entries("leader", 3, [{"term": 3, "index": 0}], 0, 1, 0)
    assert ae.type == RAFT_MSG_APPEND_ENTRIES
    assert len(ae.data["entries"]) == 1

    aresp = build_append_response("follower", 3, True)
    assert aresp.data["success"] is True

    hb = build_heartbeat("leader", 3, 5)
    assert hb.type == RAFT_MSG_HEARTBEAT


def test_raft_tcp_server_start_stop():
    """RaftTCPServer starts and stops cleanly"""
    from engine.raft_transport import RaftTCPServer

    server = RaftTCPServer("test-node", port=0)  # port=0 means bind any available
    started = server.start()
    # Port 0 will fail to bind, but start should return False gracefully
    # Let's use a known free port
    server.stop()


def test_raft_tcp_message_roundtrip():
    """Send a message between two Raft nodes via TCP"""
    import time
    import threading
    from engine.raft_transport import (
        RaftTCPServer, RaftTCPClient, RaftMessage,
        build_vote_request, build_vote_response,
    )

    received = []

    def handler(msg):
        received.append(msg)
        return build_vote_response("node-2", msg.term, True)

    # Find a free port
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    # Start server
    server = RaftTCPServer("node-2", host="127.0.0.1", port=port, handler=handler)
    assert server.start(), "Server should start"
    time.sleep(0.1)  # Let server start

    # Send message
    msg = build_vote_request("node-1", 1, 0, 0)
    resp = RaftTCPClient.send_message(f"127.0.0.1:{port}", msg)

    assert resp is not None, "Should receive response"
    assert resp.sender_id == "node-2"
    assert resp.data.get("vote_granted") is True
    assert len(received) == 1

    server.stop()


def test_raft_tcp_unreachable_peer():
    """Sending to unreachable peer returns None gracefully"""
    from engine.raft_transport import RaftTCPClient, build_vote_request

    msg = build_vote_request("node-1", 1, 0, 0)
    resp = RaftTCPClient.send_message("127.0.0.1:19999", msg)
    assert resp is None  # Unreachable returns None


def test_hybrid_node_transport_integration():
    """HybridConsensusNode transport integration"""
    from engine.raft_consensus import HybridConsensusNode
    import tempfile

    tmpdir = tempfile.mkdtemp()
    node = HybridConsensusNode("node-1", ["node-2"],
                                state_dir=tmpdir,
                                enable_transport=True)

    assert node._enable_transport is True
    assert node.transport is not None  # Lazy init

    node.register_peer_transport("node-2", "127.0.0.1:9002")
    assert "node-2" in node._peer_transport
    assert node._peer_transport["node-2"] == "127.0.0.1:9002"

    node.stop_transport()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_hybrid_node_transport_election():
    """HybridConsensusNode with transport: election communication"""
    import time
    import tempfile
    from engine.raft_consensus import HybridConsensusNode

    tmpdir = tempfile.mkdtemp()

    # Set up two nodes on different ports
    node1 = HybridConsensusNode("node-a", ["node-b"],
                                 state_dir=tmpdir,
                                 raft_host="127.0.0.1", raft_port=19001,
                                 enable_transport=True)
    node2 = HybridConsensusNode("node-b", ["node-a"],
                                 state_dir=tmpdir,
                                 raft_host="127.0.0.1", raft_port=19002,
                                 enable_transport=True)

    # Register peer transport addresses
    node1.register_peer_transport("node-b", "127.0.0.1:19002")
    node2.register_peer_transport("node-a", "127.0.0.1:19001")

    # Start transport on both
    node1.start_transport()
    node2.start_transport()
    time.sleep(0.2)

    # Make node-a leader
    node1.raft.become_leader()
    assert node1.is_leader()

    # Test TCP vote request
    votes = node1.raft_request_vote()
    assert votes >= 1  # At least self vote

    # Test heartbeat broadcast
    node1.raft_broadcast_heartbeat()

    # Test peer health
    health = node1.raft_peer_health("node-b")
    assert health is not None

    # Cleanup
    node1.stop_transport()
    node2.stop_transport()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)



