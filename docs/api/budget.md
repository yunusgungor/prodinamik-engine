# Budget Enforcement

Prodinamik Engine v0.5 — Budget Enforcement

Budget limitleri ile Degradation Manager entegrasyonu.
Her run'ın budget'ı profile'dan alınır.
Budget aşılınca DegradationManager'a bildirilir.

Aksiyonlar:
- PROCEED: Normal çalışma
- WARN: Soft limit aşıldı, kullanıcıya uyarı
- SLOW: Validator sampling rate düşer
- STOP: Yeni validasyon engellenir, degradation tetiklenir

**Module:** `engine.budget.py`

## Classes

### `BudgetAction`(Enum)

### `BudgetLimit`

Tek bir budget limiti

**Methods:**

- `soft_exceeded()`
- `hard_exceeded()`
- `usage_pct()`
- `check()`
- `progress_bar(width)`

### `BudgetEnforcer`

Budget enforcement + Degradation entegrasyonu.

Soft limit → WARN (kullanıcıya uyarı)
Hard limit → STOP + Degrade to SURVIVAL

Per-profile budget limits profile.yaml'den gelir.

**Methods:**

- `__init__(cost_tracker, degradation_manager)`
- `configure(budget_config)`
  — Profile'dan gelen budget yapılandırması
- `check_validator(validator_name, tier)`
  — Validator çalışmadan önce budget kontrolü.
- `apply_action(action, validator_name)`
  — Budget aksiyonunu uygula
- `should_run_validator(validator_name, tier)`
  — Validator'ın çalışıp çalışmayacağına karar ver (sampling ile)
- `update_from_tracker()`
  — CostTracker'dan güncel değerleri al
- `status()`
  — Budget durumunu göster
- `reset()`
  — Run bazında reset (yeni run için)

## Functions

### `demo()`
