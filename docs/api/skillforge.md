# Skill Emergence Automation

Prodinamik Engine v1.3 — Skill Emergence Automation

Automatically creates Hermes/Prodinamik skills from recurring
drift patterns. When the same drift type occurs 3+ times, this
module generates a SKILL.md with validation rules, fix steps,
and regression tests.

Architecture:
    DriftPattern → SkillTemplate → SKILL.md → Skill Registry
                      ↓
                Regression Test (.py)

Rules of emergence:
    1. 3+ occurrences of same drift type → T3 validator proposal
    2. After 10 successful fixes → promote to T2 (auto-fix)
    3. Skill auto-registers if emergence.confidence > 0.85

**Module:** `engine.skillforge.py`

## Classes

### `SkillDraft`

A generated skill ready to be written to disk

**Methods:**

- `is_ready()`

### `SkillFixStats`

Statistics for a generated skill

**Methods:**

- `success_rate()`
- `is_promotable()`
  — T3 → T2 promotion if 10+ successful uses

### `AutoSkillForge`

Automatically creates skills from emergence candidates

Usage:
    forge = AutoSkillForge(detector)
    drafts = forge.generate_skills()
    forge.save_skill(drafts[0])

**Methods:**

- `__init__(detector, output_dir)`
- `generate_skills(min_confidence)`
  — Generate skill drafts from emergence candidates
- `_create_skill_draft(candidate)`
  — Create a complete skill draft from an emergence candidate
- `_generate_detection_rules(drift_type)`
  — Generate detection rules for a drift type
- `_generate_fix_steps(drift_type, description)`
  — Generate fix steps for a drift type
- `_generate_verification(drift_type)`
  — Generate verification steps
- `_generate_test(name, drift_type)`
  — Generate a regression test for the skill
- `save_skill(draft)`
  — Write a skill draft to disk
- `save_all_skills(drafts)`
  — Save all ready skill drafts. Returns (saved, total)
- `record_fix_result(skill_name, success)`
  — Record a fix result for skill promotion tracking
- `_promote_skill(skill_name)`
  — Promote a skill from T3 to T2
- `get_promotable_skills()`
  — Get list of skills ready for T3→T2 promotion
- `stats_summary()`
  — Summary of skill statistics
