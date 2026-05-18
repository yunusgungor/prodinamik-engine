"""Prodinamik Engine v1.3 — AI Drift Detector

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
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .log import get_logger


# ──────────────────────────────────────────────
# Enums & Types
# ──────────────────────────────────────────────


class DriftType(str, Enum):
    FORMAT = "format"
    CONTENT = "content"
    LOGIC = "logic"
    HALLUCINATION = "hallucination"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    STATE_TRANSITION = "state_transition"
    PERFORMANCE = "performance"
    DEPENDENCY = "dependency"
    RESOURCE = "resource"


class DriftSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class DriftEvent:
    """A single drift occurrence"""
    drift_id: str
    drift_type: DriftType
    severity: DriftSeverity
    run_id: str
    state: str
    timestamp: datetime
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_id": self.drift_id,
            "type": self.drift_type.value,
            "severity": self.severity.value,
            "run_id": self.run_id,
            "state": self.state,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class DriftPattern:
    """A recurring drift pattern across runs"""
    pattern_id: str
    drift_type: DriftType
    description: str
    frequency: int  # Number of occurrences
    affected_runs: List[str]
    first_seen: datetime
    last_seen: datetime
    avg_severity: float
    trend: TrendDirection
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_emerging(self) -> bool:
        """A pattern is 'emerging' if seen 3+ times across different runs"""
        return self.frequency >= 3


@dataclass
class EmergenceCandidate:
    """A drift pattern that should become a skill"""
    pattern_id: str
    drift_type: DriftType
    description: str
    occurrence_count: int
    affected_runs: int
    severity_trend: TrendDirection
    recommendation: str
    suggested_skill_name: str
    confidence: float  # 0.0 - 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "type": self.drift_type.value,
            "description": self.description,
            "occurrences": self.occurrence_count,
            "affected_runs": self.affected_runs,
            "severity_trend": self.severity_trend.value,
            "recommendation": self.recommendation,
            "suggested_skill": self.suggested_skill_name,
            "confidence": self.confidence,
        }


@dataclass
class RunQualityMetrics:
    """Quality metrics for a single run"""
    run_id: str
    profile: str
    state: str
    drift_count: int
    severity_score: float  # weighted severity
    iteration_count: int
    verification_score: float  # 0.0 - 1.0
    duration_seconds: float
    anomaly_score: float = 0.0  # 0.0 = normal, 1.0 = highly anomalous


# ──────────────────────────────────────────────
# Drift Pattern Collector
# ──────────────────────────────────────────────


class DriftPatternCollector:
    """Collects and organizes drift events for analysis

    Maintains an in-memory store of drift events with indexing
    by type, run, and time window.
    """

    def __init__(self, max_history: int = 1000):
        self.log = get_logger()
        self._events: List[DriftEvent] = []
        self._max_history = max_history
        self._index_by_type: Dict[DriftType, List[DriftEvent]] = defaultdict(list)
        self._index_by_run: Dict[str, List[DriftEvent]] = defaultdict(list)

    def record(self, event: DriftEvent) -> None:
        """Record a drift event"""
        self._events.append(event)
        self._index_by_type[event.drift_type].append(event)
        self._index_by_run[event.run_id].append(event)

        # Enforce max history (LRU eviction)
        if len(self._events) > self._max_history:
            evicted = self._events.pop(0)
            # Clean indices
            type_list = self._index_by_type.get(evicted.drift_type, [])
            if type_list and type_list[0] is evicted:
                type_list.pop(0)
            run_list = self._index_by_run.get(evicted.run_id, [])
            if run_list and run_list[0] is evicted:
                run_list.pop(0)

    def record_from(self, drift_id: str, drift_type: DriftType,
                    severity: DriftSeverity, run_id: str, state: str,
                    description: str, metadata: Dict[str, Any] = None) -> DriftEvent:
        """Create and record a drift event from fields"""
        event = DriftEvent(
            drift_id=drift_id,
            drift_type=drift_type,
            severity=severity,
            run_id=run_id,
            state=state,
            timestamp=datetime.now(),
            description=description,
            metadata=metadata or {},
        )
        self.record(event)
        return event

    def get_events(self, drift_type: Optional[DriftType] = None,
                   run_id: Optional[str] = None,
                   since: Optional[datetime] = None,
                   limit: int = 100) -> List[DriftEvent]:
        """Query drift events with filters"""
        events = self._events

        if drift_type:
            events = self._index_by_type.get(drift_type, [])
        if run_id:
            events = [e for e in events if e.run_id == run_id]
        if since:
            events = [e for e in events if e.timestamp >= since]

        return events[-limit:]

    def count_by_type(self, since: Optional[datetime] = None) -> Dict[str, int]:
        """Count drift events grouped by type"""
        events = self._events
        if since:
            events = [e for e in events if e.timestamp >= since]
        return dict(Counter(e.drift_type.value for e in events))

    def count_by_run(self, run_id: str) -> int:
        """Count drift events for a specific run"""
        return len(self._index_by_run.get(run_id, []))

    @property
    def total_events(self) -> int:
        return len(self._events)

    @property
    def unique_types(self) -> List[DriftType]:
        return list(self._index_by_type.keys())

    def clear(self) -> None:
        """Clear all collected events"""
        self._events.clear()
        self._index_by_type.clear()
        self._index_by_run.clear()


# ──────────────────────────────────────────────
# Trend Analyzer
# ──────────────────────────────────────────────


class TrendAnalyzer:
    """Analyzes drift trends across runs and time windows

    Uses statistical methods:
    - Moving average for smoothing
    - Linear regression for trend direction
    - Standard deviation for volatility
    """

    def __init__(self, collector: DriftPatternCollector):
        self.collector = collector
        self.log = get_logger()

    def analyze_trend(self, drift_type: Optional[DriftType] = None,
                      window_size: int = 5) -> Dict[str, Any]:
        """Analyze trend for a drift type over recent runs

        Returns trend analysis dict with:
            direction: improving|stable|degrading
            rate: slope of regression line
            volatility: coefficient of variation
            confidence: 0.0 - 1.0
        """
        events = self.collector.get_events(drift_type=drift_type)
        if len(events) < 3:
            return {
                "direction": TrendDirection.STABLE.value,
                "rate": 0.0,
                "volatility": 0.0,
                "confidence": 0.0,
                "data_points": len(events),
            }

        # Group by run (chronological) and count
        run_counts: List[Tuple[int, int]] = []  # (run_index, count)
        run_indices: Dict[str, int] = {}
        for i, event in enumerate(events):
            if event.run_id not in run_indices:
                run_indices[event.run_id] = len(run_indices)
            idx = run_indices[event.run_id]

            # Find existing entry or create
            found = False
            for j, (r_idx, count) in enumerate(run_counts):
                if r_idx == idx:
                    run_counts[j] = (idx, count + 1)
                    found = True
                    break
            if not found:
                run_counts.append((idx, 1))

        if len(run_counts) < 2:
            return {
                "direction": TrendDirection.STABLE.value,
                "rate": 0.0,
                "volatility": 0.0,
                "confidence": 0.3,
                "data_points": len(run_counts),
            }

        # Simple linear regression
        x = [p[0] for p in run_counts]
        y = [p[1] for p in run_counts]
        n = len(x)

        # Calculate slope
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        denominator = sum((xi - x_mean) ** 2 for xi in x)

        slope = numerator / denominator if denominator != 0 else 0.0

        # Volatility (coefficient of variation)
        y_std = statistics.stdev(y) if n > 1 else 0.0
        volatility = y_std / y_mean if y_mean > 0 else 0.0

        # Determine direction
        if abs(slope) < 0.05:
            direction = TrendDirection.STABLE
        elif slope < 0:
            direction = TrendDirection.IMPROVING
        else:
            direction = TrendDirection.DEGRADING

        # Confidence based on data quality
        confidence = min(1.0, n / 10)  # 10+ runs = max confidence

        return {
            "direction": direction.value,
            "rate": round(slope, 4),
            "volatility": round(volatility, 4),
            "confidence": round(confidence, 2),
            "data_points": n,
        }

    def analyze_severity_trend(self, severity_field: str = "severity"
                                ) -> Dict[str, Any]:
        """Analyze how severity changes over time"""
        events = self.collector._events
        if len(events) < 3:
            return {"direction": TrendDirection.STABLE.value,
                    "confidence": 0.0}

        # Map severity to numeric
        severity_map = {
            DriftSeverity.LOW: 1,
            DriftSeverity.MEDIUM: 2,
            DriftSeverity.HIGH: 3,
            DriftSeverity.CRITICAL: 4,
        }

        # Severity over time (by event index)
        severities = [severity_map.get(e.severity, 2) for e in events[-50:]]
        n = len(severities)
        x = list(range(n))
        y = severities

        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        slope = (sum((xi - x_mean) * (yi - y_mean)
                     for xi, yi in zip(x, y))
                 / sum((xi - x_mean) ** 2 for xi in x))

        if abs(slope) < 0.02:
            direction = TrendDirection.STABLE
        elif slope < 0:
            direction = TrendDirection.IMPROVING
        else:
            direction = TrendDirection.DEGRADING

        return {
            "direction": direction.value,
            "rate": round(slope, 4),
            "confidence": round(min(1.0, n / 30), 2),
            "data_points": n,
        }

    def get_volatility(self, drift_type: Optional[DriftType] = None) -> float:
        """Get volatility score for a drift type (0.0 = stable, 1.0+ = volatile)"""
        events = self.collector.get_events(drift_type=drift_type)
        if len(events) < 3:
            return 0.0

        # Group by time windows (hour buckets)
        hour_counts: Dict[str, int] = defaultdict(int)
        for e in events:
            hour_key = e.timestamp.strftime("%Y-%m-%d %H:00")
            hour_counts[hour_key] += 1

        counts = list(hour_counts.values())
        if len(counts) < 2:
            return 0.0

        return statistics.stdev(counts) / statistics.mean(counts) if statistics.mean(counts) > 0 else 0.0


# ──────────────────────────────────────────────
# Emergence Detector
# ──────────────────────────────────────────────


class EmergenceDetector:
    """Detects drift patterns that should become reusable skills

    Criteria for emergence:
    1. 3+ occurrences of the same drift type across different runs
    2. Severity trend is stable or degrading (not improving on its own)
    3. Pattern has a clear remediation strategy
    """

    MIN_OCCURRENCES = 3
    CONFIDENCE_HIGH = 0.85
    CONFIDENCE_MEDIUM = 0.65

    def __init__(self, collector: DriftPatternCollector, trend_analyzer: TrendAnalyzer):
        self.collector = collector
        self.trend_analyzer = trend_analyzer
        self.log = get_logger()

    def detect_candidates(self, min_occurrences: int = MIN_OCCURRENCES
                          ) -> List[EmergenceCandidate]:
        """Scan for drift patterns that should become skills"""
        candidates = []

        # Group events by drift type and description
        pattern_groups: Dict[str, List[DriftEvent]] = defaultdict(list)

        for event in self.collector._events:
            key = f"{event.drift_type.value}:{event.description[:50]}"
            pattern_groups[key].append(event)

        for key, events in pattern_groups.items():
            if len(events) < min_occurrences:
                continue

            drift_type = events[0].drift_type
            description = events[0].description

            # Unique runs affected
            affected_runs = set(e.run_id for e in events)

            # Severity trend
            severity_trend = self.trend_analyzer.analyze_severity_trend()
            sev_dir = TrendDirection(severity_trend["direction"])

            # Calculate confidence
            occurrences = len(events)
            unique_runs = len(affected_runs)
            confidence = self._calculate_confidence(
                occurrences, unique_runs, sev_dir
            )

            if confidence < 0.5:
                continue

            # Generate recommendation and skill name
            recommendation = self._generate_recommendation(drift_type, description)
            skill_name = self._generate_skill_name(drift_type, description)

            candidate = EmergenceCandidate(
                pattern_id=f"EM-{drift_type.value}-{hash(description) % 10000:04d}",
                drift_type=drift_type,
                description=description[:200],
                occurrence_count=occurrences,
                affected_runs=unique_runs,
                severity_trend=sev_dir,
                recommendation=recommendation,
                suggested_skill_name=skill_name,
                confidence=confidence,
            )
            candidates.append(candidate)

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def _calculate_confidence(self, occurrences: int, unique_runs: int,
                               trend: TrendDirection) -> float:
        """Calculate emergence confidence score"""
        # Base: occurrences and run coverage
        occurrence_score = min(1.0, occurrences / 10)
        run_coverage = min(1.0, unique_runs / 5)

        # Trend penalty: if improving, less urgent to skillize
        trend_penalty = {
            TrendDirection.DEGRADING: 1.0,
            TrendDirection.STABLE: 0.8,
            TrendDirection.IMPROVING: 0.4,
        }.get(trend, 0.6)

        return round(occurrence_score * 0.4 + run_coverage * 0.3 + trend_penalty * 0.3, 2)

    def _generate_recommendation(self, drift_type: DriftType,
                                  description: str) -> str:
        """Generate a human-readable recommendation for skill creation"""
        recommendations = {
            DriftType.FORMAT:
                f"Create format validation skill to auto-fix '{description}' patterns",
            DriftType.CONTENT:
                f"Create content template skill to standardize '{description}'",
            DriftType.LOGIC:
                f"Create logic guard skill to prevent '{description}' in state transitions",
            DriftType.HALLUCINATION:
                f"Create hallucination scanner skill to detect '{description}' patterns",
            DriftType.TIMEOUT:
                f"Create timeout handler skill for '{description}'",
            DriftType.VALIDATION:
                f"Create validation rule skill for '{description}'",
            DriftType.STATE_TRANSITION:
                f"Create state guard skill to enforce '{description}' rules",
            DriftType.PERFORMANCE:
                f"Create performance benchmark skill for '{description}'",
            DriftType.DEPENDENCY:
                f"Create dependency checker skill for '{description}'",
            DriftType.RESOURCE:
                f"Create resource monitor skill for '{description}'",
        }
        return recommendations.get(drift_type,
                                   f"Create remediation skill for recurring issue: {description}")

    def _generate_skill_name(self, drift_type: DriftType,
                              description: str) -> str:
        """Generate a skill name from drift pattern"""
        prefix = drift_type.value
        # Extract key terms from description
        words = description.lower().split()[:3]
        suffix = "-".join(w for w in words if len(w) > 3)
        if not suffix:
            suffix = "auto-detect"
        return f"ai-{prefix}-{suffix}"


# ──────────────────────────────────────────────
# Anomaly Scanner
# ──────────────────────────────────────────────


class AnomalyScanner:
    """Statistical anomaly detection on drift data

    Uses z-score and IQR methods to flag unusual patterns.
    """

    def __init__(self, collector: DriftPatternCollector):
        self.collector = collector
        self.log = get_logger()

    def scan_runs(self) -> List[Dict[str, Any]]:
        """Scan for anomalous runs based on drift patterns"""
        anomalies = []

        # Group events by run
        run_events: Dict[str, List[DriftEvent]] = defaultdict(list)
        for event in self.collector._events:
            run_events[event.run_id].append(event)

        if len(run_events) < 3:
            return anomalies

        # Calculate per-run drift counts
        run_counts = {run_id: len(events)
                      for run_id, events in run_events.items()}
        counts = list(run_counts.values())

        if len(counts) < 3:
            return anomalies

        # Z-score method
        mean = statistics.mean(counts)
        stdev = statistics.stdev(counts) if len(counts) > 1 else 0.0

        for run_id, count in run_counts.items():
            if stdev > 0:
                z_score = (count - mean) / stdev
                if abs(z_score) > 2.0:  # Threshold: 2 sigma
                    anomalies.append({
                        "run_id": run_id,
                        "drift_count": count,
                        "z_score": round(z_score, 2),
                        "mean": round(mean, 2),
                        "std": round(stdev, 2),
                        "severity": "high" if abs(z_score) > 3.0 else "medium",
                    })

        return anomalies

    def scan_types(self) -> List[Dict[str, Any]]:
        """Scan for anomalous drift type distributions"""
        type_counts = self.collector.count_by_type()
        if len(type_counts) < 3:
            return []

        counts = list(type_counts.values())
        mean = statistics.mean(counts)
        stdev = statistics.stdev(counts) if len(counts) > 1 else 0.0

        anomalies = []
        for dtype, count in type_counts.items():
            if stdev > 0:
                z_score = (count - mean) / stdev
                if z_score > 2.0:  # Unusually high occurrence
                    anomalies.append({
                        "drift_type": dtype,
                        "count": count,
                        "z_score": round(z_score, 2),
                        "percentage": round(count / sum(counts) * 100, 1),
                    })

        return anomalies


# ──────────────────────────────────────────────
# AI Drift Detector (Facade)
# ──────────────────────────────────────────────


class AIDriftDetector:
    """Facade for all AI-driven drift detection capabilities

    Usage:
        detector = AIDriftDetector()
        detector.record_drift(...)

        # Analysis
        trends = detector.analyze_trends()
        candidates = detector.find_emergence_candidates()
        anomalies = detector.scan_anomalies()

        # Report
        report = detector.generate_report()
    """

    def __init__(self, max_history: int = 1000):
        self.collector = DriftPatternCollector(max_history=max_history)
        self.trend_analyzer = TrendAnalyzer(self.collector)
        self.emergence_detector = EmergenceDetector(
            self.collector, self.trend_analyzer
        )
        self.anomaly_scanner = AnomalyScanner(self.collector)
        self.log = get_logger()
        self._analysis_count = 0

    def record_drift(self, drift_id: str, drift_type: DriftType,
                     severity: DriftSeverity, run_id: str, state: str,
                     description: str, **metadata) -> DriftEvent:
        """Record a drift event for AI analysis"""
        return self.collector.record_from(
            drift_id=drift_id,
            drift_type=drift_type,
            severity=severity,
            run_id=run_id,
            state=state,
            description=description,
            metadata=metadata,
        )

    def analyze_trends(self, window_size: int = 5) -> Dict[str, Any]:
        """Analyze all drift trends"""
        self._analysis_count += 1
        trends = {}
        for dtype in DriftType:
            trend = self.trend_analyzer.analyze_trend(
                drift_type=dtype, window_size=window_size
            )
            if trend["data_points"] > 0:
                trends[dtype.value] = trend

        return {
            "timestamp": datetime.now().isoformat(),
            "trends": trends,
            "total_events": self.collector.total_events,
        }

    def find_emergence_candidates(self, min_occurrences: int = 3
                                   ) -> List[EmergenceCandidate]:
        """Find drift patterns that should become skills"""
        return self.emergence_detector.detect_candidates(
            min_occurrences=min_occurrences
        )

    def scan_anomalies(self) -> Dict[str, Any]:
        """Scan for anomalies in drift data"""
        return {
            "anomalous_runs": self.anomaly_scanner.scan_runs(),
            "anomalous_types": self.anomaly_scanner.scan_types(),
        }

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive AI drift report"""
        trends = self.analyze_trends()
        candidates = self.find_emergence_candidates()
        anomalies = self.scan_anomalies()

        # Determine overall health
        degrading_trends = sum(
            1 for t in trends["trends"].values()
            if t["direction"] == TrendDirection.DEGRADING.value
        )
        total_trends = len(trends["trends"])
        health_score = max(0, 100 - (degrading_trends / max(total_trends, 1)) * 50)

        # Reduce score for anomalies
        anomaly_count = len(anomalies.get("anomalous_runs", []))
        health_score = max(0, health_score - anomaly_count * 10)

        return {
            "timestamp": datetime.now().isoformat(),
            "health_score": round(health_score, 1),
            "total_events": self.collector.total_events,
            "trends": trends["trends"],
            "emergence_candidates": [c.to_dict() for c in candidates],
            "anomalies": anomalies,
            "degrading_trends": degrading_trends,
            "stable_trends": total_trends - degrading_trends,
        }

    @property
    def metrics(self) -> Dict[str, Any]:
        """Usage metrics for dashboard"""
        return {
            "total_events": self.collector.total_events,
            "unique_types": len(self.collector.unique_types),
            "analysis_count": self._analysis_count,
        }

    def reset(self) -> None:
        """Reset all collected data"""
        self.collector.clear()
        self._analysis_count = 0
