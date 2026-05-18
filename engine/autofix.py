"""Prodinamik Engine v1.3 — Auto-Remediation

Automated recovery actions for common failure patterns.
Matches failure signatures to remediation strategies and
executes fixes automatically.

Architecture:
    FailurePatterns DB → FailureMatcher → RemediationEngine
                            ↓
                    Execute Action (auto/manual)

Pattern types:
    - Transient: retry, backoff
    - State: rollback, state fix
    - Resource: cleanup, eviction
    - Config: reset, reload
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .log import get_logger


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class FailureClass(str, Enum):
    TRANSIENT = "transient"        # Temporary, retry fixes
    STATE = "state"                # State machine error
    RESOURCE = "resource"          # Memory, disk, CPU
    VALIDATION = "validation"      # Validation failure
    DEPENDENCY = "dependency"      # External service
    CONFIG = "config"              # Configuration
    TIMEOUT = "timeout"            # Timeout
    UNKNOWN = "unknown"            # Unclassified


class RemediationType(str, Enum):
    RETRY = "retry"                # Simple retry
    BACKOFF = "backoff"            # Exponential backoff retry
    ROLLBACK = "rollback"          # State rollback
    CLEANUP = "cleanup"            # Resource cleanup
    RESET = "reset"                # Reset to defaults
    RECONFIGURE = "reconfigure"    # Update config
    ESCALATE = "escalate"          # Manual intervention needed


class AutoRemediationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ESCALATED = "escalated"


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class FailureSignature:
    """Signature of a failure pattern"""
    name: str
    failure_class: FailureClass
    match_patterns: List[str]  # Substrings/patterns to match in error messages
    description: str = ""

    def matches(self, error_message: str) -> bool:
        """Check if an error message matches this signature"""
        error_lower = error_message.lower()
        return any(pattern.lower() in error_lower
                    for pattern in self.match_patterns)


@dataclass
class RemediationAction:
    """A remediation action to take"""
    action_type: RemediationType
    description: str
    handler: Optional[Callable] = None
    params: Dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 3
    cooldown_seconds: float = 10.0

    async def execute(self, context: Dict[str, Any]) -> bool:
        """Execute the remediation action"""
        if self.handler:
            try:
                result = self.handler(context, **self.params)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except Exception as e:
                get_logger().error("Remediation action '%s' failed: %s", self.description, e)
                return False
        return False


@dataclass
class RemediationPlan:
    """A complete remediation plan for a failure"""
    signature_name: str
    failure_class: FailureClass
    confidence: float  # 0.0 - 1.0
    actions: List[RemediationAction]
    auto_execute: bool = False  # True = auto, False = require approval
    timeout_seconds: float = 60.0

    @property
    def has_auto_remediation(self) -> bool:
        return self.auto_execute and len(self.actions) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature_name,
            "class": self.failure_class.value,
            "confidence": self.confidence,
            "actions": [a.description for a in self.actions],
            "auto_execute": self.auto_execute,
            "action_count": len(self.actions),
        }


@dataclass
class RemediationResult:
    """Result of a remediation execution"""
    plan_name: str
    status: AutoRemediationStatus
    action_results: List[Tuple[str, bool]] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan_name,
            "status": self.status.value,
            "actions": [
                {"description": d, "success": s}
                for d, s in self.action_results
            ],
            "duration_s": round(self.duration_seconds, 1),
            "error": self.error,
        }


# ──────────────────────────────────────────────
# Built-in Failure Patterns
# ──────────────────────────────────────────────


def create_default_patterns() -> List[FailureSignature]:
    """Create default failure patterns for the engine"""
    return [
        FailureSignature(
            name="connection_timeout",
            failure_class=FailureClass.TRANSIENT,
            match_patterns=["timeout", "connection refused",
                            "connection reset", "network unreachable"],
            description="Network connection timeout",
        ),
        FailureSignature(
            name="rate_limit",
            failure_class=FailureClass.TRANSIENT,
            match_patterns=["rate limit", "too many requests",
                            "429", "throttled"],
            description="API rate limit exceeded",
        ),
        FailureSignature(
            name="state_invalid",
            failure_class=FailureClass.STATE,
            match_patterns=["invalid state", "state not found",
                            "transition not allowed", "illegal state"],
            description="Invalid state machine transition",
        ),
        FailureSignature(
            name="state_machine_stuck",
            failure_class=FailureClass.STATE,
            match_patterns=["stuck in loop", "max iterations",
                            "infinite loop", "timeout in state"],
            description="State machine stuck in loop",
        ),
        FailureSignature(
            name="memory_pressure",
            failure_class=FailureClass.RESOURCE,
            match_patterns=["out of memory", "memory error",
                            "cannot allocate", "OOM"],
            description="Memory allocation failure",
        ),
        FailureSignature(
            name="disk_full",
            failure_class=FailureClass.RESOURCE,
            match_patterns=["disk full", "no space left",
                            "disk quota", "write failed"],
            description="Disk space exhausted",
        ),
        FailureSignature(
            name="validation_failed",
            failure_class=FailureClass.VALIDATION,
            match_patterns=["validation failed", "invalid format",
                            "schema error", "validation error"],
            description="Input validation error",
        ),
        FailureSignature(
            name="dependency_down",
            failure_class=FailureClass.DEPENDENCY,
            match_patterns=["service unavailable", "503",
                            "dependency failed", "upstream"],
            description="Dependency service unavailable",
        ),
        FailureSignature(
            name="config_error",
            failure_class=FailureClass.CONFIG,
            match_patterns=["config error", "invalid config",
                            "configuration error", "missing config"],
            description="Configuration error",
        ),
    ]


# ──────────────────────────────────────────────
# Failure Matcher
# ──────────────────────────────────────────────


class FailureMatcher:
    """Matches error messages to known failure patterns"""

    def __init__(self, patterns: Optional[List[FailureSignature]] = None):
        self.patterns = patterns or create_default_patterns()
        self.log = get_logger()

    def match(self, error_message: str) -> List[Tuple[FailureSignature, float]]:
        """Match an error message to known patterns

        Returns list of (signature, confidence) sorted by confidence.
        """
        matches = []
        error_lower = error_message.lower()

        for pattern in self.patterns:
            matching_patterns = [
                p for p in pattern.match_patterns
                if p.lower() in error_lower
            ]
            if matching_patterns:
                # Confidence based on how many patterns matched
                confidence = len(matching_patterns) / len(pattern.match_patterns)
                confidence = min(1.0, confidence * 2)  # Boost for partial matches
                matches.append((pattern, round(confidence, 2)))

        matches.sort(key=lambda m: m[1], reverse=True)
        return matches

    def best_match(self, error_message: str) -> Optional[Tuple[FailureSignature, float]]:
        """Get the single best match for an error"""
        matches = self.match(error_message)
        return matches[0] if matches else None

    def classify(self, error_message: str) -> FailureClass:
        """Classify an error into a failure class"""
        match = self.best_match(error_message)
        if match:
            return match[0].failure_class
        return FailureClass.UNKNOWN

    def add_pattern(self, pattern: FailureSignature) -> None:
        """Add a custom failure pattern"""
        self.patterns.append(pattern)

    def add_pattern_from(self, name: str, failure_class: FailureClass,
                          match_patterns: List[str],
                          description: str = "") -> FailureSignature:
        """Create and add a failure pattern"""
        pattern = FailureSignature(
            name=name,
            failure_class=failure_class,
            match_patterns=match_patterns,
            description=description,
        )
        self.add_pattern(pattern)
        return pattern


# ──────────────────────────────────────────────
# Auto Remediator
# ──────────────────────────────────────────────


class AutoRemediator:
    """Executes automated remediation for known failure patterns

    Usage:
        remediator = AutoRemediator()
        plan = remediator.create_plan(error_message)
        result = await remediator.execute(plan, context)
    """

    def __init__(self, matcher: Optional[FailureMatcher] = None):
        self.matcher = matcher or FailureMatcher()
        self.log = get_logger()
        self._results: List[RemediationResult] = []
        self._history: Dict[str, int] = defaultdict(int)  # pattern → count
        self._cooldowns: Dict[str, datetime] = {}

    def create_plan(self, error_message: str,
                    run_context: Optional[Dict[str, Any]] = None
                    ) -> Optional[RemediationPlan]:
        """Create a remediation plan for an error"""
        match = self.matcher.best_match(error_message)
        if not match:
            return None

        signature, confidence = match
        self._history[signature.name] += 1

        # Generate actions based on failure class
        actions = self._generate_actions(signature)

        # Auto-execute if high confidence and transient
        auto_exec = (
            confidence >= 0.5
            and signature.failure_class in (
                FailureClass.TRANSIENT,
                FailureClass.TIMEOUT,
            )
        )

        return RemediationPlan(
            signature_name=signature.name,
            failure_class=signature.failure_class,
            confidence=confidence,
            actions=actions,
            auto_execute=auto_exec,
            timeout_seconds=self._estimate_timeout(signature),
        )

    def _generate_actions(self, signature: FailureSignature) -> List[RemediationAction]:
        """Generate appropriate actions for a failure signature"""
        class_actions = {
            FailureClass.TRANSIENT: [
                RemediationAction(
                    RemediationType.BACKOFF,
                    "Retry with exponential backoff",
                    max_attempts=3,
                    cooldown_seconds=2.0,
                ),
                RemediationAction(
                    RemediationType.RETRY,
                    "Simple retry after cooldown",
                    max_attempts=1,
                    cooldown_seconds=5.0,
                ),
            ],
            FailureClass.STATE: [
                RemediationAction(
                    RemediationType.ROLLBACK,
                    "Rollback to previous valid state",
                    max_attempts=1,
                ),
                RemediationAction(
                    RemediationType.RESET,
                    "Reset state machine to initial state",
                    max_attempts=1,
                ),
            ],
            FailureClass.RESOURCE: [
                RemediationAction(
                    RemediationType.CLEANUP,
                    "Run cache eviction and garbage collection",
                ),
                RemediationAction(
                    RemediationType.RESET,
                    "Reset resource limits to defaults",
                ),
            ],
            FailureClass.VALIDATION: [
                RemediationAction(
                    RemediationType.RETRY,
                    "Retry with corrected input",
                    max_attempts=2,
                ),
            ],
            FailureClass.DEPENDENCY: [
                RemediationAction(
                    RemediationType.BACKOFF,
                    "Backoff and retry dependency call",
                    max_attempts=3,
                    cooldown_seconds=5.0,
                ),
                RemediationAction(
                    RemediationType.ESCALATE,
                    "Escalate to operator if dependency remains down",
                ),
            ],
            FailureClass.CONFIG: [
                RemediationAction(
                    RemediationType.RECONFIGURE,
                    "Reload configuration from defaults",
                ),
                RemediationAction(
                    RemediationType.ESCALATE,
                    "Escalate config issue to operator",
                ),
            ],
        }

        return class_actions.get(
            signature.failure_class,
            [RemediationAction(
                RemediationType.ESCALATE,
                "Unknown failure — escalate to operator",
            )],
        )

    def _estimate_timeout(self, signature: FailureSignature) -> float:
        """Estimate timeout for a remediation plan"""
        timeouts = {
            FailureClass.TRANSIENT: 30.0,
            FailureClass.STATE: 15.0,
            FailureClass.RESOURCE: 60.0,
            FailureClass.VALIDATION: 10.0,
            FailureClass.DEPENDENCY: 45.0,
            FailureClass.CONFIG: 10.0,
        }
        return timeouts.get(signature.failure_class, 30.0)

    async def execute(self, plan: RemediationPlan,
                      context: Dict[str, Any]) -> RemediationResult:
        """Execute a remediation plan"""
        result = RemediationResult(
            plan_name=plan.signature_name,
            status=AutoRemediationStatus.PENDING,
            started_at=datetime.now(),
        )

        # Check cooldown
        if plan.signature_name in self._cooldowns:
            if datetime.now() < self._cooldowns[plan.signature_name]:
                result.status = AutoRemediationStatus.SKIPPED
                result.error = "In cooldown period"
                self._results.append(result)
                return result

        if not plan.auto_execute:
            result.status = AutoRemediationStatus.SKIPPED
            result.error = "Manual approval required"
            self._results.append(result)
            return result

        result.status = AutoRemediationStatus.RUNNING

        for action in plan.actions:
            if action.action_type == RemediationType.ESCALATE:
                result.status = AutoRemediationStatus.ESCALATED
                break

            try:
                success = await asyncio.wait_for(
                    action.execute(context),
                    timeout=plan.timeout_seconds,
                )
            except asyncio.TimeoutError:
                success = False
            except Exception as e:
                success = False
                self.log.error(f"Remediation action failed: {e}")

            result.action_results.append((action.description, success))

            if success:
                break  # First successful action stops
            else:
                # Set cooldown before retry
                await asyncio.sleep(action.cooldown_seconds)

        # Final status
        any_success = any(success for _, success in result.action_results)
        result.status = AutoRemediationStatus.SUCCESS if any_success else AutoRemediationStatus.FAILED
        result.completed_at = datetime.now()
        result.duration_seconds = (
            result.completed_at - result.started_at
        ).total_seconds()

        # Set cooldown
        if result.status == AutoRemediationStatus.SUCCESS:
            self._cooldowns[plan.signature_name] = datetime.now() + timedelta(minutes=5)
        elif result.status == AutoRemediationStatus.FAILED:
            self._cooldowns[plan.signature_name] = datetime.now() + timedelta(minutes=1)

        self._results.append(result)
        return result

    async def remediate(self, error_message: str,
                         context: Dict[str, Any]) -> Optional[RemediationResult]:
        """One-shot: match error → create plan → execute"""
        plan = self.create_plan(error_message, context)
        if not plan:
            return None
        return await self.execute(plan, context)

    def get_stats(self) -> Dict[str, Any]:
        """Get remediation statistics"""
        total = len(self._results)
        success = sum(1 for r in self._results
                      if r.status == AutoRemediationStatus.SUCCESS)
        failed = sum(1 for r in self._results
                     if r.status == AutoRemediationStatus.FAILED)
        skipped = sum(1 for r in self._results
                      if r.status == AutoRemediationStatus.SKIPPED)

        return {
            "total_incidents": total,
            "auto_remediated": success,
            "failed": failed,
            "skipped": skipped,
            "success_rate": (success / total) if total > 0 else 0.0,
            "class_distribution": dict(
                Counter(
                    r.status.value for r in self._results
                )
            ),
            "pattern_frequency": dict(
                sorted(
                    self._history.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10]
            ),
        }

    @property
    def recent_results(self, limit: int = 10) -> List[RemediationResult]:
        return self._results[-limit:]
