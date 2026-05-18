"""
Prodinamik Engine v0.5 — Budget Enforcement

Budget limitleri ile Degradation Manager entegrasyonu.
Her run'ın budget'ı profile'dan alınır.
Budget aşılınca DegradationManager'a bildirilir.

Aksiyonlar:
- PROCEED: Normal çalışma
- WARN: Soft limit aşıldı, kullanıcıya uyarı
- SLOW: Validator sampling rate düşer
- STOP: Yeni validasyon engellenir, degradation tetiklenir
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Callable

from engine.cost import CostTracker
from engine.degradation import DegradationManager, DegradationLevel


class BudgetAction(Enum):
    PROCEED = "proceed"   # Normal
    WARN = "warn"         # Soft limit aşıldı
    SLOW = "slow"         # Sampling rate düşür
    STOP = "stop"         # Hard limit aşıldı


@dataclass
class BudgetLimit:
    """Tek bir budget limiti"""
    name: str
    soft_limit: float
    hard_limit: float
    current: float = 0.0
    unit: str = "usd"     # "usd" | "calls" | "tokens" | "seconds"

    @property
    def soft_exceeded(self) -> bool:
        return self.current >= self.soft_limit

    @property
    def hard_exceeded(self) -> bool:
        return self.current >= self.hard_limit

    @property
    def usage_pct(self) -> float:
        if self.hard_limit == 0:
            return 0.0
        return (self.current / self.hard_limit) * 100

    def check(self) -> BudgetAction:
        if self.hard_exceeded:
            return BudgetAction.STOP
        if self.soft_exceeded:
            return BudgetAction.WARN
        return BudgetAction.PROCEED

    def progress_bar(self, width: int = 15) -> str:
        filled = int((self.current / max(self.hard_limit, 0.01)) * width)
        filled = min(filled, width)
        bar = "▓" * filled + "░" * (width - filled)
        return f"[{bar}] {self.usage_pct:.0f}%"


class BudgetEnforcer:
    """
    Budget enforcement + Degradation entegrasyonu.

    Soft limit → WARN (kullanıcıya uyarı)
    Hard limit → STOP + Degrade to SURVIVAL

    Per-profile budget limits profile.yaml'den gelir.
    """

    def __init__(self, cost_tracker: CostTracker = None,
                 degradation_manager: DegradationManager = None):
        self.cost_tracker = cost_tracker or CostTracker()
        self.degradation = degradation_manager
        self.limits: Dict[str, BudgetLimit] = {}
        self.warnings_sent: set = set()
        self.validator_sampling: Dict[str, float] = {}  # validator → sampling rate

    def configure(self, budget_config: dict):
        """Profile'dan gelen budget yapılandırması"""
        self.limits = {
            "total_cost": BudgetLimit(
                name="total_cost",
                soft_limit=budget_config.get("soft_limit_usd", 1.0),
                hard_limit=budget_config.get("hard_limit_usd", 5.0),
                unit="usd",
            ),
            "llm_calls": BudgetLimit(
                name="llm_calls",
                soft_limit=budget_config.get("max_llm_calls_per_run", 20),
                hard_limit=budget_config.get("max_llm_calls_per_run", 30) + 10,
                unit="calls",
            ),
            "storage": BudgetLimit(
                name="storage",
                soft_limit=budget_config.get("max_storage_mb", 100) * 1024 * 1024,
                hard_limit=budget_config.get("max_storage_mb", 200) * 1024 * 1024,
                unit="bytes",
            ),
        }

    def check_validator(self, validator_name: str, tier: int) -> BudgetAction:
        """
        Validator çalışmadan önce budget kontrolü.

        Returns:
            PROCEED: Çalışabilir
            WARN: Uyarı göster, yine de çalış
            SLOW: Sampling rate düşür, bazen atla
            STOP: Çalışamaz
        """
        actions = []

        for name, limit in self.limits.items():
            action = limit.check()
            actions.append(action)

            if action == BudgetAction.WARN and name not in self.warnings_sent:
                self.warnings_sent.add(name)
            elif action == BudgetAction.STOP:
                return BudgetAction.STOP

        # Return most severe action found
        if BudgetAction.STOP in actions:
            return BudgetAction.STOP
        if BudgetAction.WARN in actions:
            return BudgetAction.WARN
        if BudgetAction.SLOW in actions:
            return BudgetAction.SLOW

        # SLOW: Hard limit'e yaklaşıldıysa
        if self.cost_tracker.total_llm_calls > self.limits.get("llm_calls", BudgetLimit("x", 100, 200)).soft_limit:
            if tier in (2, 3):
                return BudgetAction.SLOW

        return BudgetAction.PROCEED

    def apply_action(self, action: BudgetAction, validator_name: str = None):
        """Budget aksiyonunu uygula"""
        if action == BudgetAction.WARN:
            pass  # Uyarı zaten check_validator'da gönderildi

        elif action == BudgetAction.SLOW:
            rate = self.validator_sampling.get(validator_name, 1.0)
            self.validator_sampling[validator_name] = rate * 0.5
            # Min sampling rate: 0.1 (her 10 çağrıda 1)
            self.validator_sampling[validator_name] = max(
                self.validator_sampling.get(validator_name, 1.0), 0.1
            )

        elif action == BudgetAction.STOP:
            if self.degradation:
                self.degradation.manual_degrade(
                    DegradationLevel.SURVIVAL,
                    f"Budget hard limit reached: ${self.cost_tracker.total_usd:.2f}"
                )

    def should_run_validator(self, validator_name: str, tier: int) -> bool:
        """Validator'ın çalışıp çalışmayacağına karar ver (sampling ile)"""
        rate = self.validator_sampling.get(validator_name, 1.0)

        if rate >= 1.0:
            return True

        # Sampling: random check
        import random
        return random.random() < rate

    def update_from_tracker(self):
        """CostTracker'dan güncel değerleri al"""
        if "total_cost" in self.limits:
            self.limits["total_cost"].current = self.cost_tracker.total_usd
        if "llm_calls" in self.limits:
            self.limits["llm_calls"].current = self.cost_tracker.total_llm_calls
        if "storage" in self.limits:
            self.limits["storage"].current = self.cost_tracker.storage_bytes

    def status(self) -> str:
        """Budget durumunu göster"""
        self.update_from_tracker()

        lines = ["📊 **Budget Status:**"]
        for name, limit in self.limits.items():
            icon = "✅" if not limit.soft_exceeded else "⚠️" if not limit.hard_exceeded else "🆘"
            unit = limit.unit if limit.unit != "usd" else "$"
            lines.append(
                f"   {icon} `{name}`: {limit.progress_bar()} "
                f"({limit.current:.2f}{unit} / {limit.hard_limit:.2f}{unit})"
            )

        if self.warnings_sent:
            lines.append(f"   🔔 Warnings: {', '.join(self.warnings_sent)}")

        sampling = {k: f"{v:.0%}" for k, v in self.validator_sampling.items()
                    if v < 1.0}
        if sampling:
            lines.append(f"   📉 Sampling: {sampling}")

        return "\n".join(lines)

    def reset(self):
        """Run bazında reset (yeni run için)"""
        self.limits.clear()
        self.warnings_sent.clear()
        self.validator_sampling.clear()


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    from engine.cost import CostTracker
    from engine.degradation import DegradationManager
    import tempfile

    tmpdir = tempfile.mkdtemp()
    deg_mgr = DegradationManager(base_path=tmpdir)
    cost = CostTracker()
    enforcer = BudgetEnforcer(cost_tracker=cost, degradation_manager=deg_mgr)

    # Configure from profile
    enforcer.configure({
        "soft_limit_usd": 0.05,
        "hard_limit_usd": 0.10,
        "max_llm_calls_per_run": 5,
        "max_storage_mb": 50,
    })

    print("📊 Initial Budget Status:")
    print(enforcer.status())

    # Normal operation
    action = enforcer.check_validator("SlopScanT1", 1)
    print(f"\n📝 Before any calls: {action.value}")

    # Simulate costs
    for i in range(6):
        cost.record_llm("deepseek-v4-flash", 500, 150, "validation",
                        f"Validator-{i}")
        enforcer.update_from_tracker()
        action = enforcer.check_validator(f"Validator-{i}", 2)
        if action == BudgetAction.WARN:
            print(f"   ⚠️  Call {i+1}: soft limit reached")
        elif action == BudgetAction.STOP:
            print(f"   🆘 Call {i+1}: HARD LIMIT REACHED — degradation triggered!")
            enforcer.apply_action(action)
            break
        elif action == BudgetAction.SLOW:
            print(f"   🐢 Call {i+1}: slowed (sampling)")
        else:
            print(f"   ✅ Call {i+1}: proceed")

    print(f"\n📊 Final Budget Status:")
    print(enforcer.status())
    print(f"\n   Degradation level: {deg_mgr.current_level.value}")

    # Reset for new run
    enforcer.reset()
    print(f"\n🔄 Reset: limits cleared, warnings cleared")

    print(f"\n{'='*50}")
    print(f"Budget Enforcement demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
