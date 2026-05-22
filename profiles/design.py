"""
Prodinamik Engine v0.5 — Design Profile

UI/UX tasarım pipeline'ı.
8-state lifecycle: brief → research → sketch → wireframe →
mockup → prototype → review → handoff

HITL (Human-In-The-Loop) v1.0:
- brief: Brief onayı
- research: Araştırma yönlendirmesi
- wireframe: Wireframe onayı
- prototype: Prototip review
- review: PAUSE state — handoff onayı

Validators: accessibility check, design system compliance, responsive check
Adapters: Figma API, PNG export, Zeplin
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget, StoreDef

DESIGN_SM = """
profile: design
name: design-pipeline
version: 2.0

formal_properties:
  termination:
    max_steps: 80

states:
  brief:
    type: initial
    max_reentries: 1
    timeout: 172800
    validators: ["BriefCheck"]
    hitl:
      ask_user:
        - question: "Brief'i onaylıyor musun?"
          type: yes_no
          timeout: 86400
      resume_transitions:
        "yes": research
        "no": brief

  research:
    type: intermediate
    max_reentries: 3
    timeout: 259200
    validators: ["ResearchCheck"]
    hitl:
      ask_user:
        - question: "Hangi tasarım yönünü keşfedelim?"
          type: multiple_choice
          choices: ["Mevcut tasarım sistemine uygun", "Yeni ve deneysel", "Rakip analizi bazlı"]
          timeout: 86400

  sketch:
    type: intermediate
    max_reentries: 5
    timeout: 172800
    hitl:
      ask_if:
        - condition: "reentry_count >= 3"
          question: "3. sketch denemesi. Wireframe'e geçmek ister misin?"
          type: yes_no
          on_timeout: proceed

  wireframe:
    type: intermediate
    max_reentries: 5
    timeout: 172800
    hitl:
      ask_user:
        - question: "Wireframe onaylıyor musun?"
          type: yes_no
          timeout: 86400
      resume_transitions:
        "yes": mockup
        "no": sketch

  mockup:
    type: intermediate
    max_reentries: 8
    timeout: 259200
    validators: ["AccessibilityCheck", "DesignSystemCheck"]
    hitl:
      ask_if:
        - condition: "drift_count > 0"
          question: "Görsel tasarımda değişiklik var. Prototip'e geçmeden önce onaylıyor musun?"
          type: yes_no
          on_timeout: hold

  prototype:
    type: intermediate
    max_reentries: 8
    timeout: 345600
    validators: ["ResponsiveCheck", "InteractionCheck"]
    hitl:
      ask_user:
        - question: "Prototip review'e hazır mı?"
          type: yes_no
          timeout: 172800
      resume_transitions:
        "yes": review
        "no": mockup

  review:
    type: pause
    max_reentries: null
    timeout: 604800
    temporal:
      max_idle: 172800
      reminders:
        - after: 86400
          message: "Design review 1 gündür bekliyor"
        - after: 172800
          message: "2 gündür review'da, escalation"
    hitl:
      ask_user:
        - question: "Tasarımı onaylıyor musun?"
          type: yes_no
          timeout: 259200
      ask_if:
        - condition: "reentry_count > 0"
          question: "Bu review'a 2. kez geliyoruz. Major revizyon mu yoksa minor fix mi?"
          type: multiple_choice
          choices: ["Onayla", "Minor fix", "Major revizyon"]
          on_timeout: hold
      resume_transitions:
        "yes": handoff
        "Onayla": handoff
        "Minor fix": prototype
        "Major revizyon": wireframe
        "no": prototype

  handoff:
    type: terminal
    max_reentries: 0

transitions:
  brief -> research: {condition: "brief_approved"}
  research -> sketch: {condition: "research_complete"}
  sketch -> wireframe: {condition: "sketch_approved"}
  sketch -> sketch: {condition: "drift_detected", action: "log_drift"}
  wireframe -> mockup: {condition: "wireframe_approved"}
  wireframe -> sketch: {condition: "major_changes_needed"}
  mockup -> prototype: {condition: "mockup_approved"}
  mockup -> wireframe: {condition: "structure_changes_needed"}
  prototype -> review: {condition: "prototype_ready"}
  prototype -> mockup: {condition: "visual_changes_needed"}
  prototype -> prototype: {condition: "drift_detected", action: "log_drift"}
  review -> handoff: {condition: "review_approved"}
  review -> prototype: {condition: "changes_requested"}
"""


class DesignProfile(ProductProfile):
    """UI/UX design pipeline"""

    name = "design"
    version = "2.0"
    description = "UI/UX design: brief → research → sketch → wireframe → mockup → prototype → review → handoff + HITL"
    state_machine_yaml = DESIGN_SM

    def setup_validators(self):
        self.add_validator(ValidatorDef(
            name="BriefCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=10,
        ))
        self.add_validator(ValidatorDef(
            name="ResearchCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=15,
        ))
        self.add_validator(ValidatorDef(
            name="AccessibilityCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=20,
        ))
        self.add_validator(ValidatorDef(
            name="DesignSystemCheck", tier=ValidatorTier.T1, critical=False,
            timeout_seconds=10,
        ))
        self.add_validator(ValidatorDef(
            name="ResponsiveCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=30,
        ))
        self.add_validator(ValidatorDef(
            name="InteractionCheck", tier=ValidatorTier.T1, critical=False,
            timeout_seconds=15,
        ))
        # StateGuard dimension validators (config-driven)
        from engine.stateguard_config import make_profile_validators
        for v in make_profile_validators("design"):
            self.add_validator(v)

    def setup_adapters(self):
        self.add_adapter(AdapterDef(
            name="FigmaAPI", type="api", max_retries=3,
            circuit_breaker_threshold=3, fallback_mode="file",
        ))
        self.add_adapter(AdapterDef(
            name="PNGExport", type="file", fallback_mode="file",
        ))
        self.add_adapter(AdapterDef(
            name="Zeplin", type="api", max_retries=2,
            fallback_mode="file",
        ))

    def setup_stores(self):
        self.add_store(StoreDef(name="design_system", type="json",
                                path="stores/design-system/", required=False))
        self.add_store(StoreDef(name="assets", type="png",
                                path="stores/assets/", required=False))
        self.add_store(StoreDef(name="feedback", type="markdown",
                                path="stores/feedback/", required=False))

    def setup_budget(self):
        self._budget = Budget(
            max_concurrent_validators=3,
            max_llm_calls_per_run=15,
            max_storage_mb=1000,
            timeout_per_state=172800,
            soft_limit_usd=2.0,
            hard_limit_usd=10.0,
        )


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    profile = DesignProfile()
    profile.initialize()

    print("🎨 DesignProfile loaded:")
    print(f"   Name: {profile.name} v{profile.version}")
    print(f"   SM: {profile.state_machine}")
    print(f"   Validators: {len(profile.validators)} "
          f"(T1:{len(profile.tier1_validators)})")
    print(f"   Adapters: {[a.name for a in profile.adapters]}")
    print(f"   Stores: {[s.name for s in profile.stores]}")
    print(f"   Budget: ${profile.budget.hard_limit_usd} hard limit")

    sm = profile.state_machine
    rt = sm.create_runtime()
    print(f"\n📌 Initial: {rt.current_state}")
    print(f"   Total states: {len(sm.config.states)}")
    print(f"   Total transitions: {len(sm.config.transitions)}")

    # Test HITL
    print(f"\n🔔 HITL Test:")
    for state_name in ["brief", "research", "wireframe", "prototype", "review"]:
        hitl = sm.get_hitl_questions(state_name, rt)
        is_pause = sm.is_pause_state(state_name)
        state_def = sm.config.states[state_name]
        pause_tag = "⏸️ PAUSE" if state_def.state_type.name == "PAUSE" else ""
        print(f"   {state_name}: {len(hitl)} questions {'(' + pause_tag + ')' if pause_tag else ''}")
        for q in hitl:
            choices_str = f" [{', '.join(q['choices'])}]" if q.get('choices') else ""
            print(f"     - [{q['type']}] {q['question']}{choices_str}")

    # Test forward path
    path = ["brief", "research", "sketch", "wireframe", "mockup",
            "prototype", "review", "handoff"]
    all_ok = True
    for i in range(len(path) - 1):
        allowed, reason = sm.can_transition(path[i], path[i + 1], rt)
        if not allowed:
            print(f"   {path[i]} → {path[i+1]}: ❌ ({reason})")
            all_ok = False
        else:
            print(f"   {path[i]} → {path[i+1]}: ✅")
    if all_ok:
        print(f"\n   ✅ Full forward path: brief → handoff")

    # Test back transitions (revisions)
    allowed, reason = sm.can_transition("review", "prototype", rt)
    print(f"   review → prototype (revision): {'✅' if allowed else '❌'}")

    allowed, reason = sm.can_transition("review", "brief", rt)
    print(f"   review → brief (pivot): {'✅' if allowed else '❌'}")

    # Test terminal constraint
    allowed, reason = sm.can_transition("handoff", "review", rt)
    print(f"   handoff → review: {'✅' if allowed else '❌'} ({reason})")

    print(f"\n{'='*50}")
    print(f"DesignProfile demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
