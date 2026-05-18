"""Prodinamik Engine v1.1 — Phase 4: Observability Tests

Tests for:
- Metrics Pipeline (engine/metrics.py)
- Dashboard (engine/dashboard.py)
- Audit Log (engine/audit.py)
- CLI extensions (dashboard, metrics, audit)
"""

import os
import json
import tempfile
import shutil
from pathlib import Path

import pytest


# ──────────────────────────────────────────────
# Metrics Tests
# ──────────────────────────────────────────────


def test_counter_basic():
    """Counter increments and resets"""
    from engine.metrics import Counter
    c = Counter(name="test_counter")
    assert c.value == 0.0
    c.inc()
    assert c.value == 1.0
    c.inc(5.0)
    assert c.value == 6.0
    c.reset()
    assert c.value == 0.0


def test_gauge_basic():
    """Gauge set, inc, dec works"""
    from engine.metrics import Gauge
    g = Gauge(name="test_gauge")
    assert g.value == 0.0
    g.set(42.0)
    assert g.value == 42.0
    g.inc(10.0)
    assert g.value == 52.0
    g.dec(20.0)
    assert g.value == 32.0


def test_histogram_basic():
    """Histogram observe, count, sum, avg"""
    from engine.metrics import Histogram
    h = Histogram(name="test_hist", buckets=[1, 5, 10, 50, 100])
    h.observe(3)
    h.observe(7)
    h.observe(42)
    assert h.count == 3
    assert h.sum == 52.0
    assert h.avg == pytest.approx(17.333, rel=1e-3)


def test_metrics_registry_instance():
    """Global metrics instance exists"""
    from engine.metrics import metrics, MetricsRegistry
    assert isinstance(metrics, MetricsRegistry)


def test_metrics_registry_counter():
    """Registry counter auto-creates and tracks"""
    from engine.metrics import MetricsRegistry
    r = MetricsRegistry()
    c = r.counter("test_runs", "Test counter")
    c.inc()
    c.inc(3)
    snap = r.snapshot()
    assert snap["counters"]["counter:test_runs"] == 4.0


def test_metrics_registry_gauge():
    """Registry gauge auto-creates and tracks"""
    from engine.metrics import MetricsRegistry
    r = MetricsRegistry()
    g = r.gauge("active_items", "Active items gauge")
    g.set(5)
    g.inc()
    snap = r.snapshot()
    assert snap["gauges"]["gauge:active_items"] == 6.0


def test_metrics_registry_histogram():
    """Registry histogram auto-creates and tracks"""
    from engine.metrics import MetricsRegistry
    r = MetricsRegistry()
    h = r.histogram("latency", "Request latency")
    h.observe(10)
    h.observe(20)
    snap = r.snapshot()
    assert snap["histograms"]["histogram:latency"]["count"] == 2
    assert snap["histograms"]["histogram:latency"]["sum"] == 30.0


def test_prometheus_export():
    """Prometheus format export produces valid output"""
    from engine.metrics import MetricsRegistry
    r = MetricsRegistry()
    r.counter("runs_created").inc(5)
    r.gauge("active_runs").set(3)
    h = r.histogram("latency_ms")
    h.observe(25)
    h.observe(150)
    h.observe(500)

    output = r.render_prometheus()
    assert "# HELP" in output
    assert "# TYPE" in output
    assert "runs_created_total" in output
    assert "active_runs" in output
    assert "latency_ms_bucket" in output
    assert "latency_ms_count" in output
    assert "latency_ms_sum" in output
    # Valid Prometheus format: ends with newline, has no empty lines between metrics
    assert output.endswith("\n")


def test_engine_metrics_poll():
    """EngineMetrics polls engine without error"""
    from engine.metrics import EngineMetrics, MetricsRegistry
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)
    em = EngineMetrics(engine)
    em.poll()
    snap = em.snapshot()
    assert "metrics" in snap


# ──────────────────────────────────────────────
# Dashboard Tests
# ──────────────────────────────────────────────


def test_dashboard_basic():
    """Dashboard renders without error"""
    from engine.dashboard import Dashboard
    d = Dashboard()
    output = d.render()
    assert "Prodinamik Engine" in output
    assert "Health Dashboard" in output


def test_dashboard_compact():
    """Compact render works"""
    from engine.dashboard import Dashboard
    d = Dashboard()
    output = d.render_compact()
    assert "Prodinamik" in output


def test_dashboard_with_engine():
    """Dashboard works with attached engine"""
    from engine.dashboard import Dashboard
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)
    d = Dashboard(engine)
    output = d.render()
    assert "Thermal Map" in output
    # Run Matrix sadece aktif run varsa gösterilir; yoksa "No active runs"
    assert "Run Matrix" in output or "No active runs" in output


def test_dashboard_alerts():
    """Alert logging works"""
    from engine.dashboard import Dashboard
    d = Dashboard()
    d.log_alert("info", "System started")
    d.log_alert("warning", "Budget near limit")
    d.log_alert("error", "Degradation triggered")
    output = d.render()
    assert "System started" in output
    assert "Budget near limit" in output
    assert "Degradation triggered" in output


def test_dashboard_thermal_bar():
    """Thermal bar renders correctly"""
    from engine.dashboard import Dashboard
    d = Dashboard()
    bar_full = d._thermal_bar(1.0, width=10)
    assert "█" * 10 in bar_full
    bar_empty = d._thermal_bar(0.0, width=10)
    assert "░" * 10 in bar_empty
    bar_half = d._thermal_bar(0.5, width=10)
    assert "█" * 5 in bar_half
    assert "░" * 5 in bar_half


def test_html_dashboard():
    """HTML dashboard generates valid HTML"""
    from engine.dashboard import render_html_dashboard
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)
    html = render_html_dashboard(engine)
    assert "<!DOCTYPE html>" in html
    assert "Prodinamik Engine" in html
    assert "</html>" in html


# ──────────────────────────────────────────────
# Audit Log Tests
# ──────────────────────────────────────────────


@pytest.fixture
def audit_log():
    """Temporary audit log for testing"""
    tmpdir = tempfile.mkdtemp()
    from engine.audit import AuditLog
    log = AuditLog(base_path=os.path.join(tmpdir, "audit"), max_segment_size=100)
    yield log
    log.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_audit_record(audit_log):
    """Recording an entry works"""
    entry = audit_log.record("run.created", {"slug": "test-run", "profile": "software"})
    assert entry.event_type == "run.created"
    assert entry.data["slug"] == "test-run"
    assert entry.trace_id == ""


def test_audit_record_with_trace(audit_log):
    """Recording with trace_id works"""
    entry = audit_log.record("run.transition", {"slug": "test", "to": "done"},
                              trace_id="trace-123")
    assert entry.trace_id == "trace-123"


def test_audit_query_all(audit_log):
    """Query returns all entries"""
    audit_log.record("run.created", {"slug": "a"})
    audit_log.record("run.created", {"slug": "b"})
    audit_log.record("run.transition", {"slug": "a", "to": "active"})
    results = audit_log.query(limit=10)
    assert len(results) == 3


def test_audit_query_filter_type(audit_log):
    """Query filters by event_type"""
    audit_log.record("run.created", {"slug": "a"})
    audit_log.record("run.created", {"slug": "b"})
    audit_log.record("run.transition", {"slug": "a", "to": "active"})
    results = audit_log.query(event_type="run.transition", limit=10)
    assert len(results) == 1
    assert results[0].data["slug"] == "a"


def test_audit_query_limit(audit_log):
    """Query respects limit"""
    for i in range(10):
        audit_log.record("run.created", {"slug": f"test-{i}"})
    results = audit_log.query(limit=3)
    assert len(results) == 3


def test_audit_count(audit_log):
    """Count works without filter"""
    assert audit_log.count() == 0
    audit_log.record("run.created", {"slug": "a"})
    assert audit_log.count() == 1


def test_audit_count_filtered(audit_log):
    """Count works with event_type filter"""
    audit_log.record("run.created", {"slug": "a"})
    audit_log.record("run.transition", {"slug": "a", "to": "b"})
    assert audit_log.count(event_type="run.created") == 1


def test_audit_latest(audit_log):
    """Latest returns most recent entries"""
    for i in range(10):
        audit_log.record("run.created", {"slug": f"test-{i}"})
    latest = audit_log.latest(3)
    assert len(latest) == 3
    assert latest[-1].data["slug"] == "test-9"


def test_audit_replay(audit_log):
    """Replay reconstructs state"""
    audit_log.record("run.created", {"slug": "my-run", "state": "created"})
    audit_log.record("run.transition", {"slug": "my-run", "to": "active"})
    audit_log.record("run.transition", {"slug": "my-run", "to": "review"})

    state = {}
    entries = audit_log.replay(target_state=state)
    assert len(entries) == 3
    assert state["my-run"]["state"] == "review"
    assert state["my-run"]["events"] == 2


def test_audit_compaction(audit_log):
    """Compaction works (basic)"""
    for i in range(10):
        audit_log.record("run.created", {"slug": f"test-{i}"})
    assert audit_log.count() == 10
    # Compact with 0 days to force all entries
    compacted = audit_log.compact(older_than_days=0)
    assert compacted == 10


def test_audit_export_json(audit_log):
    """JSON export produces valid JSON array"""
    audit_log.record("run.created", {"slug": "a"})
    audit_log.record("run.transition", {"slug": "a", "to": "b"})
    exported = audit_log.export_json()
    data = json.loads(exported)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["type"] == "run.created"


# ──────────────────────────────────────────────
# CLI Integration Tests
# ──────────────────────────────────────────────


def test_cli_dashboard_help():
    """CLI dashboard help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["dashboard", "--help"])
    assert result.exit_code == 0
    assert "Show engine health dashboard" in result.output


def test_cli_dashboard_compact():
    """CLI dashboard compact works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["dashboard", "--compact"])
    assert result.exit_code == 0
    assert "Prodinamik" in result.output


def test_cli_metrics_prometheus():
    """CLI metrics prometheus works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["metrics", "--prometheus"])
    assert result.exit_code == 0
    assert "# HELP" in result.output


def test_cli_audit_help():
    """CLI audit help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["audit", "--help"])
    assert result.exit_code == 0
    assert "Query and manage audit log" in result.output


def test_cli_audit_stats():
    """CLI audit stats works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["audit", "stats"])
    assert result.exit_code == 0
    assert "Audit Log Stats" in result.output
