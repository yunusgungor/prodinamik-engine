# AI-Native Features

Prodinamik Engine v1.3 introduces **AI-driven automation** across the engine — drift detection, degradation forecasting, run recommendations, skill emergence, and auto-remediation — all using statistical methods (no external ML dependencies required).

## Overview

```
🔍 Drift Detection        → Sağlık skoru, trend analizi, anomali taraması
📊 Degradation Forecasting → MA/LR/Holt-Winters, threshold breach prediction
🎯 Run Recommender         → Transition scoring, bottleneck detection
🧬 Skill Emergence         → 3+ drift → otomatik SKILL.md + regression test
🛠️ Auto-Remediation        → 10 failure pattern, exponential backoff, cooldown
```

## 1. AI Drift Detection

Detects patterns, trends, and anomalies in state machine drift events.

### Architecture

```
DriftEvent → DriftPatternCollector
                  │
          ┌───────┴───────┐
          │               │
    TrendAnalyzer   AnomalyScanner
    (LR regression)  (z-score)
          │               │
          └───────┬───────┘
                  │
          EmergenceDetector
          (3+ threshold)
                  │
            AIDriftDetector
            .generate_report()
```

### Programmatic Usage

```python
from engine.aidetect import AIDriftDetector, DriftType, DriftSeverity

detector = AIDriftDetector()

# Record drifts
detector.record_drift("D01", DriftType.FORMAT, DriftSeverity.MEDIUM,
                      "run-1", "drafting", "Invalid YAML frontmatter")
detector.record_drift("D02", DriftType.CONTENT, DriftSeverity.HIGH,
                      "run-1", "verification", "Missing required sections")

# Generate comprehensive report
report = detector.generate_report()
print(f"Health Score: {report['health_score']}/100")
print(f"Total Events: {report['total_events']}")

# Find emergence candidates (drifts that should become skills)
for candidate in report['emergence_candidates']:
    print(f"  💡 {candidate['suggested_skill']} "
          f"(confidence={candidate['confidence']})")
```

### CLI

```bash
prodinamik ai detect                          # Full report
prodinamik ai detect --json                   # JSON output
```

**Sample output:**
```
🔍 AI Drift Detection Report
   Health Score:     85.0/100
   Total Events:     12
   Degrading Trends: 1
   Stable Trends:    3

🧬 Emergence Candidates:
   💡 ai-format-invalid-yaml (confidence=0.64)
      Create format validation skill to auto-fix 'Invalid YAML' patterns

⚠️  Anomalous Runs:
   run-3: z=2.34 (drifts=6)
```

## 2. Predictive Degradation

Forecasts metric values and predicts when degradation thresholds will be breached.

### Architecture

```
MetricPoint → MetricCollector → ForecastEngine
                                     │
                          ┌──────────┼──────────┐
                          │          │          │
                     Moving Avg  Linear Reg  Holt-Winters
                          │          │          │
                          └──────────┼──────────┘
                                     │
                             DegradationPredictor
                                     │
                             DegradationPrediction
                             (level, time, confidence, recommendation)
```

### Methods

| Method | Data Required | Best For |
|--------|--------------|----------|
| **Moving Average** | 3+ points | Short-term smoothing, volatile data |
| **Linear Regression** | 5+ points | Medium-term trend projection |
| **Holt-Winters** | 10+ points | Seasonal patterns with trend |

### Programmatic Usage

```python
from engine.predict import AIDegradationForecaster

forecaster = AIDegradationForecaster()

# Record metrics
forecaster.record_metric("latency_ms", 150.0)
forecaster.record_metric("latency_ms", 180.0)
# ...

# Predict degradation
prediction = forecaster.predict("latency_ms", horizon_minutes=60)
if prediction:
    print(f"Current: {prediction.current_level.value}")
    print(f"Predicted: {prediction.predicted_level.value}")
    if prediction.time_to_degradation:
        print(f"Time to degradation: {prediction.time_to_degradation:.1f}m")
    print(f"Recommendation: {prediction.recommendation}")
```

### Thresholds (Default)

| Metric | Warning | Critical |
|--------|---------|----------|
| `latency_ms` | 200 | 500 |
| `error_rate` | 0.05 | 0.10 |
| `memory_mb` | 512 | 1024 |
| `cpu_percent` | 80 | 95 |
| `run_duration_s` | 300 | 600 |
| `drift_rate` | 3 | 6 |

### CLI

```bash
prodinamik ai predict                         # All metrics
prodinamik ai predict --metric latency_ms     # Specific metric
prodinamik ai predict --horizon 120           # 2-hour horizon
prodinamik ai predict --json                  # JSON output
```

**Sample output:**
```
📊 Degradation Forecast Report
   Health Score: 85/100
   🔴 Critical: 0
   🟡 Warning:  1
   🟢 Normal:   2
   Metrics Tracked: 3
```

## 3. Run Recommender

Suggests optimal next state transitions based on historical success data.

### Scoring Formula

```
score = success_rate × 0.5 + frequency × 0.3 + recency × 0.2
```

### Programmatic Usage

```python
from engine.recommend import AIRecommender

recommender = AIRecommender()

# Record transitions
recommender.record_transition("r1", "software",
                               "drafting", "verification",
                               15.0, True)
# ...

# Get recommendation
rec = recommender.get_recommendation("run-new", "drafting", "software")
if rec:
    print(f"Best next state: {rec.best_next_state}")
    print(f"Confidence: {rec.confidence:.0%}")
    print(f"Reasoning: {rec.reasoning}")

# Find bottlenecks
bottlenecks = recommender.find_bottlenecks()
```

### CLI

```bash
prodinamik ai recommend drafting                  # Basic
prodinamik ai recommend drafting --profile software # With profile
prodinamik ai recommend drafting --json            # JSON output
```

**Sample output:**
```
🎯 Next State Recommendations
   Current: drafting
   Best Next: verification
   Confidence: 87%
   Reasoning: Transition drafting → verification has 95% success rate
              (19/20 attempts). Reliability: highly_reliable.
   Est. Duration: 15s
```

## 4. Skill Emergence

Automatically generates Hermes/Prodinamik skills from recurring drift patterns.

### Emergence Rules

| Rule | Description |
|------|-------------|
| **3+ occurrences** | Same drift type across different runs → T3 validator proposal |
| **10 successful fixes** | Promote T3 → T2 (auto-fix enabled) |
| **Confidence ≥ 0.85** | Auto-register skill without manual approval |

### Pipeline

```
DriftEvent → PatternCollector → TrendAnalyzer → EmergenceDetector
                                                       │
                                              AutoSkillForge
                                               ├── SKILL.md
                                               └── test_skill.py
```

## 5. Auto-Remediation

Automatically matches errors to known failure patterns and executes recovery actions.

### Built-in Patterns

| Pattern | Class | Auto-fix? |
|---------|-------|-----------|
| `connection_timeout` | TRANSIENT | ✅ |
| `rate_limit` | TRANSIENT | ✅ |
| `state_invalid` | STATE | ❌ (requires manual) |
| `state_machine_stuck` | STATE | ❌ |
| `memory_pressure` | RESOURCE | ✅ |
| `disk_full` | RESOURCE | ✅ |
| `validation_failed` | VALIDATION | ✅ |
| `dependency_down` | DEPENDENCY | ✅ |
| `config_error` | CONFIG | ❌ |
| Unknown | UNKNOWN | ❌ |

### Programmatic Usage

```python
from engine.autofix import AutoRemediator

remediator = AutoRemediator()

# One-shot: match → create plan → execute
result = await remediator.remediate(
    "Connection timeout after 30s",
    {"run_id": "flux-v1"}
)
if result:
    print(f"Status: {result.status.value}")
    print(f"Actions: {result.action_results}")

# Get statistics
stats = remediator.get_stats()
print(f"Auto-remediated: {stats['auto_remediated']}")
```

## CLI Status

```bash
prodinamik ai status
```

**Sample output:**
```
🤖 AI-Native Features Status
──────────────────────────────────────────────────

🔍 Drift Detection
   Events: 12
   Types:  3

📊 Degradation Forecasting
   Metrics: 3
   Points:  30

🎯 Run Recommender
   Transitions: 25
   Bottlenecks: 1

🛠️  Auto-Remediation
   Incidents:   8
   Auto-fixed:  5
   Success:     63%

🧬 Skill Emergence
   Generated:  2
   Promotable: 0
──────────────────────────────────────────────────
   ⚡ Usage: prodinamik ai <detect|predict|recommend>
```
