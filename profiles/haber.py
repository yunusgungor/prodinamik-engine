"""
Prodinamik Engine v0.5 — Haber Profile

Haber doğrulama pipeline'ı (eski Haber-Kurator).
8-state lifecycle: captured → fact_checking → cross_verified →
published → correction_needed → corrected/retracted → archived

HITL (Human-In-The-Loop) v1.0:
- captured: Haber kaynağı onayı
- fact_checking: Doğrulama yöntemi seçimi
- cross_verified: Kısmi doğrulama uyarısı
- published: PAUSE state — yayın onayı
- correction_needed: Düzeltme onayı

Validators: SourceVerification, FactCheck, HallucinationCheck, CrossReference
Adapters: Memos, FileOutput
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget, StoreDef

HABER_SM = """
profile: haber
name: haber-pipeline
version: 2.0

formal_properties:
  termination:
    max_steps: 50

states:
  captured:
    type: initial
    max_reentries: 1
    validators: ["SourceCheck"]
    hitl:
      ask_user:
        - question: "Bu haber kaynağını doğrulayalım mı? Kaynak güvenilir mi?"
          type: yes_no
          timeout: 300
      resume_transitions:
        "yes": fact_checking
        "no": archived

  fact_checking:
    type: intermediate
    max_reentries: 3
    validators: ["FactCheck", "HallucinationCheck"]
    hitl:
      ask_user:
        - question: "Hangi doğrulama yöntemini kullanalım?"
          type: multiple_choice
          choices: ["Resmi kaynak sorgula", "Haber ajansı karşılaştır", "Sivil toplum doğrulaması", "Hepsini dene"]
          timeout: 600
      resume_transitions:
        "Resmi kaynak sorgula": cross_verified
        "Haber ajansı karşılaştır": cross_verified
        "Sivil toplum doğrulaması": cross_verified
        "Hepsini dene": cross_verified

  cross_verified:
    type: intermediate
    max_reentries: 2
    validators: ["CrossReferenceCheck"]
    hitl:
      ask_if:
        - condition: "drift_count > 0"
          question: "Kaynaklar arasında tutarsızlık var ({{drift_count}} kaynak). Yine de yayınlamak istiyor musun?"
          type: multiple_choice
          choices: ["Yayınla", "Tekrar doğrula", "Arşivle"]
          on_timeout: hold
      resume_transitions:
        "Yayınla": published
        "Tekrar doğrula": fact_checking
        "Arşivle": archived

  published:
    type: pause
    max_reentries: 1
    temporal:
      max_idle: 86400
      reminders:
        - after: 43200
          message: "Yayın öncesi son onay bekliyor"
    hitl:
      ask_user:
        - question: "Haber yayına hazır mı?"
          type: yes_no
          timeout: 86400
      ask_if:
        - condition: "reentry_count > 0"
          question: "Bu haber daha önce yayından çekildi. Tekrar yayınlamak istediğine emin misin?"
          type: yes_no
          on_timeout: hold
      resume_transitions:
        "yes": published_active
        "no": correction_needed

  published_active:
    type: intermediate
    max_reentries: 0

  correction_needed:
    type: pause
    max_reentries: 3
    hitl:
      ask_user:
        - question: "Düzeltme metnini onaylıyor musun?"
          type: yes_no
          timeout: 86400
      ask_if:
        - condition: "reentry_count >= 2"
          question: "2. kez düzeltme yapılıyor. Haberi tamamen geri çekelim mi?"
          type: yes_no
          on_timeout: proceed
      resume_transitions:
        "yes": corrected
        "no": retracted

  corrected:
    type: intermediate
    max_reentries: 1

  retracted:
    type: intermediate
    max_reentries: 0

  archived:
    type: terminal
    max_reentries: 0

transitions:
  captured -> fact_checking: {}
  captured -> archived: {condition: "project_abandoned"}
  fact_checking -> cross_verified: {}
  fact_checking -> archived: {condition: "max_iterations_exceeded"}
  cross_verified -> published: {condition: "human_approved"}
  cross_verified -> fact_checking: {condition: "changes_requested"}
  cross_verified -> archived: {condition: "project_abandoned"}
  published -> published_active: {condition: "human_approved"}
  published -> correction_needed: {condition: "changes_requested"}
  published_active -> correction_needed: {condition: "drift_detected"}
  correction_needed -> corrected: {condition: "human_approved"}
  correction_needed -> retracted: {condition: "project_abandoned"}
  corrected -> archived: {}
  retracted -> archived: {}
"""


class HaberProfile(ProductProfile):
    """Haber doğrulama pipeline'ı (Haber-Kurator v3.1.0 uyumlu)"""

    name = "haber"
    version = "2.0"
    description = "News verification: capture → fact-check → cross-verify → publish → correct + HITL"
    state_machine_yaml = HABER_SM

    def setup_validators(self):
        self.add_validator(ValidatorDef(
            name="SourceCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=10,
        ))
        self.add_validator(ValidatorDef(
            name="FactCheck", tier=ValidatorTier.T2, critical=True,
            timeout_seconds=120,
        ))
        self.add_validator(ValidatorDef(
            name="HallucinationCheck", tier=ValidatorTier.T2, critical=True,
            timeout_seconds=60,
        ))
        self.add_validator(ValidatorDef(
            name="CrossReferenceCheck", tier=ValidatorTier.T3, critical=False,
            timeout_seconds=180,
        ))
        # StateGuard dimension validators (config-driven)
        from engine.stateguard_config import make_profile_validators
        for v in make_profile_validators("haber"):
            self.add_validator(v)

    def setup_adapters(self):
        self.add_adapter(AdapterDef(
            name="Memos", type="api", max_retries=2,
            fallback_mode="file",
        ))
        self.add_adapter(AdapterDef(
            name="FileOutput", type="file", fallback_mode="file",
        ))

    def setup_stores(self):
        self.add_store(StoreDef(name="sources", type="json",
                                path="stores/sources/", required=False))
        self.add_store(StoreDef(name="corrections", type="markdown",
                                path="stores/corrections/", required=False))

    def setup_budget(self):
        self._budget = Budget(
            max_concurrent_validators=3,
            max_llm_calls_per_run=30,
            max_storage_mb=50,
            timeout_per_state=86400,
            soft_limit_usd=0.5,
            hard_limit_usd=2.0,
        )


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    profile = HaberProfile()
    profile.initialize()

    print("📰 HaberProfile loaded:")
    print(f"   Name: {profile.name} v{profile.version}")
    print(f"   SM: {profile.state_machine}")
    print(f"   Validators: {len(profile.validators)} "
          f"(T1:{len(profile.tier1_validators)} T2:{len(profile.tier2_validators)} T3:{len(profile.tier3_validators)})")
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
    for state_name in ["captured", "fact_checking", "cross_verified",
                        "published", "correction_needed"]:
        hitl = sm.get_hitl_questions(state_name, rt)
        is_pause = sm.is_pause_state(state_name)
        state_def = sm.config.states[state_name]
        pause_tag = "⏸️ PAUSE" if state_def.state_type.name == "PAUSE" else ""
        print(f"   {state_name}: {len(hitl)} questions {'(' + pause_tag + ')' if pause_tag else ''}")
        for q in hitl:
            choices_str = f" [{', '.join(q['choices'])}]" if q.get('choices') else ""
            source = "ask_if" if q.get('source') == "ask_if" else "ask_user"
            print(f"     - [{source}] [{q['type']}] {q['question']}{choices_str}")

    # Test resume_transitions
    print(f"\n🔄 Resume Transitions Test:")
    for ans, expected in [("yes", "fact_checking"), ("Resmi kaynak sorgula", "cross_verified"),
                           ("Hepsini dene", "cross_verified")]:
        result = sm.evaluate_resume_transition("fact_checking", {"answer": ans})
        status = "✅" if result == expected else "❌"
        print(f"   fact_checking + '{ans}' → {result} {status}")

    print(f"\n{'='*50}")
    print(f"HaberProfile demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
