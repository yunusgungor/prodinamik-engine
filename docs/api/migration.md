# Migration

Prodinamik Engine v0.5 — Cross-Profile Integration

Review #10: Formal Migration Plan
Review #4: Cross-Profile Event Chain

Content + Software profillerinin birlikte çalışması:
1. Software release → Content announcement thread
2. Formal migration: v1 → v2 (state rename + new states)

**Module:** `engine.migration.py`

## Classes

### `CrossProfileOrchestrator`

Content + Software profilleri arasında event zinciri.

Örnek akış:
Software: release.published
  → Event Bus → Content: announcement.needed
    → Content: creating new run "Flux v1.0 release thread"

**Methods:**

- `__init__(bus)`
- `setup_software_release_chain(on_release)`
  — Software release → tetikleyici
- `setup_content_announcement_chain(on_announcement)`
  — Content announcement tetikleyici
- `teardown()`
  — Event chain'ini temizle

### `MigrationResult`

Migration sonucu

**Methods:**

- `__init__()`
- `add_error(msg)`
- `summary()`

### `MigrationPlan`

Formal migration plan between profile versions.

Kullanım:
    plan = MigrationPlan(
        state_map={"prototyping": "implementation"},
        added_states=["code_review"],
        added_validators=["CodeReviewCheck"],
    )
    result = plan.execute(old_sm, new_sm_config)

**Methods:**

- `__init__(state_map, added_states, removed_states, added_validators, removed_validators, backward_compatible)`
- `execute(old_sm, new_config)`
  — Migration'ı çalıştır ve doğrula.

## Functions

### `demo()`
