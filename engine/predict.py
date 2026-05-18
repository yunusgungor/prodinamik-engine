"""Prodinamik Engine v1.3 — Predictive Degradation

Forecast engine degradation before it happens using statistical
models on metric time series data.

Architecture:
    MetricCollector → Forecaster → DegradationPredictor → AlertGate

Methods:
    - Moving Average (MA): short-term trend smoothing
    - Linear Regression: medium-term trend projection
    - Holt-Winters: seasonal pattern detection
    - Z-Score Anomaly: threshold breach forecasting
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


from .log import get_logger
from .llm_base import LLMProviderPlugin


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class ForecastMethod(str, Enum):
    MOVING_AVERAGE = "moving_average"
    LINEAR_REGRESSION = "linear_regression"
    HOLT_WINTERS = "holt_winters"


class DegradationLevel(str, Enum):
    NORMAL = "normal"
    WATCHING = "watching"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertTrigger(str, Enum):
    THRESHOLD_BREACH = "threshold_breach"
    TREND_ACCELERATION = "trend_acceleration"
    ANOMALY_SPIKE = "anomaly_spike"
    FORECAST_OVERFLOW = "forecast_overflow"


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class MetricPoint:
    """A single metric data point"""
    name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ForecastResult:
    """Result of a forecasting operation"""
    metric: str
    current_value: float
    predicted_value: float
    confidence_interval: Tuple[float, float]
    method: ForecastMethod
    horizon_minutes: int
    trend_direction: str  # "up", "down", "stable"
    accuracy_score: float  # 0.0 - 1.0 (how well the model fits)

    def breach_probability(self, threshold: float, above: bool = True) -> float:
        """Probability of breaching a threshold within the forecast horizon"""
        if above:
            if self.predicted_value <= threshold:
                return 0.0
            # How far into the confidence band is above threshold
            lower, upper = self.confidence_interval
            if upper <= threshold:
                return 0.0
            if lower >= threshold:
                return 1.0
            return (upper - threshold) / (upper - lower)
        else:
            if self.predicted_value >= threshold:
                return 0.0
            lower, upper = self.confidence_interval
            if lower >= threshold:
                return 0.0
            if upper <= threshold:
                return 1.0
            return (threshold - lower) / (upper - lower)


@dataclass
class DegradationPrediction:
    """A prediction about future degradation"""
    metric: str
    current_level: DegradationLevel
    predicted_level: DegradationLevel
    time_to_degradation: Optional[float]  # Minutes until predicted level
    confidence: float  # 0.0 - 1.0
    trigger: Optional[AlertTrigger] = None
    forecast: Optional[ForecastResult] = None
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "current_level": self.current_level.value,
            "predicted_level": self.predicted_level.value,
            "time_to_degradation_minutes": self.time_to_degradation,
            "confidence": self.confidence,
            "trigger": self.trigger.value if self.trigger else None,
            "recommendation": self.recommendation,
        }


# ──────────────────────────────────────────────
# Metric Collector
# ──────────────────────────────────────────────


class MetricCollector:
    """Collects and stores metric time series for forecasting

    Maintains rolling windows per metric with configurable
    retention (default: 1000 points per metric).
    """

    def __init__(self, max_points_per_metric: int = 1000):
        self._series: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_points_per_metric)
        )
        self.log = get_logger()

    def record(self, name: str, value: float,
               labels: Dict[str, str] = None) -> MetricPoint:
        """Record a metric data point"""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=datetime.now(),
            labels=labels or {},
        )
        self._series[name].append(point)
        return point

    def get_series(self, name: str, since: Optional[datetime] = None,
                   limit: int = 100) -> List[MetricPoint]:
        """Get metric time series with optional filter"""
        series = list(self._series.get(name, []))
        if since:
            series = [p for p in series if p.timestamp >= since]
        return series[-limit:]

    def get_values(self, name: str, since: Optional[datetime] = None,
                   limit: int = 100) -> List[float]:
        """Get just the values from a metric series"""
        return [p.value for p in self.get_series(name, since, limit)]

    def latest_value(self, name: str) -> Optional[float]:
        """Get the most recent value for a metric"""
        series = self._series.get(name)
        if series:
            return series[-1].value
        return None

    @property
    def metrics(self) -> List[str]:
        return list(self._series.keys())

    @property
    def total_points(self) -> int:
        return sum(len(s) for s in self._series.values())


# ──────────────────────────────────────────────
# Forecast Engine
# ──────────────────────────────────────────────


class ForecastEngine:
    """Statistical forecasting for metric time series

    Supports multiple forecasting methods with automatic
    method selection based on data characteristics.
    """

    def __init__(self, collector: MetricCollector):
        self.collector = collector
        self.log = get_logger()

    def forecast(self, metric: str, horizon_minutes: int = 60,
                 method: Optional[ForecastMethod] = None) -> Optional[ForecastResult]:
        """Forecast a metric into the future

        Automatically selects the best method if none specified.
        """
        values = self.collector.get_values(metric)
        if len(values) < 3:
            return None

        current = values[-1]

        # Auto-select method based on data quantity
        if method is None:
            if len(values) >= 10:
                method = ForecastMethod.LINEAR_REGRESSION
            else:
                method = ForecastMethod.MOVING_AVERAGE

        if method == ForecastMethod.MOVING_AVERAGE:
            return self._ma_forecast(metric, values, current, horizon_minutes)
        elif method == ForecastMethod.LINEAR_REGRESSION:
            return self._lr_forecast(metric, values, current, horizon_minutes)
        elif method == ForecastMethod.HOLT_WINTERS:
            return self._hw_forecast(metric, values, current, horizon_minutes)

        return None

    def _ma_forecast(self, metric: str, values: List[float],
                      current: float, horizon: int) -> ForecastResult:
        """Moving average forecast"""
        window = min(10, len(values))
        ma = statistics.mean(values[-window:])

        # Simple forecast: value stays at moving average
        predicted = ma

        # Confidence interval based on recent volatility
        recent = values[-window:]
        std = statistics.stdev(recent) if len(recent) > 1 else 0.0
        ci = (predicted - 1.96 * std, predicted + 1.96 * std)

        # Trend direction
        if len(values) >= 2:
            trend = "up" if predicted > values[-2] else "down" if predicted < values[-2] else "stable"
        else:
            trend = "stable"

        # Accuracy: how well does MA fit recent data?
        errors = [abs(v - ma) for v in recent]
        mae = statistics.mean(errors)
        accuracy = max(0, min(1, 1 - (mae / max(abs(ma), 0.01))))

        return ForecastResult(
            metric=metric,
            current_value=current,
            predicted_value=round(predicted, 4),
            confidence_interval=(round(ci[0], 4), round(ci[1], 4)),
            method=ForecastMethod.MOVING_AVERAGE,
            horizon_minutes=horizon,
            trend_direction=trend,
            accuracy_score=round(accuracy, 4),
        )

    def _lr_forecast(self, metric: str, values: List[float],
                      current: float, horizon: int) -> ForecastResult:
        """Linear regression forecast"""
        n = len(values)
        x = list(range(n))
        y = values

        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)

        # Calculate slope and intercept
        numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        denominator = sum((xi - x_mean) ** 2 for xi in x)
        slope = numerator / denominator if denominator != 0 else 0.0
        intercept = y_mean - slope * x_mean

        # Predict next value
        predicted = slope * (n) + intercept

        # Confidence interval
        residuals = [yi - (slope * xi + intercept) for xi, yi in zip(x, y)]
        residual_std = statistics.stdev(residuals) if len(residuals) > 1 else 0.0
        ci = (predicted - 1.96 * residual_std, predicted + 1.96 * residual_std)

        # R-squared (goodness of fit)
        ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        trend = "up" if slope > 0.01 else "down" if slope < -0.01 else "stable"

        return ForecastResult(
            metric=metric,
            current_value=current,
            predicted_value=round(predicted, 4),
            confidence_interval=(round(ci[0], 4), round(ci[1], 4)),
            method=ForecastMethod.LINEAR_REGRESSION,
            horizon_minutes=horizon,
            trend_direction=trend,
            accuracy_score=round(max(0, r_squared), 4),
        )

    def _hw_forecast(self, metric: str, values: List[float],
                      current: float, horizon: int) -> ForecastResult:
        """Simple Holt-Winters-like forecast (level + trend)

        Full Holt-Winters requires seasonality. We use a simplified
        double exponential smoothing with alpha (level) and beta (trend).
        """
        if len(values) < 3:
            return self._lr_forecast(metric, values, current, horizon)

        # Initialize
        alpha = 0.3  # Level smoothing
        beta = 0.1   # Trend smoothing

        level = values[0]
        trend = values[1] - values[0] if len(values) > 1 else 0.0

        # Smooth
        for i in range(1, len(values)):
            prev_level = level
            level = alpha * values[i] + (1 - alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend

        # Forecast h steps ahead (h = horizon // 5, assuming 5-min intervals)
        h = max(1, horizon // 5)
        predicted = level + h * trend

        # Confidence based on error
        errors = []
        for i in range(1, len(values)):
            fitted = values[i-1] + (values[i] - values[i-1]) / 2
            errors.append(abs(values[i] - fitted))

        mae = statistics.mean(errors) if errors else 0.0
        std = statistics.stdev(errors) if len(errors) > 1 else mae
        ci = (predicted - 1.96 * std, predicted + 1.96 * std)

        accuracy = max(0, min(1, 1 - (mae / max(abs(values[-1]), 0.01))))

        return ForecastResult(
            metric=metric,
            current_value=current,
            predicted_value=round(predicted, 4),
            confidence_interval=(round(ci[0], 4), round(ci[1], 4)),
            method=ForecastMethod.HOLT_WINTERS,
            horizon_minutes=horizon,
            trend_direction="up" if trend > 0.01 else "down" if trend < -0.01 else "stable",
            accuracy_score=round(accuracy, 4),
        )

    def forecast_all(self, horizon_minutes: int = 60
                     ) -> Dict[str, ForecastResult]:
        """Forecast all tracked metrics"""
        results = {}
        for metric in self.collector.metrics:
            result = self.forecast(metric, horizon_minutes)
            if result:
                results[metric] = result
        return results


# ──────────────────────────────────────────────
# Degradation Predictor
# ──────────────────────────────────────────────


class DegradationPredictor:
    """Predicts future degradation levels based on metric forecasts

    Uses configurable thresholds per metric to determine when
    a metric will cross from 'normal' into 'warning' or 'critical'.
    """

    def __init__(self, forecast_engine: ForecastEngine,
                 thresholds: Optional[Dict[str, Dict[str, float]]] = None):
        self.forecast = forecast_engine
        self.log = get_logger()

        # Default thresholds: metric_name → {warning, critical}
        self.thresholds: Dict[str, Dict[str, float]] = thresholds or {
            "latency_ms": {"warning": 200, "critical": 500},
            "error_rate": {"warning": 0.05, "critical": 0.10},
            "memory_mb": {"warning": 512, "critical": 1024},
            "cpu_percent": {"warning": 80, "critical": 95},
            "run_duration_s": {"warning": 300, "critical": 600},
            "drift_rate": {"warning": 3, "critical": 6},
        }

    def predict(self, metric: str,
                horizon_minutes: int = 60) -> Optional[DegradationPrediction]:
        """Predict degradation for a single metric"""
        forecast_result = self.forecast.forecast(metric, horizon_minutes)
        if not forecast_result:
            return None

        current_value = forecast_result.current_value
        predicted_value = forecast_result.predicted_value
        thresholds = self.thresholds.get(metric)

        if not thresholds:
            return None

        # Determine current level
        current_level = self._classify(metric, current_value)

        # Determine predicted level
        predicted_level = self._classify(metric, predicted_value)

        # Estimate time to degradation
        time_to = None
        if predicted_level != DegradationLevel.NORMAL:
            # Rough estimate: proportional to how far in the future
            drift = predicted_value - current_value
            if drift > 0:
                # Calculate time to cross warning threshold
                target = thresholds.get("warning", thresholds.get("critical", 0))
                if target > current_value:
                    ratio = (target - current_value) / drift if drift != 0 else 1
                    time_to = min(horizon_minutes, ratio * horizon_minutes)

        # Determine trigger
        trigger = self._determine_trigger(metric, current_value,
                                           predicted_value, thresholds)

        # Recommendation
        recommendation = self._generate_recommendation(
            metric, predicted_level, predicted_value
        )

        return DegradationPrediction(
            metric=metric,
            current_level=current_level,
            predicted_level=predicted_level,
            time_to_degradation=round(time_to, 1) if time_to is not None else None,
            confidence=forecast_result.accuracy_score,
            trigger=trigger,
            forecast=forecast_result,
            recommendation=recommendation,
        )

    def predict_all(self, horizon_minutes: int = 60
                    ) -> Dict[str, DegradationPrediction]:
        """Predict degradation for all tracked metrics"""
        predictions: Dict[str, DegradationPrediction] = {}
        for metric in self.forecast.collector.metrics:
            pred = self.predict(metric, horizon_minutes)
            if pred:
                predictions[metric] = pred
        return predictions

    def _classify(self, metric: str, value: float) -> DegradationLevel:
        """Classify a metric value into a degradation level"""
        thresholds = self.thresholds.get(metric)
        if not thresholds:
            return DegradationLevel.NORMAL

        if value >= thresholds.get("critical", float("inf")):
            return DegradationLevel.CRITICAL
        if value >= thresholds.get("warning", float("inf")):
            return DegradationLevel.WARNING

        # Near-warning detection (80% of warning)
        warning = thresholds.get("warning")
        if warning and value >= warning * 0.8:
            return DegradationLevel.WATCHING

        return DegradationLevel.NORMAL

    def _determine_trigger(self, metric: str, current: float,
                            predicted: float,
                            thresholds: Dict[str, float]) -> Optional[AlertTrigger]:
        """Determine what triggered the prediction"""
        if predicted > current * 1.5:
            return AlertTrigger.TREND_ACCELERATION
        if predicted >= thresholds.get("critical", float("inf")):
            return AlertTrigger.FORECAST_OVERFLOW
        return AlertTrigger.THRESHOLD_BREACH

    def _generate_recommendation(self, metric: str,
                                  level: DegradationLevel,
                                  value: float) -> str:
        """Generate human-readable recommendation"""
        recs = {
            "latency_ms": "Consider scaling workers or optimizing critical path",
            "error_rate": "Check recent state transitions and validation pipeline",
            "memory_mb": "Enable cache eviction or increase memory allocation",
            "cpu_percent": "Reduce concurrent run processing or add backpressure",
            "run_duration_s": "Optimize adapter calls or reduce iteration count",
            "drift_rate": "Review recent drift patterns — skill emergence may help",
        }

        base_rec = recs.get(metric, "Monitor metric and investigate if trend continues")

        if level == DegradationLevel.CRITICAL:
            return f"🚨 {base_rec} (immediate action required)"
        elif level == DegradationLevel.WARNING:
            return f"⚠️  {base_rec}"
        elif level == DegradationLevel.WATCHING:
            return f"👀 {base_rec} (preventive)"
        return f"✅ Metric within normal range ({value:.2f})"


# ──────────────────────────────────────────────
# AI Degradation Forecaster (Facade)
# ──────────────────────────────────────────────


class AIDegradationForecaster:
    """Facade for all predictive degradation capabilities

    Usage:
        forecaster = AIDegradationForecaster()
        forecaster.record_metric("latency_ms", 150.0)
        predictions = forecaster.predict_all()
        summary = forecaster.generate_report()
    """

    def __init__(self, thresholds: Optional[Dict[str, Dict[str, float]]] = None,
                 llm_provider: Optional[LLMProviderPlugin] = None):
        self.collector = MetricCollector()
        self.forecast_engine = ForecastEngine(self.collector)
        self.predictor = DegradationPredictor(self.forecast_engine, thresholds)
        self.llm_provider = llm_provider
        self._prediction_count = 0

    def record_metric(self, name: str, value: float,
                      labels: Dict[str, str] = None) -> None:
        """Record a metric data point for forecasting"""
        self.collector.record(name, value, labels)

    def predict(self, metric: str, horizon_minutes: int = 60
                ) -> Optional[DegradationPrediction]:
        """Predict degradation for a metric"""
        self._prediction_count += 1
        return self.predictor.predict(metric, horizon_minutes)

    def predict_all(self, horizon_minutes: int = 60
                    ) -> Dict[str, DegradationPrediction]:
        """Predict degradation for all metrics"""
        self._prediction_count += 1
        return self.predictor.predict_all(horizon_minutes)

    def forecast(self, metric: str, horizon_minutes: int = 60
                 ) -> Optional[ForecastResult]:
        """Forecast a single metric"""
        return self.forecast_engine.forecast(metric, horizon_minutes)

    def forecast_all(self, horizon_minutes: int = 60
                     ) -> Dict[str, ForecastResult]:
        """Forecast all metrics"""
        return self.forecast_engine.forecast_all(horizon_minutes)

    def generate_report(self, horizon_minutes: int = 60) -> Dict[str, Any]:
        """Generate comprehensive degradation report"""
        predictions = self.predict_all(horizon_minutes)

        # Overall assessment
        levels = [p.predicted_level for p in predictions.values()]
        critical_count = sum(1 for l in levels if l == DegradationLevel.CRITICAL)
        warning_count = sum(1 for l in levels if l == DegradationLevel.WARNING)

        report = {
            "timestamp": datetime.now().isoformat(),
            "metrics_tracked": len(self.collector.metrics),
            "total_points": self.collector.total_points,
            "degradation_assessment": {
                "critical": critical_count,
                "warning": warning_count,
                "normal": len(levels) - critical_count - warning_count,
                "health_score": max(0, 100 - critical_count * 30 - warning_count * 10),
            },
            "predictions": {k: v.to_dict() for k, v in predictions.items()},
        }

        if self.llm_provider:
            insight = self.generate_whatif(
                f"Predict degradation at horizon {horizon_minutes}m: "
                f"{critical_count} critical, {warning_count} warning"
            )
            if insight:
                report["ai_insight"] = insight

        return report

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "tracked_metrics": len(self.collector.metrics),
            "total_points": self.collector.total_points,
            "prediction_runs": self._prediction_count,
        }

    def generate_whatif(self, scenario: str) -> str:
        """Use LLM for what-if analysis of a degradation scenario

        Args:
            scenario: Natural language description of the scenario

        Returns:
            AI-generated analysis string, or empty string if no LLM provider
        """
        if not self.llm_provider:
            return ""

        try:
            metrics_context = "\n".join(
                f"- {m}: {self.collector.latest_value(m)}"
                for m in self.collector.metrics[-10:]
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a degradation forensics assistant. Given a scenario "
                        "description and current metric values, provide a concise "
                        "what-if analysis of likely impacts, root causes, and "
                        "recommended preventive actions."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Scenario: {scenario}\n\n"
                        f"Current metrics:\n{metrics_context or '(none tracked)'}\n\n"
                        "Provide a brief what-if analysis: what would happen, "
                        "what might cause it, and how to prevent/mitigate."
                    ),
                },
            ]
            result = self.llm_provider.complete(
                messages, temperature=0.3, max_tokens=400
            )
            return result.get("content", "")
        except Exception as e:
            self.log.warning("LLM what-if analysis failed: %s", e)
            return ""

    def set_threshold(self, metric: str, warning: float, critical: float) -> None:
        """Set or update thresholds for a metric"""
        self.predictor.thresholds[metric] = {
            "warning": warning,
            "critical": critical,
        }
