# Metrics Pipeline

Prodinamik Engine v1.1 — Metrics Pipeline

Counter, Gauge, Histogram metrics with Prometheus export format.
Integration with DegradationManager and health system.

Usage:
    from engine.metrics import metrics
    metrics.counter("runs_created").inc()
    metrics.gauge("active_runs").set(5)
    metrics.histogram("transition_latency_ms").observe(42.0)
    print(metrics.render_prometheus())  # Prometheus format

**Module:** `engine.metrics.py`

## Classes

### `Counter`

Monotonically increasing counter

**Methods:**

- `inc(amount)`
- `reset()`
- `value()`
- `prometheus()`
- `_sanitize(s)`
- `_labels_str()`

### `Gauge`

Point-in-time value that can go up or down

**Methods:**

- `set(value)`
- `inc(amount)`
- `dec(amount)`
- `value()`
- `prometheus()`
- `_labels_str()`

### `Histogram`

Value distribution with buckets

**Methods:**

- `observe(value)`
- `count()`
- `sum()`
- `avg()`
- `prometheus()`
- `_labels_str(extra)`

### `MetricsRegistry`

Thread-safe singleton metrics registry.

Auto-registers counters/gauges/histograms on first access.
Renders Prometheus text format for /metrics endpoint.

**Methods:**

- `__init__()`
- `counter(name, help, labels)`
- `gauge(name, help, labels)`
- `histogram(name, help, labels, buckets)`
- `render_prometheus()`
  — Render all metrics in Prometheus text format
- `snapshot()`
  — Return a JSON-serializable snapshot of all metrics
- `__repr__()`

### `EngineMetrics`

Bind engine metrics to the MetricsRegistry.

Attach to AsyncEngine for automatic metric collection.

**Methods:**

- `__init__(engine, registry)`
- `attach(engine)`
  — Attach to an engine instance
- `poll()`
  — Collect metrics from engine — call periodically
- `snapshot()`
  — Return combined engine + metrics snapshot
