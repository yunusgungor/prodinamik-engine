"""
Prodinamik Engine v2.1 — Content Profile

Content-OS'un ProductProfile olarak implementasyonu.
10-state lifecycle: captured → decide_route → idea_review → brief_ready →
drafting → verification → draft_review → approved → published → archived

HITL v1.1 (Türkçe uyumlu):
- decide_route: Kullanıcıya kanal seçimi sorulur
- brief_ready: Brief onayı alınır (Türkçe/İngilizce cevap destekli)
- drafting: 3+ reentry'de tone önerisi
- draft_review: PAUSE state — yayın onayı + drift uyarısı + Türkçe/İngilizce

T1 validators: SlopScan (107 pattern), LengthCheck, SchemaCheck
Adapters: Buffer (Twitter), FileOutput (fallback)
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget, StoreDef
from engine.validators import RegexValidator, LengthValidator, SchemaValidator

# Content state machine — 10 state, 14 transition + HITL (Türkçe uyumlu)
CONTENT_SM = """
profile: content
name: content-pipeline
version: 2.1

states:
  captured:
    type: initial
    max_reentries: 1
    validators: ["IdeaCheck"]

  decide_route:
    type: intermediate
    max_reentries: 3
    hitl:
      ask_user:
        - question: "Bu fikri hangi kanalda yayınlamalıyız?"
          type: multiple_choice
          choices: ["Blog", "Newsletter", "Twitter/X", "Hepsi"]
          timeout: 300
      resume_transitions:
        Blog: idea_review
        Newsletter: idea_review
        "Twitter/X": idea_review
        Hepsi: idea_review

  idea_review:
    type: intermediate
    max_reentries: 3
    hitl:
      ask_user:
        - question: "Fikir detaylarını inceledin mi? Devam edelim mi?"
          type: yes_no
          timeout: 300
      resume_transitions:
        "yes": brief_ready
        "evet": brief_ready
        "no": captured
        "hayır": captured

  brief_ready:
    type: intermediate
    max_reentries: 5
    hitl:
      ask_user:
        - question: "Brief'i onaylıyor musun?"
          type: yes_no
          timeout: 300
      ask_if:
        - condition: "reentry_count >= 2"
          question: "3. kez brief düzenliyorsun. Konuyu değiştirmek ister misin?"
          type: yes_no
          on_timeout: proceed
      resume_transitions:
        "yes": drafting
        "evet": drafting
        "no": idea_review
        "hayır": idea_review

  drafting:
    type: intermediate
    max_reentries: 10
    validators: ["DraftValidator"]
    hitl:
      ask_if:
        - condition: "reentry_count >= 3"
          question: "Tone doğru mu? Daha resmi mi samimi mi olsun?"
          type: multiple_choice
          choices: ["Resmi", "Samimi", "Teknik"]
          on_timeout: proceed

  verification:
    type: intermediate
    max_reentries: 10
    validators: ["SlopScanT1", "LengthCheck", "SchemaCheck"]

  draft_review:
    type: pause
    max_reentries: null
    temporal:
      max_idle: 259200
      reminders:
        - after: 86400
          message: "Review bekliyor"
          channel: "telegram"
    hitl:
      ask_user:
        - question: "Yazı yayına hazır mı?"
          type: yes_no
          timeout: 86400
      ask_if:
        - condition: "drift_count > 0"
          question: "Drift tespit edildi. Yine de yayınlamak istiyor musun, yoksa düzeltme turu mu atalım?"
          type: multiple_choice
          choices: ["Yayınla", "Düzelt"]
          on_timeout: hold
      resume_transitions:
        "yes": approved
        "evet": approved
        "Yayınla": approved
        "no": drafting
        "hayır": drafting
        "Düzelt": drafting

  approved:
    type: intermediate
    max_reentries: 1

  published:
    type: intermediate
    max_reentries: 1

  archived:
    type: terminal
    max_reentries: 0

transitions:
  captured -> decide_route: {}
  decide_route -> idea_review: {}
  idea_review -> brief_ready: {}
  idea_review -> captured: {}
  brief_ready -> drafting: {}
  brief_ready -> idea_review: {}
  drafting -> verification: {}
  drafting -> drafting: {condition: "drift_detected", action: "log_drift"}
  verification -> draft_review: {}
  verification -> drafting: {condition: "drift_detected", action: "log_drift"}
  draft_review -> approved: {condition: "human_approved"}
  draft_review -> drafting: {condition: "changes_requested"}
  approved -> published: {}
  published -> archived: {}
"""

CONTENT_SM_V1 = """
profile: content
name: content-pipeline
version: 1.0

states:
  captured:
    type: initial
    max_reentries: 1
    validators: ["IdeaCheck"]

  idea_review:
    type: intermediate
    max_reentries: 3

  brief_ready:
    type: intermediate
    max_reentries: 5

  drafting:
    type: intermediate
    max_reentries: 10
    validators: ["DraftValidator"]

  verification:
    type: intermediate
    max_reentries: 10
    validators: ["SlopScanT1", "LengthCheck", "SchemaCheck"]

  draft_review:
    type: intermediate
    max_reentries: null
    temporal:
      max_idle: 259200
      reminders:
        - after: 86400
          message: "Review bekliyor"
          channel: "telegram"

  approved:
    type: intermediate
    max_reentries: 1

  published:
    type: intermediate
    max_reentries: 1

  archived:
    type: terminal
    max_reentries: 0

transitions:
  captured -> idea_review: {}
  idea_review -> brief_ready: {}
  brief_ready -> drafting: {}
  drafting -> verification: {}
  drafting -> drafting: {condition: "drift_detected", action: "log_drift"}
  verification -> draft_review: {}
  verification -> drafting: {condition: "drift_detected", action: "log_drift"}
  draft_review -> approved: {condition: "human_approved"}
  draft_review -> drafting: {condition: "changes_requested"}
  approved -> published: {}
  published -> archived: {}
"""


class ContentProfile(ProductProfile):
    """Content production pipeline (Content-OS v2.5.0 uyumlu)"""

    name = "content"
    version = "2.1"
    description = "Content production pipeline with 10-state lifecycle + HITL v1.1"
    state_machine_yaml = CONTENT_SM

    def setup_validators(self):
        # T1: Slop scan (107 pattern — örnek alt küme)
        self.add_validator(ValidatorDef(
            name="SlopScanT1", tier=ValidatorTier.T1, critical=True,
            timeout_seconds=10,
        ))
        self.add_validator(ValidatorDef(
            name="LengthCheck", tier=ValidatorTier.T1, critical=False,
            timeout_seconds=5,
        ))
        self.add_validator(ValidatorDef(
            name="SchemaCheck", tier=ValidatorTier.T1, critical=False,
            timeout_seconds=5,
        ))

    def setup_adapters(self):
        self.add_adapter(AdapterDef(
            name="Buffer", type="buffer", max_retries=2,
            circuit_breaker_threshold=3, fallback_mode="file",
        ))
        self.add_adapter(AdapterDef(
            name="FileOutput", type="file", fallback_mode="file",
        ))

    def setup_budget(self):
        self._budget = Budget(
            max_concurrent_validators=2,
            max_llm_calls_per_run=20,
            max_storage_mb=100,
            timeout_per_state=3600,
            soft_limit_usd=1.0,
            hard_limit_usd=5.0,
        )

    def setup_stores(self):
        self.add_store(StoreDef(name="hooks", type="markdown",
                         path="stores/hooks/", required=False))
        self.add_store(StoreDef(name="proof", type="markdown",
                         path="stores/proof/", required=False))
        self.add_store(StoreDef(name="ideas", type="markdown",
                         path="stores/ideas/", required=False))


# ──────────────────────────────────────────────
# Migration: v1.0 → v2.0 (Content Profile)
# ──────────────────────────────────────────────

class ContentMigrationPlan:
    """v1.0 → v2.0 migration: draft_review state type changed to 'pause' + HITL"""

    V1_TO_V2 = {
        "state_map": {
            "captured": "captured",
            "idea_review": "idea_review",
            "brief_ready": "brief_ready",
            "drafting": "drafting",
            "verification": "verification",
            "draft_review": "draft_review",
            "approved": "approved",
            "published": "published",
            "archived": "archived",
        },
        "state_changes": {
            "draft_review": {
                "type": "pause",  # was: intermediate
                "added_hitl": True,
            },
            "idea_review": {"added_hitl": True},
            "brief_ready": {"added_hitl": True},
            "drafting": {"added_hitl": True},
        },
        "backward_compatible": True,
    }


# ──────────────────────────────────────────────
# Create T1 Slop Validator Instance
# ──────────────────────────────────────────────

def create_slop_validator() -> RegexValidator:
    """Content slop pattern'leri ile T1 validator oluştur"""
    patterns = [
        # Tier 1 — Critical (zero tolerance)
        ("promo_language", r"(harika|mükemmel|inanılmaz|şahane|benzersiz|olağanüstü)", "error"),
        ("vague_attribution", r"(uzmanlar\s+söylüyor|kaynaklara\s+göre|araştırmacılar\s+belirtiyor)", "error"),
        ("clickbait", r"(gözlerden\s+kaçan|kimsenin\s+bilmediği|duymadınız|şaşırtıcı)", "error"),
        ("overclaim", r"(devrim\s+yaratan|çığır\s+açan|dönüm\s+noktası|ezber\s+bozan|tarihi\s+an)", "warning"),
        ("urgency", r"(hemen\s+şimdi|sınırlı\s+süre|son\s+şans|kaçırma)", "error"),
        ("absolute", r"(her\s+zaman|asla|kesinlikle|tamamen|hiçbir\s+zaman)", "warning"),

        # Tier 2 — Filler phrases
        ("filler_aslinda", r"\baslında\b", "warning"),
        ("filler_srf", r"\bsırf\b", "warning"),
        ("filler_sadece", r"\bsadece\b", "warning"),
        ("filler_bence", r"\bbence\b", "warning"),

        # Tier 3 — Style
        ("passive_voice", r"\b(belirtildi|açıklandı|kaydedildi|görüldü)\b", "info"),
        ("elegant_variation", r"\b(bahsetmek|söz\s+etmek|değinmek)\b", "info"),
    ]

    defn = ValidatorDef(name="SlopScanT1", tier=ValidatorTier.T1, critical=True)
    return RegexValidator(defn, patterns)


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    profile = ContentProfile()
    profile.initialize()

    print("📦 ContentProfile loaded:")
    print(f"   Name: {profile.name} v{profile.version}")
    print(f"   SM: {profile.state_machine}")
    print(f"   Validators: {len(profile.validators)} "
          f"(T1:{len(profile.tier1_validators)})")
    print(f"   Adapters: {[a.name for a in profile.adapters]}")
    print(f"   Budget: ${profile.budget.hard_limit_usd} hard limit")

    # Test state machine
    sm = profile.state_machine
    rt = sm.create_runtime()
    print(f"\n📌 Initial: {rt.current_state}")
    print(f"   Next states: {sm.get_next_states('captured')}")
    print(f"   Total states: {len(sm.config.states)}")
    print(f"   Total transitions: {len(sm.config.transitions)}")

    # Test HITL
    print(f"\n🔔 HITL Test:")
    for state_name in ["decide_route", "idea_review", "brief_ready", "drafting", "draft_review"]:
        hitl = sm.get_hitl_questions(state_name, rt)
        state_def = sm.config.states[state_name]
        is_pause = sm.is_pause_state(state_name)
        pause_tag = " ⏸️ PAUSE" if state_def.state_type.name == "PAUSE" else ""
        print(f"   {state_name}: {len(hitl)} question(s){pause_tag}")
        for q in hitl:
            print(f"     - [{q['type']}] {q['question']}")

    # Test resume_transitions — Türkçe/İngilizce uyumluluk
    print(f"\n🔄 Resume Transitions Test:")

    # decide_route: multiple_choice
    for ans, expected in [("Blog", "idea_review"), ("Twitter/X", "idea_review"),
                           ("Hepsi", "idea_review")]:
        result = sm.evaluate_resume_transition("decide_route", {"answer": ans})
        status = "✅" if result == expected else "❌"
        print(f"   decide_route + '{ans}' → {result} {status}")

    # idea_review: yes_no (Türkçe/İngilizce)
    for ans, expected in [("yes", "brief_ready"), ("evet", "brief_ready"),
                           ("no", "captured"), ("hayır", "captured")]:
        result = sm.evaluate_resume_transition("idea_review", {"answer": ans})
        status = "✅" if result == expected else "❌"
        print(f"   idea_review + '{ans}' → {result} {status}")

    # brief_ready: yes_no (Türkçe/İngilizce)
    for ans, expected in [("yes", "drafting"), ("evet", "drafting"),
                           ("no", "idea_review"), ("hayır", "idea_review")]:
        result = sm.evaluate_resume_transition("brief_ready", {"answer": ans})
        status = "✅" if result == expected else "❌"
        print(f"   brief_ready + '{ans}' → {result} {status}")

    # draft_review: yes_no + multiple_choice (Türkçe/İngilizce)
    for ans, expected in [("yes", "approved"), ("evet", "approved"),
                           ("Yayınla", "approved"),
                           ("no", "drafting"), ("hayır", "drafting"),
                           ("Düzelt", "drafting")]:
        result = sm.evaluate_resume_transition("draft_review", {"answer": ans})
        status = "✅" if result == expected else "❌"
        print(f"   draft_review + '{ans}' → {result} {status}")

    # Test slop validator
    slop = create_slop_validator()
    import asyncio
    clean = "RISC-V timing closure için pipeline stratejileri."
    result = asyncio.run(slop.validate(clean))
    print(f"\n✅ Clean content: {'PASS' if result.passed else 'FAIL'}")
    sloppy = "Bu mükemmel ve harika bir ürün! Uzmanlar söylüyor ki..."
    result = asyncio.run(slop.validate(sloppy))
    print(f"❌ Slop content: {'PASS' if result.passed else 'FAIL'} "
          f"({len(result.details['errors'])} errors)")

    print(f"\n{'='*50}")
    print(f"ContentProfile demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
