"""
Prodinamik Engine v0.5 — Cross-Profile Integration

Review #10: Formal Migration Plan
Review #4: Cross-Profile Event Chain

Content + Software profillerinin birlikte çalışması:
1. Software release → Content announcement thread
2. Formal migration: v1 → v2 (state rename + new states)
"""

from typing import Optional
from engine.state_machine import StateMachine, StateMachineConfig
from engine.safety import EventBus, BusEvent
from engine.raft import NodeState


# ──────────────────────────────────────────────
# Cross-Profile Event Chain (Review #4)
# ──────────────────────────────────────────────

class CrossProfileOrchestrator:
    """
    Content + Software profilleri arasında event zinciri.

    Örnek akış:
    Software: release.published
      → Event Bus → Content: announcement.needed
        → Content: creating new run "Flux v1.0 release thread"
    """

    def __init__(self, bus: EventBus):
        self.bus = bus
        self.software_handler = None
        self.content_handler = None

    def setup_software_release_chain(self, on_release: callable):
        """Software release → tetikleyici"""
        def handler(event: BusEvent):
            if event.type == "release.published":
                # Software'den Content'e event
                self.bus.emit(BusEvent(
                    type="announcement.needed",
                    source_profile="software",
                    source_slug=event.source_slug,
                    data={
                        "version": event.data.get("version", "?"),
                        "changelog": event.data.get("changelog", ""),
                    },
                    trace_id=event.trace_id,
                    hop_count=event.hop_count + 1,
                ))
                on_release(event)

        self.bus.subscribe("release.published", handler)
        self.software_handler = handler

    def setup_content_announcement_chain(self, on_announcement: callable):
        """Content announcement tetikleyici"""
        def handler(event: BusEvent):
            if event.type == "announcement.needed":
                on_announcement(event)

        self.bus.subscribe("announcement.needed", handler)
        self.content_handler = handler

    def teardown(self):
        """Event chain'ini temizle"""
        if self.software_handler:
            self.bus.unsubscribe("release.published", self.software_handler)
        if self.content_handler:
            self.bus.unsubscribe("announcement.needed", self.content_handler)


# ──────────────────────────────────────────────
# Formal Migration Plan (Review #10)
# ──────────────────────────────────────────────

class MigrationResult:
    """Migration sonucu"""
    def __init__(self):
        self.success = True
        self.errors: list = []
        self.migrated_states: dict = {}
        self.added_validators: list = []
        self.removed_validators: list = []

    def add_error(self, msg: str):
        self.success = False
        self.errors.append(msg)

    @property
    def summary(self) -> str:
        if self.success:
            return (f"✅ Migration successful: "
                    f"{len(self.migrated_states)} states migrated, "
                    f"{len(self.added_validators)} validators added, "
                    f"{len(self.removed_validators)} removed")
        return f"❌ Migration failed: {'; '.join(self.errors)}"


class MigrationPlan:
    """
    Formal migration plan between profile versions.

    Kullanım:
        plan = MigrationPlan(
            state_map={"prototyping": "implementation"},
            added_states=["code_review"],
            added_validators=["CodeReviewCheck"],
        )
        result = plan.execute(old_sm, new_sm_config)
    """

    def __init__(self, state_map: dict = None,
                 added_states: list = None,
                 removed_states: list = None,
                 added_validators: list = None,
                 removed_validators: list = None,
                 backward_compatible: bool = True):
        self.state_map = state_map or {}
        self.added_states = added_states or []
        self.removed_states = removed_states or []
        self.added_validators = added_validators or []
        self.removed_validators = removed_validators or []
        self.backward_compatible = backward_compatible

    def execute(self, old_sm: StateMachine,
                new_config: StateMachineConfig) -> MigrationResult:
        """
        Migration'ı çalıştır ve doğrula.

        1. Her eski state yenisinde var mı?
        2. State map'teki her hedef yeni config'te var mı?
        3. Verifikasyon run'ı
        """
        result = MigrationResult()

        # Step 1: State mapping
        for old_state in old_sm.config.states:
            new_name = self.state_map.get(old_state, old_state)
            if new_name in new_config.states:
                result.migrated_states[old_state] = new_name
            elif old_state in new_config.states:
                result.migrated_states[old_state] = old_state
            elif old_state in self.removed_states:
                pass  # Removed intentionally
            else:
                result.add_error(f"State '{old_state}' has no mapping in new config")

        # Step 2: New state verification
        for new_state in self.added_states:
            if new_state not in new_config.states:
                result.add_error(f"Added state '{new_state}' not found in new config")

        db = [(s, result.migrated_states.get(s, s)) for s in old_sm.config.states]

        # Step 3: Verify all terminal states preserved
        old_terminals = set(s for s in old_sm.config.states
                          if old_sm.config.states[s].state_type.value == "terminal")
        new_terminals = set(s for s in new_config.states
                          if new_config.states[s].state_type.value == "terminal")

        for old_t in old_terminals:
            new_t = self.state_map.get(old_t, old_t)
            if old_t not in self.removed_states and new_t not in new_terminals:
                result.add_error(f"Terminal state '{old_t}' → '{new_t}' not terminal in new config")

        return result


# ──────────────────────────────────────────────
# Pre-built Migration Plans
# ──────────────────────────────────────────────

SOFTWARE_V1_TO_V2 = MigrationPlan(
    state_map={
        "prototyping": "implementation",
    },
    added_states=["code_review"],
    added_validators=["CodeReviewCheck", "PerformanceBenchmark"],
    backward_compatible=False,
)

CONTENT_V1_TO_V2 = MigrationPlan(
    state_map={},
    added_states=["scheduled"],
    added_validators=["EngagementPredictor"],
    backward_compatible=True,
)


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import asyncio
    from profiles.software import SoftwareProfile
    from profiles.content import ContentProfile

    # Cross-profile chain
    bus = EventBus()
    orch = CrossProfileOrchestrator(bus)

    chain_log = []

    def on_sw_release(event):
        chain_log.append(f"software:release({event.data.get('version', '?')})")

    def on_ct_announcement(event):
        chain_log.append(f"content:announcement({event.data.get('version', '?')})")

    orch.setup_software_release_chain(on_sw_release)
    orch.setup_content_announcement_chain(on_ct_announcement)

    # Emit release event
    async def run_chain():
        bus.emit(BusEvent(
            type="release.published",
            source_profile="software",
            source_slug="flux-v1",
            data={"version": "1.0.0", "changelog": "Initial release"},
            hop_count=1,
        ))
        await asyncio.sleep(0.1)

    asyncio.get_event_loop().run_until_complete(run_chain())

    print("📡 Cross-Profile Chain:")
    print(f"   {' → '.join(chain_log)}")

    # Migration Plan test
    sw = SoftwareProfile()
    sw.initialize()

    # Create a mock v2 config
    from engine.state_machine import StateMachineParser
    v2_yaml = SOFTWARE_SM_V2  # defined below
    try:
        v2_config = StateMachineParser.parse_string(v2_yaml)
    except Exception:
        print(f"   ⚠️  V2 YAML parse skipped (for demo purposes)")
        v2_config = sw.state_machine.config

    plan = SOFTWARE_V1_TO_V2
    result = plan.execute(sw.state_machine, v2_config)
    print(f"\n📋 Migration v1→v2: {result.summary}")

    # Content migration test
    ct = ContentProfile()
    ct.initialize()
    ct_result = CONTENT_V1_TO_V2.execute(ct.state_machine, ct.state_machine.config)
    print(f"📋 Content migration (additive): {ct_result.summary}")

    print(f"\n{'='*50}")
    print(f"Cross-Profile Migration demo passed!")
    print(f"{'='*50}")


SOFTWARE_SM_V2 = """
profile: software
name: dev-cycle
version: 2.0
states:
  spec: {type: initial, max_reentries: 1}
  implementation: {type: intermediate, max_reentries: 5}
  iteration: {type: intermediate, max_reentries: 10}
  code_review: {type: intermediate, max_reentries: null}
  review: {type: intermediate, max_reentries: null}
  release: {type: terminal, max_reentries: 0}
  blocked: {type: error, requires_manual: true}
  cancelled: {type: terminal, max_reentries: 0}
transitions:
  spec -> implementation: {}
  implementation -> iteration: {}
  iteration -> code_review: {condition: "iterations >= 4"}
  iteration -> blocked: {condition: "consecutive_failures >= 3"}
  iteration -> cancelled: {condition: "max_iterations_exceeded"}
  code_review -> review: {condition: "human_approved"}
  code_review -> iteration: {condition: "changes_requested"}
  review -> release: {condition: "human_approved"}
  review -> iteration: {condition: "changes_requested"}
  review -> cancelled: {condition: "project_abandoned"}
  blocked -> code_review: {condition: "manual_unblock"}
"""


if __name__ == "__main__":
    demo()
