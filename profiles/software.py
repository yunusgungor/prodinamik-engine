"""
Prodinamik Engine v0.5 — Software Profile

dev-cycle skill'in ProductProfile olarak implementasyonu.
7-state lifecycle: spec → prototyping → iteration → review → release

Review #10: Formal migration plan included (v1.0 → v2.0)
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget
from engine.raft import NodeState, StateCRDT

SOFTWARE_SM = """
profile: software
name: dev-cycle
version: 1.0

formal_properties:
  termination:
    max_steps: 100

states:
  spec:
    type: initial
    max_reentries: 1
    timeout: 3600
    validators: ["SpecCheck"]

  prototyping:
    type: intermediate
    max_reentries: 5
    timeout: 7200
    validators: ["BuildCheck"]

  iteration:
    type: intermediate
    max_reentries: 10
    timeout: 86400
    validators: ["TestCheck", "LintCheck"]

  review:
    type: intermediate
    max_reentries: null
    timeout: 2592000
    temporal:
      max_idle: 259200
      reminders:
        - after: 86400
          message: "Review bekliyor"
        - after: 259200
          message: "3 gündür review'da, escalation"

  release:
    type: terminal
    max_reentries: 0

  blocked:
    type: error
    requires_manual: true

  cancelled:
    type: terminal
    max_reentries: 0

transitions:
  spec -> prototyping: {type: REVERSIBLE}
  prototyping -> iteration: {type: REVERSIBLE, condition: "prototype_passes(spec)"}
  iteration -> iteration: {type: REVERSIBLE, condition: "drift_detected", action: "log_drift"}
  iteration -> review: {type: REVERSIBLE, condition: "iterations >= 4"}
  iteration -> blocked: {type: REVERSIBLE, condition: "consecutive_failures >= 3"}
  iteration -> cancelled: {type: REVERSIBLE, condition: "max_iterations_exceeded"}
  review -> release: {type: COMPENSABLE, condition: "human_approved"}
  review -> iteration: {type: REVERSIBLE, condition: "changes_requested"}
  review -> cancelled: {type: REVERSIBLE, condition: "project_abandoned"}
  blocked -> iteration: {type: REVERSIBLE, condition: "manual_unblock"}
"""


class SoftwareProfile(ProductProfile):
    """Software development lifecycle (dev-cycle v4.0 uyumlu)"""

    name = "software"
    version = "1.0"
    description = "Software development: spec → prototype → iterate → review → release"
    state_machine_yaml = SOFTWARE_SM

    def setup_validators(self):
        self.add_validator(ValidatorDef(
            name="SpecCheck", tier=ValidatorTier.T1, critical=True,
        ))
        self.add_validator(ValidatorDef(
            name="BuildCheck", tier=ValidatorTier.T1, critical=True,
        ))
        self.add_validator(ValidatorDef(
            name="TestCheck", tier=ValidatorTier.T1, critical=False,
        ))
        self.add_validator(ValidatorDef(
            name="LintCheck", tier=ValidatorTier.T1, critical=False,
        ))

    def setup_adapters(self):
        self.add_adapter(AdapterDef(
            name="GitHubRelease", type="github", max_retries=2,
        ))
        self.add_adapter(AdapterDef(
            name="FileOutput", type="file", fallback_mode="file",
        ))

    def setup_budget(self):
        self._budget = Budget(
            max_concurrent_validators=3,
            max_llm_calls_per_run=10,
            max_storage_mb=200,
            timeout_per_state=86400,
            soft_limit_usd=2.0,
            hard_limit_usd=10.0,
        )

    # State machine DAG for CRDT merge
    @property
    def transition_map(self) -> dict:
        return {
            "spec": ["prototyping"],
            "prototyping": ["iteration"],
            "iteration": ["iteration", "review", "blocked", "cancelled"],
            "review": ["release", "iteration", "cancelled"],
            "blocked": ["iteration"],
        }


# ──────────────────────────────────────────────
# Review #10: Formal Migration Plan
# ──────────────────────────────────────────────

class SoftwareMigrationPlan:
    """
    Formal migration plan: SoftwareProfile v1.0 → v2.0

    Changes:
    - "prototyping" renamed to "implementation"
    - New "code_review" state added between iteration and review
    - "blocked" state: "iteration" → "blocked" → "code_review"
    """

    V1_TO_V2 = {
        "state_map": {
            "spec": "spec",              # 1:1
            "prototyping": "implementation",  # 1:1 rename
            "iteration": "iteration",    # 1:1
            "review": "review",          # 1:1
            "release": "release",        # 1:1
            "blocked": "blocked",        # 1:1
            "cancelled": "cancelled",    # 1:1
        },
        "added_states": ["code_review"],
        "removed_states": [],
        "transition_additions": [
            "iteration -> code_review: {}",
            "code_review -> review: {condition: 'human_approved'}",
            "code_review -> iteration: {condition: 'changes_requested'}",
            "blocked -> code_review: {condition: 'manual_unblock'}",
        ],
        "backward_compatible": False,  # Breaking change — new state inserted
    }

    @classmethod
    def migrate_state(cls, old_state: str) -> str:
        """Eski state adını yenisine map et"""
        return cls.V1_TO_V2["state_map"].get(old_state, old_state)

    @classmethod
    def migrate_node_state(cls, node_state: NodeState) -> NodeState:
        """NodeState'i migrate et (state adı + version korunur)"""
        if node_state.current_state in cls.V1_TO_V2["state_map"]:
            node_state.current_state = cls.migrate_state(node_state.current_state)
        return node_state

    @classmethod
    def verify_migration(cls, old_state_machine, new_state_machine) -> bool:
        """
        Migration doğrulama.
        Her eski state, yeni state'te karşılık bulmalı.
        """
        for old_state in old_state_machine.config.states:
            new_name = cls.migrate_state(old_state)
            if new_name not in new_state_machine.config.states:
                print(f"❌ Migration gap: '{old_state}' → '{new_name}' not found")
                return False
        return True


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    profile = SoftwareProfile()
    profile.initialize()

    print("📦 SoftwareProfile loaded:")
    print(f"   Name: {profile.name} v{profile.version}")
    print(f"   SM: {profile.state_machine}")
    print(f"   Validators: {len(profile.validators)} (T1:{len(profile.tier1_validators)})")
    print(f"   Adapters: {[a.name for a in profile.adapters]}")
    print(f"   Budget: ${profile.budget.hard_limit_usd} hard limit")

    # Test state machine
    sm = profile.state_machine
    rt = sm.create_runtime()
    print(f"\n📌 Initial: {rt.current_state}")
    print(f"   All states: {list(sm.config.states.keys())}")

    # Test transitions
    for to_state in sm.get_next_states("spec"):
        allowed, reason = sm.can_transition("spec", to_state, rt)
        print(f"   spec → {to_state}: {'✅' if allowed else '❌'} ({reason})")

    # Test IRREVERSIBLE (release'den çıkış yasak)
    allowed, reason = sm.can_transition("release", "iteration", rt)
    print(f"   release → iteration: {'✅' if allowed else '❌'} ({reason})")

    # Migration plan
    print(f"\n📋 Migration Plan v1 → v2:")
    print(f"   prototyping → {SoftwareMigrationPlan.migrate_state('prototyping')}")
    print(f"   States added: {SoftwareMigrationPlan.V1_TO_V2['added_states']}")
    print(f"   Backward compatible: {SoftwareMigrationPlan.V1_TO_V2['backward_compatible']}")

    # CRDT merge test
    local = NodeState(current_state="iteration", version=3)
    remote = NodeState(current_state="review", version=2)
    merged = StateCRDT.merge(local, remote, profile.transition_map)
    print(f"\n🔄 CRDT merge: local=iteration v3 + remote=review v2 → {merged.current_state}")

    print(f"\n{'='*50}")
    print(f"SoftwareProfile demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
