# Health Dashboard

Prodinamik Engine v1.1 — Health Dashboard

ASCII/ANSI dashboard for terminal use. Shows:
- Thermal map of engine health
- Run status matrix
- Degradation timeline
- Cost summary
- Alert log

Usage:
    from engine.dashboard import Dashboard
    dash = Dashboard(engine)
    print(dash.render())

**Module:** `engine.dashboard.py`

## Classes

### `Dashboard`

Terminal health dashboard for Prodinamik Engine

**Methods:**

- `__init__(engine)`
- `attach(engine)`
  — Attach to engine
- `log_alert(level, message, source)`
  — Add alert to rolling log
- `render()`
  — Render full dashboard
- `render_compact()`
  — Compact single-line status
- `_header()`
- `_thermal_map()`
  — ASCII thermal bar for key metrics
- `_run_matrix()`
  — Run status matrix
- `_degradation_timeline()`
  — ASCII timeline of degradation levels
- `_cost_summary()`
  — Cost summary section
- `_alert_section()`
  — Recent alerts
- `_get_health()`
- `_thermal_bar(value, width)`
  — Render a thermal bar █████░░░░░
- `_thermal_color(value)`
- `_deg_color(deg)`
- `_deg_normalized(deg)`
- `_score_color(score)`
- `_state_color(state)`

## Functions

### `render_html_dashboard(engine, metrics_snapshot)`

Generate a simple HTML dashboard page
