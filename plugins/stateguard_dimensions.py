"""StateGuard Dimension Plugins — Prodinamik Engine Plugin System.

Wraps each of StateGuard's 5 validation dimensions as a
discoverable, enable/disable-able :class:`PluginBase` plugin.

Each plugin:
- Lazily imports its StateGuard validator
- Exposes ``provides_validators`` in the manifest
- Implements ``get_validators()`` for pipeline integration (returns ``Validator`` subclass)
- Implements ``get_tools()`` for CLI/manual invocation

Registered IDs:
    - ``prodinamik.stateguard.structural``
    - ``prodinamik.stateguard.semantic``
    - ``prodinamik.stateguard.quantitative``
    - ``prodinamik.stateguard.behavioral``
    - ``prodinamik.stateguard.security``

Usage::

    from plugins.stateguard_dimensions import StructuralPlugin

    plugin = StructuralPlugin()
    validators = plugin.get_validators()  # → List[Validator]
    result = await validators[0].validate(artifact)
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List

from engine.plugin import PluginBase, PluginManifest, PluginType, PluginTool
from engine.profile import Validator, ValidatorDef, ValidationResult, ValidatorTier


# ──────────────────────────────────────────────
# Lazy loader
# ──────────────────────────────────────────────

_VALIDATOR_CACHE: dict[str, Any] = {}


def _load_validator(dimension: str):
    """Lazy-import and cache a StateGuard dimension validator.

    Args:
        dimension: One of ``structural``, ``semantic``, ``quantitative``,
                   ``behavioral``, ``security``.

    Returns:
        An instantiated validator, or ``None`` if StateGuard is not
        installed or the dimension module errors.
    """
    if dimension in _VALIDATOR_CACHE:
        return _VALIDATOR_CACHE[dimension]

    try:
        import importlib
        # Retry: skip sentence-transformers import (too slow for lazy init)
        import os
        os.environ["SENTENCE_TRANSFORMERS_AUTO"] = "0"

        mod_path = f"stateguard.dimensions.{dimension}"
        mod = importlib.import_module(mod_path)
        # Each dimension has a class named like StructuralValidator etc.
        class_name = f"{dimension.capitalize()}Validator"
        # Special case: quantitative → QuantitativeValidator
        if dimension == "quantitative":
            class_name = "QuantitativeValidator"

        cls = getattr(mod, class_name)
        instance = cls()
        _VALIDATOR_CACHE[dimension] = instance
        return instance
    except (ImportError, AttributeError, Exception):
        _VALIDATOR_CACHE[dimension] = None
        return None


# ──────────────────────────────────────────────
# DimensionValidatorAdapter — Validator subclass
# ──────────────────────────────────────────────


class DimensionValidatorAdapter(Validator):
    """Wraps a StateGuard dimension validator as a Prodinamik :class:`Validator`.

    This bridges the plugin system's :meth:`get_validators` (which must
    return :class:`Validator` instances) with StateGuard's dimension-level
    validation callables.  The returned :class:`ValidationResult` is fully
    compatible with :class:`ValidatorPipeline`.
    """

    def __init__(
        self,
        dimension: str,
        validate_fn: Callable,
        tier: ValidatorTier = ValidatorTier.T2,
        critical: bool = False,
    ) -> None:
        defn = ValidatorDef(
            name=f"stateguard.{dimension}",
            tier=tier,
            critical=critical,
            timeout_seconds=120,
            depends_on=[],
            cache_ttl=3600,
        )
        super().__init__(defn)
        self._validate_fn = validate_fn
        self._dimension = dimension

    async def validate(self, artifact: Any) -> ValidationResult:
        """Run the StateGuard dimension validator on *artifact*.

        Args:
            artifact: The data to validate.

        Returns:
            A Prodinamik :class:`ValidationResult` with ``passed``,
            ``score``, ``message``, and dimension details.
        """
        if artifact is None:
            return ValidationResult(
                passed=False,
                message=f"❌ StateGuard {self._dimension}: artifact is None",
            )

        try:
            result = self._validate_fn(artifact, {})
        except Exception as exc:
            return ValidationResult(
                passed=False,
                message=f"❌ StateGuard {self._dimension} error: {exc}",
                details={"error": str(exc), "dimension": self._dimension},
            )

        # Map StateGuard ValidatorResult → Prodinamik ValidationResult
        score = getattr(result, "score", 0.0)
        if not math.isfinite(score):
            score = 0.0

        passed = bool(getattr(result, "passed", False))

        details: dict[str, Any] = {
            "dimension": self._dimension,
            "source": "stateguard",
            "validator": self.name,
        }
        sg_details = getattr(result, "details", None)
        if sg_details:
            details["stateguard_details"] = sg_details
        sg_error = getattr(result, "error", None)
        if sg_error:
            details["error"] = sg_error

        message = (
            f"✅ StateGuard {self._dimension}: score={score:.1f}"
            if passed
            else f"❌ StateGuard {self._dimension}: score={score:.1f}"
        )

        return ValidationResult(
            passed=passed,
            message=message,
            details=details,
            skipped=False,
            cost_usd=0.0,
        )


# ──────────────────────────────────────────────
# Base mixin for dimension plugins
# ──────────────────────────────────────────────


class _DimensionPluginBase(PluginBase):
    """Base class shared by all dimension plugins."""

    dimension: str = ""  # Override in subclasses
    display_name: str = ""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id=f"prodinamik.stateguard.{self.dimension}",
            name=f"StateGuard {self.display_name}",
            version="1.0.0",
            description=f"StateGuard {self.display_name} validation dimension",
            author="StateGuard",
            license="MIT",
            plugin_type=PluginType.VALIDATOR,
            requires_python=">=3.11",
            requires_engine=">=1.3.0",
            provides_validators=[f"stateguard.{self.dimension}"],
            tags=["stateguard", "validation", self.dimension],
        )

    def _get_validator(self):
        """Return the cached StateGuard validator for this dimension."""
        return _load_validator(self.dimension)

    # ── Plugin Capabilities ────

    def get_validators(self) -> list:  # type: ignore[override]
        """Return a list with one :class:`DimensionValidatorAdapter`.

        Returns:
            A list containing one :class:`Validator` subclass that
            wraps the StateGuard dimension validator.  If the
            dimension validator is unavailable, returns an empty list.
        """
        sg_validator = self._get_validator()
        if sg_validator is None:
            return []

        return [
            DimensionValidatorAdapter(
                dimension=self.dimension,
                validate_fn=sg_validator.validate,
                tier=ValidatorTier.T2,
                critical=False,
            )
        ]

    def get_tools(self) -> List[PluginTool]:
        """Expose a tool for CLI/manual invocation."""

        async def _validate_tool(output: str, context: str = "{}") -> dict:
            import json
            from engine.stateguard_bridge import _map_engine_result

            validator = self._get_validator()
            if validator is None:
                return {"error": f"StateGuard {self.display_name} validator unavailable"}

            ctx = json.loads(context) if isinstance(context, str) else {}
            result = validator.validate(output, ctx)

            # Wrap in a bridge-friendly object
            class FakeResult:
                def __init__(self, score, passed, details):
                    self.overall_score = score
                    self.passed = passed
                    self.tier_path = []
                    self.dimension_scores = {}
                    self.details = details

            bridge_result = _map_engine_result(
                FakeResult(
                    score=result.score,
                    passed=result.passed,
                    details={"validator": f"stateguard.{self.dimension}", "dimension": self.dimension, **result.details},
                ),
                f"stateguard.{self.dimension}",
            )
            return {
                "passed": bridge_result.passed,
                "message": bridge_result.message,
                "details": bridge_result.details,
            }

        return [
            PluginTool(
                name=f"stateguard_{self.dimension}_validate",
                description=f"Run StateGuard {self.display_name} validation on output",
                handler=_validate_tool,
                parameters={
                    "output": {"type": "string", "description": "The output to validate"},
                    "context": {"type": "string", "description": "Optional JSON context dict (default '{}')"},
                },
            )
        ]

    async def health_check(self) -> Dict[str, Any]:
        validator = self._get_validator()
        return {
            "healthy": validator is not None,
            "status": "ok" if validator else "unavailable",
            "dimension": self.dimension,
            "stateguard_available": validator is not None,
        }

    async def on_enable(self) -> None:
        """Validate that StateGuard is importable on enable."""
        if self._get_validator() is None:
            raise RuntimeError(
                f"StateGuard {self.display_name} validator not available. "
                f"Ensure stateguard is installed."
            )

    async def on_disable(self) -> None:
        pass

    async def on_install(self) -> None:
        pass

    async def on_uninstall(self) -> None:
        pass


# ──────────────────────────────────────────────
# 5 Dimension Plugins
# ──────────────────────────────────────────────


class StructuralPlugin(_DimensionPluginBase):
    """StateGuard Structural Validation — JSON schema, regex, type checks."""
    dimension = "structural"
    display_name = "Structural"


class SemanticPlugin(_DimensionPluginBase):
    """StateGuard Semantic Validation — embedding similarity, cross-validation."""
    dimension = "semantic"
    display_name = "Semantic"


class QuantitativePlugin(_DimensionPluginBase):
    """StateGuard Quantitative Validation — outlier detection, Z-Score, Isolation Forest."""
    dimension = "quantitative"
    display_name = "Quantitative"


class BehavioralPlugin(_DimensionPluginBase):
    """StateGuard Behavioral Validation — state machine, snapshot comparison."""
    dimension = "behavioral"
    display_name = "Behavioral"


class SecurityPlugin(_DimensionPluginBase):
    """StateGuard Security Validation — prompt injection, pattern detection."""
    dimension = "security"
    display_name = "Security"
