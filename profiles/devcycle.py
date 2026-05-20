"""
Prodinamik Engine v2.1 — DevCycle Profile

dev-cycle v8.0 metodolojisinin ProductProfile olarak eksiksiz implementasyonu.
4 aşamalı (Prototype → Iterate → Fine-Tune → Deploy) drift-odaklı geliştirme
lifecycle'i.

State Machine (15 state):
  idea → brief → prototyping → development ⇄ verification → drift_resolution
    → fine_tune → review → approved → deploy → deployed → archived
  Rollback: review → development, deployed → development
  Block: blocked (pause), cancelled/failed (terminal)

HITL v1.1 (Türkçe uyumlu):
  - brief: Brief onayı (yes → prototyping, no → idea)
  - prototyping: İlk prototip onayı (Türkçe/İngilizce)
  - development: Her 3+ iterasyonda durum sorusu
  - drift_resolution: Drift düzeltme planı onayı, 3+ tekrarda yaklaşım değişikliği
  - review: PAUSE — release onayı + değişiklik talebi + re-entry kontrolü
  - blocked: PAUSE — blok kaldırma kararı (5 seçenek)

3-Tier Verification:
  T1: IdeaCheck, SpecCheck, LintCheck, BuildCheck + DeployCheck + PreDeployCheck (deterministic, <50ms)
  T2: TestCheck, CodeReviewCheck, DriftCheck, HealthCheck (LLM destekli)
  T3: IntegrationTestCheck, SecurityCheck, PerformanceCheck (E2E)

Drift Management:
  Her T1/T2/T3 başarısızlığı drift olarak kaydedilir.
  Iterasyon sayacı development→verification döngüsünde artar.
  3 ardışık başarısız doğrulama → blocked state'e geçiş.
  Drift azalma hedefi: ilk 4 iterasyonda ≥%80.
"""

from engine.profile import ProductProfile, ValidatorDef, ValidatorTier, AdapterDef, Budget, StoreDef, TemplateDef

DEVCYCLE_SM = """
profile: devcycle
name: dev-cycle-pipeline
version: 1.0

formal_properties:
  termination:
    max_steps: 150

states:
  # ═══════════════════════════════════════════
  # PHASE 1: PROTOTYPE (gün 0)
  # ═══════════════════════════════════════════

  idea:
    type: initial
    max_reentries: 1
    timeout: 86400
    validators: ["IdeaCheck"]
    description: "Fikrin tanımlandığı başlangıç state'i. Proje brief'i yazılır."

  brief:
    type: intermediate
    max_reentries: 3
    timeout: 86400
    validators: ["SpecCheck"]
    description: "Brief/spec yazılır ve insan onayına sunulur."
    hitl:
      ask_user:
        - question: "Brief/Spec'i onaylıyor musun? Prototip aşamasına geçelim mi?"
          type: yes_no
          timeout: 86400
      resume_transitions:
        "yes": prototyping
        "no": idea
        "Evet": prototyping
        "Hayır": idea

  prototyping:
    type: intermediate
    max_reentries: 5
    timeout: 259200
    validators: ["BuildCheck"]
    description: "İlk çalışan prototip geliştirilir. Gün 0 çıktısı."
    hitl:
      ask_user:
        - question: "Prototip çalışıyor mu? Iterasyon aşamasına geçelim mi?"
          type: yes_no
          timeout: 86400
      ask_if:
        - condition: "reentry_count >= 3"
          question: "3. prototip denemesi. Yaklaşımı değiştirmek veya brief'i revize etmek ister misin?"
          type: multiple_choice
          choices: ["Yaklaşım değiştir", "Brief revize et", "Devam et"]
          on_timeout: proceed
      resume_transitions:
        "yes": development
        "Evet": development
        "Yaklaşım değiştir": prototyping
        "Brief revize et": brief
        "Devam et": development
        "no": brief
        "Hayır": brief

  # ═══════════════════════════════════════════
  # PHASE 2: ITERATE [4-10] (gün 1-N)
  # ═══════════════════════════════════════════

  development:
    type: intermediate
    max_reentries: 50
    timeout: 604800
    validators: ["LintCheck"]
    description: |
      Ana iterasyon döngüsü. Kod yazılır, test edilir.
      Iteration counter: her development→verification döngüsü 1 artar.
      Min 4 iterasyon, max 10 iterasyon sonra manuel değerlendirme.
    hitl:
      ask_if:
        - condition: "iteration_count >= 3 AND iteration_count % 3 == 0"
          question: "{iteration_count}. iterasyon tamamlandı. Durum nedir?"
          type: multiple_choice
          choices: ["Devam et", "Review'a hazır", "Block et", "Yaklaşım değiştir"]
          on_timeout: proceed
        - condition: "iteration_count >= 8"
          question: "8 iterasyonu geçtin. Bu iterasyonu sonlandırıp Fine-Tune'a geçmek ister misin?"
          type: yes_no
          on_timeout: proceed

  verification:
    type: intermediate
    max_reentries: 30
    timeout: 86400
    validators: ["TestCheck", "CodeReviewCheck"]
    description: |
      3-kademeli doğrulama (T1→T2→T3).
      T1: Fail-fast (lint, schema, build, spec)
      T2: Parallel (test, code review, drift analysis)
      T3: Sequential (integration, security, performance)

  drift_resolution:
    type: intermediate
    max_reentries: 20
    timeout: 172800
    validators: ["DriftCheck"]
    description: |
      Drift tespit edildiğinde belgeleme ve düzeltme state'i.
      Her drift D001.yml formatında kaydedilir.
      5 adım: tespit → kök neden → düzeltme → doğrulama → regresyon testi.
    hitl:
      ask_user:
        - question: "Drift tespit edildi. Düzeltme planını onaylıyor musun?"
          type: yes_no
          timeout: 86400
      ask_if:
        - condition: "reentry_count >= 3"
          question: "3+ kez aynı drift düzeltiliyor. Kalıcı çözüm için yaklaşım değişikliği gerekli mi?"
          type: yes_no
          on_timeout: proceed
      resume_transitions:
        "yes": development
        "Evet": development
        "no": blocked
        "Hayır": blocked

  # ═══════════════════════════════════════════
  # PHASE 3: FINE-TUNE (gün N+1)
  # ═══════════════════════════════════════════

  fine_tune:
    type: intermediate
    max_reentries: 5
    timeout: 172800
    validators: ["IntegrationTestCheck", "SecurityCheck", "PerformanceCheck"]
    description: |
      Son doğrulama aşaması.
      Tüm T1/T2/T3'ten geçen kod son kez kontrol edilir.
      Entegrasyon testi, güvenlik taraması, performans testi.
      Çıktı: final-package.md

  # ═══════════════════════════════════════════
  # PHASE 4: DEPLOY (gün N+2)
  # ═══════════════════════════════════════════

  review:
    type: pause
    max_reentries: null
    timeout: 2592000
    description: |
      İnsan review ve onay state'i.
      PAUSE: kullanıcı cevap verene kadar bekler.
    temporal:
      max_duration: 604800
      reminders:
        - after: 86400
          message: "Review bekliyor — 1 gün geçti"
        - after: 259200
          message: "3 gündür review'da — lütfen kontrol edin"
        - after: 604800
          message: "7 gün geçti — escalation başlatılıyor"
    hitl:
      ask_user:
        - question: "Release'e hazır mı? Deploy edelim mi?"
          type: yes_no
          timeout: 604800
      ask_if:
        - condition: "reentry_count > 0"
          question: "Bu review'a daha önce de geldi. Ne yapalım?"
          type: multiple_choice
          choices: ["Release et", "Minor fix yap", "Major değişiklik yap", "İptal et"]
          on_timeout: hold
        - condition: "changes_requested == True"
          question: "Değişiklik talep edilmişti. Düzeltmeler yapıldı mı?"
          type: yes_no
          on_timeout: hold
      resume_transitions:
        "yes": approved
        "Evet": approved
        "Release et": approved
        "no": development
        "Hayır": development
        "Minor fix yap": development
        "Major değişiklik yap": prototyping
        "İptal et": cancelled

  approved:
    type: intermediate
    max_reentries: 1
    timeout: 86400
    validators: ["PreDeployCheck"]
    description: "Deploy öncesi son hazırlık. Deploy checklist çalıştırılır."

  deploy:
    type: intermediate
    max_reentries: 3
    timeout: 14400
    validators: ["DeployCheck"]
    description: "Deploy işleminin gerçekleştiği state."

  deployed:
    type: intermediate
    max_reentries: 3
    timeout: 2592000
    description: "Production'da. Monitoring ve gözlem altında."
    validators: ["HealthCheck"]

  archived:
    type: terminal
    max_reentries: 0
    description: "Proje arşivlendi. Artık aktif değil."

  cancelled:
    type: terminal
    max_reentries: 0
    description: "Proje iptal edildi."

  failed:
    type: terminal
    max_reentries: 0
    description: "Proje başarısız oldu. Kurtarılamaz hata."

  blocked:
    type: pause
    requires_manual: true
    timeout: 2592000
    description: |
      Proje bloke oldu. 3 ardışık başarısız doğrulama veya
      kritik hata durumunda bu state'e geçilir.
    temporal:
      max_duration: 604800
      reminders:
        - after: 86400
          message: "Block devam ediyor — 1 gün"
        - after: 172800
          message: "Block 2. gün — müdahale gerekli"
        - after: 604800
          message: "Block 7. gün — escalation"
    hitl:
      ask_user:
        - question: "Block'u kaldırmak için ne yapalım?"
          type: multiple_choice
          choices: ["Yaklaşım değiştir", "Brief revize et", "Yeni prototip dene", "Projeyi iptal et", "Devam et (ignore)"]
          timeout: 604800
      resume_transitions:
        "Yaklaşım değiştir": prototyping
        "Brief revize et": idea
        "Yeni prototip dene": prototyping
        "Projeyi iptal et": cancelled
        "Devam et (ignore)": development


# ═══════════════════════════════════════════════
# TRANSITIONS
# ═══════════════════════════════════════════════

transitions:
  # Phase 1: Prototype
  idea -> brief: {type: REVERSIBLE}
  brief -> prototyping: {type: REVERSIBLE, condition: "human_approved"}
  brief -> idea: {type: REVERSIBLE, condition: "human_rejected"}
  prototyping -> development: {type: REVERSIBLE, condition: "prototype_passes AND human_approved"}
  prototyping -> brief: {type: REVERSIBLE, condition: "human_rejected OR prototype_fails"}

  # Phase 2: Iterate (core loop)
  development -> verification: {type: REVERSIBLE}
  verification -> development: {type: REVERSIBLE, condition: "verification_failed"}
  verification -> drift_resolution: {type: REVERSIBLE, condition: "drift_detected"}
  verification -> fine_tune: {type: REVERSIBLE, condition: "verification_passed AND iterations >= 4"}
  verification -> review: {type: REVERSIBLE, condition: "verification_passed AND iterations >= 4 AND fine_tune_skipped"}
  drift_resolution -> development: {type: REVERSIBLE, condition: "drift_fixed AND human_approved"}
  drift_resolution -> blocked: {type: REVERSIBLE, condition: "human_rejected OR drift_unresolved"}

  # Phase 3: Fine-Tune
  fine_tune -> review: {type: REVERSIBLE, condition: "fine_tune_passed"}
  fine_tune -> development: {type: REVERSIBLE, condition: "fine_tune_failed"}

  # Phase 4: Deploy
  review -> approved: {type: COMPENSABLE, condition: "human_approved"}
  review -> development: {type: REVERSIBLE, condition: "changes_requested"}
  review -> prototyping: {type: REVERSIBLE, condition: "major_changes_requested"}
  review -> cancelled: {type: REVERSIBLE, condition: "project_abandoned"}
  approved -> deploy: {type: IRREVERSIBLE}
  deploy -> deployed: {type: IRREVERSIBLE, condition: "deploy_success"}
  deploy -> development: {type: REVERSIBLE, condition: "deploy_failed"}
  deployed -> archived: {type: REVERSIBLE, condition: "archive_requested"}
  deployed -> development: {type: REVERSIBLE, condition: "production_issue"}

  # Error states
  development -> blocked: {type: REVERSIBLE, condition: "consecutive_failures >= 3"}
  verification -> blocked: {type: REVERSIBLE, condition: "consecutive_failures >= 3"}
  development -> cancelled: {type: REVERSIBLE, condition: "max_iterations_exceeded"}
  blocked -> development: {type: REVERSIBLE, condition: "manual_unblock"}
  blocked -> prototyping: {type: REVERSIBLE, condition: "approach_change"}
  blocked -> idea: {type: REVERSIBLE, condition: "brief_revision"}
  blocked -> cancelled: {type: REVERSIBLE, condition: "project_abandoned"}
  blocked -> failed: {type: REVERSIBLE, condition: "unrecoverable"}
"""


class DevCycleProfile(ProductProfile):
    """
    dev-cycle v8.0 metodolojisinin eksiksiz ProductProfile implementasyonu.

    15-state lifecycle: Prototype → Iterate [4-10] → Fine-Tune → Deploy
    Drift-odaklı iteratif geliştirme, 3-tier verification, HITL + state machine recovery.

    Reference skill: `skill_view('dev-cycle')`
    """

    name = "devcycle"
    version = "1.0"
    description = (
        "dev-cycle v8.0: Prototype → Iterate [4-10] → Fine-Tune → Deploy. "
        "Drift-odaklı iteratif geliştirme, 3-tier verification, "
        "state machine recovery. Araçtan bağımsız genel metodoloji."
    )
    state_machine_yaml = DEVCYCLE_SM

    def setup_validators(self):
        """6 T1 + 4 T2 + 3 T3 = 13 validator"""
        # T1 — Fail-fast (deterministic, <50ms)
        self.add_validator(ValidatorDef(
            name="IdeaCheck", tier=ValidatorTier.T1, critical=True,
        ))
        self.add_validator(ValidatorDef(
            name="SpecCheck", tier=ValidatorTier.T1, critical=True,
        ))
        self.add_validator(ValidatorDef(
            name="LintCheck", tier=ValidatorTier.T1, critical=False,
            cache_ttl=3600,
        ))
        self.add_validator(ValidatorDef(
            name="BuildCheck", tier=ValidatorTier.T1, critical=True,
        ))

        # T2 — Parallel (LLM destekli)
        self.add_validator(ValidatorDef(
            name="TestCheck", tier=ValidatorTier.T2, critical=False,
            model="default", timeout_seconds=300,
        ))
        self.add_validator(ValidatorDef(
            name="CodeReviewCheck", tier=ValidatorTier.T2, critical=False,
            model="default", timeout_seconds=300,
        ))
        self.add_validator(ValidatorDef(
            name="DriftCheck", tier=ValidatorTier.T2, critical=True,
            model="default", timeout_seconds=120,
        ))

        # T3 — Sequential (E2E)
        self.add_validator(ValidatorDef(
            name="IntegrationTestCheck", tier=ValidatorTier.T3, critical=True,
            depends_on=["TestCheck"], timeout_seconds=600,
        ))
        self.add_validator(ValidatorDef(
            name="SecurityCheck", tier=ValidatorTier.T3, critical=True,
            depends_on=["CodeReviewCheck"], timeout_seconds=600,
        ))
        self.add_validator(ValidatorDef(
            name="PerformanceCheck", tier=ValidatorTier.T3, critical=False,
            depends_on=["IntegrationTestCheck"], timeout_seconds=600,
        ))

        # Deploy validator
        self.add_validator(ValidatorDef(
            name="PreDeployCheck", tier=ValidatorTier.T1, critical=True,
        ))
        self.add_validator(ValidatorDef(
            name="DeployCheck", tier=ValidatorTier.T1, critical=True,
        ))
        self.add_validator(ValidatorDef(
            name="HealthCheck", tier=ValidatorTier.T2, critical=True,
            model="default", timeout_seconds=120,
        ))

    def setup_adapters(self):
        """Deploy ve çıktı adaptörleri"""
        self.add_adapter(AdapterDef(
            name="GitRelease", type="github", max_retries=2,
            circuit_breaker_threshold=3,
            config={"auto_tag": True, "release_notes": True},
        ))
        self.add_adapter(AdapterDef(
            name="FileOutput", type="file", fallback_mode="file",
            config={"base_path": "./output"},
        ))
        self.add_adapter(AdapterDef(
            name="DockerDeploy", type="docker", max_retries=2,
            fallback_mode="queue",
        ))

    def setup_stores(self):
        """Dev cycle çıktı şeması"""
        self.add_store(StoreDef(
            name="brief", type="markdown", path="brief.md", required=True,
        ))
        self.add_store(StoreDef(
            name="drift_log", type="yaml", path="drift/", required=False,
        ))
        self.add_store(StoreDef(
            name="final_package", type="markdown", path="final-package.md", required=True,
        ))
        self.add_store(StoreDef(
            name="deploy_artifact", type="binary", path="dist/", required=False,
        ))

    def setup_templates(self):
        """Dev cycle şablon referansları (skill'den)"""
        self.add_template(TemplateDef(
            name="drift-documentation-template",
            path="templates/drift-documentation-template.md",
            description="Drift dokümantasyon şablonu (D001.yml formatı)",
        ))
        self.add_template(TemplateDef(
            name="pre-deploy-checklist",
            path="templates/pre-deploy-checklist.md",
            description="14 maddeli deploy checklist",
        ))
        self.add_template(TemplateDef(
            name="prototype-init",
            path="templates/prototype-init.md",
            description="Prototip başlangıç şablonu",
        ))
        self.add_template(TemplateDef(
            name="iterate",
            path="templates/iterate.md",
            description="Iterasyon döngüsü şablonu",
        ))
        self.add_template(TemplateDef(
            name="deploy",
            path="templates/deploy.md",
            description="Deploy akışı şablonu",
        ))
        self.add_template(TemplateDef(
            name="exhaustive-verify",
            path="templates/exhaustive-verify.md",
            description="Son doğrulama şablonu",
        ))

    def setup_budget(self):
        """Dev cycle resource budget"""
        self._budget = Budget(
            max_concurrent_validators=4,   # T1 + T2 paralel
            max_llm_calls_per_run=50,      # 10 iterasyon × ~5 LLM call
            max_storage_mb=500,            # Drift log + artifact
            timeout_per_state=604800,      # 7 gün max bekleme
            max_wal_entries=5000,          # Yoğun iterasyon log'u
            soft_limit_usd=5.0,            # Soft limit
            hard_limit_usd=25.0,           # Hard limit (uzun iterasyonlar)
        )

    # ──────────────────────────────────────────────
    # State machine DAG for CRDT merge
    # ──────────────────────────────────────────────

    @property
    def transition_map(self) -> dict:
        return {
            "idea": ["brief"],
            "brief": ["prototyping", "idea"],
            "prototyping": ["development", "brief"],
            "development": ["verification", "blocked", "cancelled"],
            "verification": ["development", "drift_resolution", "fine_tune", "review", "blocked"],
            "drift_resolution": ["development", "blocked"],
            "fine_tune": ["review", "development"],
            "review": ["approved", "development", "prototyping", "cancelled"],
            "approved": ["deploy"],
            "deploy": ["deployed", "development"],
            "deployed": ["archived", "development"],
            "blocked": ["development", "prototyping", "idea", "cancelled", "failed"],
        }

    # ──────────────────────────────────────────────
    # Dev Cycle Metadata
    # ──────────────────────────────────────────────

    @property
    def cycle_phases(self) -> dict:
        """4 aşamalı lifecycle fasetleri"""
        return {
            "prototype": {
                "states": ["idea", "brief", "prototyping"],
                "description": "Fikri yakala, rotayı belirle, brief yaz (gün 0)",
                "output": "brief.md + durum-001.md",
            },
            "iterate": {
                "states": ["development", "verification", "drift_resolution"],
                "description": "Kodla → test et → drift tespit et → düzelt (gün 1-N)",
                "min_iterations": 4,
                "max_iterations": 10,
                "drift_reduction_target": 0.80,
                "output": "drift-00X.md",
            },
            "fine_tune": {
                "states": ["fine_tune"],
                "description": "Son doğrulama, entegrasyon, güvenlik (gün N+1)",
                "output": "final-package.md",
                "verification_gates": ["T1", "T2", "T3"],
            },
            "deploy": {
                "states": ["review", "approved", "deploy", "deployed"],
                "description": "Onay, yayınla, arşivle (gün N+2)",
                "checklist_items": 14,
                "output": "production artifact",
            },
        }

    @property
    def iteration_rules(self) -> dict:
        """Dev cycle iteration constraints"""
        return {
            "min_iterations": 4,
            "max_iterations": 10,
            "consecutive_failures_limit": 3,
            "drift_reduction_target_pct": 80,
            "auto_evaluate_at_max": True,
            "block_on_3_failures": True,
        }

    @property
    def verification_tiers(self) -> dict:
        """3-tier verification metadata"""
        return {
            "T1": {
                "name": "Otomatik Kontrol",
                "methods": ["Lint", "Tip kontrolü", "Schema validation", "Derleme", "Deploy onayı"],
                "purpose": "Temel kalite",
                "pass_criteria": "0 hata",
                "validators": ["IdeaCheck", "SpecCheck", "LintCheck", "BuildCheck", "PreDeployCheck", "DeployCheck"],
            },
            "T2": {
                "name": "Rubric/Test",
                "methods": ["Unit test", "Entegrasyon testi", "Kod review", "Drift analizi", "Health check"],
                "purpose": "Doğruluk",
                "pass_criteria": "≥%90 geçme",
                "validators": ["TestCheck", "CodeReviewCheck", "DriftCheck", "HealthCheck"],
            },
            "T3": {
                "name": "Çapraz Doğrulama",
                "methods": ["E2E test", "Güvenlik taraması", "Performans testi"],
                "purpose": "Bütünlük",
                "pass_criteria": "0 kritik bulgu",
                "validators": ["IntegrationTestCheck", "SecurityCheck", "PerformanceCheck"],
            },
        }


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    """DevCycle profile demo — state machine, HITL, transitions"""
    profile = DevCycleProfile()
    profile.initialize()

    print("=" * 60)
    print("📦 DevCycleProfile v1.0 — dev-cycle v8.0 Engine Profile")
    print("=" * 60)
    print(f"   Name: {profile.name} v{profile.version}")
    print(f"   SM: {profile.state_machine}")
    print(f"   Validators: {len(profile.validators)} "
          f"(T1:{len(profile.tier1_validators)} + "
          f"T2:{len(profile.tier2_validators)} + "
          f"T3:{len(profile.tier3_validators)})")
    print(f"   Adapters: {[a.name for a in profile.adapters]}")
    print(f"   Stores: {[s.name for s in profile.stores]}")
    print(f"   Templates: {[t.name for t in profile.templates]}")
    print(f"   Budget: ${profile.budget.hard_limit_usd} hard limit")

    # Test state machine
    sm = profile.state_machine
    rt = sm.create_runtime()
    print(f"\n📌 Initial state: {rt.current_state}")
    print(f"   All states ({len(sm.config.states)}): {', '.join(sm.config.states.keys())}")

    # Test initial transitions
    print(f"\n🔀 Initial transitions from 'idea':")
    for to_state in sm.get_next_states("idea"):
        allowed, reason = sm.can_transition("idea", to_state, rt)
        print(f"   idea → {to_state}: {'✅' if allowed else '❌'} ({reason})")

    # Test all possible transitions
    print(f"\n🔀 Full transition map:")
    for from_state in sm.config.states:
        next_states = sm.get_next_states(from_state)
        if next_states:
            print(f"   {from_state} → {', '.join(next_states)}")

    # Test HITL
    print(f"\n🔔 HITL Questions by state:")
    hitl_states = ["brief", "prototyping", "development", "verification",
                   "drift_resolution", "review", "blocked"]
    for state_name in hitl_states:
        if state_name not in sm.config.states:
            continue
        hitl = sm.get_hitl_questions(state_name, rt)
        is_pause = sm.is_pause_state(state_name)
        state_def = sm.config.states[state_name]
        pause_tag = "⏸️ PAUSE" if state_def.state_type.name == "PAUSE" else ""
        print(f"   {state_name}: {len(hitl)} questions {f'({pause_tag})' if pause_tag else ''}")
        for q in hitl:
            choices_str = f" [{', '.join(q['choices'])}]" if q.get('choices') else ""
            print(f"     - [{q['type']}] {q['question']}{choices_str}")

    # Test terminal state constraints
    print(f"\n🔒 Terminal state constraints:")
    for t_state in ["deployed", "archived", "cancelled", "failed"]:
        allowed, reason = sm.can_transition(t_state, "development", rt)
        print(f"   {t_state} → development: {'✅' if allowed else '❌'} ({reason})")

    # Test CRDT merge
    from engine.raft import NodeState, StateCRDT
    local = NodeState(current_state="verification", version=5)
    remote = NodeState(current_state="fine_tune", version=3)
    merged = StateCRDT.merge(local, remote, profile.transition_map)
    print(f"\n🔄 CRDT merge: local=verification v5 + remote=fine_tune v3 → {merged.current_state}")

    # Test phase info
    print(f"\n📋 Dev Cycle Phases:")
    for phase, info in profile.cycle_phases.items():
        print(f"   {phase.upper()}: {info['description']}")
        print(f"       States: {', '.join(info['states'])}")
        print(f"       Output: {info['output']}")

    # Test verification tiers
    print(f"\n✅ Verification Tiers:")
    for tier, info in profile.verification_tiers.items():
        print(f"   {tier}: {info['name']} — {info['purpose']}")
        print(f"       Methods: {', '.join(info['methods'])}")
        print(f"       Pass: {info['pass_criteria']}")

    print(f"\n{'=' * 60}")
    print(f"✅ DevCycleProfile demo passed!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
