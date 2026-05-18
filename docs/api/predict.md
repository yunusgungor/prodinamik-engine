# Predictive Degradation

Prodinamik Engine v1.3 — Predictive Degradation

Forecast engine degradation before it happens using statistical
models on metric time series data.

Architecture:
    MetricCollector → Forecaster → DegradationPredictor → AlertGate

Methods:
    - Moving Average (MA): short-term trend smoothing
    - Linear Regression: medium-term trend projection
    - Holt-Winters: seasonal pattern detection
    - Z-Score Anomaly: threshold breach forecasting

**Module:** `engine.predict.py`

## Classes

### `ForecastMethod`(str, Enum)

### `DegradationLevel`(str, Enum)

### `AlertTrigger`(str, Enum)

### `MetricPoint`

A single metric data point

### `ForecastResult`

Result of a forecasting operation

**Methods:**

- `breach_probability(threshold, above)`
  — Probability of breaching a threshold within the forecast horizon

### `DegradationPrediction`

A prediction about future degradation

**Methods:**

- `to_dict()`

### `MetricCollector`

Collects and stores metric time series for forecasting

Maintains rolling windows per metric with configurable
retention (default: 1000 points per metric).

**Methods:**

- `__init__(max_points_per_metric)`
- `record(name, value, labels)`
  — Record a metric data point
- `get_series(name, since, limit)`
  — Get metric time series with optional filter
- `get_values(name, since, limit)`
  — Get just the values from a metric series
- `latest_value(name)`
  — Get the most recent value for a metric
- `metrics()`
- `total_points()`

### `ForecastEngine`

Statistical forecasting for metric time series

Supports multiple forecasting methods with automatic
method selection based on data characteristics.

**Methods:**

- `__init__(collector)`
- `forecast(metric, horizon_minutes, method)`
  — Forecast a metric into the future
- `_ma_forecast(metric, values, current, horizon)`
  — Moving average forecast
- `_lr_forecast(metric, values, current, horizon)`
  — Linear regression forecast
- `_hw_forecast(metric, values, current, horizon)`
  — Simple Holt-Winters-like forecast (level + trend)
- `forecast_all(horizon_minutes)`
  — Forecast all tracked metrics

### `DegradationPredictor`

Predicts future degradation levels based on metric forecasts

Uses configurable thresholds per metric to determine when
a metric will cross from 'normal' into 'warning' or 'critical'.

**Methods:**

- `__init__(forecast_engine, thresholds)`
- `predict(metric, horizon_minutes)`
  — Predict degradation for a single metric
- `predict_all(horizon_minutes)`
  — Predict degradation for all tracked metrics
- `_classify(metric, value)`
  — Classify a metric value into a degradation level
- `_determine_trigger(metric, current, predicted, thresholds)`
  — Determine what triggered the prediction
- `_generate_recommendation(metric, level, value)`
  — Generate human-readable recommendation

### `AIDegradationForecaster`

Facade for all predictive degradation capabilities

Usage:
    forecaster = AIDegradationForecaster()
    forecaster.record_metric("latency_ms", 150.0)
    predictions = forecaster.predict_all()
    summary = forecaster.generate_report()

**Methods:**

- `__init__(thresholds)`
- `record_metric(name, value, labels)`
  — Record a metric data point for forecasting
- `predict(metric, horizon_minutes)`
  — Predict degradation for a metric
- `predict_all(horizon_minutes)`
  — Predict degradation for all metrics
- `forecast(metric, horizon_minutes)`
  — Forecast a single metric
- `forecast_all(horizon_minutes)`
  — Forecast all metrics
- `generate_report(horizon_minutes)`
  — Generate comprehensive degradation report
- `metrics()`
- `set_threshold(metric, warning, critical)`
  — Set or update thresholds for a metric
