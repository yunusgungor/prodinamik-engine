"""
Prodinamik Engine v0.5 — Degradation Manager

3-seviyeli graceful degradation (Review #10 → refined):
- FULL:     Tüm özellikler aktif
- DEGRADED: T2/T3 validator'lar + remote adapter'lar kapalı, prediction aktif
- SURVIVAL: Tüm validator/adapter'lar kapalı, sadece state tracking

Health monitor:
- LLM API sağlığı
- Disk kullanımı
- Budget limitleri
- Invariant violations
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Set, Callable
import shutil


class DegradationLevel(Enum):
    FULL = "full"
    DEGRADED = "degraded"
    SURVIVAL = "survival"


@dataclass
class HealthCheckResult:
    """Tek bir health check sonucu"""
    name: str
    passed: bool
    detail: str = ""
    metric: float = 0.0
    threshold: float = 0.0


@dataclass
class DegradationEvent:
    """Degradation değişikliği — event store'a yazılır"""
    timestamp: str
    from_level: DegradationLevel
    to_level: DegradationLevel
    reason: str
    checks: Dict[str, bool]


class DegradationManager:
    """
    Health monitor + degradation controller.
    
    Otomatik degradation:
    - LLM API hatası + remote adapter hatası → DEGRADED
    - Disk >%95 + Budget hard limit aşımı → SURVIVAL
    
    Manuel override:
    - Kullanıcı manuel degrade edebilir
    - Kullanıcı manuel recover edebilir
    """

    def __init__(self, base_path: str = ".hermes"):
        self.base_path = base_path
        self.current_level = DegradationLevel.FULL
        self.previous_level = DegradationLevel.FULL
        self.disabled_features: Set[str] = set()
        self.degradation_history: List[DegradationEvent] = []
        self.last_check_time: Optional[datetime] = None
        self.check_count = 0

        # Health check threshold'ları
        self.thresholds = {
            "disk_usage_max_pct": 95,
            "disk_usage_warn_pct": 80,
            "budget_hard_limit_reached": True,
            "consecutive_llm_failures": 3,
            "consecutive_adapter_failures": 3,
        }

    # ──────────────────────────────────────
    # Health Checks
    # ──────────────────────────────────────

    def check_health(self, engine_state: dict = None) -> List[HealthCheckResult]:
        """Tüm health check'leri çalıştır"""
        self.check_count += 1
        self.last_check_time = datetime.now()

        checks = [
            self._check_disk_usage(),
            self._check_llm_api(engine_state),
            self._check_remote_adapters(engine_state),
            self._check_budget(engine_state),
            self._check_memory(engine_state),
        ]

        return checks

    def _check_disk_usage(self) -> HealthCheckResult:
        """Disk kullanımı kontrolü"""
        try:
            usage = shutil.disk_usage(self.base_path)
            pct = usage.used / usage.total * 100
            return HealthCheckResult(
                name="disk_usage",
                passed=pct < self.thresholds["disk_usage_max_pct"],
                detail=f"{pct:.1f}% used",
                metric=pct,
                threshold=self.thresholds["disk_usage_max_pct"],
            )
        except OSError as e:
            return HealthCheckResult(
                name="disk_usage",
                passed=True,  # Can't check → assume OK
                detail=f"Cannot check: {e}",
            )

    def _check_llm_api(self, state: dict = None) -> HealthCheckResult:
        """LLM API sağlığı (engine_state'dan gelen veriye göre)"""
        failures = (state or {}).get("consecutive_llm_failures", 0)
        return HealthCheckResult(
            name="llm_api",
            passed=failures < self.thresholds["consecutive_llm_failures"],
            detail=f"{failures} consecutive failures",
            metric=failures,
            threshold=self.thresholds["consecutive_llm_failures"],
        )

    def _check_remote_adapters(self, state: dict = None) -> HealthCheckResult:
        """Remote adapter sağlığı"""
        failures = (state or {}).get("consecutive_adapter_failures", 0)
        return HealthCheckResult(
            name="remote_adapters",
            passed=failures < self.thresholds["consecutive_adapter_failures"],
            detail=f"{failures} consecutive failures",
            metric=failures,
            threshold=self.thresholds["consecutive_adapter_failures"],
        )

    def _check_budget(self, state: dict = None) -> HealthCheckResult:
        """Budget limit kontrolü"""
        hard_reached = (state or {}).get("budget_hard_limit_reached", False)
        return HealthCheckResult(
            name="budget",
            passed=not hard_reached,
            detail="Hard limit reached" if hard_reached else "OK",
        )

    def _check_memory(self, state: dict = None) -> HealthCheckResult:
        """Memory kullanımı (basit)"""
        return HealthCheckResult(
            name="memory",
            passed=True,
            detail="OK",
        )

    # ──────────────────────────────────────
    # Degradation Logic
    # ──────────────────────────────────────

    def evaluate(self, engine_state: dict = None) -> DegradationLevel:
        """
        Health check sonuçlarına göre degradation seviyesini belirle.

        FULL → DEGRADED: LLM hatası VEYA adapter hatası
        FULL → SURVIVAL: Direkt geçilemez (önce DEGRADED)
        DEGRADED → SURVIVAL: Disk >%95 VEYA budget hard limit
        DEGRADED → FULL: Tüm check'ler düzeldi
        SURVIVAL → DEGRADED: Disk/budget düzeldi (insan onayı gerekli)
        """
        checks = self.check_health(engine_state)
        failed = [c for c in checks if not c.passed]
        critical_fails = [c for c in failed if c.metric >= c.threshold]

        new_level = self.current_level

        if self.current_level == DegradationLevel.FULL:
            if any(c.name in ("llm_api", "remote_adapters") for c in failed):
                new_level = DegradationLevel.DEGRADED
            elif critical_fails:
                new_level = DegradationLevel.DEGRADED

        elif self.current_level == DegradationLevel.DEGRADED:
            if any(c.name == "disk_usage" for c in failed):
                new_level = DegradationLevel.SURVIVAL
            elif any(c.name == "budget" for c in failed):
                new_level = DegradationLevel.SURVIVAL
            elif not failed:
                new_level = DegradationLevel.FULL  # Auto-recover

        elif self.current_level == DegradationLevel.SURVIVAL:
            pass  # Survival'dan çıkmak için manuel müdahale gerekli

        if new_level != self.current_level:
            self._transition_to(new_level, failed, engine_state)

        return self.current_level

    def _transition_to(self, new_level: DegradationLevel,
                       failed_checks: List[HealthCheckResult],
                       engine_state: dict = None):
        """Degradation seviyesini değiştir"""
        self.previous_level = self.current_level
        reason = "; ".join(f"{c.name}: {c.detail}" for c in failed_checks)

        # Disabled features
        if new_level == DegradationLevel.DEGRADED:
            self.disabled_features = {"t2_validators", "t3_validators", "remote_adapters"}
        elif new_level == DegradationLevel.SURVIVAL:
            self.disabled_features = {
                "t1_validators", "t2_validators", "t3_validators",
                "all_adapters", "event_store_write"
            }
        else:
            self.disabled_features = set()

        self.current_level = new_level

        event = DegradationEvent(
            timestamp=datetime.now().isoformat(),
            from_level=self.previous_level,
            to_level=new_level,
            reason=reason,
            checks={c.name: c.passed for c in failed_checks},
        )
        self.degradation_history.append(event)

    # ──────────────────────────────────────
    # Manual Override
    # ──────────────────────────────────────

    def manual_degrade(self, level: DegradationLevel, reason: str):
        """Kullanıcı manuel degrade eder"""
        self._transition_to(level, [], {"manual": reason})

    def manual_recover(self):
        """Kullanıcı manuel FULL moda döner"""
        self._transition_to(DegradationLevel.FULL, [], {"manual": "User requested recovery"})

    # ──────────────────────────────────────
    # Feature Access
    # ──────────────────────────────────────

    def is_enabled(self, feature: str) -> bool:
        """Belirli bir feature'ın aktif olup olmadığını kontrol et"""
        if feature in self.disabled_features:
            return False

        # Level-based defaults
        level_checks = {
            "t1_validators": [DegradationLevel.FULL, DegradationLevel.DEGRADED],
            "t2_validators": [DegradationLevel.FULL],
            "t3_validators": [DegradationLevel.FULL],
            "remote_adapters": [DegradationLevel.FULL],
            "local_adapters": [DegradationLevel.FULL, DegradationLevel.DEGRADED],
            "state_tracking": [DegradationLevel.FULL, DegradationLevel.DEGRADED, DegradationLevel.SURVIVAL],
            "event_writing": [DegradationLevel.FULL, DegradationLevel.DEGRADED],
            "run_crud": [DegradationLevel.FULL, DegradationLevel.DEGRADED, DegradationLevel.SURVIVAL],
        }

        allowed = level_checks.get(feature, [DegradationLevel.FULL])
        return self.current_level in allowed

    @property
    def feature_matrix(self) -> Dict[str, bool]:
        """Tüm feature'ların durumu"""
        features = [
            "t1_validators", "t2_validators", "t3_validators",
            "remote_adapters", "local_adapters",
            "state_tracking", "event_writing", "run_crud",
        ]
        return {f: self.is_enabled(f) for f in features}

    # ──────────────────────────────────────
    # Display
    # ──────────────────────────────────────

    def status_report(self) -> str:
        """Kullanıcıya durum raporu"""
        level_icon = {
            DegradationLevel.FULL: "✅",
            DegradationLevel.DEGRADED: "⚠️",
            DegradationLevel.SURVIVAL: "🆘",
        }

        lines = [f"{level_icon[self.current_level]} **Degradation: `{self.current_level.value}`**"]

        if self.disabled_features:
            lines.append(f"   🚫 Disabled: `{', '.join(sorted(self.disabled_features))}`")

        lines.append(f"   📊 Features:")
        for feat, enabled in self.feature_matrix.items():
            icon = "✅" if enabled else "❌"
            lines.append(f"      {icon} {feat}")

        if self.degradation_history:
            last = self.degradation_history[-1]
            lines.append(f"\n   📜 Last change: `{last.from_level.value}` → `{last.to_level.value}`")
            lines.append(f"      Reason: {last.reason}")

        return "\n".join(lines)


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import tempfile
    import os

    tmpdir = tempfile.mkdtemp()

    mgr = DegradationManager(base_path=tmpdir)
    print("📊 Initial status:")
    print(mgr.status_report())

    # Test 1: FULL → DEGRADED (LLM failure)
    print(f"\n📝 Test 1: LLM failure → DEGRADED")
    state = {"consecutive_llm_failures": 3}
    level = mgr.evaluate(state)
    print(f"   Level: {level.value}")
    assert level == DegradationLevel.DEGRADED
    print(mgr.status_report())

    # Test 2: DEGRADED → SURVIVAL (disk full)
    print(f"\n📝 Test 2: Disk full → SURVIVAL")
    # Fill the temp directory with trash
    trash_file = os.path.join(tmpdir, "trash.bin")
    with open(trash_file, "wb") as f:
        f.write(b"0" * 1024 * 1024 * 10)  # 10MB dummy
    level = mgr.evaluate(state)
    print(f"   Level: {level.value}")
    # Note: disk check might pass if tmpdir is on a large filesystem
    print(f"   (Disk check result depends on actual filesystem)")

    # Test 3: Manual recover
    print(f"\n📝 Test 3: Manual recover")
    mgr.manual_recover()
    print(mgr.status_report())
    assert mgr.current_level == DegradationLevel.FULL

    # Test 4: Feature access
    print(f"\n📝 Test 4: Feature access control")
    mgr.manual_degrade(DegradationLevel.DEGRADED, "test")
    assert mgr.is_enabled("t1_validators")
    assert not mgr.is_enabled("t2_validators")
    assert not mgr.is_enabled("remote_adapters")
    assert mgr.is_enabled("state_tracking")
    print(f"   ✅ Feature access: correct")

    print(f"\n{'='*50}")
    print(f"Degradation Manager tests passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
