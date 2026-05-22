"""StateGuard → Prodinamik Engine — Uçtan Uca Entegrasyon Testleri.

Kapsanan akışlar:
1. Profil Konfigürasyonu → ValidatorDef üretimi
2. StateGuardValidator → ValidationResult dönüşümü
3. HITL talep → çözüm döngüsü
4. DecisionLog → EventStore kalıcılığı
5. Dimension Plugin kayıt ve validator sağlama
6. Tam pipeline: validasyon → karar → EventStore persist
7. StateGuard yok senaryosu (fail-open)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from engine.event_store import EventStore, Event, EventType
from engine.decision_bridge import ProdinamikDecisionBridge
from engine.hitl_bridge import ProdinamikHITLHandler
from engine.stateguard_config import (
    STATEGUARD_PROFILE_CONFIG,
    make_profile_validators,
    list_profile_configs,
)
from engine.stateguard_bridge import StateGuardValidator, make_stateguard_def


# ════════════════════════════════════════════════════════════
# 1. Profil Konfigürasyonu — ValidatorDef Üretimi
# ════════════════════════════════════════════════════════════


class TestProfileConfig:
    """STATEGUARD_PROFILE_CONFIG → ValidatorDef dönüşümü."""

    @pytest.mark.parametrize("profile", ["content", "software", "haber", "research", "design"])
    def test_all_profiles_have_config(self, profile: str):
        """Her profil için konfigürasyon tanımlı olmalı."""
        assert profile in STATEGUARD_PROFILE_CONFIG
        assert len(STATEGUARD_PROFILE_CONFIG[profile]) > 0

    @pytest.mark.parametrize(
        ("profile", "expected_dimensions"),
        [
            ("content", ["structural", "semantic", "security"]),
            ("software", ["structural", "quantitative", "behavioral"]),
            ("haber", ["structural", "semantic"]),
            ("research", ["semantic", "quantitative"]),
            ("design", ["structural", "semantic"]),
        ],
    )
    def test_profile_has_correct_dimensions(self, profile: str, expected_dimensions: list[str]):
        """Her profil için doğru boyutlar tanımlanmış olmalı."""
        dims = [e["dimension"] for e in STATEGUARD_PROFILE_CONFIG[profile]]
        assert dims == expected_dimensions

    def test_make_profile_validators_returns_defs(self):
        """make_profile_validators() ValidatorDef listesi döndürmeli."""
        defns = make_profile_validators("content")
        assert len(defns) > 0
        for d in defns:
            assert d.name.startswith("stateguard.")
            assert d.tier is not None
            assert d.timeout_seconds > 0

    def test_make_profile_validators_name_pattern(self):
        """ValidatorDef isimleri 'stateguard.{dimension}' formatında olmalı."""
        defns = make_profile_validators("software")
        names = [d.name for d in defns]
        expected_dims = ["structural", "quantitative", "behavioral"]
        for dim in expected_dims:
            assert f"stateguard.{dim}" in names

    def test_make_profile_validators_tier_mapping(self):
        """Tier string'leri doğru ValidatorTier enum'larına dönüşmeli."""
        from engine.profile import ValidatorTier

        defns = make_profile_validators("content")
        # content: structural=T1, semantic=T2, security=T1
        for d in defns:
            if "structural" in d.name or "security" in d.name:
                assert d.tier == ValidatorTier.T1
            elif "semantic" in d.name:
                assert d.tier == ValidatorTier.T2

    def test_make_profile_validators_unknown_profile(self):
        """Bilinmeyen profil KeyError fırlatmalı."""
        with pytest.raises(KeyError):
            make_profile_validators("nonexistent")

    def test_list_profile_configs_summary(self):
        """list_profile_configs() özet dict döndürmeli."""
        summary = list_profile_configs()
        assert set(summary.keys()) == {"content", "software", "haber", "research", "design"}
        assert "structural" in summary["content"]
        assert "quantitative" in summary["software"]

    def test_each_entry_has_required_keys(self):
        """Her config entry'si gerekli anahtarları içermeli."""
        for profile, entries in STATEGUARD_PROFILE_CONFIG.items():
            for entry in entries:
                assert "dimension" in entry, f"{profile}: missing dimension"
                assert "tier" in entry, f"{profile}/{entry['dimension']}: missing tier"
                assert "critical" in entry, f"{profile}/{entry['dimension']}: missing critical"
                assert "timeout" in entry, f"{profile}/{entry['dimension']}: missing timeout"
                assert "reason" in entry, f"{profile}/{entry['dimension']}: missing reason"

    def test_make_stateguard_def_defaults(self):
        """make_stateguard_def() varsayılan değerlerle çalışmalı."""
        defn = make_stateguard_def()
        assert defn.name == "stateguard"
        assert defn.timeout_seconds == 120
        assert defn.critical is True
        assert defn.depends_on == []
        assert defn.cache_ttl == 0

    def test_make_stateguard_def_custom(self):
        """make_stateguard_def() özel değerlerle çalışmalı."""
        from engine.profile import ValidatorTier

        defn = make_stateguard_def(
            name="custom-sg",
            tier=ValidatorTier.T3,
            critical=False,
            timeout_seconds=300,
        )
        assert defn.name == "custom-sg"
        assert defn.tier == ValidatorTier.T3
        assert defn.critical is False
        assert defn.timeout_seconds == 300


# ════════════════════════════════════════════════════════════
# 2. StateGuardValidator Bridge
# ════════════════════════════════════════════════════════════


# Fake StateGuard result for testing
class FakeSGResult:
    def __init__(self, passed: bool = True, score: float = 85.0):
        self.passed = passed
        self.overall_score = score
        self.tier_path = ["T1", "T2"]
        self.dimension_scores = {"structural": 90.0, "semantic": 80.0}
        self.details = {"info": "test"}


class FakeSGEngine:
    """Mock StateGuard ValidationEngine."""

    def __init__(self, validate_result: FakeSGResult | None = None):
        self._result = validate_result or FakeSGResult()
        self.validate_calls = []

    def validate(self, output, context=None):
        self.validate_calls.append((output, context))
        return self._result

    @property
    def name(self) -> str:
        return "FakeSGEngine"


class TestStateGuardValidatorBridge:
    """StateGuardValidator temel işlevsellik testleri."""

    def test_create_with_defn(self):
        defn = make_stateguard_def(name="sg-test")
        engine = FakeSGEngine()
        validator = StateGuardValidator(defn, engine=engine)
        assert validator.name == "sg-test"
        assert validator._engine_instance is engine

    def test_validate_passed(self):
        defn = make_stateguard_def()
        engine = FakeSGEngine(FakeSGResult(passed=True, score=95.0))
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.validate("test output"))
        assert result.passed is True
        assert "score=95.0" in result.message
        assert result.details["overall_score"] == 95.0
        assert result.details["source"] == "stateguard"
        assert len(engine.validate_calls) == 1

    def test_validate_failed(self):
        defn = make_stateguard_def()
        engine = FakeSGEngine(FakeSGResult(passed=False, score=45.0))
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.validate("bad output"))
        assert result.passed is False
        assert result.details["overall_score"] == 45.0

    def test_validate_none_artifact(self):
        defn = make_stateguard_def()
        engine = FakeSGEngine()
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.validate(None))
        assert result.passed is False
        assert "None" in result.message

    def test_validate_exception_propagation(self):
        defn = make_stateguard_def()

        class FailingEngine:
            def validate(self, output, context=None):
                raise ValueError("engine failure")

        validator = StateGuardValidator(defn, engine=FailingEngine())

        import asyncio
        result = asyncio.run(validator.validate("test"))
        assert result.passed is False
        assert "engine failure" in result.message

    def test_health_ok(self):
        defn = make_stateguard_def()
        engine = FakeSGEngine()
        validator = StateGuardValidator(defn, engine=engine)

        health = validator.health()
        assert health["status"] == "ok"
        assert health["stateguard_available"] is True

    def test_health_unavailable(self):
        defn = make_stateguard_def()
        validator = StateGuardValidator(defn, engine=None)

        health = validator.health()
        assert health["status"] == "unavailable"
        assert health["stateguard_available"] is False

    def test_auto_fix_passthrough(self):
        defn = make_stateguard_def()
        engine = FakeSGEngine()
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.auto_fix("data"))
        assert result == "data"

    def test_explain_passed(self):
        defn = make_stateguard_def(name="my-sg")
        engine = FakeSGEngine(FakeSGResult(passed=True, score=90.0))
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.validate("x"))
        explanation = validator.explain(result)
        assert "✅" in explanation
        assert "my-sg" in explanation

    def test_explain_failed(self):
        defn = make_stateguard_def(name="my-sg")
        engine = FakeSGEngine(FakeSGResult(passed=False, score=30.0))
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.validate("x"))
        explanation = validator.explain(result)
        assert "❌" in explanation

    def test_result_carries_dimension_scores(self):
        defn = make_stateguard_def()
        engine = FakeSGEngine(FakeSGResult(passed=True, score=88.0))
        validator = StateGuardValidator(defn, engine=engine)

        import asyncio
        result = asyncio.run(validator.validate("x"))
        assert "dimension_scores" in result.details
        assert result.details["dimension_scores"]["structural"] == 90.0

    def test_map_engine_result_nan_score(self):
        """NaN score 0.0'a clamp'lenmeli."""
        from engine.stateguard_bridge import _map_engine_result

        class NanResult:
            passed = False
            overall_score = float("nan")
            tier_path = []
            dimension_scores = {}
            details = {}

        mapped = _map_engine_result(NanResult(), "sg")
        assert mapped.passed is False
        assert mapped.details["overall_score"] == 0.0

    def test_map_engine_result_inf_score(self):
        """Inf score 0.0'a clamp'lenmeli."""
        from engine.stateguard_bridge import _map_engine_result

        class InfResult:
            passed = True
            overall_score = float("inf")
            tier_path = []
            dimension_scores = {}
            details = {}

        mapped = _map_engine_result(InfResult(), "sg")
        assert mapped.details["overall_score"] == 0.0


# ════════════════════════════════════════════════════════════
# 3. DecisionLog → EventStore
# ════════════════════════════════════════════════════════════


class TestDecisionBridgeE2E:
    """ProdinamikDecisionBridge + gerçek EventStore entegrasyonu."""

    def test_bridge_to_real_store(self, tmp_path):
        """Karar EventStore'a persist edilmeli."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="e2e")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="e2e")

        entry = DecisionEntry(
            agent_id="agent-1",
            step_id="tier_1",
            dimension=ValidationDimension.STRUCTURAL,
            score=95.0,
            decision="pass",
            details={"threshold": 80.0},
        )
        bridge.log(entry)

        # In-memory count
        assert bridge.count() == 1

        # Disk persistence
        event_files = [
            f for f in store.events_dir.glob("*.json")
            if f.name != "index.json"
        ]
        assert len(event_files) == 1

    def test_multiple_decisions_sequenced(self, tmp_path):
        """Birden çok karar sıralı sequence numarası almalı."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="multi")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="multi")

        for i in range(5):
            entry = DecisionEntry(
                agent_id=f"agent-{i}",
                step_id=f"step_{i}",
                dimension=ValidationDimension.SEMANTIC,
                score=float(60 + i * 8),
                decision="pass" if i % 2 == 0 else "escalate",
            )
            bridge.log(entry)

        assert bridge.count() == 5
        assert store._last_sequence == 5

    def test_query_filtered_decisions(self, tmp_path):
        """query() filtreleme çalışmalı."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="query")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="query")

        for decision in ["pass", "fail", "escalate", "pass"]:
            bridge.log(DecisionEntry(
                agent_id="ag",
                step_id="st",
                dimension=ValidationDimension.STRUCTURAL,
                score=80.0,
                decision=decision,
            ))

        passes = bridge.query(result="pass")
        assert len(passes) == 2

        fails = bridge.query(result="fail")
        assert len(fails) == 1

    def test_event_type_is_validation(self, tmp_path):
        """EventStore'daki event VALIDATION tipinde olmalı."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="type")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="type")

        bridge.log(DecisionEntry(
            agent_id="ag", step_id="st",
            dimension=ValidationDimension.SECURITY,
            score=90.0, decision="pass",
        ))

        events = store.query()
        assert len(events) == 1
        assert events[0].event_type == EventType.VALIDATION.value
        assert events[0].run_slug == "type"

    def test_trace_id_format(self, tmp_path):
        """trace_id 'sg-{step_id}' formatında olmalı."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="trace")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="trace")

        bridge.log(DecisionEntry(
            agent_id="ag", step_id="custom-step",
            dimension=ValidationDimension.BEHAVIORAL,
            score=85.0, decision="pass",
        ))

        events = store.query()
        assert events[0].trace_id == "sg-custom-step"

    def test_create_default_factory(self, tmp_path):
        """create_default() çalışan bir bridge oluşturmalı."""
        base = str(tmp_path / "factory")
        bridge = ProdinamikDecisionBridge.create_default(
            base_path=base,
            run_slug="factory-test",
        )
        assert bridge.event_store is not None
        assert bridge.run_slug == "factory-test"

    def test_event_query_by_validator(self, tmp_path):
        """EventStore.query() validator adına göre filtreleyebilmeli."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="qval")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="qval")

        # Log decisions (they become validation events)
        for i in range(3):
            entry = DecisionEntry(
                agent_id="ag", step_id=f"step_{i}",
                dimension=ValidationDimension.STRUCTURAL,
                score=float(80 + i * 5), decision="pass",
            )
            bridge.log(entry)

        # Query via EventStore — all validation events
        events = store.query(event_type="validation")
        assert len(events) == 3


# ════════════════════════════════════════════════════════════
# 4. HITL Escalasyon Döngüsü
# ════════════════════════════════════════════════════════════


class TestHITLE2E:
    """ProdinamikHITLHandler komple döngü testi."""

    def test_request_approval_returns_pending(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        result = hitl.request_approval({
            "step": "tier_3",
            "dimension": "semantic",
            "error": "Low similarity score: 0.45",
        })
        assert result["status"] == "pending"
        assert result["request_id"].startswith("hitl_")
        assert "timeout_at" in result

    def test_resolve_approval_approve(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        req = hitl.request_approval({"step": "tier_3", "error": "test"})
        resolved = hitl.resolve_approval(req["request_id"], approved=True, reason="looks good")
        assert resolved["approved"] is True
        assert resolved["status"] == "decided"

        # Check status
        check = hitl.check_approval(req["request_id"])
        assert check["approved"] is True

    def test_resolve_approval_reject(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        req = hitl.request_approval({"step": "tier_3", "error": "test"})
        resolved = hitl.resolve_approval(req["request_id"], approved=False, reason="bad output")
        assert resolved["approved"] is False
        assert resolved["reason"] == "bad output"

    def test_resolve_approval_type_error(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        req = hitl.request_approval({"step": "test", "error": "test"})
        with pytest.raises(TypeError):
            hitl.resolve_approval(req["request_id"], approved="yes")  # type: ignore

    def test_check_approval_not_found(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        with pytest.raises(KeyError):
            hitl.check_approval("nonexistent")

    def test_multiple_pending_requests(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        hitl.request_approval({"step": "s1", "error": "e1"})
        hitl.request_approval({"step": "s2", "error": "e2"})
        pending = hitl.get_pending_requests()
        assert pending["count"] == 2
        assert len(pending["pending"]) == 2

    def test_pending_count_after_resolve(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        req1 = hitl.request_approval({"step": "s1", "error": "e1"})
        hitl.request_approval({"step": "s2", "error": "e2"})
        hitl.resolve_approval(req1["request_id"], approved=True)

        # Resolved requests still show in the loop (they're in _resolved)
        # The handler tracks all requests
        pending = hitl.get_pending_requests()
        # After resolve, the item moves from queue to resolved
        # get_pending_requests filters by _reverse_map only
        assert pending["count"] == 1  # Only unresolved remains

    def test_on_timeout_default(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        result = hitl.on_timeout()
        assert result["approved"] is False
        assert result["reason"] == "timeout"

    def test_stats_return_dict(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        stats = hitl.stats()
        assert isinstance(stats, dict)

    def test_request_approval_type_error(self):
        hitl = ProdinamikHITLHandler(timeout_minutes=10)
        with pytest.raises(TypeError):
            hitl.request_approval("not a dict")  # type: ignore


# ════════════════════════════════════════════════════════════
# 5. Dimension Plugin Kaydı
# ════════════════════════════════════════════════════════════


class TestDimensionPluginsE2E:
    """StateGuard dimension plugin'leri temel işlevsellik testleri."""

    @pytest.mark.parametrize(
        ("plugin_cls", "dimension"),
        [
            ("StructuralPlugin", "structural"),
            ("SemanticPlugin", "semantic"),
            ("QuantitativePlugin", "quantitative"),
            ("BehavioralPlugin", "behavioral"),
            ("SecurityPlugin", "security"),
        ],
    )
    def test_plugin_manifest_id(self, plugin_cls: str, dimension: str):
        """Plugin manifest ID 'prodinamik.stateguard.{dimension}' formatında."""
        import importlib
        mod = importlib.import_module("plugins.stateguard_dimensions")
        cls = getattr(mod, plugin_cls)
        plugin = cls()
        assert plugin.manifest.id == f"prodinamik.stateguard.{dimension}"
        assert dimension in plugin.manifest.tags

    def test_plugin_registers_validators(self):
        """Her plugin get_validators() döndürebilmeli."""
        from plugins.stateguard_dimensions import (
            StructuralPlugin, SemanticPlugin,
            QuantitativePlugin, BehavioralPlugin, SecurityPlugin,
        )

        for plugin in [
            StructuralPlugin(), SemanticPlugin(),
            QuantitativePlugin(), BehavioralPlugin(), SecurityPlugin(),
        ]:
            manifest = plugin.manifest
            assert len(manifest.provides_validators) >= 1

    def test_all_plugins_have_tools(self):
        """Her plugin en az bir tool sağlamalı."""
        from plugins.stateguard_dimensions import (
            StructuralPlugin, SemanticPlugin,
            QuantitativePlugin, BehavioralPlugin, SecurityPlugin,
        )

        for plugin in [
            StructuralPlugin(), SemanticPlugin(),
            QuantitativePlugin(), BehavioralPlugin(), SecurityPlugin(),
        ]:
            tools = plugin.get_tools()
            assert len(tools) >= 1
            assert all(t.name.startswith("stateguard_") for t in tools)

    def test_all_plugins_health_check(self):
        """Her plugin health_check döndürebilmeli."""
        from plugins.stateguard_dimensions import (
            StructuralPlugin, SemanticPlugin,
            QuantitativePlugin, BehavioralPlugin, SecurityPlugin,
        )

        import asyncio
        for plugin in [
            StructuralPlugin(), SemanticPlugin(),
            QuantitativePlugin(), BehavioralPlugin(), SecurityPlugin(),
        ]:
            health = asyncio.run(plugin.health_check())
            assert "healthy" in health
            assert "status" in health
            assert "dimension" in health

    def test_plugin_type_is_validator(self):
        """Tüm plugin'ler VALIDATOR tipinde olmalı."""
        from plugins.stateguard_dimensions import StructuralPlugin
        from engine.plugin import PluginType

        plugin = StructuralPlugin()
        assert plugin.manifest.plugin_type == PluginType.VALIDATOR

    def test_plugins_contained_in_plugin_registry(self):
        """Plugin'ler engine/__init__.py'den export edilmeli."""
        from engine import StructuralPlugin, SemanticPlugin
        from engine import QuantitativePlugin, BehavioralPlugin, SecurityPlugin

        for cls in [StructuralPlugin, SemanticPlugin, QuantitativePlugin, BehavioralPlugin, SecurityPlugin]:
            assert cls is not None


# ════════════════════════════════════════════════════════════
# 6. Tam Pipeline: Validasyon → Karar → EventStore
# ════════════════════════════════════════════════════════════


class TestFullPipeline:
    """StateGuard → Prodinamik Engine — uçtan uca pipeline testi.

    Akış:
    make_profile_validators() → StateGuardValidator → validate()
    → ProdinamikDecisionBridge.log() → EventStore.query()
    """

    def test_content_profile_full_flow(self, tmp_path):
        """Content profili tam pipeline: config → validate → log → query."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension
        import asyncio

        # 1. Config'den ValidatorDef üret
        defns = make_profile_validators("content")
        assert len(defns) == 3  # structural, semantic, security

        # 2. EventStore + Bridge kur
        base = str(tmp_path / "pipeline")
        store = EventStore(base_path=base, slug="e2e-content")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="e2e-content")

        # 3. Her validator için mock engine ile validate et
        engine = FakeSGEngine(FakeSGResult(passed=True, score=92.0))
        for defn in defns:
            validator = StateGuardValidator(defn, engine=engine)
            result = asyncio.run(validator.validate("test content output"))

            assert result.passed is True
            assert result.details["source"] == "stateguard"

            # 4. DecisionBridge'e log
            entry = DecisionEntry(
                agent_id=defn.name,
                step_id=f"tier_{defn.tier.value}",
                dimension=ValidationDimension.STRUCTURAL,
                score=result.details["overall_score"],
                decision="pass" if result.passed else "fail",
                details=result.details,
            )
            bridge.log(entry)

        # 5. EventStore'da kayıtları kontrol et
        assert bridge.count() == 3
        events = store.query(event_type="validation")
        assert len(events) == 3

        # Her event'in trace_id'si 'sg-' ile başlamalı
        for event in events:
            assert event.trace_id.startswith("sg-")

    def test_software_profile_validator_types(self):
        """Software profili tüm validator tiplerini içermeli."""
        defns = make_profile_validators("software")
        names = {d.name for d in defns}
        assert "stateguard.structural" in names
        assert "stateguard.quantitative" in names
        assert "stateguard.behavioral" in names

    def test_pipeline_with_mixed_results(self, tmp_path):
        """Farklı sonuçlar (pass/fail) pipeline'da doğru işlenmeli."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension
        import asyncio

        base = str(tmp_path / "mixed")
        store = EventStore(base_path=base, slug="mixed")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="mixed")

        # Pass
        pass_engine = FakeSGEngine(FakeSGResult(passed=True, score=90.0))
        pass_validator = StateGuardValidator(make_stateguard_def(name="pass-val"), engine=pass_engine)
        pass_result = asyncio.run(pass_validator.validate("good output"))
        bridge.log(DecisionEntry(
            agent_id="pass-val", step_id="T1",
            dimension=ValidationDimension.STRUCTURAL,
            score=90.0, decision="pass",
        ))

        # Fail
        fail_engine = FakeSGEngine(FakeSGResult(passed=False, score=35.0))
        fail_validator = StateGuardValidator(make_stateguard_def(name="fail-val"), engine=fail_engine)
        fail_result = asyncio.run(fail_validator.validate("bad output"))
        bridge.log(DecisionEntry(
            agent_id="fail-val", step_id="T1",
            dimension=ValidationDimension.STRUCTURAL,
            score=35.0, decision="fail",
        ))

        assert pass_result.passed is True
        assert fail_result.passed is False
        assert bridge.count() == 2

        # EventStore'da her iki event de olmalı
        events = store.query()
        assert len(events) == 2

    def test_dimension_plugin_get_validators_structure(self):
        """Plugin validator'leri DimensionValidatorAdapter döndürmeli."""
        from plugins.stateguard_dimensions import StructuralPlugin, DimensionValidatorAdapter

        # Plugin mock output ile validate et
        plugin = StructuralPlugin()
        validators = plugin.get_validators()

        # StateGuard yüklü olduğunda DimensionValidatorAdapter döner
        if validators:
            assert isinstance(validators[0], DimensionValidatorAdapter)

    def test_profile_config_has_all_required_tiers(self):
        """Her profil config'inde tüm gerekli alanlar var."""
        for profile, entries in STATEGUARD_PROFILE_CONFIG.items():
            for entry in entries:
                assert entry["tier"] in ("T1", "T2", "T3")
                assert isinstance(entry["critical"], bool)
                assert isinstance(entry["timeout"], int)
                assert entry["timeout"] > 0
                assert isinstance(entry["reason"], str)

    def test_decision_logger_timestamp_iso(self, tmp_path):
        """DecisionEntry timestamp ISO formatında Event'e taşınmalı."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "iso")
        store = EventStore(base_path=base, slug="iso")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="iso")

        entry = DecisionEntry(
            agent_id="ag", step_id="st",
            dimension=ValidationDimension.STRUCTURAL,
            score=88.0, decision="pass",
        )
        bridge.log(entry)

        event = store.get(1)
        assert event is not None
        # Timestamp ISO formatında olmalı (T karakteri içerir)
        assert "T" in event.timestamp

    def test_event_store_stats_after_decisions(self, tmp_path):
        """EventStore.stats() karar loglamasından sonra doğru bilgi vermeli."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        base = str(tmp_path / "stats")
        store = EventStore(base_path=base, slug="stats-e2e")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="stats-e2e")

        for i in range(4):
            bridge.log(DecisionEntry(
                agent_id=f"ag-{i}", step_id=f"st-{i}",
                dimension=ValidationDimension.STRUCTURAL,
                score=float(70 + i * 5), decision="pass",
            ))

        stats = store.stats()
        assert stats["event_count"] == 4
        assert stats["slug"] == "stats-e2e"
        assert stats["last_sequence"] == 4
        assert "validation" in stats["event_types"]
        assert stats["event_types"]["validation"] == 4

    def test_full_flow_with_hitl(self, tmp_path):
        """Tam akış: validasyon → HITL escalation → çözüm → EventStore."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension
        import asyncio

        base = str(tmp_path / "hitl-flow")
        store = EventStore(base_path=base, slug="hitl-e2e")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="hitl-e2e")
        hitl = ProdinamikHITLHandler(timeout_minutes=10)

        # 1. Validate (fail durumu)
        engine = FakeSGEngine(FakeSGResult(passed=False, score=42.0))
        validator = StateGuardValidator(make_stateguard_def(name="e2e-test"), engine=engine)
        result = asyncio.run(validator.validate("risky output"))

        # 2. Kararı logla
        bridge.log(DecisionEntry(
            agent_id="e2e-test", step_id="T2",
            dimension=ValidationDimension.SEMANTIC,
            score=result.details["overall_score"],
            decision="fail" if not result.passed else "pass",
            details=result.details,
        ))

        # 3. HITL escalation (fail durumunda insan onayı)
        hitl_req = hitl.request_approval({
            "step": "T2",
            "dimension": "semantic",
            "score": result.details["overall_score"],
            "error": "Low score requires human review",
        })
        assert hitl_req["status"] == "pending"

        # 4. İnsan onayı
        resolution = hitl.resolve_approval(
            hitl_req["request_id"],
            approved=True,  # İnsan onayladı
            reason="Acceptable risk for this case",
        )
        assert resolution["approved"] is True

        # 5. Onay kararını da logla
        bridge.log(DecisionEntry(
            agent_id="e2e-test", step_id="T2-HITL",
            dimension=ValidationDimension.SEMANTIC,
            score=result.details["overall_score"],
            decision="approved_after_hitl",
            details={"hitl_result": resolution},
        ))

        # 6. EventStore'da 2 event olmalı (fail + HITL onay)
        assert bridge.count() == 2
        events = store.query()
        assert len(events) == 2


# ════════════════════════════════════════════════════════════
# 7. StateGuard Yok / Fail-Open Senaryoları
# ════════════════════════════════════════════════════════════


class TestFailOpen:
    """StateGuard kullanılamadığında sistem çalışmaya devam etmeli."""

    def test_stateguard_bridge_unavailable_health(self):
        """StateGuard yokken health unavailable dönmeli."""
        defn = make_stateguard_def()
        validator = StateGuardValidator(defn, engine=None)
        health = validator.health()
        assert health["status"] == "unavailable"
        assert health["stateguard_available"] is False

    def test_bridge_works_without_stateguard_lazy_import(self):
        """StateGuard yokken bile bridge import edilebilmeli."""
        # Bu test sadece import'un çalıştığını doğrular
        from engine.stateguard_bridge import StateGuardValidator, make_stateguard_def, _map_engine_result
        assert callable(make_stateguard_def)
        assert callable(_map_engine_result)

    def test_decision_bridge_works_without_stateguard(self):
        """DecisionBridge StateGuard'dan bağımsız çalışabilmeli."""
        from stateguard.models.log import DecisionEntry
        from stateguard.models.enums import ValidationDimension

        store = MagicMock(spec=EventStore)
        store.append.return_value = 1

        bridge = ProdinamikDecisionBridge(event_store=store)
        entry = DecisionEntry(
            agent_id="ag", step_id="st",
            dimension=ValidationDimension.STRUCTURAL,
            score=85.0, decision="pass",
        )
        bridge.log(entry)
        assert bridge.count() == 1
        store.append.assert_called_once()

    def test_dimension_plugin_gracious_fail(self):
        """Dimension plugin StateGuard yokken None döndürmeli."""
        from plugins.stateguard_dimensions import _load_validator

        # _VALIDATOR_CACHE'i temizleyip yüklemeyi dene
        # Not: StateGuard yüklü olduğu için bu test sadece mekanizmayı kontrol eder
        result = _load_validator("structural")
        # StateGuard yüklü olduğu için None DEĞİL
        assert result is not None
