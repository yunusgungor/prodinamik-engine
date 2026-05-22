"""Tests for StateGuard Dimension Plugins.

Tests cover:
1. Manifest creation — correct IDs, types, validators
2. Health check — available and healthy (with mocks for speed)
3. Validator invocation — returns correct shape (with mocks)
4. Tool creation — tool has correct name and parameters
5. Lazy loading — cache behaviour, graceful fallback

All heavy imports (StateGuard real validators) are mocked to keep
tests fast.  Real-engine integration tests are marked ``slow``.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from plugins.stateguard_dimensions import (
    StructuralPlugin,
    SemanticPlugin,
    QuantitativePlugin,
    BehavioralPlugin,
    SecurityPlugin,
    _load_validator,
    _VALIDATOR_CACHE,
)

ALL_PLUGIN_CLASSES = [
    StructuralPlugin,
    SemanticPlugin,
    QuantitativePlugin,
    BehavioralPlugin,
    SecurityPlugin,
]


# ═══════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the validator cache before each test so isolation is clean."""
    _VALIDATOR_CACHE.clear()


def _mock_validator(passed: bool = True, score: float = 100.0, dimension: str = "structural"):
    """Create a mock StateGuard validator that returns fast."""
    v = MagicMock()
    result = MagicMock()
    result.passed = passed
    result.score = score
    result.dimension.value = dimension
    result.details = {}
    result.error = None
    v.validate.return_value = result
    return v


# ═══════════════════════════════════════════════
# 1. Manifest
# ═══════════════════════════════════════════════


class TestManifest:
    @pytest.mark.parametrize("cls,expected_id,expected_dim", [
        (StructuralPlugin, "prodinamik.stateguard.structural", "structural"),
        (SemanticPlugin, "prodinamik.stateguard.semantic", "semantic"),
        (QuantitativePlugin, "prodinamik.stateguard.quantitative", "quantitative"),
        (BehavioralPlugin, "prodinamik.stateguard.behavioral", "behavioral"),
        (SecurityPlugin, "prodinamik.stateguard.security", "security"),
    ])
    def test_manifest_id(self, cls, expected_id, expected_dim):
        p = cls()
        m = p.manifest
        assert m.id == expected_id
        assert m.plugin_type.value == "validator"
        assert f"stateguard.{expected_dim}" in m.provides_validators

    def test_all_have_correct_type(self):
        for cls in ALL_PLUGIN_CLASSES:
            p = cls()
            assert p.manifest.plugin_type.value == "validator"

    def test_all_provide_validators(self):
        for cls in ALL_PLUGIN_CLASSES:
            p = cls()
            assert len(p.manifest.provides_validators) >= 1

    def test_tags_include_dimension(self):
        for cls in ALL_PLUGIN_CLASSES:
            p = cls()
            assert p.dimension in p.manifest.tags


# ═══════════════════════════════════════════════
# 2. Health check
# ═══════════════════════════════════════════════


class TestHealthCheck:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("cls", ALL_PLUGIN_CLASSES)
    async def test_health_returns_dict(self, cls):
        """health_check() returns the expected keys."""
        with patch.object(cls, "_get_validator", return_value=_mock_validator()):
            p = cls()
            h = await p.health_check()
            assert "healthy" in h
            assert "status" in h
            assert "dimension" in h
            assert h["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_when_unavailable(self):
        """When StateGuard unavailable, health is 'unavailable'."""
        with patch.object(StructuralPlugin, "_get_validator", return_value=None):
            p = StructuralPlugin()
            h = await p.health_check()
            assert h["healthy"] is False
            assert h["status"] == "unavailable"


# ═══════════════════════════════════════════════
# 3. Validator invocation
# ═══════════════════════════════════════════════


class TestValidator:
    @pytest.mark.parametrize("cls", ALL_PLUGIN_CLASSES)
    def test_get_validators_returns_list(self, cls):
        with patch.object(cls, "_get_validator", return_value=_mock_validator()):
            p = cls()
            validators = p.get_validators()
            assert isinstance(validators, list)

    def test_validator_result_shape(self):
        """get_validators() returns a DimensionValidatorAdapter.

        The adapter has an async ``validate()`` method returning
        ``ValidationResult`` with ``passed``/``score``/``dimension``.
        """
        import asyncio
        with patch.object(StructuralPlugin, "_get_validator", return_value=_mock_validator()):
            p = StructuralPlugin()
            validators = p.get_validators()
            assert len(validators) > 0
            adapter = validators[0]
            # DimensionValidatorAdapter has async validate, not __call__
            assert hasattr(adapter, "validate")
            result = asyncio.run(adapter.validate("test"))
            assert result.passed is True
            assert result.details.get("dimension") == "structural"

    def test_validator_fail_propagates(self):
        """Validator passing fail through to the result."""
        import asyncio
        with patch.object(StructuralPlugin, "_get_validator", return_value=_mock_validator(passed=False, score=30.0)):
            p = StructuralPlugin()
            result = asyncio.run(p.get_validators()[0].validate("bad"))
            assert result.passed is False
            assert result.details.get("validator") is not None

    def test_no_validator_when_unavailable(self):
        """When StateGuard validator unavailable, get_validators returns []."""
        with patch.object(StructuralPlugin, "_get_validator", return_value=None):
            p = StructuralPlugin()
            assert p.get_validators() == []


# ═══════════════════════════════════════════════
# 4. Tools
# ═══════════════════════════════════════════════


class TestTools:
    @pytest.mark.parametrize("cls,expected_suffix", [
        (StructuralPlugin, "structural"),
        (SemanticPlugin, "semantic"),
        (QuantitativePlugin, "quantitative"),
        (BehavioralPlugin, "behavioral"),
        (SecurityPlugin, "security"),
    ])
    def test_tool_name(self, cls, expected_suffix):
        p = cls()
        tools = p.get_tools()
        expected = f"stateguard_{expected_suffix}_validate"
        assert any(t.name == expected for t in tools), \
            f"Expected tool {expected} in {[t.name for t in tools]}"

    def test_tool_has_parameters(self):
        p = StructuralPlugin()
        tools = p.get_tools()
        for t in tools:
            assert "output" in t.parameters
            assert "context" in t.parameters

    def test_tool_handler_is_callable(self):
        p = StructuralPlugin()
        tools = p.get_tools()
        for t in tools:
            assert callable(t.handler)


# ═══════════════════════════════════════════════
# 5. Lazy loading
# ═══════════════════════════════════════════════


class TestLazyLoading:
    def test_cache_returns_none_for_bad_dimension(self):
        v = _load_validator("nonexistent")
        assert v is None

    @pytest.mark.asyncio
    async def test_on_enable_raises_for_missing_stateguard(self):
        with patch.object(StructuralPlugin, "_get_validator", return_value=None):
            p = StructuralPlugin()
            with pytest.raises(RuntimeError, match="StateGuard"):
                await p.on_enable()

    @pytest.mark.asyncio
    async def test_on_enable_passes_when_available(self):
        with patch.object(StructuralPlugin, "_get_validator", return_value=_mock_validator()):
            p = StructuralPlugin()
            await p.on_enable()  # Should not raise


# ═══════════════════════════════════════════════
# 6. @pytest.mark.slow: Real StateGuard validators
# ═══════════════════════════════════════════════


@pytest.mark.slow
class TestRealValidator:
    """Tests that load real StateGuard validators (slow first-import).

    Run with::

        pytest tests/test_stateguard_dimensions_plugin.py -xvs -k RealValidator
    """

    @pytest.mark.parametrize("cls,expected_dim", [
        (StructuralPlugin, "structural"),
        (SemanticPlugin, "semantic"),
        (QuantitativePlugin, "quantitative"),
        (BehavioralPlugin, "behavioral"),
        (SecurityPlugin, "security"),
    ])
    def test_real_validator_loads(self, cls, expected_dim):
        _VALIDATOR_CACHE.clear()
        p = cls()
        v = p._get_validator()
        assert v is not None
        assert v.name == expected_dim

    @pytest.mark.parametrize("cls", ALL_PLUGIN_CLASSES)
    def test_real_validator_returns_result(self, cls):
        _VALIDATOR_CACHE.clear()
        p = cls()
        validators = p.get_validators()
        assert len(validators) > 0
        import asyncio
        result = asyncio.run(validators[0].validate("test output"))
        assert result.passed is True
        assert hasattr(result, "passed")
