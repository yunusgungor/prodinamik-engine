"""Prodinamik Engine v1.1 — Metrics Pipeline

Counter, Gauge, Histogram metrics with Prometheus export format.
Integration with DegradationManager and health system.

Usage:
    from engine.metrics import metrics
    metrics.counter("runs_created").inc()
    metrics.gauge("active_runs").set(5)
    metrics.histogram("transition_latency_ms").observe(42.0)
    print(metrics.render_prometheus())  # Prometheus format
"""

import time
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta


# ──────────────────────────────────────────────
# Metric Types
# ──────────────────────────────────────────────


@dataclass
class Counter:
    """Monotonically increasing counter"""
    name: str
    help: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    _value: float = 0.0

    def inc(self, amount: float = 1.0):
        self._value += amount

    def reset(self):
        self._value = 0.0

    @property
    def value(self) -> float:
        return self._value

    def prometheus(self) -> str:
        name = self._sanitize(self.name)
        labels = self._labels_str()
        return f"{name}_total{labels} {self._value}\n"

    @staticmethod
    def _sanitize(s: str) -> str:
        return s.replace("-", "_").replace(" ", "_").replace(".", "_").lower()

    def _labels_str(self) -> str:
        if not self.labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in sorted(self.labels.items())]
        return "{" + ",".join(parts) + "}"


@dataclass
class Gauge:
    """Point-in-time value that can go up or down"""
    name: str
    help: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    _value: float = 0.0

    def set(self, value: float):
        self._value = value

    def inc(self, amount: float = 1.0):
        self._value += amount

    def dec(self, amount: float = 1.0):
        self._value -= amount

    @property
    def value(self) -> float:
        return self._value

    def prometheus(self) -> str:
        name = Counter._sanitize(self.name)
        labels = self._labels_str()
        return f"{name}{labels} {self._value}\n"

    def _labels_str(self) -> str:
        if not self.labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in sorted(self.labels.items())]
        return "{" + ",".join(parts) + "}"


@dataclass
class Histogram:
    """Value distribution with buckets"""
    name: str
    help: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    buckets: List[float] = field(default_factory=lambda:
        [1, 5, 10, 25, 50, 100, 250, 500, 1000, float("inf")])
    _counts: Dict[int, float] = field(default_factory=lambda: defaultdict(float))
    _sum: float = 0.0
    _count: int = 0

    def observe(self, value: float):
        self._sum += value
        self._count += 1
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                self._counts[i] += 1.0
                break

    @property
    def count(self) -> int:
        return self._count

    @property
    def sum(self) -> float:
        return self._sum

    @property
    def avg(self) -> float:
        return self._sum / self._count if self._count > 0 else 0.0

    def prometheus(self) -> str:
        name = Counter._sanitize(self.name)
        labels_base = self._labels_str()
        labels_le = self._labels_str(extra='le')
        out = ""

        # Buckets
        for i, bound in enumerate(self.buckets):
            le_labels = labels_le.replace('"', f'"{bound}"', 1) if labels_le else f'{{le="{bound}"}}'
            out += f"{name}_bucket{le_labels} {self._counts.get(i, 0)}\n"

        # +Inf bucket
        inf_labels = labels_le.replace('"', '"+Inf"', 1) if labels_le else '{le="+Inf"}'
        out += f"{name}_bucket{inf_labels} {self._count}\n"

        # Count + Sum
        out += f"{name}_count{labels_base} {self._count}\n"
        out += f"{name}_sum{labels_base} {self._sum}\n"
        return out

    def _labels_str(self, extra: str = "") -> str:
        parts = []
        for k, v in sorted(self.labels.items()):
            parts.append(f'{k}="{v}"')
        if extra:
            parts.append(f'{extra}=?')  # placeholder
        if not parts:
            return ""
        return "{" + ",".join(parts) + "}"


# ──────────────────────────────────────────────
# Metrics Registry
# ──────────────────────────────────────────────


class MetricsRegistry:
    """Thread-safe singleton metrics registry.

    Auto-registers counters/gauges/histograms on first access.
    Renders Prometheus text format for /metrics endpoint.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._metadata: Dict[str, str] = {}
        self._started_at = time.time()

    # ──────────────────────────────────────
    # Registration
    # ──────────────────────────────────────

    def counter(self, name: str, help: str = "", labels: dict = None) -> Counter:
        key = f"counter:{name}"
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(name=name, help=help, labels=labels or {})
            return self._counters[key]

    def gauge(self, name: str, help: str = "", labels: dict = None) -> Gauge:
        key = f"gauge:{name}"
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = Gauge(name=name, help=help, labels=labels or {})
            return self._gauges[key]

    def histogram(self, name: str, help: str = "", labels: dict = None,
                  buckets: list = None) -> Histogram:
        key = f"histogram:{name}"
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(
                    name=name, help=help, labels=labels or {},
                    buckets=buckets or [1, 5, 10, 25, 50, 100, 250, 500, 1000, float("inf")]
                )
            return self._histograms[key]

    # ──────────────────────────────────────
    # Prometheus Export
    # ──────────────────────────────────────

    def render_prometheus(self) -> str:
        """Render all metrics in Prometheus text format"""
        lines = [
            f"# HELP prodinamik_engine_info Prodinamik Engine metrics",
            f"# TYPE prodinamik_engine_info gauge",
            f'prodinamik_engine_info{{version="1.1.0",uptime_seconds="{int(time.time() - self._started_at)}"}} 1',
            "",
        ]

        with self._lock:
            # Counters
            for key, c in sorted(self._counters.items()):
                if c.help:
                    lines.append(f"# HELP {Counter._sanitize(c.name)}_total {c.help}")
                lines.append(f"# TYPE {Counter._sanitize(c.name)}_total counter")
                lines.append(c.prometheus().rstrip())

            # Gauges
            for key, g in sorted(self._gauges.items()):
                if g.help:
                    lines.append(f"# HELP {Counter._sanitize(g.name)} {g.help}")
                lines.append(f"# TYPE {Counter._sanitize(g.name)} gauge")
                lines.append(g.prometheus().rstrip())

            # Histograms
            for key, h in sorted(self._histograms.items()):
                if h.help:
                    lines.append(f"# HELP {Counter._sanitize(h.name)} {h.help}")
                lines.append(f"# TYPE {Counter._sanitize(h.name)} histogram")
                lines.append(h.prometheus().rstrip())

        return "\n".join(lines) + "\n"

    # ──────────────────────────────────────
    # JSON Export (for dashboard)
    # ──────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a JSON-serializable snapshot of all metrics"""
        with self._lock:
            return {
                "counters": {k: v.value for k, v in self._counters.items()},
                "gauges": {k: v.value for k, v in self._gauges.items()},
                "histograms": {
                    k: {"count": v.count, "sum": v.sum, "avg": v.avg}
                    for k, v in self._histograms.items()
                },
                "uptime_seconds": int(time.time() - self._started_at),
                "timestamp": datetime.now().isoformat(),
            }

    def __repr__(self) -> str:
        s = self.snapshot()
        return (
            f"MetricsRegistry("
            f"counters={len(s['counters'])}, "
            f"gauges={len(s['gauges'])}, "
            f"histograms={len(s['histograms'])}"
            f")"
        )


# Singleton
metrics = MetricsRegistry()


# ──────────────────────────────────────────────
# Engine Metrics Integration
# ──────────────────────────────────────────────

class EngineMetrics:
    """Bind engine metrics to the MetricsRegistry.

    Attach to AsyncEngine for automatic metric collection.
    """

    def __init__(self, engine=None, registry: MetricsRegistry = None):
        self.engine = engine
        self.registry = registry or metrics
        self._last_poll = 0.0

    def attach(self, engine):
        """Attach to an engine instance"""
        self.engine = engine

    def poll(self):
        """Collect metrics from engine — call periodically"""
        if not self.engine:
            return

        now = time.time()
        if now - self._last_poll < 1.0:
            return  # Rate limit: 1Hz max
        self._last_poll = now

        try:
            health = self.engine.health_snapshot
        except Exception:
            health = {}

        g = self.registry.gauge

        # Core metrics
        g("prodinamik_active_runs", "Currently active runs").set(
            health.get("active_runs", 0))
        g("prodinamik_health_score", "Engine health score 0-100").set(
            health.get("health_score", 0))

        # Degradation level as numeric
        deg = health.get("degradation", "FULL")
        deg_map = {"FULL": 0, "DEGRADED": 1, "SURVIVAL": 2}
        g("prodinamik_degradation_level", "Degradation level: 0=FULL, 1=DEGRADED, 2=SURVIVAL").set(
            deg_map.get(deg, 0))

        # Profiles
        profiles = health.get("profiles", [])
        g("prodinamik_profile_count", "Number of registered profiles").set(
            len(profiles))

        # Cost
        total_cost = health.get("total_cost", 0)
        g("prodinamik_total_cost_usd", "Total accumulated cost in USD").set(
            total_cost)

    def snapshot(self) -> dict:
        """Return combined engine + metrics snapshot"""
        engine_snap = {}
        if self.engine:
            try:
                engine_snap = self.engine.health_snapshot
            except Exception:
                pass

        return {
            **engine_snap,
            "metrics": self.registry.snapshot(),
        }
