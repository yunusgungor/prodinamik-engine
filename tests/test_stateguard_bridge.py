"""Tests for StateGuard → Prodinamik Engine Bridge.

Tests cover:
1. :func:`make_stateguard_def` — ValidatorDef factory
2. :class:`StateGuardValidator` — with mock engine injection
3. :func:`_map_engine_result` — EngineResult → ValidationResult mapping
4. Profile integration — StateGuard in SoftwareProfile
5. Edge cases — None input, NaN scores, missing attributes
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from engine.profile import ValidatorTier, ValidationResult
from engine.stateguard_bridge import (
    StateGuardValidator,
    make_stateguard_def,
    _map_engine_result,
)


# ═══════════════════════════════════════════════
# 1. make_stateguard_def
# ═══════════════════════════════════════════════


class TestMakeStateGuardDef:
    def test_default_tier(self):
        """Default tier is T1 if not specified."""
        defn = make_stateguard_def()
        assert defn.name == "stateguard"
        assert defn.tier == ValidatorTier.T1
        assert defn.critical is True
        assert defn.cache_ttl == 0  # No caching

    def test_custom_name(self):
        defn = make_stateguard_def(name="my-sg")
        assert defn.name == "my-sg"

    def test_tier2(self):
        defn = make_stateguard_def(tier=ValidatorTier.T2)
        assert defn.tier == ValidatorTier.T2

    def test_non_critical(self):
        defn = make_stateguard_def(critical=False)
        assert defn.critical is False


# ═══════════════════════════════════════════════
# 2. StateGuardValidator — engine injection
# ═══════════════════════════════════════════════


def _make_mock_engine(**overrides):
    """Create a mock StateGuard engine result.

    Defaults to a PASS result.  Override keys:
    ``overall_score``, ``passed``, ``tier_path``, ``dimension_scores``.
    """
    engine = MagicMock()
    result = MagicMock()
    result.overall_score = overrides.get("overall_score", 85.0)
    result.passed = overrides.get("passed", True)
    result.tier_path = overrides.get("tier_path", [1])
    result.dimension_scores = overrides.get("dimension_scores", {"tier_1": 85.0})
    result.details = overrides.get("details", {"config": {"tier1_threshold": 80.0}})
    engine.validate.return_value = result
    return engine


class TestStateGuardValidator:
    @pytest.mark.asyncio
    async def test_create(self):
        """Validator can be created with a mock engine."""
        defn = make_stateguard_def()
        engine = _make_mock_engine()
        v = StateGuardValidator(defn, engine=engine)
        assert v.name == "stateguard"
        assert v.engine is engine  # Injected engine is used

    @pytest.mark.asyncio
    async def test_validate_pass(self):
        """PASS result maps correctly."""
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(passed=True, overall_score=92.0),
        )
        result = await v.validate("test")
        assert result.passed is True
        assert "score=92.0" in result.message

    @pytest.mark.asyncio
    async def test_validate_fail(self):
        """FAIL result maps correctly."""
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(passed=False, overall_score=35.0, tier_path=[1, 2, 3]),
        )
        result = await v.validate("bad output")
        assert result.passed is False
        assert "score=35.0" in result.message
        assert "tier_path=[1, 2, 3]" in result.message

    @pytest.mark.asyncio
    async def test_validate_none_input(self):
        """None artifact → immediate fail without touching engine."""
        engine = _make_mock_engine()
        v = StateGuardValidator(make_stateguard_def(), engine=engine)
        result = await v.validate(None)
        assert result.passed is False
        assert "artifact is None" in result.message
        engine.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_dimension_scores_carried(self):
        """dimension_scores are forwarded into details."""
        dim_scores = {"tier_1": 80.0, "tier_2": 65.0}
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(dimension_scores=dim_scores),
        )
        result = await v.validate("test")
        assert result.details["dimension_scores"] == dim_scores

    @pytest.mark.asyncio
    async def test_stateguard_details_carried(self):
        """StateGuard's details dict is nested under stateguard_details."""
        sg_details = {"config": {"fail_mode": "fail-close"}}
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(details=sg_details),
        )
        result = await v.validate("test")
        assert result.details["stateguard_details"] == sg_details

    @pytest.mark.asyncio
    async def test_engine_exception(self):
        """Exception from StateGuard → FAIL result, not crash."""
        broken_engine = MagicMock()
        broken_engine.validate.side_effect = RuntimeError("connection lost")
        v = StateGuardValidator(make_stateguard_def(), engine=broken_engine)
        result = await v.validate("boom")
        assert result.passed is False
        assert "StateGuard error" in result.message
        assert "connection lost" in result.details["error"]

    def test_health_ok(self):
        """health() returns status=ok when engine is injected."""
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(),
        )
        h = v.health()
        assert h["status"] == "ok"

    def test_health_unavailable(self):
        """health() returns status=unavailable when engine is None."""
        v = StateGuardValidator(make_stateguard_def(), engine=None)
        h = v.health()
        assert h["status"] == "unavailable"

    def test_explain_pass(self):
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(),
        )
        r = ValidationResult(passed=True)
        assert "✅" in v.explain(r)

    def test_explain_fail(self):
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(),
        )
        r = ValidationResult(passed=False, message="test fail")
        assert "❌" in v.explain(r)
        assert "test fail" in v.explain(r)

    @pytest.mark.asyncio
    async def test_auto_fix_pass_through(self):
        """auto_fix returns the artifact unchanged."""
        v = StateGuardValidator(
            make_stateguard_def(),
            engine=_make_mock_engine(),
        )
        result = await v.auto_fix("hello")
        assert result == "hello"


# ═══════════════════════════════════════════════
# 3. _map_engine_result — standalone
# ═══════════════════════════════════════════════


class FakeSGResult:
    """Minimal stand-in for StateGuard EngineResult."""
    def __init__(self, score=75.0, passed=True, tier_path=None,
                 dim_scores=None, details=None):
        self.overall_score = score
        self.passed = passed
        self.tier_path = tier_path if tier_path is not None else [1]
        self.dimension_scores = dim_scores or {}
        self.details = details or {}


class TestMapEngineResult:
    def test_basic_mapping(self):
        r = FakeSGResult(score=88.0, passed=True)
        result = _map_engine_result(r, "stateguard")
        assert result.passed is True
        assert result.details["overall_score"] == 88.0
        assert result.details["source"] == "stateguard"

    def test_nan_score_guarded(self):
        """NaN score → clamped to 0.0, fail."""
        import math
        r = FakeSGResult(score=float("nan"), passed=False)
        result = _map_engine_result(r, "stateguard")
        assert result.passed is False
        assert result.details["overall_score"] == 0.0

    def test_inf_score_guarded(self):
        """Inf score → clamped to 0.0."""
        r = FakeSGResult(score=float("inf"), passed=True)
        result = _map_engine_result(r, "stateguard")
        assert result.details["overall_score"] == 0.0

    def test_no_tier_path(self):
        r = FakeSGResult(tier_path=[])
        result = _map_engine_result(r, "stateguard")
        assert "no-tiers" in result.message

    def test_cost_is_zero(self):
        r = FakeSGResult()
        result = _map_engine_result(r, "stateguard")
        assert result.cost_usd == 0.0


# ═══════════════════════════════════════════════
# 4. SoftwareProfile integration
# ═══════════════════════════════════════════════


def test_software_profile_includes_stateguard():
    """SoftwareProfile.setup_validators() adds a stateguard validator."""
    from profiles.software import SoftwareProfile

    profile = SoftwareProfile()
    profile.setup_validators()  # Don't call full initialize()

    names = [v.name for v in profile._validators]
    assert "stateguard" in names, (
        f"Expected 'stateguard' in validators, got {names}"
    )


# ═══════════════════════════════════════════════
# 5. Real engine integration (heavy — skipped by default)
# ═══════════════════════════════════════════════


@pytest.mark.slow
class TestRealEngine:
    """Integration tests that use the real StateGuard engine.

    These are skipped by default.  Run with::

        pytest tests/test_stateguard_bridge.py -xvs -k RealEngine
    """

    @pytest.fixture
    def real_validator(self):
        from engine.stateguard_bridge import StateGuardValidator, make_stateguard_def
        return StateGuardValidator(make_stateguard_def())

    @pytest.mark.asyncio
    async def test_validate_basic(self, real_validator):
        """Basic validation with the real engine passes."""
        result = await real_validator.validate("simple test output")
        # The engine validates against itself — should pass structurally
        assert result.passed is not None
        assert 0.0 <= result.details["overall_score"] <= 100.0

    @pytest.mark.asyncio
    async def test_validate_dict(self, real_validator):
        """Dict artifact is handled without crash."""
        result = await real_validator.validate({"text": "hello", "expected": "world"})
        assert result.passed is not None

    @pytest.mark.asyncio
    async def test_health(self, real_validator):
        h = real_validator.health()
        assert h["status"] == "ok"
        assert h["stateguard_available"] is True
