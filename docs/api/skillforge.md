# Skill Emergence Automation (AutoSkillForge)

**Module:** `engine.skillforge.py`

Automatically creates Hermes/Prodinamik skills from recurring drift patterns.
When the same drift type occurs repeatedly, this module generates a complete
`SKILL.md` with validation rules, fix steps, and regression tests, then
manages its lifecycle from proposal (T3) through promotion to auto-fix (T2).

## Overview

The skill emergence pipeline follows a four-stage architecture:

```
DriftPattern ──→ EmergenceCandidate ──→ SkillDraft ──→ SKILL.md + test_skill.py
     ↑                    ↑                    ↑                 ↑
  AIDriftDetector    find_emergence_    _create_skill_      save_skill()
                     candidates()       draft()
```

**Emergence rules:**

1. **3+ occurrences** of the same drift type → a T3 (validator proposal) skill
   is generated.
2. **10+ successful fixes** (tracked via `record_fix_result`) → the skill is
   promoted from T3 to T2 (auto-fix capable).
3. **Confidence threshold** — skills with `confidence >= 0.65` are considered
   "ready" for disk; those with `confidence > 0.85` would auto-register in the
   skill registry.

**Tier system:**

| Tier | Label | Meaning |
|---|---|---|
| T4 | Monitoring | Drift observed but insufficient occurrences |
| T3 | Validator | Skill proposed; manual fix only |
| T2 | Auto-Fix | 10+ successful fixes; can auto-apply |
| T1 | Production | Battle-tested; full lifecycle |

## Data Classes

### `SkillDraft`

A generated skill ready to be written to disk. Passed through the forge
pipeline from candidate evaluation to file I/O.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | — | Skill name (derived from `candidate.suggested_skill_name`) |
| `description` | `str` | — | Human-readable description from the emergence candidate |
| `content` | `str` | — | Full `SKILL.md` content with frontmatter, detection rules, fix steps, verification |
| `drift_type` | `DriftType` | — | The drift type this skill addresses |
| `confidence` | `float` | — | Emergence confidence score (0.0–1.0) |
| `test_content` | `str` | `""` | Generated pytest regression test content |
| `skill_path` | `str` | `""` | Absolute path where `SKILL.md` will be written |
| `test_path` | `str` | `""` | Absolute path where `test_skill.py` will be written |

**`is_ready -> bool`** — Returns `True` when `confidence >= 0.65`. Skills
below this threshold are not written to disk by `save_skill()`.

---

### `SkillFixStats`

Per-skill statistics tracking fix outcomes and promotion eligibility.

| Field | Type | Default | Description |
|---|---|---|---|
| `skill_name` | `str` | — | Unique skill name |
| `times_used` | `int` | `0` | How many times the skill was applied |
| `success_count` | `int` | `0` | How many of those applications succeeded |
| `failure_count` | `int` | `0` | How many of those applications failed |
| `created_at` | `Optional[datetime]` | `None` | Timestamp of skill creation |
| `last_used` | `Optional[datetime]` | `None` | Timestamp of most recent use |

**`success_rate -> float`** — Returns `success_count / (success_count + failure_count)`.
Returns `0.0` when there have been zero total uses.

**`is_promotable -> bool`** — Returns `True` when `success_count >= 10`.
This is the gate for T3 → T2 promotion.

## Class: `AutoSkillForge`

The central orchestrator. Takes an `AIDriftDetector` instance and an output
directory, then orchestrates candidate evaluation, draft generation, file I/O,
and promotion tracking.

**`__init__(detector: AIDriftDetector, output_dir: str = "~/.hermes/skills/ai-generated")`**

- `detector` — An `AIDriftDetector` instance providing emergence candidates.
- `output_dir` — Base directory for generated skill artifacts. Created on
  instantiation if it does not exist.
- Initialises an empty `_fix_stats: Dict[str, SkillFixStats]` for tracking.

### Skill Generation Methods

**`generate_skills(min_confidence: float = 0.5) -> List[SkillDraft]`**

The main generation entry point. Calls `detector.find_emergence_candidates()`,
filters by `min_confidence`, and passes each qualifying candidate through
`_create_skill_draft()`. Logs each generated draft at INFO level.

- `min_confidence` — Minimum emergence confidence to consider (default 0.5).
  Note: `is_ready` still requires 0.65 for disk persistence.

```python
forge = AutoSkillForge(detector)
drafts = forge.generate_skills()           # default min_confidence=0.5
high_confidence = forge.generate_skills(min_confidence=0.8)
```

**`_create_skill_draft(candidate: EmergenceCandidate) -> SkillDraft`**

Builds a complete `SkillDraft` from an emergence candidate:

1. **Frontmatter** — YAML with `name`, `description`, `version: 0.1.0`,
   `tier: T3`, `drift_type`, `emergence_id`, `created_at`, `occurrences`,
   `affected_runs`, and `tags`.
2. **Description** — The candidate's recommendation text.
3. **Detection rules** — Drift-type-specific rules via `_generate_detection_rules()`.
4. **Fix steps** — Manual fix procedure via `_generate_fix_steps()`.
5. **Verification checklist** — Common 5-item checklist via `_generate_verification()`.
6. **Drift pattern metadata** — Type, occurrences, affected runs, severity
   trend.
7. **Regression test** — pytest boilerplate via `_generate_test()`.

Fills `skill_path` and `test_path` from `output_dir / name / SKILL.md` and
`output_dir / name / test_skill.py`.

**`_generate_detection_rules(drift_type: DriftType) -> str`**

Returns a markdown rule list tailored to the drift type:

| `DriftType` | Detection Rules |
|---|---|
| `FORMAT` | Validate YAML frontmatter, required fields, schema |
| `CONTENT` | Minimum content length, section headers, required keywords |
| `LOGIC` | State transition rules, pre/post-condition consistency, idempotency |
| `HALLUCINATION` | Cross-reference claims, flag unverifiable stats, fact-check regex |
| `TIMEOUT` | Measure duration, compare with bounds, flag if >2x |
| *(other)* | Catch-all: detect anomalous pattern → log → alert |

**`_generate_fix_steps(drift_type: DriftType, description: str) -> str`**

Returns manual fix steps prefixed by the drift type and a truncated
description. For `FORMAT` and `CONTENT` drift types, also includes an
auto-fix section that will be activated when the skill reaches T2.

**`_generate_verification(drift_type: DriftType) -> str`**

Returns a standard 5-item checklist:
- Fix applied successfully
- Re-run passes all validation layers
- No regression detected
- Drift count decreases in subsequent run
- Skill effectiveness logged

**`_generate_test(name: str, drift_type: DriftType) -> str`**

Returns a pytest skeleton:

```python
"""Test for AI-generated skill: {name}"""

import pytest

class Test{safe_name}:
    """Regression tests for {name} skill"""

    def test_detection(self):
        """Should detect {drift_type.value} drifts"""
        assert True  # TODO: implement

    def test_fix_application(self):
        """Fix should resolve the drift"""
        assert True  # TODO: implement

    def test_no_regression(self):
        """Fix should not introduce new drifts"""
        assert True  # TODO: implement
```

### Persistence Methods

**`save_skill(draft: SkillDraft) -> bool`**

Writes a single skill draft to disk:

1. Checks `draft.is_ready` — logs a warning and returns `False` if
   `confidence < 0.65`.
2. Creates the skill directory (`mkdir -p`).
3. Writes `draft.content` → `SKILL.md`.
4. Writes `draft.test_content` → `test_skill.py` (if non-empty).
5. Initialises a `SkillFixStats` entry in `_fix_stats` with `created_at=now`.
6. Returns `True` on success.

On any `Exception`, logs the error and returns `False`.

**`save_all_skills(drafts: List[SkillDraft]) -> Tuple[int, int]`**

Calls `save_skill()` for every draft in the list. Returns `(saved_count, total_count)`.

```python
forge = AutoSkillForge(detector)
drafts = forge.generate_skills()
saved, total = forge.save_all_skills(drafts)
print(f"Saved {saved}/{total} skills")
```

### Promotion & Statistics Methods

**`record_fix_result(skill_name: str, success: bool) -> None`**

Records a fix outcome for the named skill. Creates a new `SkillFixStats`
entry if one does not already exist. Increments `times_used` and either
`success_count` or `failure_count`. Sets `last_used = datetime.now()`.

If the skill becomes promotable (`success_count >= 10`), automatically
calls `_promote_skill()`.

```python
forge.record_fix_result("api-format-validator", success=True)
forge.record_fix_result("api-format-validator", success=True)
# ... after 10 successful fixes, auto-promoted to T2
```

**`_promote_skill(skill_name: str) -> None`**

Promotes a skill from T3 (validator) to T2 (auto-fix):

1. Reads `output_dir / skill_name / SKILL.md`.
2. Replaces `tier: T3` with `tier: T2` in the file content.
3. Appends an "## Auto-Fix Activated" section noting the promotion.
4. Writes the updated file back.

Only operates if the `SKILL.md` file actually exists. No-op on missing files.

**`get_promotable_skills() -> List[str]`**

Returns a list of skill names whose `SkillFixStats.is_promotable` is `True`.

**`stats_summary() -> Dict[str, Any]`**

Returns a comprehensive summary dictionary:

```python
{
    "total_generated": 5,           # skills in _fix_stats
    "promotable": 1,                # count of promotable skills
    "total_uses": 47,               # sum of all times_used
    "overall_success_rate": 0.85,   # weighted average
    "skills": {
        "api-format-validator": {
            "uses": 12,
            "success_rate": 0.916666,
            "is_promotable": True
        },
        # ... per-skill entries
    }
}
```

## Usage Examples

### Complete Workflow

```python
from engine.aidetect import AIDriftDetector
from engine.skillforge import AutoSkillForge

# 1. Set up the detector (already populated with run data)
detector = AIDriftDetector()

# 2. Create the forge
forge = AutoSkillForge(detector, output_dir="/tmp/my-skills")

# 3. Generate drafts
drafts = forge.generate_skills(min_confidence=0.65)
print(f"Generated {len(drafts)} skill drafts")

# 4. Save to disk
saved, total = forge.save_all_skills(drafts)
print(f"Saved {saved}/{total}")

# 5. Record outcomes over time
for i in range(12):
    forge.record_fix_result("content-section-checker", success=True)

# 6. Check promotion
print(forge.get_promotable_skills())   # ["content-section-checker"]
print(forge.stats_summary())
```

### Custom Output Directory

```python
forge = AutoSkillForge(
    detector,
    output_dir="/etc/prodinamik/skills/custom"
)
```

### Inspecting Drafts Before Saving

```python
drafts = forge.generate_skills()
for draft in drafts:
    print(f"  {draft.name}  (confidence={draft.confidence:.0%})")
    print(f"    Path: {draft.skill_path}")
    print(f"    Ready: {draft.is_ready}")
    print(f"    Drift: {draft.drift_type.value}")
    # Preview first 200 chars of content
    print(f"    Content preview: {draft.content[:200]}...")
```

## Error Handling & Edge Cases

- **Low-confidence candidates** — `generate_skills(min_confidence=0.5)` filters
  out weak signals. The threshold is configurable; raising it yields fewer but
  more reliable drafts.
- **`save_skill` on unready drafts** — Returns `False` and logs a warning when
  `draft.is_ready` is `False`. Callers should gate with `if draft.is_ready` or
  use `save_all_skills` which silently counts them as unsaved.
- **Missing SKILL.md during promotion** — `_promote_skill` is a no-op if the
  file does not exist (e.g., if the skill was generated in a different session
  or manually deleted).
- **File I/O errors** — `save_skill` catches all `Exception` types, logs the
  error, and returns `False`. This covers permissions, disk full, and path
  length issues.
- **Thread safety** — `_fix_stats` is a plain `dict` with no locking. The
  module is intended for single-threaded CLI or sequential pipeline use.
- **Graceful missing detector** — If `detector.find_emergence_candidates()`
  returns an empty list, `generate_skills()` returns an empty list without
  error.

## Constants

| Constant | Value | Description |
|---|---|---|
| `SKILLS_BASE_DIR` | `~/.hermes/skills/ai-generated` | Default output directory |
| `T3_VALIDATOR_MARKER` | `"tier: T3"` | Frontmatter marker for T3 |
| `T2_VALIDATOR_MARKER` | `"tier: T2"` | Frontmatter marker for T2 (post-promotion) |
| `PROMOTION_THRESHOLD` | `10` | Successful fixes required for T3→T2 promotion |

## Related Modules

| Module | Relationship |
|---|---|
| `engine.aidetect` | Provides `AIDriftDetector`, `DriftType`, `EmergenceCandidate`, `TrendDirection` — the input to skill generation |
| `engine.log` | Logger used for INFO/WARNING/ERROR messages |
| Hermes Skill Registry | Target registry that consumes generated `SKILL.md` files |
