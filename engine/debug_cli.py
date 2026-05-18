"""
Prodinamik Engine v0.5 — Debug CLI

Comprehensive debug commands for run inspection.

/debug timeline <slug>        → Son 20 event
/debug event <slug> <id>      → Event detayı
/debug state <slug> <id>      → Event sonrası state
/debug why <slug> <id>        → 5-Why root cause analysis
/debug cost <slug>            → Cost timeline + anomalies
/debug efficiency <slug>      → T0/T1 efficiency
/debug health <slug>          → Engine health report
/debug budget <slug>          → Budget status
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path
import re


class DebugCLI:
    """
    Hermes slash command benzeri debug komutları.
    Tüm engine bileşenlerinin durumunu sorgulayabilir.
    """

    def __init__(self, run_manager=None, event_store=None,
                 cost_tracker=None, efficiency_tracker=None,
                 degradation_manager=None, budget_enforcer=None,
                 runtime_safety=None, profile_registry=None):
        self.run_manager = run_manager
        self.event_store = event_store
        self.cost_tracker = cost_tracker
        self.efficiency_tracker = efficiency_tracker
        self.degradation = degradation_manager
        self.budget = budget_enforcer
        self.safety = runtime_safety
        self.registry = profile_registry

    # ──────────────────────────────────────
    # Command Router
    # ──────────────────────────────────────

    def handle(self, command: str, *args) -> str:
        """Komutu route et"""
        cmd_map = {
            "timeline": self._cmd_timeline,
            "event": self._cmd_event,
            "state": self._cmd_state,
            "why": self._cmd_why,
            "cost": self._cmd_cost,
            "efficiency": self._cmd_efficiency,
            "health": self._cmd_health,
            "budget": self._cmd_budget,
            "summary": self._cmd_summary,
            "help": self._cmd_help,
        }

        handler = cmd_map.get(command)
        if not handler:
            return self._cmd_help()

        try:
            return handler(*args)
        except TypeError as e:
            return f"❌ Wrong arguments for '{command}': {e}\n{self._cmd_usage(command)}"

    def _cmd_usage(self, command: str) -> str:
        usage = {
            "timeline": "Usage: /debug timeline <slug>",
            "event": "Usage: /debug event <slug> <event_id>",
            "state": "Usage: /debug state <slug> [event_id]",
            "why": "Usage: /debug why <slug> <event_id>",
            "cost": "Usage: /debug cost <slug>",
            "efficiency": "Usage: /debug efficiency <slug>",
            "health": "Usage: /debug health [slug]",
            "budget": "Usage: /debug budget <slug>",
            "summary": "Usage: /debug summary <slug>",
        }
        return usage.get(command, "Unknown command. Try /debug help")

    # ──────────────────────────────────────
    # Commands
    # ──────────────────────────────────────

    def _cmd_timeline(self, slug: str = None) -> str:
        """Run'ın son 20 event'ini göster"""
        if not slug:
            return "❌ Slug required. /debug timeline <slug>"

        if not self.event_store:
            return self._event_store_missing()

        events = self.event_store.get_range(
            max(1, self.event_store.event_count - 19),
            20
        )

        if not events:
            return f"📭 No events for `{slug}`"

        lines = [f"📜 **Timeline:** `{slug}`"]
        for e in events[-20:]:
            icon = {
                "state_transition": "🔄",
                "validation": "✅" if e.data.get("passed", True) else "❌",
                "adapter_call": "📤",
                "error": "💥",
                "user_action": "👤",
                "degradation_change": "⚠️",
                "invariant_violation": "🚨",
            }.get(e.event_type, "📌")

            summary = self._event_summary(e)
            lines.append(f"  {icon} `#{e.sequence}` [{e.timestamp[11:19] if len(e.timestamp) > 18 else e.timestamp}] {summary}")

        return "\n".join(lines)

    def _cmd_event(self, slug: str = None, event_id: str = None) -> str:
        """Belirli bir event'in detayı"""
        if not slug or not event_id:
            return "❌ Usage: /debug event <slug> <event_id>"

        if not self.event_store:
            return self._event_store_missing()

        try:
            eid = int(event_id)
        except ValueError:
            return f"❌ Invalid event_id: {event_id}"

        event = self.event_store.get(eid)
        if not event:
            return f"❌ Event #{eid} not found for `{slug}`"

        import json
        return (
            f"📌 **Event #{event.sequence}**\n"
            f"   Type: `{event.event_type}`\n"
            f"   Time: `{event.timestamp}`\n"
            f"   Cost: `${event.cost_usd:.4f}`\n"
            f"   Trace: `{event.trace_id or 'N/A'}`\n"
            f"   Parent: `{event.parent_id or 'N/A'}`\n"
            f"   Data: ```json\n{json.dumps(event.data, indent=2, ensure_ascii=False)[:500]}\n```"
        )

    def _cmd_state(self, slug: str = None, event_id: str = None) -> str:
        """Run'ın mevcut veya belirli event sonrası state'i"""
        if not slug:
            return "❌ Usage: /debug state <slug> [event_id]"

        if not self.run_manager:
            return "❌ RunManager not configured"

        run = self.run_manager.get_run(slug)
        if not run:
            return f"❌ Run '{slug}' not found"

        if event_id:
            return (
                f"⏪ **Time Travel:** Event `#{event_id}` sonrası state\n"
                f"   Run: `{slug}`\n"
                f"   (Full event replay requires EventStore)"
            )

        meta = run.meta
        return (
            f"📌 **Run State:** `{slug}`\n"
            f"   Current: `{meta.state}`\n"
            f"   Profile: `{meta.profile}`\n"
            f"   Title: `{meta.title}`\n"
            f"   Status: `{meta.status}`\n"
            f"   Version: `{meta.version}`\n"
            f"   Created: `{meta.created_at}`\n"
            f"   Updated: `{meta.updated_at}`"
        )

    def _cmd_why(self, slug: str = None, event_id: str = None) -> str:
        """5-Why root cause analysis"""
        if not slug or not event_id:
            return "❌ Usage: /debug why <slug> <event_id>"

        if not self.event_store:
            return self._event_store_missing()

        try:
            eid = int(event_id)
        except ValueError:
            return f"❌ Invalid event_id: {event_id}"

        event = self.event_store.get(eid)
        if not event:
            return f"❌ Event #{eid} not found"

        # Build causal chain
        chain = [event]
        current = event
        seen = {event.sequence}

        while current.parent_id and current.parent_id not in seen:
            parent = self.event_store.get(current.parent_id)
            if not parent:
                break
            chain.append(parent)
            seen.add(parent.sequence)
            current = parent

        chain.reverse()

        lines = [f"🔍 **5-Why Analysis:** `{slug}` Event `#{event_id}`"]
        lines.append(f"   Problem: `{self._event_summary(event)}`")

        for i, e in enumerate(chain[:6], 1):
            lines.append(f"\n   ⬆️ **Why #{i}?**")
            lines.append(f"      `{self._event_summary(e)}`")
            lines.append(f"      Type: `{e.event_type}`, Cost: `${e.cost_usd:.4f}`")

        if len(chain) > 6:
            lines.append(f"\n   ... and {len(chain) - 6} more")

        # Root cause
        root = chain[0] if chain else event
        lines.append(f"\n   **Root Cause:** `{self._event_summary(root)}`")
        lines.append(f"   **Recommendation:** Review `{root.event_type}` at `#{root.sequence}`")

        return "\n".join(lines)

    def _cmd_cost(self, slug: str = None) -> str:
        """Cost timeline"""
        if not slug:
            return "❌ Usage: /debug cost <slug>"

        if not self.event_store:
            return self._event_store_missing()

        events = self.event_store.get_all()

        from engine.cost import TemporalCostDebugger
        debugger = TemporalCostDebugger()
        return debugger.cost_timeline(events)

    def _cmd_efficiency(self, slug: str = None) -> str:
        """Efficiency display"""
        if not slug:
            return "❌ Usage: /debug efficiency <slug>"

        if self.efficiency_tracker:
            return self.efficiency_tracker.display(slug)
        return "❌ EfficiencyTracker not configured"

    def _cmd_health(self, slug: str = None) -> str:
        """Engine health report"""
        lines = ["🏥 **Engine Health Report**"]

        if self.degradation:
            lines.append(f"\n{self.degradation.status_report()}")

        if self.safety:
            lines.append(f"\n{self.safety.health_report()}")

        if self.event_store:
            stats = self.event_store.stats()
            lines.append(f"\n📦 **Event Store:** `{stats['slug']}`")
            lines.append(f"   Events: `{stats['event_count']}`")
            lines.append(f"   Storage: `{stats['storage_kb']}KB`")
            lines.append(f"   Types: {stats['event_types']}")

        if self.budget:
            lines.append(f"\n{self.budget.status()}")

        if self.cost_tracker:
            lines.append(f"\n{self.cost_tracker.summary()}")

        return "\n".join(lines)

    def _cmd_budget(self, slug: str = None) -> str:
        """Budget status"""
        if self.budget:
            return self.budget.status()
        return "❌ BudgetEnforcer not configured"

    def _cmd_summary(self, slug: str = None) -> str:
        """Run özeti"""
        if not slug:
            return "❌ Usage: /debug summary <slug>"

        if not self.run_manager:
            return "❌ RunManager not configured"

        run = self.run_manager.get_run(slug)
        if not run:
            return f"❌ Run '{slug}' not found"

        lines = [f"📋 **Run Summary:** `{slug}`"]
        lines.append(f"   Profile: `{run.meta.profile}`")
        lines.append(f"   State: `{run.meta.state}`")
        lines.append(f"   Title: `{run.meta.title}`")
        lines.append(f"   Created: `{run.meta.created_at}`")
        lines.append(f"   Updated: `{run.meta.updated_at}`")

        if self.event_store:
            events = self.event_store.get_all()
            passed = sum(1 for e in events if e.data.get("passed", True))
            failed = sum(1 for e in events if not e.data.get("passed", True))

            # Cost
            total_cost = sum(e.cost_usd for e in events)

            lines.append(f"\n📊 **Metrics:**")
            lines.append(f"   Events: `{len(events)}` ({passed} passed, {failed} failed)")
            lines.append(f"   Total Cost: `${total_cost:.4f}`")
            lines.append(f"   Top event: `{max(events, key=lambda e: e.cost_usd).event_type if events else 'N/A'}` "
                         f"(${max(events, key=lambda e: e.cost_usd).cost_usd:.4f})" if events else "")

        if self.degradation:
            lines.append(f"\n{self.degradation.status_report()}")

        return "\n".join(lines)

    def _cmd_help(self) -> str:
        return (
            "🔍 **Debug CLI Commands:**\n"
            "   `/debug timeline <slug>`       → Son 20 event\n"
            "   `/debug event <slug> <id>`     → Event detayı\n"
            "   `/debug state <slug> [id]`     → Run state / time travel\n"
            "   `/debug why <slug> <id>`       → 5-Why root cause\n"
            "   `/debug cost <slug>`           → Cost timeline\n"
            "   `/debug efficiency <slug>`     → T0/T1 efficiency\n"
            "   `/debug health [slug]`         → Engine health report\n"
            "   `/debug budget <slug>`         → Budget status\n"
            "   `/debug summary <slug>`        → Run özeti"
        )

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────

    def _event_summary(self, event) -> str:
        """Event'i tek satırda özetle"""
        etype = event.event_type

        if etype == "state_transition":
            return f"{event.data.get('from', '?')} → {event.data.get('to', '?')}"
        elif etype == "validation":
            vname = event.data.get("validator", "?")
            passed = event.data.get("passed", True)
            return f"{'✅' if passed else '❌'} {vname}"
        elif etype == "error":
            return f"⚠️ {event.data.get('message', '?')[:80]}"
        elif etype == "adapter_call":
            return f"📤 {event.data.get('adapter', '?')}"
        elif etype == "adapter_response":
            return f"📥 {event.data.get('status', '?')}"
        elif etype == "user_action":
            return f"👤 {event.data.get('action', '?')}"
        elif etype == "degradation_change":
            return f"⚠️ {event.data.get('from', '?')} → {event.data.get('to', '?')}"
        elif etype == "weekly_summary":
            return f"📊 {event.data.get('compacted_events', '?')} events compacted"
        return etype

    def _event_store_missing(self) -> str:
        return "❌ EventStore not configured. Use `EventStore` to enable debug commands."


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import tempfile
    import os
    from engine.event_store import EventStore, CostAwareEvent
    from engine.run_manager import RunManager
    from engine.profile import ProductProfile
    from engine.cost import CostTracker, EfficiencyTracker, RunEfficiency
    from engine.budget import BudgetEnforcer
    from engine.degradation import DegradationManager
    from engine.safety import RuntimeSafetyMonitor, EventBus
    from engine.state_machine import StateMachineParser

    tmpdir = tempfile.mkdtemp()

    # Setup mock components
    slug = "flux-release"
    store = EventStore(base_path=tmpdir, slug=slug)

    # Add events
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:00:00",
        event_type="state_transition", data={"from": "spec", "to": "prototyping"},
        cost_usd=0.0))
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:05:00",
        event_type="validation", data={"validator": "BuildCheck", "passed": True},
        cost_usd=0.01))
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:10:00",
        event_type="state_transition", data={"from": "prototyping", "to": "iteration"},
        cost_usd=0.0))
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:15:00",
        event_type="validation", data={"validator": "TestCase", "passed": False},
        cost_usd=0.35))
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:20:00",
        event_type="error", data={"source": "test", "message": "Test coverage failed: 65%"},
        cost_usd=0.0))
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:25:00",
        event_type="validation", data={"validator": "Coverage", "passed": True},
        cost_usd=0.28))
    store.append(CostAwareEvent(
        sequence=0, run_slug=slug, timestamp="2026-05-18T08:30:00",
        event_type="state_transition", data={"from": "iteration", "to": "review"},
        cost_usd=0.0))

    # Cost + Efficiency
    cost = CostTracker()
    cost.record_llm("gpt-4o", 1000, 300, "validation", "BuildCheck")
    cost.record_llm("deepseek-v4-flash", 500, 150, "validation", "TestCase", wasted=True)

    eff = EfficiencyTracker()
    eff.add_completed(RunEfficiency(
        slug="flux-v1", profile="software", format="release",
        total_cost=0.5, estimated=2.0, actual=2.5, source="api"))

    # Degradation + Safety
    deg = DegradationManager(base_path=tmpdir)
    bus = EventBus()
    safety = RuntimeSafetyMonitor(event_bus=bus)

    # Budget
    budget = BudgetEnforcer(cost_tracker=cost, degradation_manager=deg)
    budget.configure({"soft_limit_usd": 0.05, "hard_limit_usd": 0.10})

    # RunManager
    mgr = RunManager(base_path=tmpdir)
    yaml_str = """
profile: software
name: dev-cycle
version: 1.0
states:
  spec: {type: initial, max_reentries: 1}
  prototyping: {type: intermediate, max_reentries: 5}
  iteration: {type: intermediate, max_reentries: 10}
  review: {type: intermediate, max_reentries: null}
  release: {type: terminal, max_reentries: 0}
  cancelled: {type: terminal, max_reentries: 0}
transitions:
  spec -> prototyping: {}
  prototyping -> iteration: {}
  iteration -> review: {condition: "iterations >= 4"}
  iteration -> cancelled: {condition: "max_iterations_exceeded"}
  review -> release: {condition: "human_approved"}
  review -> iteration: {condition: "changes_requested"}
  review -> cancelled: {condition: "project_abandoned"}
"""
    config = StateMachineParser.parse_string(yaml_str)

    class SWProfile(ProductProfile):
        name = "software"
        version = "1.0"
        state_machine_yaml = yaml_str

    profile = SWProfile()
    profile.initialize()
    mgr.create_run("Flux v1.0", profile, slug="flux-v1-release")

    # Debug CLI
    cli = DebugCLI(
        run_manager=mgr,
        event_store=store,
        cost_tracker=cost,
        efficiency_tracker=eff,
        degradation_manager=deg,
        budget_enforcer=budget,
        runtime_safety=safety,
    )

    print("🔍 Debug CLI Demo\n")

    print("─── help ───")
    print(cli.handle("help"))

    print("\n─── timeline ───")
    print(cli.handle("timeline", slug))

    print("\n─── event 2 ───")
    print(cli.handle("event", slug, "2"))

    print("\n─── why 5 ───")
    print(cli.handle("why", slug, "5"))

    print("\n─── cost ───")
    print(cli.handle("cost", slug))

    print("\n─── efficiency flux-v1 ───")
    print(cli.handle("efficiency", "flux-v1"))

    print("\n─── health ───")
    print(cli.handle("health"))

    print("\n─── budget ───")
    print(cli.handle("budget", slug))

    print(f"\n{'='*50}")
    print(f"Debug CLI demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
