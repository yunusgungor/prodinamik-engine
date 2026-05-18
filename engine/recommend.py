"""Prodinamik Engine v1.3 — Intelligent Run Recommender

Suggests optimal state transitions, next actions, and
profile configurations based on historical run data.

Architecture:
    HistoricalRunData → TransitionMatrix → SuccessPredictor
                              ↓
                      NextBestAction Recommender

Key features:
    - Transition success probability (based on history)
    - Optimal next state suggestion
    - Profile-specific recommendations
    - Bottleneck detection
"""

from __future__ import annotations

import statistics
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .log import get_logger


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class TransitionRecord:
    """Record of a state transition"""
    run_id: str
    profile: str
    from_state: str
    to_state: str
    timestamp: datetime
    duration_seconds: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransitionStats:
    """Statistics for a specific transition"""
    from_state: str
    to_state: str
    total_attempts: int
    success_count: int
    failure_count: int
    avg_duration: float
    median_duration: float
    last_used: Optional[datetime] = None
    common_errors: List[Tuple[str, int]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_attempts if self.total_attempts > 0 else 0.0

    @property
    def reliability(self) -> str:
        if self.total_attempts < 3:
            return "insufficient_data"
        if self.success_rate >= 0.95:
            return "highly_reliable"
        if self.success_rate >= 0.80:
            return "reliable"
        if self.success_rate >= 0.60:
            return "unstable"
        return "unreliable"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "attempts": self.total_attempts,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_s": round(self.avg_duration, 1),
            "reliability": self.reliability,
        }


@dataclass
class Recommendation:
    """A recommended action for a run"""
    run_id: str
    current_state: str
    recommended_states: List[Tuple[str, float]]  # (state, score)
    best_next_state: str
    confidence: float
    reasoning: str
    estimated_duration: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "current_state": self.current_state,
            "recommended": [
                {"state": s, "score": sc} for s, sc in self.recommended_states
            ],
            "best_next": self.best_next_state,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "estimated_duration_s": self.estimated_duration,
            "warnings": self.warnings,
        }


# ──────────────────────────────────────────────
# Transition History
# ──────────────────────────────────────────────


class TransitionHistory:
    """Collects and analyzes transition records"""

    def __init__(self, max_records: int = 5000):
        self._records: List[TransitionRecord] = []
        self._max_records = max_records
        self.log = get_logger()

    def record(self, run_id: str, profile: str,
               from_state: str, to_state: str,
               duration_seconds: float, success: bool,
               error: Optional[str] = None) -> TransitionRecord:
        """Record a transition"""
        record = TransitionRecord(
            run_id=run_id,
            profile=profile,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(),
            duration_seconds=duration_seconds,
            success=success,
            error=error,
        )
        self._records.append(record)

        # Enforce max
        if len(self._records) > self._max_records:
            self._records.pop(0)

        return record

    def get_transitions(self, from_state: Optional[str] = None,
                        profile: Optional[str] = None,
                        since: Optional[datetime] = None,
                        limit: int = 100) -> List[TransitionRecord]:
        """Query transitions with filters"""
        records = self._records

        if from_state:
            records = [r for r in records if r.from_state == from_state]
        if profile:
            records = [r for r in records if r.profile == profile]
        if since:
            records = [r for r in records if r.timestamp >= since]

        return records[-limit:]

    @property
    def total_count(self) -> int:
        return len(self._records)

    @property
    def total_successful(self) -> int:
        return sum(1 for r in self._records if r.success)

    @property
    def success_rate(self) -> float:
        return self.total_successful / self.total_count if self.total_count > 0 else 0.0


# ──────────────────────────────────────────────
# Transition Analyzer
# ──────────────────────────────────────────────


class TransitionAnalyzer:
    """Analyzes transition patterns and computes statistics"""

    def __init__(self, history: TransitionHistory):
        self.history = history
        self.log = get_logger()

    def analyze(self, from_state: Optional[str] = None,
                profile: Optional[str] = None) -> Dict[str, TransitionStats]:
        """Analyze transitions, optionally filtered"""
        records = self.history._records

        if from_state:
            records = [r for r in records if r.from_state == from_state]
        if profile:
            records = [r for r in records if r.profile == profile]

        # Group by (from_state, to_state)
        groups: Dict[Tuple[str, str], List[TransitionRecord]] = defaultdict(list)
        for r in records:
            groups[(r.from_state, r.to_state)].append(r)

        stats: Dict[str, TransitionStats] = {}
        for (frm, to), recs in groups.items():
            durations = [r.duration_seconds for r in recs]
            successes = [r for r in recs if r.success]
            failures = [r for r in recs if not r.success]

            # Common errors
            error_counter = Counter(
                r.error for r in failures if r.error
            )

            key = f"{frm}→{to}"
            stats[key] = TransitionStats(
                from_state=frm,
                to_state=to,
                total_attempts=len(recs),
                success_count=len(successes),
                failure_count=len(failures),
                avg_duration=statistics.mean(durations) if durations else 0.0,
                median_duration=statistics.median(durations) if durations else 0.0,
                last_used=max(r.timestamp for r in recs),
                common_errors=error_counter.most_common(5),
            )

        return stats

    def get_possible_transitions(self, state: str) -> List[str]:
        """Get all states reachable from a given state"""
        to_states = set()
        for r in self.history._records:
            if r.from_state == state:
                to_states.add(r.to_state)
        return sorted(to_states)

    def get_most_common(self, limit: int = 10) -> List[TransitionStats]:
        """Get the most frequently attempted transitions"""
        all_stats = self.analyze()
        sorted_stats = sorted(
            all_stats.values(),
            key=lambda s: s.total_attempts,
            reverse=True,
        )
        return sorted_stats[:limit]

    def get_bottlenecks(self) -> List[Dict[str, Any]]:
        """Find problematic transitions (low success, high duration)"""
        bottlenecks = []
        for key, stat in self.analyze().items():
            if stat.reliability in ("unstable", "unreliable"):
                bottlenecks.append({
                    "transition": f"{stat.from_state} → {stat.to_state}",
                    "success_rate": stat.success_rate,
                    "attempts": stat.total_attempts,
                    "failures": stat.failure_count,
                    "common_errors": [e for e, _ in stat.common_errors[:3]],
                })
        return bottlenecks


# ──────────────────────────────────────────────
# Run Recommender
# ──────────────────────────────────────────────


class RunRecommender:
    """Recommends optimal next state for a run

    Scoring factors:
    - Historical success rate of the transition
    - Frequency of use (popularity)
    - Recency (last used)
    - Profile compatibility
    """

    def __init__(self, history: TransitionHistory,
                 analyzer: Optional[TransitionAnalyzer] = None):
        self.history = history
        self.analyzer = analyzer or TransitionAnalyzer(history)
        self.log = get_logger()

    def recommend(self, run_id: str, current_state: str,
                  profile: str = "default",
                  top_n: int = 3) -> Optional[Recommendation]:
        """Get the best next state recommendations for a run"""
        possible_targets = self._get_valid_targets(current_state, profile)

        if not possible_targets:
            return None

        # Score each target
        scored: List[Tuple[str, float]] = []
        for target in possible_targets:
            score = self._score_transition(
                current_state, target, profile
            )
            scored.append((target, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        best = scored[0] if scored else None
        if not best:
            return None

        # Generate reasoning
        reasoning = self._generate_reasoning(
            current_state, best[0], profile
        )

        # Estimate duration
        estimated = self._estimate_duration(current_state, best[0])

        # Warnings
        warnings = self._get_warnings(current_state, best[0])

        return Recommendation(
            run_id=run_id,
            current_state=current_state,
            recommended_states=scored[:top_n],
            best_next_state=best[0],
            confidence=best[1],
            reasoning=reasoning,
            estimated_duration=estimated,
            warnings=warnings,
        )

    def _get_valid_targets(self, current_state: str,
                            profile: str) -> List[str]:
        """Get valid next states from history and state machine"""
        # Prefer historically observed transitions
        observed = self.analyzer.get_possible_transitions(current_state)

        # Fallback: common state machine transitions
        common_transitions = {
            "captured": ["idea_review"],
            "idea_review": ["brief_ready", "captured"],
            "brief_ready": ["drafting"],
            "drafting": ["drafting", "verification"],
            "verification": ["drafting", "draft_review"],
            "draft_review": ["approved", "drafting"],
            "approved": ["scheduler_ready"],
            "scheduled": ["published"],
            "published": ["feedback_24h"],
        }

        targets = observed or common_transitions.get(current_state, [])
        return targets

    def _score_transition(self, from_state: str, to_state: str,
                           profile: str) -> float:
        """Score a possible transition (0.0 - 1.0)"""
        key = f"{from_state}→{to_state}"
        all_stats = self.analyzer.analyze(from_state=from_state)

        stat = all_stats.get(key)
        if not stat:
            return 0.3  # Default score for unobserved transitions

        # Success rate score (0-0.5)
        success_score = stat.success_rate * 0.5

        # Frequency score (0-0.3)
        freq_score = min(0.3, stat.total_attempts / 50 * 0.3)

        # Recency score (0-0.2)
        if stat.last_used:
            hours_since = (datetime.now() - stat.last_used).total_seconds() / 3600
            recency_score = max(0, 0.2 - hours_since / 720 * 0.2)  # Decay over 30 days
        else:
            recency_score = 0.0

        return success_score + freq_score + recency_score

    def _generate_reasoning(self, from_state: str, to_state: str,
                             profile: str) -> str:
        """Generate human-readable reasoning for recommendation"""
        key = f"{from_state}→{to_state}"
        all_stats = self.analyzer.analyze(from_state=from_state)
        stat = all_stats.get(key)

        if stat:
            return (
                f"Transition {from_state} → {to_state} has "
                f"{stat.success_rate:.0%} success rate "
                f"({stat.success_count}/{stat.total_attempts} attempts). "
                f"Reliability: {stat.reliability}."
            )
        else:
            return (
                f"No historical data for {from_state} → {to_state}. "
                f"This is a standard transition in the {profile} profile."
            )

    def _estimate_duration(self, from_state: str, to_state: str) -> float:
        """Estimate transition duration in seconds"""
        key = f"{from_state}→{to_state}"
        all_stats = self.analyzer.analyze(from_state=from_state)
        stat = all_stats.get(key)
        return stat.avg_duration if stat else 30.0

    def _get_warnings(self, from_state: str, to_state: str) -> List[str]:
        """Get warnings for a transition"""
        warnings = []
        key = f"{from_state}→{to_state}"
        all_stats = self.analyzer.analyze(from_state=from_state)
        stat = all_stats.get(key)

        if stat:
            if stat.reliability == "unreliable":
                warnings.append(
                    f"Low success rate ({stat.success_rate:.0%}) "
                    f"— consider manual verification"
                )
            if stat.failure_count > 0:
                errors = [e for e, _ in stat.common_errors[:2]]
                if errors:
                    warnings.append(f"Common errors: {', '.join(errors)}")

        return warnings


# ──────────────────────────────────────────────
# AI Recommender (Facade)
# ──────────────────────────────────────────────


class AIRecommender:
    """Facade for intelligent recommendation capabilities

    Usage:
        recommender = AIRecommender()
        recommender.record_transition(...)
        rec = recommender.get_recommendation(run_id, current_state)
        bottlenecks = recommender.find_bottlenecks()
    """

    def __init__(self):
        self.history = TransitionHistory()
        self.analyzer = TransitionAnalyzer(self.history)
        self.recommender = RunRecommender(self.history, self.analyzer)
        self.log = get_logger()

    def record_transition(self, run_id: str, profile: str,
                          from_state: str, to_state: str,
                          duration_seconds: float, success: bool,
                          error: Optional[str] = None) -> TransitionRecord:
        """Record a state transition for learning"""
        return self.history.record(
            run_id, profile, from_state, to_state,
            duration_seconds, success, error,
        )

    def get_recommendation(self, run_id: str, current_state: str,
                           profile: str = "default",
                           top_n: int = 3) -> Optional[Recommendation]:
        """Get the best next state recommendation"""
        return self.recommender.recommend(
            run_id, current_state, profile, top_n
        )

    def find_bottlenecks(self) -> List[Dict[str, Any]]:
        """Find problematic transitions"""
        return self.analyzer.get_bottlenecks()

    def get_most_common_transitions(self, limit: int = 10) -> List[TransitionStats]:
        """Get most common transitions"""
        return self.analyzer.get_most_common(limit)

    def get_transition_stats(self, from_state: Optional[str] = None,
                              profile: Optional[str] = None) -> Dict[str, TransitionStats]:
        """Get detailed transition statistics"""
        return self.analyzer.analyze(from_state, profile)

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive recommendation report"""
        bottlenecks = self.find_bottlenecks()
        common = self.get_most_common_transitions(5)

        return {
            "timestamp": datetime.now().isoformat(),
            "total_transitions": self.history.total_count,
            "overall_success_rate": round(self.history.success_rate, 3),
            "bottlenecks": bottlenecks,
            "most_common": [s.to_dict() for s in common],
            "state_count": len(set(
                r.from_state for r in self.history._records
            ) | set(r.to_state for r in self.history._records)),
        }

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "total_transitions": self.history.total_count,
            "success_rate": self.history.success_rate,
            "bottlenecks": len(self.find_bottlenecks()),
        }
