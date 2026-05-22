"""StateGuard Dimension Plugins — Prodinamik Engine Plugin System.

Wraps each of StateGuard's 5 validation dimensions as a
discoverable, enable/disable-able :class:`PluginBase` plugin.

Each plugin:
- Lazily imports its StateGuard validator
- Exposes ``provides_validators`` in the manifest
- Implements ``get_validators()`` for pipeline integration
- Implements ``get_tools()`` for CLI/manual invocation

Registered IDs:
    - ``prodinamik.stateguard.structural``
    - ``prodinamik.stateguard.semantic``
    - ``prodinamik.stateguard.quantitative``
    - ``prodinamik.stateguard.behavioral``
    - ``prodinamik.stateguard.security``
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from engine.plugin import PluginBase, PluginManifest, PluginType, PluginTool


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

    def get_validators(self) -> List[Callable]:
        """Return a list with one validator callable."""
        validator = self._get_validator()
        if validator is None:
            return []

        def validate(output: Any, context: dict | None = None) -> dict:
            result = validator.validate(output, context)
            return {
                "passed": result.passed,
                "score": result.score,
                "dimension": result.dimension.value if hasattr(result.dimension, "value") else str(result.dimension),
                "details": result.details,
                "error": result.error,
            }

        return [validate]

    def get_tools(self) -> List[PluginTool]:
        """Expose a tool for CLI/manual invocation."""

        async def _validate_tool(output: str, context: str = "{}") -> dict:
            import json
            from engine.stateguard_bridge import _map_engine_result

            validator = self._get_validator()
            if validator is None:
                return {"error": f"StateGuard {self.dimension} validator unavailable"}

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
                description=f"Run StateGuard {self.displayName} validation on output",
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
                f"StateGuard {self.displayName} validator not available. "
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
    displayName = "Structural"


class SemanticPlugin(_DimensionPluginBase):
    """StateGuard Semantic Validation — embedding similarity, cross-validation."""
    dimension = "semantic"
    display_name = "Semantic"
    displayName = "Semantic"


class QuantitativePlugin(_DimensionPluginBase):
    """StateGuard Quantitative Validation — outlier detection, Z-Score, Isolation Forest."""
    dimension = "quantitative"
    display_name = "Quantitative"
    displayName = "Quantitative"


class BehavioralPlugin(_DimensionPluginBase):
    """StateGuard Behavioral Validation — state machine, snapshot comparison."""
    dimension = "behavioral"
    display_name = "Behavioral"
    displayName = "Behavioral"


class SecurityPlugin(_DimensionPluginBase):
    """StateGuard Security Validation — prompt injection, pattern detection."""
    dimension = "security"
    display_name = "Security"
    displayName = "Security"
