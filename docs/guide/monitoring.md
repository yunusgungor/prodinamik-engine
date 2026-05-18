# Monitoring & Metrics

Prodinamik Engine includes a comprehensive observability stack covering metrics collection (Prometheus), health dashboards (terminal and HTML), structured audit logging, alert management with webhook delivery to Slack/Telegram, and deep Grafana integration. The four subsystems — Metrics, Dashboard, Audit Log, and Alert Manager — work together to provide full visibility into engine health, run activity, costs, and system events.

## Metrics Subsystem

The metrics pipeline (`engine/metrics.py`) provides a thread-safe, Prometheus-compatible metrics registry that supports counters, gauges, and histograms.

### Metric Types

| Type | Behavior | Use Case |
|------|----------|----------|
| **Counter** | Monotonically increasing value. Supports `inc(amount)`. | Run creations, transitions, errors, events |
| **Gauge** | Point-in-time value that can increase or decrease. Supports `set()`, `inc()`, `dec()`. | Active runs, health score, budget usage |
| **Histogram** | Value distribution with configurable buckets. Supports `observe(value)`. Tracks count, sum, and per-bucket counts. | Transition latency, event store append duration, iteration times |

### Usage

```python
from engine.metrics import metrics

# Counter
c = metrics.counter("runs_created", "Total runs created", labels={"profile": "software"})
c.inc()         # +1
c.inc(5)        # +5

# Gauge
g = metrics.gauge("active_runs", "Currently active runs")
g.set(42)       # Set exact value
g.inc()         # +1
g.dec()         # -1

# Histogram
h = metrics.histogram("transition_latency_ms", "State transition latency in ms",
                       buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000])
h.observe(42.0)  # Record a value
print(f"Avg: {h.avg}ms, Count: {h.count}")
```

### Prometheus Export

The registry renders all metrics in the standard Prometheus text format:

```python
prometheus_text = metrics.render_prometheus()
print(prometheus_text)
```

Output example:

```
# HELP prodinamik_engine_info Prodinamik Engine metrics
# TYPE prodinamik_engine_info gauge
prodinamik_engine_info{version="1.1.0",uptime_seconds="12345"} 1

# HELP prodinamik_runs_created_total Total runs created
# TYPE prodinamik_runs_created_total counter
prodinamik_runs_created_total{profile="software"} 150
prodinamik_runs_created_total{profile="hardware"} 72

# HELP prodinamik_active_runs Currently active runs
# TYPE prodinamik_active_runs gauge
prodinamik_active_runs 42

# HELP prodinamik_transition_latency_ms State transition latency in ms
# TYPE prodinamik_transition_latency_ms histogram
prodinamik_transition_latency_ms_bucket{le="1"} 0
prodinamik_transition_latency_ms_bucket{le="5"} 12
prodinamik_transition_latency_ms_bucket{le="10"} 89
prodinamik_transition_latency_ms_bucket{le="+Inf"} 150
prodinamik_transition_latency_ms_count 150
prodinamik_transition_latency_ms_sum 3450.0
```

### /metrics Endpoint

When the HTTP server is running, metrics are available at the `/metrics` endpoint:

```bash
curl http://localhost:8080/metrics
```

Response includes all registered counters, gauges, and histograms in Prometheus text format, compatible with `prometheus.yml` scrape configuration:

```yaml
scrape_configs:
  - job_name: 'prodinamik-engine'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
```

### Engine Metrics Integration

The `EngineMetrics` class binds the metrics registry to the engine runtime:

```python
from engine.metrics import EngineMetrics

engine_metrics = EngineMetrics(engine)
engine_metrics.poll()  # Collect current metrics
```

Polls at a maximum rate of 1 Hz and captures:

- **prodinamik_active_runs** — Count of currently active runs.
- **prodinamik_health_score** — Engine health score (0–100).
- **prodinamik_degradation_level** — Numeric degradation level (0=FULL, 1=DEGRADED, 2=SURVIVAL).
- **prodinamik_profile_count** — Number of registered product profiles.
- **prodinamik_total_cost_usd** — Accumulated cost across all runs.

### Snapshot

The `snapshot()` method returns a JSON-serializable dict of all current metrics:

```python
snap = metrics.snapshot()
# {
#   "counters": {"counter:runs_created": 150},
#   "gauges": {"gauge:active_runs": 42},
#   "histograms": {"histogram:transition_latency_ms": {"count": 150, "sum": 3450, "avg": 23.0}},
#   "uptime_seconds": 12345,
#   "timestamp": "2026-05-18T14:32:15"
# }
```

## Health Dashboard

The dashboard module (`engine/dashboard.py`) provides both terminal (ANSI) and HTML rendering of engine health.

### Terminal Dashboard

```bash
prodinamik dashboard
prodinamik dashboard --compact  # Single-line status
```

The full dashboard renders five sections:

#### Header
Displays engine name and current timestamp in a bordered box.

#### Thermal Map
ASCII thermal bars for key metrics:

```
Thermal Map
  Health Score:  ████████░░░░░░░░░░░░ 42%
  Degradation:   ████████████████████ 0%   (green = FULL)
  Budget Used:   ████░░░░░░░░░░░░░░░░ 8%
  Profiles: software, hardware
```

Colors indicate severity: green (0–49%), yellow (50–79%), red (80–100%).

#### Run Matrix
Grouped by profile, each run shows slug, current state, and elapsed time:

```
Run Matrix (3 active)
  software:
    🔄 release-v2-1-0 → development [3420s]
    🔄 hotfix-auth    → review [120s]
  hardware:
    🔄 pcb-revision-3 → staging [86400s]
```

#### Degradation Timeline
Visual indicator of current degradation level:

```
Degradation State
  FULL ●  DEGRADED ○  SURVIVAL ○
```

#### Cost Summary
```
Cost Summary
  Total:      $15.3420
  Active:     3 runs
  Est.Daily:  $0.0075
```

#### Alert Log
Last 5 alerts with color-coded severity:

```
Recent Alerts
  🔴 [warning] Budget usage > 80% for profile software
  🔵 [info]    Run release-v2-1-0 entered review state
```

### HTML Dashboard

Export an HTML dashboard for browser viewing:

```bash
prodinamik dashboard --html > dashboard.html
```

The HTML output is a self-contained page with dark theme styling, grid layout with cards, progress bars, and a runs table. Suitable for embedding in CI/CD pipeline artifacts or serving from a file server.

```python
from engine.dashboard import render_html_dashboard

html = render_html_dashboard(engine, metrics.snapshot())
with open("dashboard.html", "w") as f:
    f.write(html)
```

### Real-Time Updates

For continuous monitoring, run the dashboard in polling mode:

```bash
watch -n 5 "prodinamik dashboard --compact"
```

This updates the single-line status every 5 seconds showing degradation level, health score, and active run count.

## Audit Log

The audit subsystem (`engine/audit.py`) provides a JSONL-based append-only audit trail with compaction, querying, and event replay capabilities.

### Architecture

```
audit/
├── audit.log              # Active append log (JSONL)
├── archive/               # Compacted gzipped segments
│   ├── audit_001.jsonl.gz
│   └── audit_002.jsonl.gz
└── index.json             # Segment index
```

### Recording Events

```python
from engine.audit import AuditLog

audit = AuditLog(base_path="./.hermes/audit")

# Record different event types
audit.record("run.created", {"slug": "my-run", "profile": "software", "state": "backlog"})
audit.record("run.transition", {"slug": "my-run", "from": "backlog", "to": "development"})
audit.record("run.archived", {"slug": "my-run"})
audit.record("degradation.change", {"from": "FULL", "to": "DEGRADED", "reason": "budget_exceeded"})
audit.record("metric.recorded", {"prometheus": "..."})
```

Each entry includes: `ts` (ISO timestamp), `type` (event type), `data` (payload), and optional `trace_id` for cross-session correlation.

### Querying

```python
# Recent events
recent = audit.latest(10)

# Filter by time range
entries = audit.query(since="2026-05-01T00:00:00", until="2026-05-18T00:00:00")

# Filter by event type
errors = audit.query(event_type="run.transition", limit=50)

# Count events
total = audit.count()
transition_count = audit.count(event_type="run.transition")
```

### Event Replay

The audit log can reconstruct state by replaying all events:

```python
state = {}
audit.replay(target_state=state)
# state now contains reconstructed run states
# e.g., {"my-run": {"state": "development", "events": 5}}
```

Built-in replay handlers support: `run.created`, `run.transition`, `run.archived`, `degradation.change`, `metric.recorded`.

### Compaction

Old audit entries can be compacted into gzipped archive segments:

```bash
prodinamik audit compact --older-than 30
```

```python
compacted = audit.compact(older_than_days=30)
print(f"Compacted {compacted} entries")
```

Compaction moves entries older than the cutoff into a gzipped JSONL segment and rewrites the active log with only recent entries.

### CLI Commands

| Command | Description |
|---------|-------------|
| `prodinamik audit query [type]` | Query audit entries, optionally filtered by event type |
| `prodinamik audit stats` | Show audit log statistics (entry count, archive segments) |
| `prodinamik audit compact` | Compact entries older than the default threshold (7 days) |
| `prodinamik audit export` | Export all entries as a JSON array |

## Alert Manager

The alert manager (`engine/alert.py`) provides webhook-based alert delivery to Slack, Telegram, and generic HTTP endpoints. It includes rate limiting, deduplication, and subscription support.

### Configuration

Configure via environment variables or constructor:

```python
from engine.alert import AlertManager

alert = AlertManager(
    slack_webhook="https://hooks.slack.com/services/...",
    telegram_token="123456:ABC-DEF...",
    telegram_chat_id="-1001234567890",
    generic_webhook="https://hooks.example.com/alerts",
    min_interval_sec=60,        # Minimum interval between alerts per channel
    dedup_window_sec=300,       # Suppress identical alerts within 5 minutes
)
```

Or via environment variables:
- `PRODINAMIK_SLACK_WEBHOOK`
- `PRODINAMIK_TELEGRAM_TOKEN`
- `PRODINAMIK_TELEGRAM_CHAT_ID`
- `PRODINAMIK_GENERIC_WEBHOOK`

### Sending Alerts

```python
# Simple alert
alert.send_alert("info", "Run completed", "Software profile run finished successfully")

# Alert with metrics
alert.send_alert(
    "warning",
    "Budget near limit",
    message="Software profile budget at 85%",
    metrics={"usage": 0.85, "budget": 100.00, "spent": 85.00},
    source="cost_tracker",
)
```

Three severity levels: `info`, `warning`, `critical` — each with its own emoji and formatting.

### Slack Integration

Alerts are formatted as Slack Block Kit messages with:
- Header block with emoji + title.
- Section block with level, source, and timestamp.
- Fields for metric key-value pairs.
- Context footer with alert ID.

### Telegram Integration

Alerts are formatted as HTML messages with:
- Bold title with emoji and severity.
- Message body.
- Metrics rendered as bold key + code value pairs.
- Footer with alert ID.

### Deduplication and Rate Limiting

Two mechanisms prevent alert storms:

1. **Deduplication** — Alerts with the same `level:title` combination are suppressed within `dedup_window_sec` (default: 5 minutes).
2. **Rate limiting** — Per-channel rate limiting at `min_interval_sec` (default: 60 seconds) prevents webhook spam.

### Custom Handlers

```python
def log_to_db(alert):
    db.execute("INSERT INTO alerts ...", alert.to_dict())

alert.subscribe(log_to_db)
```

### Alertmanager Webhook Receiver

The engine can act as a receiver for Prometheus Alertmanager webhooks:

```python
# POST /alertmanager
data = request.json
alert.handle_alertmanager_webhook(data)
```

This allows external Prometheus rules to flow through the engine's notification channels.

### Test Alerts

```bash
prodinamik alert test --channel slack
prodinamik alert send --level warning "Test alert from CLI"
```

## Prometheus Alert Rules

The file `monitoring/prometheus-alerts.yml` defines 19 alert rules organized into six groups:

### Engine Health (2 rules)
- **EngineDown** — Fires after 1 minute of unreachability (critical).
- **EngineRestarted** — Detects recent restarts via uptime < 2 minutes (warning).

### Degradation (2 rules)
- **EngineDegraded** — Engine in DEGRADED mode for >2 minutes (warning).
- **EngineSurvivalMode** — Engine in SURVIVAL mode for >30 seconds (critical).

### Run Activity (3 rules)
- **RunCreationSpike** — >10 runs/sec sustained for 2 minutes (warning).
- **TooManyActiveRuns** — >100 active runs for 5 minutes (warning).
- **RunStuckInState** — Run in same state for >24 hours (info).

### Performance (2 rules)
- **HighTransitionLatency** — P99 > 1 second for 5 minutes (warning).
- **EventStoreSlow** — Append latency >500ms average (warning).

### Chaos Engineering (2 rules)
- **ChaosTestFailed** — Chaos scenario failed (warning).
- **SelfHealingFailed** — Engine did not recover from injected fault (critical).

### Budget & Cost (2 rules)
- **BudgetSoftLimit** — Usage >80% for 5 minutes (info).
- **BudgetHardLimit** — Usage >100% for 1 minute (warning).

### Security (2 rules)
- **AuthFailureRate** — >5 auth failures/sec sustained (warning).
- **RateLimitHit** — >10 rate limit hits/sec (info).

## Grafana Dashboard

The file `monitoring/grafana-dashboard.json` provides a complete Grafana dashboard with:

- **Health Score gauge** — Current engine health percentage.
- **Degradation level** — Color-coded degradation state.
- **Active Runs panel** — Time-series of active run count.
- **Transition Latency heatmap** — Histogram of transition durations.
- **Alert Events log** — Rolling log of recent alerts.
- **Cost Over Time** — Accumulated cost chart per profile.
- **Run Status table** — Active runs with current state and duration.

Import into Grafana:

1. Open Grafana → Create → Import.
2. Upload `monitoring/grafana-dashboard.json` or paste the JSON.
3. Set the Prometheus datasource to match your engine's `/metrics` endpoint.

## Health Check Endpoints

The HTTP server exposes two health-check endpoints:

### /healthz

Simple liveness probe:

```bash
curl http://localhost:8080/healthz
# OK
```

Returns `200 OK` with body `OK` if the engine process is alive.

### /health

Detailed health snapshot:

```bash
curl http://localhost:8080/health
```

Returns JSON with: degradation level, health score, active runs, profiles, cost, and recent alerts.

## CLI Reference

| Command | Description |
|---------|-------------|
| `prodinamik metrics` | Show current metrics summary |
| `prodinamik metrics --prometheus` | Export metrics in Prometheus text format |
| `prodinamik dashboard` | Full terminal dashboard |
| `prodinamik dashboard --compact` | Single-line status |
| `prodinamik dashboard --html` | Export HTML dashboard page |
| `prodinamik audit query` | Query recent audit entries |
| `prodinamik audit stats` | Show audit log statistics |
| `prodinamik audit compact` | Compact old audit entries |
| `prodinamik audit export` | Export all audit entries as JSON |
| `prodinamik alert send` | Send a test alert |
| `prodinamik alert test` | Test a notification channel |
