# AI Drift Detection

Prodinamik Engine v1.3 — AI Drift Detector

Pattern recognition, trend analysis, and emergence candidate
identification for state machine drift detection.

Architecture:
    DriftPatternCollector ──┬──→ TrendAnalyzer ──→ EmergenceDetector
                            │
                            └──→ AnomalyScanner ──→ DriftReport

Key metrics:
    - Drift frequency per run (instant rate)
    - Drift trend (increasing/decreasing/stable)
    - Emergence candidates (3+ same drift type → skill proposal)

**Module:** `engine.aidetect.py`

## Classes

### `DriftType`(str, Enum)

### `DriftSeverity`(str, Enum)

### `TrendDirection`(str, Enum)

### `DriftEvent`

A single drift occurrence

**Methods:**

- `to_dict()`

### `DriftPattern`

A recurring drift pattern across runs

**Methods:**

- `is_emerging()`
  — A pattern is 'emerging' if seen 3+ times across different runs

### `EmergenceCandidate`

A drift pattern that should become a skill

**Methods:**

- `to_dict()`

### `RunQualityMetrics`

Quality metrics for a single run

### `DriftPatternCollector`

Collects and organizes drift events for analysis

Maintains an in-memory store of drift events with indexing
by type, run, and time window.

**Methods:**

- `__init__(max_history)`
- `record(event)`
  — Record a drift event
- `record_from(drift_id, drift_type, severity, run_id, state, description, metadata)`
  — Create and record a drift event from fields
- `get_events(drift_type, run_id, since, limit)`
  — Query drift events with filters
- `count_by_type(since)`
  — Count drift events grouped by type
- `count_by_run(run_id)`
  — Count drift events for a specific run
- `total_events()`
- `unique_types()`
- `clear()`
  — Clear all collected events

### `TrendAnalyzer`

Analyzes drift trends across runs and time windows

Uses statistical methods:
- Moving average for smoothing
- Linear regression for trend direction
- Standard deviation for volatility

**Methods:**

- `__init__(collector)`
- `analyze_trend(drift_type, window_size)`
  — Analyze trend for a drift type over recent runs
- `analyze_severity_trend(severity_field)`
  — Analyze how severity changes over time
- `get_volatility(drift_type)`
  — Get volatility score for a drift type (0.0 = stable, 1.0+ = volatile)

### `EmergenceDetector`

Detects drift patterns that should become reusable skills

Criteria for emergence:
1. 3+ occurrences of the same drift type across different runs
2. Severity trend is stable or degrading (not improving on its own)
3. Pattern has a clear remediation strategy

**Methods:**

- `__init__(collector, trend_analyzer)`
- `detect_candidates(min_occurrences)`
  — Scan for drift patterns that should become skills
- `_calculate_confidence(occurrences, unique_runs, trend)`
  — Calculate emergence confidence score
- `_generate_recommendation(drift_type, description)`
  — Generate a human-readable recommendation for skill creation
- `_generate_skill_name(drift_type, description)`
  — Generate a skill name from drift pattern

### `AnomalyScanner`

Statistical anomaly detection on drift data

Uses z-score and IQR methods to flag unusual patterns.

**Methods:**

- `__init__(collector)`
- `scan_runs()`
  — Scan for anomalous runs based on drift patterns
- `scan_types()`
  — Scan for anomalous drift type distributions

### `AIDriftDetector`

Facade for all AI-driven drift detection capabilities

Usage:
    detector = AIDriftDetector()
    detector.record_drift(...)

    # Analysis
    trends = detector.analyze_trends()
    candidates = detector.find_emergence_candidates()
    anomalies = detector.scan_anomalies()

    # Report
    report = detector.generate_report()

**Methods:**

- `__init__(max_history)`
- `record_drift(drift_id, drift_type, severity, run_id, state, description)`
  — Record a drift event for AI analysis
- `analyze_trends(window_size)`
  — Analyze all drift trends
- `find_emergence_candidates(min_occurrences)`
  — Find drift patterns that should become skills
- `scan_anomalies()`
  — Scan for anomalies in drift data
- `generate_report()`
  — Generate comprehensive AI drift report
- `metrics()`
  — Usage metrics for dashboard
- `reset()`
  — Reset all collected data
