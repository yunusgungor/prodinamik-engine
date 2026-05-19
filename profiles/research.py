"""
Prodinamik Engine v0.5 — Research Profile

Akademik araştırma pipeline'ı.
10-state lifecycle: topic_selected → literature_review → hypothesis →
experiment_design → data_collection → analysis → paper_draft →
peer_review → published → archived

HITL (Human-In-The-Loop) v1.0:
- topic_selected: Konu onayı
- hypothesis: Hipotez seçimi
- paper_draft: Makale taslak onayı
- peer_review: PAUSE state — yayın onayı

Validators: citation check, methodology consistency, statistical significance
Adapters: arXiv, PDF export, Zotero
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget

RESEARCH_SM = """
profile: research
name: research-pipeline
version: 2.0

formal_properties:
  termination:
    max_steps: 100

states:
  topic_selected:
    type: initial
    max_reentries: 1
    timeout: 604800
    validators: ["ScopeCheck"]
    hitl:
      ask_user:
        - question: "Araştırma konusunu onaylıyor musun?"
          type: yes_no
          timeout: 86400
      resume_transitions:
        "yes": literature_review
        "no": topic_selected

  literature_review:
    type: intermediate
    max_reentries: 5
    timeout: 1209600
    validators: ["CitationCheck"]
    hitl:
      ask_if:
        - condition: "reentry_count >= 3"
          question: "Literatür taraması 3. kez revize ediliyor. Kapsamı daraltmak ister misin?"
          type: yes_no
          on_timeout: proceed

  hypothesis:
    type: intermediate
    max_reentries: 3
    timeout: 604800
    validators: ["MethodologyCheck"]
    hitl:
      ask_user:
        - question: "Hangi hipotezle devam edelim?"
          type: multiple_choice
          choices: ["Hipotez A (null hipotez)", "Hipotez B (alternatif)", "Henüz karar vermedim"]
          timeout: 604800
      resume_transitions:
        "Hipotez A (null hipotez)": experiment_design
        "Hipotez B (alternatif)": experiment_design
        "Henüz karar vermedim": literature_review

  experiment_design:
    type: intermediate
    max_reentries: 5
    timeout: 1209600
    validators: ["StatisticalCheck"]
    hitl:
      ask_if:
        - condition: "drift_count > 0"
          question: "Deney tasarımında değişiklik var. Devam edelim mi?"
          type: yes_no
          on_timeout: hold

  data_collection:
    type: intermediate
    max_reentries: 5
    timeout: 2592000

  analysis:
    type: intermediate
    max_reentries: 5
    timeout: 1209600

  paper_draft:
    type: intermediate
    max_reentries: 10
    timeout: 2592000
    hitl:
      ask_user:
        - question: "Makale taslağı peer review'a hazır mı?"
          type: yes_no
          timeout: 604800
      resume_transitions:
        "yes": peer_review
        "no": paper_draft

  peer_review:
    type: pause
    max_reentries: null
    timeout: 2592000
    temporal:
      max_idle: 604800
      reminders:
        - after: 259200
          message: "Peer review 3 gündür bekliyor"
        - after: 604800
          message: "1 haftadır review'da, escalation"
    hitl:
      ask_user:
        - question: "Makaleyi yayınlıyor muyuz?"
          type: yes_no
          timeout: 604800
      ask_if:
        - condition: "reentry_count > 0"
          question: "Revizyon sonrası tekrar review'da. Yayına hazır mı?"
          type: yes_no
          on_timeout: hold
      resume_transitions:
        "yes": published
        "no": paper_draft

  published:
    type: intermediate
    max_reentries: 1

  archived:
    type: terminal
    max_reentries: 0

transitions:
  topic_selected -> literature_review: {}
  literature_review -> hypothesis: {condition: "lit_review_complete"}
  hypothesis -> experiment_design: {condition: "hypothesis_approved"}
  hypothesis -> literature_review: {condition: "lit_review_needed"}
  experiment_design -> data_collection: {condition: "design_approved"}
  experiment_design -> hypothesis: {condition: "hypothesis_revision_needed"}
  data_collection -> analysis: {condition: "data_ready"}
  data_collection -> experiment_design: {condition: "design_revision_needed"}
  analysis -> paper_draft: {condition: "analysis_complete"}
  analysis -> data_collection: {condition: "more_data_needed"}
  paper_draft -> peer_review: {condition: "draft_ready"}
  paper_draft -> paper_draft: {condition: "drift_detected", action: "log_drift"}
  peer_review -> published: {condition: "review_approved"}
  peer_review -> paper_draft: {condition: "revisions_requested"}
  published -> archived: {}
"""


class ResearchProfile(ProductProfile):
    """Academic research pipeline"""

    name = "research"
    version = "2.0"
    description = "Academic research: topic → lit review → hypothesis → experiment → paper → publish + HITL"
    state_machine_yaml = RESEARCH_SM

    def setup_validators(self):
        # T1: Fail-fast checks
        self.add_validator(ValidatorDef(
            name="ScopeCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=10,
        ))
        self.add_validator(ValidatorDef(
            name="CitationCheck", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=15,
        ))
        self.add_validator(ValidatorDef(
            name="MethodologyCheck", tier=ValidatorTier.T1, critical=False,
            timeout_seconds=10,
        ))
        self.add_validator(ValidatorDef(
            name="StatisticalCheck", tier=ValidatorTier.T1, critical=False,
            timeout_seconds=10,
        ))

    def setup_adapters(self):
        self.add_adapter(AdapterDef(
            name="PDFExport", type="file", fallback_mode="file",
        ))
        self.add_adapter(AdapterDef(
            name="ArXiv", type="web", max_retries=2,
            circuit_breaker_threshold=3, fallback_mode="file",
        ))
        self.add_adapter(AdapterDef(
            name="Zotero", type="api", max_retries=2,
            fallback_mode="file",
        ))

    def setup_stores(self):
        from engine.profile import StoreDef
        self.add_store(StoreDef(name="references", type="bibtex",
                                path="stores/references/", required=True))
        self.add_store(StoreDef(name="data", type="csv",
                                path="stores/data/", required=False))
        self.add_store(StoreDef(name="figures", type="png",
                                path="stores/figures/", required=False))

    def setup_budget(self):
        self._budget = Budget(
            max_concurrent_validators=2,
            max_llm_calls_per_run=50,
            max_storage_mb=500,
            timeout_per_state=604800,
            soft_limit_usd=5.0,
            hard_limit_usd=20.0,
        )


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    profile = ResearchProfile()
    profile.initialize()

    print("📦 ResearchProfile loaded:")
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
    for state_name in ["topic_selected", "hypothesis", "paper_draft", "peer_review"]:
        hitl = sm.get_hitl_questions(state_name, rt)
        is_pause = sm.is_pause_state(state_name)
        state_def = sm.config.states[state_name]
        pause_tag = "⏸️ PAUSE" if state_def.state_type.name == "PAUSE" else ""
        print(f"   {state_name}: {len(hitl)} questions {'(' + pause_tag + ')' if pause_tag else ''}")
        for q in hitl:
            choices_str = f" [{', '.join(q['choices'])}]" if q.get('choices') else ""
            print(f"     - [{q['type']}] {q['question']}{choices_str}")

    # Test state machine
    for to_state in sm.get_next_states(rt.current_state):
        allowed, reason = sm.can_transition(rt.current_state, to_state, rt)
        print(f"   {rt.current_state} → {to_state}: "
              f"{'✅' if allowed else '❌'} ({reason})")

    # Test terminal constraint
    allowed, reason = sm.can_transition("published", "paper_draft", rt)
    print(f"\n   published → paper_draft: {'✅' if allowed else '❌'} ({reason})")

    # Test full path
    path = ["topic_selected", "literature_review", "hypothesis",
            "experiment_design", "data_collection", "analysis",
            "paper_draft", "peer_review", "published"]
    for i in range(len(path) - 1):
        allowed, reason = sm.can_transition(path[i], path[i + 1], rt)
        if not allowed and path[i] == "peer_review":
            print(f"   {path[i]} → {path[i+1]}: ⏳ (requires human approval)")
        else:
            print(f"   {path[i]} → {path[i+1]}: {'✅' if allowed else '❌'}")

    print(f"\n{'='*50}")
    print(f"ResearchProfile demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
