"""
Prodinamik Engine v0.5 — Content Profile

Content-OS'un ProductProfile olarak implementasyonu.
9-state lifecycle: captured → idea_review → brief_ready → drafting →
verification → draft_review → approved → published → archived

T1 validators: SlopScan (107 pattern), LengthCheck, SchemaCheck
Adapters: Buffer (Twitter), FileOutput (fallback)
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget, StoreDef
from engine.validators import RegexValidator, LengthValidator, SchemaValidator

# Content state machine — 9 state, 11 transition
CONTENT_SM = """
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
    version = "1.0"
    description = "Content production pipeline with 9-state lifecycle"
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
