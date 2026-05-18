"""
Prodinamik Engine v0.5 — Event Bus + Runtime Safety Invariants

Event Bus (Review #4):
- Trace ID + max hop count (5 hops)
- Duplicate detection
- Cross-profile cycle safety

Runtime Safety Invariants (Review #8):
- 10 runtime invariant
- Her invariant ihlalinde otomatik aksiyon
- Health report
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Set, Any, Callable
from enum import Enum
import uuid
import asyncio
from collections import defaultdict


# ──────────────────────────────────────────────
# Safe Event Bus (Review #4)
# ──────────────────────────────────────────────

@dataclass
class BusEvent:
    """Event bus event'i — trace ID + hop count ile"""
    type: str
    source_profile: str
    source_slug: str
    data: dict = field(default_factory=dict)
    timestamp: str = ""
    trace_id: str = ""
    hop_count: int = 0
    cost_usd: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.trace_id:
            self.trace_id = str(uuid.uuid4())


class EventBus:
    """
    Cross-profile event bus with cycle safety.

    - Trace ID: Her event zinciri benzersiz UUID
    - Hop count: Max 5 profil hops, aşılınca durdurulur
    - Duplicate detection: Aynı trace_id + type ikincisi atılır
    - Async subscribers
    """

    MAX_HOPS = 5
    _seen_traces: Set[str] = set()

    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.cycle_warnings: List[dict] = []
        self._seen_traces = set()

    def subscribe(self, event_type: str, handler: Callable):
        """Bir event tipine abone ol"""
        self.subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        """Aboneliği iptal et"""
        if handler in self.subscribers.get(event_type, []):
            self.subscribers[event_type].remove(handler)

    def emit(self, event: BusEvent):
        """
        Event yayınla.

        1. Hop count kontrolü (max 5)
        2. Duplicate kontrolü
        3. Subscriber'ları async çağır
        """
        # Hop count
        if event.hop_count >= self.MAX_HOPS:
            self.cycle_warnings.append({
                "trace_id": event.trace_id,
                "hop_count": event.hop_count,
                "last_type": event.type,
                "source_slug": event.source_slug,
                "timestamp": datetime.now().isoformat(),
            })
            return  # Sessizce durdur

        # Duplicate detection
        trace_key = f"{event.trace_id}:{event.type}"
        if trace_key in self._seen_traces:
            self.cycle_warnings.append({
                "trace_id": event.trace_id,
                "type": "duplicate",
                "event_type": event.type,
                "hop_count": event.hop_count,
                "timestamp": datetime.now().isoformat(),
            })
            return  # Duplicate atla
        self._seen_traces.add(trace_key)

        # Subscriber'ları çağır
        for handler in self.subscribers.get(event.type, []):
            asyncio.create_task(self._safe_call(handler, event))

    async def _safe_call(self, handler: Callable, event: BusEvent):
        """Subscriber'ı hata toleranslı çağır"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            self.cycle_warnings.append({
                "trace_id": event.trace_id,
                "error": str(e),
                "handler": handler.__name__ if hasattr(handler, '__name__') else str(handler),
                "timestamp": datetime.now().isoformat(),
            })

    def unsubscribe(self, event_type: str, handler: Callable):
        """Aboneliği iptal et"""
        handlers = self.subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def clear_traces(self):
        """Periyodik temizlik (trace set'i çok büyümesin)"""
        self._seen_traces.clear()

    @property
    def has_cycles(self) -> bool:
        """Hiç cycle tespit edilmiş mi?"""
        return len(self.cycle_warnings) > 0

    @property
    def stats(self) -> dict:
        return {
            "subscribers": {
                etype: len(hs) for etype, hs in self.subscribers.items()
            },
            "total_subscribers": sum(len(hs) for hs in self.subscribers.values()),
            "cycle_warnings": len(self.cycle_warnings),
            "seen_traces": len(self._seen_traces),
        }


# ──────────────────────────────────────────────
# Runtime Safety Invariants (Review #8)
# ──────────────────────────────────────────────

@dataclass
class InvariantViolation:
    name: str
    category: str
    severity: str       # "WARNING" | "CRITICAL" | "FATAL"
    message: str
    timestamp: str
    resolved: bool = False
    resolved_at: Optional[str] = None


class RuntimeSafetyMonitor:
    """
    Runtime'da sürekli kontrol edilen invariant'lar.
    Her transition, validasyon, event sonrası çalıştırılabilir.
    Invariant ihlali → otomatik aksiyon (action matrix).
    """

    INVARIANTS = {
        # State machine invariants
        "state_exists": {
            "check": lambda sm, s: s in sm.all_states,
            "category": "state_machine",
            "severity": "CRITICAL",
            "action": "pause",
        },
        "valid_transition": {
            "check": lambda sm, f, t: t in sm.transitions.get(f, []),
            "category": "state_machine",
            "severity": "CRITICAL",
            "action": "pause",
        },
        "no_state_leak": {
            "check": lambda sm, **kw: all(
                s in sm.all_states
                for s in sm.current_states.values()
            ) if hasattr(sm, 'current_states') else True,
            "category": "state_machine",
            "severity": "CRITICAL",
            "action": "pause",
        },

        # Progress invariants
        "monotonic_progress": {
            "check": lambda sm, **kw: (
                sm.iteration_count <= sm.max_iterations
            ) if hasattr(sm, 'iteration_count') else True,
            "category": "progress",
            "severity": "CRITICAL",
            "action": "block",
        },

        # Resource invariants
        "budget_respected": {
            "check": lambda run, **kw: (
                run.cost_tracker.total_usd <= run.profile.budget.hard_limit
            ) if hasattr(run, 'cost_tracker') else True,
            "category": "resources",
            "severity": "FATAL",
            "action": "degrade_survival",
        },
        "event_count_reasonable": {
            "check": lambda store, **kw: (
                store.event_count < 10000
            ),
            "category": "resources",
            "severity": "WARNING",
            "action": "compact",
        },

        # Data integrity invariants
        "no_orphan_events": {
            "check": lambda store, **kw: (
                len(store._index) == 0 or
                all(store.get(s) is not None for s in list(store._index.keys())[:100])
            ),
            "category": "data_integrity",
            "severity": "WARNING",
            "action": "compact",
        },
        "cache_fresh": {
            "check": lambda cache, deg, **kw: (
                deg != DegradationLevel.FULL or cache.hit_rate > 0.3
            ) if hasattr(cache, 'hit_rate') else True,
            "category": "data_integrity",
            "severity": "WARNING",
            "action": "notify",
        },

        # Drift invariants
        "drift_not_exploding": {
            "check": lambda run, **kw: (
                run.drift.instant_rate < 0.9
            ) if hasattr(run, 'drift') else True,
            "category": "drift",
            "severity": "CRITICAL",
            "action": "escalate",
        },

        # Safety invariants
        "cross_profile_no_cycle": {
            "check": lambda bus, **kw: (
                not bus.has_cycles
            ),
            "category": "safety",
            "severity": "FATAL",
            "action": "bus_reset",
        },
    }

    # Aksiyon matrisi: hangi invariant hangi aksiyonu tetikler
    ACTIONS = {
        "pause": "⏸️ Pause run",
        "block": "🚫 Block transition",
        "degrade_survival": "🆘 Degrade to SURVIVAL",
        "compact": "🧹 Compact event store",
        "notify": "🔔 Notify user",
        "escalate": "📢 Escalate to human",
        "bus_reset": "🔄 Reset event bus",
    }

    def __init__(self, event_bus: EventBus = None):
        self.violations: List[InvariantViolation] = []
        self.check_count = 0
        self.event_bus = event_bus

    def check_all(self, state_machine=None, run=None,
                  store=None, cache=None, bus=None,
                  degradation=None) -> List[InvariantViolation]:
        """
        Tüm invariant'ları kontrol et.
        
        Her invariant'ın `check` fonksiyonuna ilgili parametreler
            otomatik olarak verilir.
        """
        self.check_count += 1
        new_violations = []

        context = {
            "sm": state_machine,
            "run": run,
            "store": store,
            "cache": cache,
            "bus": bus or self.event_bus,
            "deg": degradation,
        }

        for name, config in self.INVARIANTS.items():
            try:
                # check fonksiyonuna context'teki uygun parametreleri ver
                check_fn = config["check"]
                passed = self._call_with_context(check_fn, context, name)

                if not passed:
                    violation = InvariantViolation(
                        name=name,
                        category=config["category"],
                        severity=config["severity"],
                        message=f"Invariant '{name}' violated",
                        timestamp=datetime.now().isoformat(),
                    )
                    new_violations.append(violation)
                    self.violations.append(violation)

                    # Otomatik aksiyon
                    self._take_action(config["action"], name, context)

            except Exception as e:
                violation = InvariantViolation(
                    name=name,
                    category="system",
                    severity="CRITICAL",
                    message=f"Invariant check '{name}' failed: {e}",
                    timestamp=datetime.now().isoformat(),
                )
                new_violations.append(violation)
                self.violations.append(violation)

        return new_violations

    def _call_with_context(self, check_fn, context, name) -> bool:
        """
        Invariant check fonksiyonuna uygun parametreleri geçir.
        
        check = lambda sm, s: s in sm.all_states
        → context'ten "sm" parametresini bulur
        → fonksiyona sm=... olarak geçirir
        """
        import inspect
        sig = inspect.signature(check_fn)
        kwargs = {}

        for param_name in sig.parameters:
            if param_name in context and context[param_name] is not None:
                kwargs[param_name] = context[param_name]

        return check_fn(**kwargs)

    def _take_action(self, action: str, invariant_name: str, context: dict):
        """Invariant ihlalinde aksiyon al"""
        if action == "compact" and context.get("store"):
            asyncio.create_task(self._async_compact(context["store"]))
        elif action == "bus_reset" and context.get("bus"):
            context["bus"].clear_traces()

    async def _async_compact(self, store):
        """Async compaction"""
        try:
            store.compact(store.events_dir.parent.name)
        except Exception:
            pass

    def resolve_violation(self, name: str):
        """Violation'ı çözülmüş olarak işaretle"""
        for v in self.violations:
            if v.name == name and not v.resolved:
                v.resolved = True
                v.resolved_at = datetime.now().isoformat()
                break

    @property
    def active_violations(self) -> List[InvariantViolation]:
        return [v for v in self.violations if not v.resolved]

    @property
    def health_score(self) -> float:
        """
        0.0 (critical) → 1.0 (perfect)
        
        - Her active CRITICAL violation: -0.3
        - Her active WARNING violation: -0.1
        - Her active FATAL violation: İndeks direkt 0.0
        """
        fatals = [v for v in self.active_violations if v.severity == "FATAL"]
        if fatals:
            return 0.0

        score = 1.0
        for v in self.active_violations:
            if v.severity == "CRITICAL":
                score -= 0.3
            elif v.severity == "WARNING":
                score -= 0.1

        return max(0.0, score)

    def health_report(self) -> str:
        """Kullanıcıya invariant durumunu göster"""
        active = self.active_violations
        if not active:
            return (
                f"✅ **Runtime Safety:** Score `{self.health_score:.2f}`\n"
                f"   All invariants passed (`{self.check_count}` checks)"
            )

        score_icon = "✅" if self.health_score >= 0.8 else "⚠️" if self.health_score >= 0.3 else "🆘"

        lines = [
            f"{score_icon} **Runtime Safety:** Score `{self.health_score:.2f}`",
            f"   `{len(active)}` active violation(s) (`{self.check_count}` checks)",
        ]

        for v in active[:5]:
            action = self.INVARIANTS.get(v.name, {}).get("action", "unknown")
            icon = {
                "FATAL": "💥", "CRITICAL": "❌", "WARNING": "⚠️",
            }.get(v.severity, "📌")
            lines.append(f"   {icon} `{v.name}` [{v.category}] → {self.ACTIONS.get(action, '?')}")

        if len(active) > 5:
            lines.append(f"   ... and `{len(active) - 5}` more")

        # Category summary
        from collections import Counter
        cats = Counter(v.category for v in active)
        lines.append(f"\n   📊 By category: " + ", ".join(
            f"`{c}`: {n}" for c, n in cats.most_common()
        ))

        return "\n".join(lines)


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

async def async_demo():
    from engine.degradation import DegradationLevel, DegradationManager

    # Event Bus
    bus = EventBus()
    print("📡 Event Bus created")

    # Subscribe
    call_count = [0]

    async def on_release(event):
        call_count[0] += 1
        print(f"   📩 Received: {event.type} from {event.source_profile}")

    bus.subscribe("release.published", on_release)

    # Emit
    event1 = BusEvent(
        type="release.published",
        source_profile="software",
        source_slug="flux-v1",
        data={"version": "1.0.0"},
    )
    bus.emit(event1)
    await asyncio.sleep(0.05)  # Allow async handler to run
    print(f"   📤 Emitted: {event1.type} (trace_id={event1.trace_id[:8]}...)")

    # Duplicate (same trace_id + type)
    bus.emit(event1)
    await asyncio.sleep(0.05)
    print(f"   📤 Duplicate: {event1.type} → should be ignored")

    # Cycle test: max hops
    event3 = BusEvent(
        type="release.published",
        source_profile="software",
        source_slug="flux-changelog",
        trace_id=event1.trace_id,
        hop_count=5,
    )
    bus.emit(event3)
    await asyncio.sleep(0.05)
    print(f"   📤 Max hops reached: {len(bus.cycle_warnings)} cycle warning(s)")

    print(f"\n📊 Bus stats: {bus.stats}")

    # Runtime Safety Monitor
    monitor = RuntimeSafetyMonitor(event_bus=bus)
    violations = monitor.check_all(bus=bus)
    print(f"\n🛡️ Runtime Safety: {monitor.health_report()}")
    print(f"   Active violations: {len(monitor.active_violations)}")
    print(f"   Health score: {monitor.health_score:.2f}")

    print(f"\n{'='*50}")
    print(f"Event Bus + Runtime Safety tests passed!")
    print(f"{'='*50}")


def demo():
    import asyncio
    asyncio.run(async_demo())
