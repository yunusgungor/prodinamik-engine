"""
Prodinamik Engine v0.5 — Cost Tracker

Multi-dimensional cost tracking:
1. TOKENS — LLM çağrıları (validator, generation)
2. COMPUTE — CPU/GPU süresi (build, test)
3. STORAGE — Disk kullanımı (run data, cache, log)
4. NETWORK — API çağrıları (adapter, remote validator)

Deferred Efficiency (Review #6):
- T0: Run bitince benzer run'ların ortalamasına göre tahmin
- T1: N gün sonra API'den gerçek metrikler

Cost-Aware Events (Review #7):
- Event'ler cost_usd taşır
- TemporalCostDebugger ile cost timeline + anomaly detection
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum
import json
import statistics
from pathlib import Path


# ──────────────────────────────────────────────
# Cost Types
# ──────────────────────────────────────────────

@dataclass
class LLMCall:
    """Tek bir LLM API çağrısı"""
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    purpose: str           # "validation" | "generation" | "analysis"
    validator: str         # Hangi validator çağırdı
    timestamp: str = ""
    wasted: bool = False   # Retry sonrası başarısız mı?

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ComputeOp:
    """CPU/GPU işlemi"""
    phase: str             # "build" | "test" | "compile"
    duration_s: float
    cores: int
    gpu: bool = False
    cost_usd: float = 0.0

    def __post_init__(self):
        if self.cost_usd == 0.0:
            COST_PER_CORE_HOUR = 0.05
            COST_PER_GPU_HOUR = 2.50
            hours = self.duration_s / 3600
            self.cost_usd = hours * self.cores * COST_PER_CORE_HOUR
            if self.gpu:
                self.cost_usd += hours * COST_PER_GPU_HOUR


@dataclass
class NetworkCall:
    """API/network çağrısı"""
    adapter: str
    endpoint: str
    duration_ms: int
    cost_usd: float
    status_code: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ──────────────────────────────────────────────
# Cost Tracker
# ──────────────────────────────────────────────

class CostTracker:
    """
    Multi-dimensional cost tracker.

    Cost per model ($/1M tokens):
      deepseek-v4-flash: $0.15 input / $0.60 output
      gpt-4o:           $2.50 / $10.00
      claude-sonnet-4:  $3.00 / $15.00

    Compute: $0.05/core/hour, $2.50/GPU/hour
    Storage: $0.10/GB/month
    """

    COST_PER_MODEL = {
        "deepseek-v4-flash": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "claude-sonnet-4": {"input": 3.00, "output": 15.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    }

    COST_PER_CORE_HOUR = 0.05
    COST_PER_GPU_HOUR = 2.50
    COST_PER_GB_MONTH = 0.10

    def __init__(self):
        self.llm_calls: List[LLMCall] = []
        self.compute_ops: List[ComputeOp] = []
        self.network_calls: List[NetworkCall] = []
        self.storage_bytes: int = 0

    # ──────────────────────────────────────
    # Record
    # ──────────────────────────────────────

    def record_llm(self, model: str, input_tokens: int, output_tokens: int,
                   purpose: str, validator: str, wasted: bool = False) -> float:
        """LLM çağrısı kaydet. Cost'u döndür."""
        rates = self.COST_PER_MODEL.get(model, {"input": 0, "output": 0})
        cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

        self.llm_calls.append(LLMCall(
            model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=cost, purpose=purpose, validator=validator,
            wasted=wasted,
        ))
        return cost

    def record_compute(self, phase: str, duration_s: float,
                       cores: int = 1, gpu: bool = False) -> float:
        """Compute işlemi kaydet. Cost'u döndür."""
        op = ComputeOp(phase=phase, duration_s=duration_s, cores=cores, gpu=gpu)
        self.compute_ops.append(op)
        return op.cost_usd

    def record_network(self, adapter: str, endpoint: str, duration_ms: int,
                       cost_usd: float, status_code: int = 0) -> float:
        """Network çağrısı kaydet."""
        self.network_calls.append(NetworkCall(
            adapter=adapter, endpoint=endpoint, duration_ms=duration_ms,
            cost_usd=cost_usd, status_code=status_code,
        ))
        return cost_usd

    def record_storage(self, bytes_count: int):
        """Storage kullanımı güncelle."""
        self.storage_bytes += bytes_count

    # ──────────────────────────────────────
    # Totals
    # ──────────────────────────────────────

    @property
    def total_llm_cost(self) -> float:
        return sum(c.cost_usd for c in self.llm_calls)

    @property
    def total_compute_cost(self) -> float:
        return sum(c.cost_usd for c in self.compute_ops)

    @property
    def total_network_cost(self) -> float:
        return sum(c.cost_usd for c in self.network_calls)

    @property
    def total_storage_cost(self) -> float:
        gb = self.storage_bytes / (1024 ** 3)
        return gb * self.COST_PER_GB_MONTH

    @property
    def total_usd(self) -> float:
        return (self.total_llm_cost + self.total_compute_cost +
                self.total_network_cost + self.total_storage_cost)

    @property
    def total_llm_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.llm_calls)

    @property
    def total_llm_calls(self) -> int:
        return len(self.llm_calls)

    # ──────────────────────────────────────
    # Breakdown
    # ──────────────────────────────────────

    def breakdown_by_validator(self) -> Dict[str, float]:
        """Hangi validator ne kadar token harcadı?"""
        b = {}
        for c in self.llm_calls:
            b[c.validator] = b.get(c.validator, 0.0) + c.cost_usd
        for c in self.compute_ops:
            b[c.phase] = b.get(c.phase, 0.0) + c.cost_usd
        return dict(sorted(b.items(), key=lambda x: x[1], reverse=True))

    def breakdown_by_purpose(self) -> Dict[str, float]:
        """Ne amaçla harcandı?"""
        b = {}
        for c in self.llm_calls:
            b[c.purpose] = b.get(c.purpose, 0.0) + c.cost_usd
        return b

    def breakdown_by_model(self) -> Dict[str, float]:
        """Hangi model ne kadar harcadı?"""
        b = {}
        for c in self.llm_calls:
            b[c.model] = b.get(c.model, 0.0) + c.cost_usd
        return b

    @property
    def waste_estimate(self) -> float:
        """Boşa giden token maliyeti"""
        return sum(c.cost_usd for c in self.llm_calls if c.wasted)

    @property
    def top_spenders(self, n: int = 5) -> List[dict]:
        """En pahalı N validator/phase"""
        b = self.breakdown_by_validator()
        return [{"name": k, "cost": v} for k, v in list(b.items())[:n]]

    @property
    def savings_tips(self) -> List[str]:
        """Maliyet düşürme önerileri"""
        tips = []

        if self.waste_estimate > 0.5:
            tips.append("🔧 Boşa giden token: ${:.2f}. "
                       "Cache'i kontrol et.".format(self.waste_estimate))

        llm_cost = self.total_llm_cost
        compute_cost = self.total_compute_cost
        if compute_cost > llm_cost and compute_cost > 1.0:
            tips.append("⚡ Compute maliyeti LLM'den yüksek. "
                       "Paralel build'i optimize et.")

        model_costs = self.breakdown_by_model()
        expensive = [m for m, c in model_costs.items()
                    if c > 1.0 and m in ("gpt-4o", "claude-sonnet-4")]
        if expensive:
            tips.append(f"💰 Pahalı model kullanımı: {', '.join(expensive)}. "
                       f"Daha ucuz modele geçmeyi dene.")

        return tips

    # ──────────────────────────────────────
    # Display
    # ──────────────────────────────────────

    def summary(self) -> str:
        return (
            f"💵 **Cost:** `${self.total_usd:.3f}`\n"
            f"   Tokens: `${self.total_llm_cost:.3f}` "
            f"({self.total_llm_calls} calls, {self.total_llm_tokens} tokens)\n"
            f"   Compute: `${self.total_compute_cost:.3f}`\n"
            f"   Network: `${self.total_network_cost:.3f}`\n"
            f"   Storage: `${self.total_storage_cost:.4f}`\n"
            f"   Waste: `${self.waste_estimate:.3f}`\n"
            f"   Efficiency: `{self.efficiency_score:.2f}x`"
        )

    @property
    def efficiency_score(self) -> float:
        """output_value / total_cost (şimdilik output_value=1.0 varsayılan)"""
        return 1.0 / max(self.total_usd, 0.001)

    def to_dict(self) -> dict:
        return {
            "total_usd": self.total_usd,
            "llm": {"calls": self.total_llm_calls, "tokens": self.total_llm_tokens,
                    "cost": self.total_llm_cost},
            "compute": {"ops": len(self.compute_ops), "cost": self.total_compute_cost},
            "network": {"calls": len(self.network_calls), "cost": self.total_network_cost},
            "storage": {"bytes": self.storage_bytes, "cost": self.total_storage_cost},
            "waste": self.waste_estimate,
        }


# ──────────────────────────────────────────────
# Deferred Efficiency (Review #6)
# ──────────────────────────────────────────────

@dataclass
class RunEfficiency:
    """Bir run'ın efficiency verisi"""
    slug: str
    profile: str
    format: str
    total_cost: float
    estimated: float       # T0: benzer run'ların ortalaması
    actual: Optional[float] = None  # T1: API'den gelen gerçek değer
    updated_at: str = ""
    source: str = "estimate"  # "estimate" | "api" | "manual"

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    @property
    def display_value(self) -> str:
        if self.actual:
            return f"{self.actual:.2f}x (actual)"
        return f"{self.estimated:.2f}x (estimate)"

    @property
    def variance_pct(self) -> Optional[float]:
        if self.actual and self.estimated:
            return (self.actual - self.estimated) / self.estimated * 100
        return None


class EfficiencyTracker:
    """
    Efficiency iki aşamada hesaplanır:
    T0 (run bitince):  Tahmini — benzer run'ların ortalaması
    T1 (N gün sonra):  Gerçek — API'den veri çekilince
    """

    def __init__(self):
        self.completed_runs: List[RunEfficiency] = []

    def add_completed(self, run: RunEfficiency):
        """Tamamlanmış run ekle"""
        self.completed_runs.append(run)

    def estimate(self, slug: str, profile: str, format: str,
                 total_cost: float) -> RunEfficiency:
        """
        Run bitince: benzer profile+format'taki run'ların
        ortalama efficiency'sini tahmin et.
        """
        similar = [
            r for r in self.completed_runs
            if r.profile == profile and r.format == format
            and r.actual is not None
        ]

        estimated = 1.0
        if similar:
            estimated = statistics.mean(r.actual for r in similar)

        eff = RunEfficiency(
            slug=slug, profile=profile, format=format,
            total_cost=total_cost, estimated=estimated,
        )
        self.completed_runs.append(eff)
        return eff

    def record_actual(self, slug: str, actual_value: float, source: str = "api"):
        """N gün sonra: gerçek efficiency değerini gir."""
        for r in self.completed_runs:
            if r.slug == slug:
                r.actual = actual_value
                r.source = source
                r.updated_at = datetime.now().isoformat()
                return r
        return None

    def display(self, slug: str) -> str:
        for r in self.completed_runs:
            if r.slug == slug:
                diff = ""
                if r.variance_pct is not None:
                    sign = "+" if r.variance_pct >= 0 else ""
                    diff = f" ({sign}{r.variance_pct:.1f}% vs estimate)"
                return (f"📊 **Efficiency:** `{r.slug}`\n"
                       f"   T0 estimate: `{r.estimated:.2f}x`\n"
                       f"   T1 actual:   `{r.actual:.2f}x`{diff}\n"
                       f"   Source: `{r.source}`"
                       if r.actual else
                       f"📊 **Efficiency:** `{r.slug}`\n"
                       f"   T0 estimate: `{r.estimated:.2f}x`\n"
                       f"   Actual: pending")
        return f"⚠️ Run '{slug}' not found"


# ──────────────────────────────────────────────
# Temporal Cost Debugger (Review #7)
# ──────────────────────────────────────────────

@dataclass
class CostAnomaly:
    """İstatistiksel cost anomalisi"""
    sequence: int
    event_type: str
    cost_usd: float
    mean: float
    std: float
    sigma: float
    reason: str


class TemporalCostDebugger:
    """
    Cost-Aware event'ler üzerinden çalışır.
    Event store'dan cost verisini okur, anomaly detection yapar.
    """

    def analyze_events(self, events: List[Any]) -> dict:
        """
        Event listesinden cost analizi çıkar.

        events: CostAwareEvent listesi (cost_usd field'lı)
        """
        if not events:
            return {"total_cost": 0, "event_count": 0, "anomalies": []}

        costs = [e.cost_usd for e in events]
        total = sum(costs)
        mean = statistics.mean(costs)
        stdev = statistics.stdev(costs) if len(costs) > 1 else 0.001

        # Anomaly detection: 3σ threshold
        anomalies = [
            CostAnomaly(
                sequence=e.sequence,
                event_type=e.event_type,
                cost_usd=e.cost_usd,
                mean=mean,
                std=stdev,
                sigma=abs(e.cost_usd - mean) / max(stdev, 0.001),
                reason=f"${e.cost_usd:.3f} is {abs(e.cost_usd - mean) / max(stdev, 0.001):.1f}σ above mean (${mean:.3f})"
            )
            for e in events
            if e.cost_usd > mean + 3 * stdev and e.cost_usd > 0.01
        ]

        # Top spenders
        by_type = {}
        for e in events:
            by_type[e.event_type] = by_type.get(e.event_type, 0.0) + e.cost_usd

        return {
            "total_cost": round(total, 4),
            "event_count": len(events),
            "mean_cost": round(mean, 4),
            "std_cost": round(stdev, 4),
            "anomalies": anomalies,
            "top_by_type": dict(sorted(
                by_type.items(), key=lambda x: x[1], reverse=True
            )[:5]),
        }

    def cost_timeline(self, events: List[Any]) -> str:
        """Event timeline'ı cost ile göster"""
        analysis = self.analyze_events(events)

        lines = [f"💰 **Cost Timeline:** {analysis['event_count']} events, "
                 f"total `${analysis['total_cost']:.3f}`"]

        for e in events[-10:]:  # Son 10 event
            if e.cost_usd > 0.005:
                icon = "💰" if e.cost_usd > 0.1 else "🪙"
                lines.append(
                    f"  {icon} `#{e.sequence}` `{e.event_type}` "
                    f"`${e.cost_usd:.3f}`"
                )

        if analysis['anomalies']:
            lines.append(f"\n⚠️ **Anomalies:** {len(analysis['anomalies'])}")
            for a in analysis['anomalies'][:3]:
                lines.append(f"  • `#{a.sequence}` {a.reason}")

        if analysis['top_by_type']:
            lines.append(f"\n📊 **By type:**")
            for etype, cost in list(analysis['top_by_type'].items())[:5]:
                lines.append(f"  • `{etype}`: `${cost:.3f}`")

        return "\n".join(lines)


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    # Cost Tracker
    tracker = CostTracker()
    tracker.record_llm("deepseek-v4-flash", 500, 150, "validation", "SlopScanT1")
    tracker.record_llm("gpt-4o", 1000, 300, "validation", "RubricScore")
    tracker.record_llm("deepseek-v4-flash", 300, 80, "generation", "WriterAgent")
    tracker.record_llm("deepseek-v4-flash", 200, 50, "validation", "SlopScanT1",
                       wasted=True)  # Retry sonrası başarısız

    tracker.record_compute("build", 120, cores=4)
    tracker.record_compute("test", 60, cores=8)

    tracker.record_storage(1024 * 1024 * 50)  # 50MB

    print("📊 Cost Tracker:")
    print(tracker.summary())
    print(f"\n   By validator: {tracker.breakdown_by_validator()}")
    print(f"   By model: {tracker.breakdown_by_model()}")
    print(f"   Waste: ${tracker.waste_estimate:.3f}")
    if tracker.savings_tips:
        print(f"   Tips: {tracker.savings_tips[0]}")

    # Efficiency Tracker
    eff = EfficiencyTracker()
    eff.add_completed(RunEfficiency(
        slug="flux-v1", profile="software", format="release",
        total_cost=0.5, estimated=2.0, actual=2.5, source="api"
    ))
    eff.add_completed(RunEfficiency(
        slug="ai-thread", profile="content", format="thread",
        total_cost=0.05, estimated=1.5, actual=0.8, source="api"
    ))

    print(f"\n📊 Efficiency:")
    print(f"   Flux: {eff.display('flux-v1')}")
    print(f"   AI Thread: {eff.display('ai-thread')}")

    flux_eff = eff.estimate("new-run", "software", "release", 0.3)
    print(f"   New (est.): {flux_eff.display_value}")

    # Cost Timeline (simulated events)
    from engine.event_store import CostAwareEvent, EventType
    events = [
        CostAwareEvent(sequence=1, run_slug="demo", timestamp="2026-05-18T10:00:00",
                      event_type="validation", data={"validator": "SlopScanT1", "passed": True},
                      cost_usd=0.01),
        CostAwareEvent(sequence=2, run_slug="demo", timestamp="2026-05-18T10:01:00",
                      event_type="validation", data={"validator": "RubricScore", "passed": False},
                      cost_usd=0.35),
        CostAwareEvent(sequence=3, run_slug="demo", timestamp="2026-05-18T10:02:00",
                      event_type="adapter", data={"adapter": "Buffer", "status": "sent"},
                      cost_usd=0.001),
        CostAwareEvent(sequence=4, run_slug="demo", timestamp="2026-05-18T10:03:00",
                      event_type="validation", data={"validator": "HallucinationCheck", "passed": True},
                      cost_usd=0.28),
        CostAwareEvent(sequence=5, run_slug="demo", timestamp="2026-05-18T10:04:00",
                      event_type="state_transition", data={"from": "drafting", "to": "verification"},
                      cost_usd=0.0),
    ]

    debugger = TemporalCostDebugger()
    print(f"\n💰 Cost Timeline:")
    print(debugger.cost_timeline(events))

    print(f"\n{'='*50}")
    print(f"Cost Tracker demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
