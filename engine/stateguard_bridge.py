"""StateGuard → Prodinamik Engine Bridge.

Wraps StateGuard's :class:`ValidationEngine` as a Prodinamik
:class:`Validator` so that every Prodinamik pipeline step can be
validated through StateGuard's multi-dimensional cascade pipeline.

Usage::

    from engine.stateguard_bridge import StateGuardValidator, make_stateguard_def

    defn = make_stateguard_def(tier=ValidatorTier.T1, critical=True)
    validator = StateGuardValidator(defn)
    result = await validator.validate(artifact)
"""

from __future__ import annotations

import math
from typing import Any

from engine.profile import Validator, ValidatorDef, ValidatorTier, ValidationResult

# ──────────────────────────────────────────────
# Lazy import — StateGuard is optional at runtime
# ──────────────────────────────────────────────

_StateGuardEngine = None


def _get_stateguard_engine():
    """Lazy-import and cache the StateGuard :class:`ValidationEngine`."""
    global _StateGuardEngine
    if _StateGuardEngine is not None:
        return _StateGuardEngine
    try:
        from stateguard import ValidationEngine as _SGEngine

        _StateGuardEngine = _SGEngine
    except ImportError:
        _StateGuardEngine = False  # Sentinel: import failed
    return _StateGuardEngine


# ──────────────────────────────────────────────
# ValidatorDef factory
# ──────────────────────────────────────────────


def make_stateguard_def(
    name: str = "stateguard",
    tier: ValidatorTier = ValidatorTier.T1,
    critical: bool = True,
    timeout_seconds: int = 120,
) -> ValidatorDef:
    """Create a :class:`ValidatorDef` pre-configured for StateGuard.

    Args:
        name: Validator name (default ``\\\"stateguard\\\"``).
        tier: Prodinamik validator tier. StateGuard's cascade
              pipeline handles all tiers internally, but the
              Prodinamik pipeline slot can be T1 (fast, fail-fast),
              T2 (parallel), or T3 (sequential).
        critical: If True, a failed validation immediately stops
                  the pipeline. Recommended for security/structural
                  validators.
        timeout_seconds: Per-request timeout.

    Returns:
        A :class:`ValidatorDef` that can be registered on any profile.
    """
    return ValidatorDef(
        name=name,
        tier=tier,
        critical=critical,
        timeout_seconds=timeout_seconds,
        depends_on=[],
        cache_ttl=0,  # No cache — each validation input is unique
    )


# ──────────────────────────────────────────────
# StateGuardValidator
# ──────────────────────────────────────────────


class StateGuardValidator(Validator):
    """Prodinamik Validator that delegates to StateGuard's cascade pipeline.

    StateGuard runs a multi-tier cascade (Tier 1 Embedding → Tier 2
    Ensemble → Tier 3 LLM) and multi-dimensional checks (structural,
    semantic, quantitative, behavioral, security).  This bridge exposes
    all of that as a single Prodinamik :class:`Validator`.

    .. note::
       StateGuard is imported lazily so that the bridge does **not**
       block Prodinamik startup when StateGuard is not installed.
    """

    def __init__(self, defn: ValidatorDef, engine: Any | None = None) -> None:
        super().__init__(defn)
        self._engine_instance = engine  # Allow injection for testing

    # ── Properties ────────────────────────────

    @property
    def engine(self):
        """Lazy-initialised StateGuard :class:`ValidationEngine` instance."""
        if self._engine_instance is not None:
            return self._engine_instance

        EngineCls = _get_stateguard_engine()
        if EngineCls is False:
            raise RuntimeError(
                "StateGuard is not installed. "
                "Run: pip install stateguard"
            )
        if EngineCls is None:
            raise RuntimeError(
                "StateGuard import not yet attempted. "
                "Call validate() to trigger lazy init."
            )

        self._engine_instance = EngineCls()
        return self._engine_instance

    # ── Validator interface ───────────────────

    async def validate(self, artifact: Any) -> ValidationResult:
        """Run StateGuard's full cascade pipeline on *artifact*.

        Args:
            artifact: The data to validate.  Passed as the ``output``
                      argument to :meth:`ValidationEngine.validate`.

        Returns:
            A Prodinamik :class:`ValidationResult` mapped from
            StateGuard's :class:`EngineResult`.
        """
        if artifact is None:
            return ValidationResult(
                passed=False,
                message="❌ StateGuard: artifact is None",
            )

        try:
            sg_result = self.engine.validate(artifact, context=None)
        except Exception as exc:
            return ValidationResult(
                passed=False,
                message=f"❌ StateGuard error: {exc}",
                details={"error": str(exc), "validator": self.name},
            )

        return _map_engine_result(sg_result, self.name)

    async def auto_fix(self, artifact: Any) -> Any:
        """StateGuard does **not** implement auto-fix — pass through."""
        return artifact

    def explain(self, result: ValidationResult) -> str:
        """Human-readable explanation of the validation outcome."""
        if result.passed:
            return f"✅ {self.name}: passed"
        return f"❌ {self.name}: {result.message}"

    # ── Diagnostics ───────────────────────────

    def health(self) -> dict:
        """Return diagnostic information about the StateGuard bridge."""
        if self._engine_instance is None:
            # Engine explicitly not injected — unavailable
            return {
                "status": "unavailable",
                "stateguard_available": False,
            }
        try:
            engine = self.engine
            return {
                "status": "ok",
                "engine": type(engine).__module__,
                "version": getattr(engine, "name", "unknown"),
                "stateguard_available": True,
            }
        except RuntimeError:
            return {
                "status": "unavailable",
                "stateguard_available": False,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
            }


# ──────────────────────────────────────────────
# Result mapper
# ──────────────────────────────────────────────


def _map_engine_result(
    sg_result: Any,
    validator_name: str,
) -> ValidationResult:
    """Map a StateGuard :class:`EngineResult` → Prodinamik :class:`ValidationResult`.

    Args:
        sg_result: The result returned by
                   :meth:`ValidationEngine.validate`.
        validator_name: Used in the message string for context.

    Returns:
        A :class:`ValidationResult` consumable by Prodinamik's
        :class:`ValidatorPipeline`.
    """
    # Safety: IEEE 754 NaN/Inf guard (StateGuard already clamps,
    # but we guard the bridge boundary too)
    score = sg_result.overall_score if hasattr(sg_result, "overall_score") else 0.0
    if not math.isfinite(score):
        score = 0.0

    passed = sg_result.passed if hasattr(sg_result, "passed") else False

    # Build human-readable message
    tier_path = getattr(sg_result, "tier_path", [])
    tier_hint = f"tier_path={tier_path}" if tier_path else "no-tiers"

    if passed:
        message = f"✅ StateGuard ({tier_hint}): score={score:.1f}"
    else:
        message = f"❌ StateGuard ({tier_hint}): score={score:.1f}"

    # Carry StateGuard's detail into details
    details: dict[str, Any] = {
        "overall_score": score,
        "tier_path": tier_path,
        "validator": validator_name,
        "source": "stateguard",
    }

    if hasattr(sg_result, "dimension_scores"):
        details["dimension_scores"] = sg_result.dimension_scores

    if hasattr(sg_result, "details") and sg_result.details:
        details["stateguard_details"] = sg_result.details

    # Cost: StateGuard doesn't track cost, but make it explicit
    return ValidationResult(
        passed=passed,
        message=message,
        details=details,
        skipped=False,
        cost_usd=0.0,
    )
