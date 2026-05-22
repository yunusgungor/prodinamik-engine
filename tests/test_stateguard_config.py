"""Tests for StateGuard Profile Validation Configuration.

Tests cover:
1. STATEGUARD_PROFILE_CONFIG — all profiles configured correctly
2. make_profile_validators — returns correct ValidatorDef list per profile
3. list_profile_configs — returns summary
4. Profile integration — each profile has StateGuard validators
5. Edge cases — unknown profile, unknown tier
"""

from __future__ import annotations

import pytest

from engine.stateguard_config import (
    STATEGUARD_PROFILE_CONFIG,
    make_profile_validators,
    list_profile_configs,
)
from engine.profile import ValidatorTier


# ═══════════════════════════════════════════════
# 1. STATEGUARD_PROFILE_CONFIG
# ═══════════════════════════════════════════════


class TestConfig:
    def test_all_profiles_configured(self):
        """All 5 supported profiles have entries."""
        expected = {"content", "software", "haber", "research", "design"}
        assert set(STATEGUARD_PROFILE_CONFIG) == expected

    def test_each_profile_has_validators(self):
        """Each profile has at least 1 dimension configured."""
        for name, entries in STATEGUARD_PROFILE_CONFIG.items():
            assert len(entries) >= 1, f"{name} has no dimensions"

    def test_each_entry_has_required_keys(self):
        """Every entry has dimension, tier, critical, timeout."""
        for name, entries in STATEGUARD_PROFILE_CONFIG.items():
            for i, e in enumerate(entries):
                assert "dimension" in e, f"{name}[{i}] missing dimension"
                assert "tier" in e, f"{name}[{i}] missing tier"
                assert "critical" in e, f"{name}[{i}] missing critical"
                assert "timeout" in e, f"{name}[{i}] missing timeout"
                assert "reason" in e, f"{name}[{i}] missing reason"

    def test_valid_dimensions(self):
        """All dimensions are known StateGuard dimensions."""
        valid = {"structural", "semantic", "quantitative", "behavioral", "security"}
        for name, entries in STATEGUARD_PROFILE_CONFIG.items():
            for e in entries:
                assert e["dimension"] in valid, \
                    f"{name}: unknown dimension {e['dimension']!r}"

    def test_valid_tiers(self):
        """All tiers are T1, T2, or T3."""
        valid = {"T1", "T2", "T3"}
        for name, entries in STATEGUARD_PROFILE_CONFIG.items():
            for e in entries:
                assert e["tier"] in valid, \
                    f"{name}: invalid tier {e['tier']!r}"


# ═══════════════════════════════════════════════
# 2. make_profile_validators
# ═══════════════════════════════════════════════


class TestMakeProfileValidators:
    @pytest.mark.parametrize("profile_name", [
        "content", "software", "haber", "research", "design",
    ])
    def test_returns_list(self, profile_name):
        defns = make_profile_validators(profile_name)
        assert isinstance(defns, list)
        assert len(defns) >= 1, f"{profile_name} returned empty list"

    @pytest.mark.parametrize("profile_name", [
        "content", "software", "haber", "research", "design",
    ])
    def test_each_is_validatordef(self, profile_name):
        for v in make_profile_validators(profile_name):
            assert hasattr(v, "name"), f"{profile_name}: missing name"
            assert hasattr(v, "tier"), f"{profile_name}: missing tier"
            assert hasattr(v, "critical"), f"{profile_name}: missing critical"
            # Names start with stateguard.
            assert v.name.startswith("stateguard."), f"{profile_name}: bad name {v.name}"

    @pytest.mark.parametrize("profile_name,expected_count", [
        ("content", 3),
        ("software", 3),
        ("haber", 2),
        ("research", 2),
        ("design", 2),
    ])
    def test_expected_count(self, profile_name, expected_count):
        defns = make_profile_validators(profile_name)
        assert len(defns) == expected_count, \
            f"{profile_name}: expected {expected_count}, got {len(defns)}"

    def test_content_config(self):
        """Content has structural(T1), semantic(T2), security(T1)."""
        defns = make_profile_validators("content")
        names = [d.name for d in defns]
        assert "stateguard.structural" in names
        assert "stateguard.semantic" in names
        assert "stateguard.security" in names

    def test_software_config(self):
        """Software has structural(T1), quantitative(T2), behavioral(T2)."""
        defns = make_profile_validators("software")
        names = [d.name for d in defns]
        assert "stateguard.structural" in names
        assert "stateguard.quantitative" in names
        assert "stateguard.behavioral" in names

    def test_critical_flag_varied(self):
        """Criticality varies per dimension."""
        for profile_name in STATEGUARD_PROFILE_CONFIG:
            for v in make_profile_validators(profile_name):
                assert isinstance(v.critical, bool)

    def test_timeout_set(self):
        """Timeout is always positive."""
        for profile_name in STATEGUARD_PROFILE_CONFIG:
            for v in make_profile_validators(profile_name):
                assert v.timeout_seconds >= 5, f"{v.name} timeout too low"


# ═══════════════════════════════════════════════
# 3. list_profile_configs
# ═══════════════════════════════════════════════


class TestListProfileConfigs:
    def test_returns_dict(self):
        result = list_profile_configs()
        assert isinstance(result, dict)

    def test_all_profiles_present(self):
        result = list_profile_configs()
        assert "content" in result
        assert "software" in result
        assert "haber" in result
        assert "research" in result
        assert "design" in result

    def test_dimensions_are_strings(self):
        result = list_profile_configs()
        for name, dims in result.items():
            for d in dims:
                assert isinstance(d, str), f"{name}: {d} not str"


# ═══════════════════════════════════════════════
# 4. Profile Integration
# ═══════════════════════════════════════════════


class TestProfileIntegration:
    @pytest.mark.parametrize("profile_cls,expected_sg_count", [
        ("content", 3),
        ("software", 3),
        ("haber", 2),
        ("research", 2),
        ("design", 2),
    ])
    def test_profile_includes_stateguard(self, profile_cls, expected_sg_count):
        """Each profile's setup_validators adds StateGuard validators."""
        import importlib
        mod = importlib.import_module(f"profiles.{profile_cls}")
        cls_name = f"{profile_cls.capitalize()}Profile"
        # Special case: haber → HaberProfile
        if profile_cls == "haber":
            cls_name = "HaberProfile"

        profile_cls_obj = getattr(mod, cls_name)
        profile = profile_cls_obj()
        profile.setup_validators()

        sg_validators = [v for v in profile._validators if v.name.startswith("stateguard.")]
        assert len(sg_validators) == expected_sg_count, \
            f"{profile_cls}: expected {expected_sg_count} SG validators, got {len(sg_validators)}: {[v.name for v in sg_validators]}"

        # Verify specific dimension names
        sg_names = {v.name for v in sg_validators}
        config_dims = STATEGUARD_PROFILE_CONFIG[profile_cls]
        for entry in config_dims:
            expected_name = f"stateguard.{entry['dimension']}"
            assert expected_name in sg_names, \
                f"{profile_cls}: missing {expected_name} in {sg_names}"


# ═══════════════════════════════════════════════
# 5. Edge cases
# ═══════════════════════════════════════════════


class TestEdgeCases:
    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError, match="No StateGuard config"):
            make_profile_validators("nonexistent")

    def test_profile_names_are_lowercase(self):
        for name in STATEGUARD_PROFILE_CONFIG:
            assert name == name.lower(), f"{name} should be lowercase"
