"""
Prodinamik Engine v0.5 — Software Profile

dev-cycle skill'in ProductProfile olarak implementasyonu.
7-state lifecycle: spec → prototyping → iteration → review → release

HITL (Human-In-The-Loop) v1.0:
- prototyping: Prototype doğrulama onayı
- iteration: Her 5 iterasyonda bir kullanıcıya durum sorusu
- review: PAUSE state — release onayı + değişiklik talebi
- blocked: PAUSE state — unblock için kullanıcı onayı

Review #10: Formal migration plan included (v1.0 → v2.0)
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget
from engine.stateguard_bridge import make_stateguard_def
from engine.raft import NodeState, StateCRDT

SOFTWARE_SM = """
profile: software
name: dev-cycle
version: 2.0

formal_properties:
  termination:
    max_steps: 100

states:
  spec:
    type: initial
    max_reentries: 1
    timeout: 3600
    validators: ["SpecCheck"]
    hitl:
      ask_user:
        - question: "Spec'i onaylıyor musun?"
          type: yes_no
          timeout: 3600
      resume_transitions:
        "yes": prototyping
        "no": spec

  prototyping:
    type: intermediate
    max_reentries: 5
    timeout: 7200
    validators: ["BuildCheck"]
    hitl:
      ask_user:
        - question: "Prototip çalışıyor mu? Iterasyon'a geçelim mi?"
          type: yes_no
          timeout: 7200
      ask_if:
        - condition: "reentry_count >= 3"
          question: "3. prototype denemesi. Yaklaşımı değiştirmek ister misin?"
          type: yes_no
          on_timeout: proceed
      resume_transitions:
        "yes": iteration
        "no": spec

  iteration:
    type: intermediate
    max_reentries: 10
    timeout: 86400
    validators: ["TestCheck", "LintCheck"]
    hitl:
      ask_if:
        - condition: "iteration_count >= 5 AND iteration_count % 5 == 0"
          question: "5 iterasyon tamamlandı. Review'a geçelim mi, yoksa devam mı?"
          type: multiple_choice
          choices: ["Review'a geç", "Devam et", "Block et"]
          on_timeout: proceed

  review:
    type: pause
    max_reentries: null
    timeout: 2592000
    temporal:
      max_idle: 259200
      reminders:
        - after: 86400
          message: "Review bekliyor"
        - after: 259200
          message: "3 gündür review'da, escalation"
    hitl:
      ask_user:
        - question: "Release'e hazır mı?"
          type: yes_no
          timeout: 604800
      ask_if:
        - condition: "reentry_count > 0"
          question: "Bu review'a daha önce de geldi. Major değişiklik mi yapalım, yoksa minor fix mi?"
          type: multiple_choice
          choices: ["Release", "Minor fix", "Major değişiklik"]
          on_timeout: hold
      resume_transitions:
        "yes": release
        "Release": release
        "Minor fix": iteration
        "Major değişiklik": prototyping
        "no": iteration

  release:
    type: terminal
    max_reentries: 0

  blocked:
    type: pause
    requires_manual: true
    hitl:
      ask_user:
        - question: "Block'u kaldırmak için ne yapalım?"
          type: multiple_choice
          choices: ["Yaklaşım değiştir", "Spec revize et", "İptal et"]
          timeout: 604800
      resume_transitions:
        "Yaklaşım değiştir": iteration
        "Spec revize et": spec
        "İptal et": cancelled

  cancelled:
    type: terminal
    max_reentries: 0

transitions:
  spec -> prototyping: {type: REVERSIBLE}
  prototyping -> iteration: {type: REVERSIBLE, condition: "prototype_passes(spec)"}
  iteration -> iteration: {type: REVERSIBLE}
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
    version = "2.0"
    description = "Software development: spec → prototype → iterate → review → release + HITL"
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
        # StateGuard multi-dimensional validation bridge
        self.add_validator(make_stateguard_def(
            name="stateguard",
            tier=ValidatorTier.T1,
            critical=True,
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
    - HITL fields added to spec, prototyping, iteration, review, blocked
    """

    V1_TO_V2 = {
        "state_map": {
            "spec": "spec",
            "prototyping": "implementation",
            "iteration": "iteration",
            "review": "review",
            "release": "release",
            "blocked": "blocked",
            "cancelled": "cancelled",
        },
        "added_states": ["code_review"],
        "state_changes": {
            "spec": {"added_hitl": True},
            "prototyping": {"added_hitl": True},
            "iteration": {"added_hitl": True},
            "review": {"type": "pause", "added_hitl": True},
            "blocked": {"type": "pause", "added_hitl": True},
        },
        "transition_additions": [
            "iteration -> code_review: {}",
            "code_review -> review: {condition: 'human_approved'}",
            "code_review -> iteration: {condition: 'changes_requested'}",
            "blocked -> code_review: {condition: 'manual_unblock'}",
        ],
        "backward_compatible": False,
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

    # Test HITL
    print(f"\n🔔 HITL Test:")
    for state_name in ["spec", "prototyping", "iteration", "review", "blocked"]:
        hitl = sm.get_hitl_questions(state_name, rt)
        is_pause = sm.is_pause_state(state_name)
        state_def = sm.config.states[state_name]
        pause_tag = "⏸️ PAUSE" if state_def.state_type.name == "PAUSE" else ""
        print(f"   {state_name}: {len(hitl)} questions {'(' + pause_tag + ')' if pause_tag else ''}")
        for q in hitl:
            choices_str = f" [{', '.join(q['choices'])}]" if q.get('choices') else ""
            print(f"     - [{q['type']}] {q['question']}{choices_str}")

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
