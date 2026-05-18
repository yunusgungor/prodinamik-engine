"""Prodinamik Engine v1.3 — Skill Emergence Automation

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
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .log import get_logger
from .aidetect import (
    AIDriftDetector,
    DriftType,
    EmergenceCandidate,
    TrendDirection,
)


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────


SKILLS_BASE_DIR = os.path.expanduser("~/.hermes/skills/ai-generated")
T3_VALIDATOR_MARKER = "tier: T3"
T2_VALIDATOR_MARKER = "tier: T2"
PROMOTION_THRESHOLD = 10  # Successful fixes before T3 → T2


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class SkillDraft:
    """A generated skill ready to be written to disk"""
    name: str
    description: str
    content: str
    drift_type: DriftType
    confidence: float
    test_content: str = ""
    skill_path: str = ""
    test_path: str = ""

    @property
    def is_ready(self) -> bool:
        return self.confidence >= 0.65


@dataclass
class SkillFixStats:
    """Statistics for a generated skill"""
    skill_name: str
    times_used: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def is_promotable(self) -> bool:
        """T3 → T2 promotion if 10+ successful uses"""
        return self.success_count >= PROMOTION_THRESHOLD


# ──────────────────────────────────────────────
# Auto Skill Forge
# ──────────────────────────────────────────────


class AutoSkillForge:
    """Automatically creates skills from emergence candidates

    Usage:
        forge = AutoSkillForge(detector)
        drafts = forge.generate_skills()
        forge.save_skill(drafts[0])
    """

    def __init__(self, detector: AIDriftDetector, output_dir: str = SKILLS_BASE_DIR):
        self.detector = detector
        self.output_dir = output_dir
        self.log = get_logger()
        self._fix_stats: Dict[str, SkillFixStats] = {}
        os.makedirs(output_dir, exist_ok=True)

    def generate_skills(self, min_confidence: float = 0.5
                        ) -> List[SkillDraft]:
        """Generate skill drafts from emergence candidates"""
        candidates = self.detector.find_emergence_candidates()
        drafts: List[SkillDraft] = []

        for candidate in candidates:
            if candidate.confidence < min_confidence:
                continue

            draft = self._create_skill_draft(candidate)
            drafts.append(draft)
            self.log.info(f"Generated skill draft: {draft.name} "
                          f"(confidence={candidate.confidence})")

        return drafts

    def _create_skill_draft(self, candidate: EmergenceCandidate) -> SkillDraft:
        """Create a complete skill draft from an emergence candidate"""
        name = candidate.suggested_skill_name
        drift_type = candidate.drift_type

        # Frontmatter
        frontmatter = (
            f"---\n"
            f"name: {name}\n"
            f"description: \"{candidate.recommendation}\"\n"
            f"version: 0.1.0\n"
            f"tier: T3\n"
            f"drift_type: {drift_type.value}\n"
            f"emergence_id: {candidate.pattern_id}\n"
            f"created_at: {datetime.now().isoformat()}\n"
            f"occurrences: {candidate.occurrence_count}\n"
            f"affected_runs: {candidate.affected_runs}\n"
            f"tags: [\"ai-generated\", \"{drift_type.value}\", \"emergence\"]\n"
            f"---\n\n"
        )

        # Detection rules
        detection_rules = self._generate_detection_rules(drift_type)

        # Fix steps
        fix_steps = self._generate_fix_steps(drift_type, candidate.description)

        # Verification
        verification = self._generate_verification(drift_type)

        # Assemble content
        content = (
            f"{frontmatter}"
            f"# {name.replace('-', ' ').title()}\n\n"
            f"> AI-Generated Skill (emergence: {candidate.pattern_id})\n"
            f"> Confidence: {candidate.confidence:.0%}\n\n"
            f"## Description\n\n{candidate.recommendation}\n\n"
            f"## Detection\n\n{detection_rules}\n\n"
            f"## Fix Steps\n\n{fix_steps}\n\n"
            f"## Verification\n\n{verification}\n\n"
            f"## Drift Pattern\n\n"
            f"- **Type:** {drift_type.value}\n"
            f"- **Occurrences:** {candidate.occurrence_count}\n"
            f"- **Affected Runs:** {candidate.affected_runs}\n"
            f"- **Severity Trend:** {candidate.severity_trend.value}\n"
            f"- **First/Last:** (auto-tracked)\n\n"
            f"---\n"
            f"_Generated by Prodinamik AI Engine v1.3_"
        )

        # Test content
        test_content = self._generate_test(name, drift_type)

        skill_path = os.path.join(self.output_dir, name, "SKILL.md")
        test_path = os.path.join(self.output_dir, name, "test_skill.py")

        return SkillDraft(
            name=name,
            description=candidate.recommendation,
            content=content,
            drift_type=drift_type,
            confidence=candidate.confidence,
            test_content=test_content,
            skill_path=skill_path,
            test_path=test_path,
        )

    def _generate_detection_rules(self, drift_type: DriftType) -> str:
        """Generate detection rules for a drift type"""
        rules = {
            DriftType.FORMAT: (
                "1. Check YAML frontmatter is valid\n"
                "2. Validate required fields present\n"
                "3. Run schema validation"
            ),
            DriftType.CONTENT: (
                "1. Scan for minimum content length\n"
                "2. Verify section headers match template\n"
                "3. Check for required keywords"
            ),
            DriftType.LOGIC: (
                "1. Validate state transition rules\n"
                "2. Check precondition/postcondition consistency\n"
                "3. Verify idempotency"
            ),
            DriftType.HALLUCINATION: (
                "1. Cross-reference claims with source data\n"
                "2. Flag unverifiable statistics\n"
                "3. Run fact-check regex patterns"
            ),
            DriftType.TIMEOUT: (
                "1. Measure execution duration\n"
                "2. Compare with expected bounds\n"
                "3. Flag if >2x expected"
            ),
        }
        return rules.get(drift_type,
                         "1. Detect anomalous pattern\n2. Log occurrence\n3. Alert operator")

    def _generate_fix_steps(self, drift_type: DriftType,
                             description: str) -> str:
        """Generate fix steps for a drift type"""
        base = f"### Manual Fix\n\n1. Identify the {drift_type.value} issue in the run\n"
        base += f"2. Apply correction for: {description[:100]}\n"
        base += "3. Re-run verification\n\n"

        if drift_type in (DriftType.FORMAT, DriftType.CONTENT):
            base += "### Auto-Fix (when promoted to T2)\n\n"
            base += "```bash\n./fix.sh # Auto-apply known pattern\n```\n"

        return base

    def _generate_verification(self, drift_type: DriftType) -> str:
        """Generate verification steps"""
        return (
            "- [ ] Fix applied successfully\n"
            "- [ ] Re-run passes all validation layers\n"
            "- [ ] No regression detected\n"
            "- [ ] Drift count decreases in subsequent run\n"
            "- [ ] Skill effectiveness logged"
        )

    def _generate_test(self, name: str, drift_type: DriftType) -> str:
        """Generate a regression test for the skill"""
        safe_name = name.replace("-", "_").replace(".", "_")
        return (
            f'"""Test for AI-generated skill: {name}"""\n\n'
            f'import pytest\n\n\n'
            f'class Test{safe_name.title()}:\n'
            f'    """Regression tests for {name} skill"""\n\n'
            f'    def test_detection(self):\n'
            f'        """Should detect {drift_type.value} drifts"""\n'
            f'        assert True  # TODO: implement\n\n'
            f'    def test_fix_application(self):\n'
            f'        """Fix should resolve the drift"""\n'
            f'        assert True  # TODO: implement\n\n'
            f'    def test_no_regression(self):\n'
            f'        """Fix should not introduce new drifts"""\n'
            f'        assert True  # TODO: implement\n'
        )

    # ── Save ───────────────────────────────────

    def save_skill(self, draft: SkillDraft) -> bool:
        """Write a skill draft to disk"""
        if not draft.is_ready:
            self.log.warning(f"Skill {draft.name} not ready "
                             f"(confidence={draft.confidence})")
            return False

        try:
            # Create directory
            skill_dir = os.path.dirname(draft.skill_path)
            os.makedirs(skill_dir, exist_ok=True)

            # Write SKILL.md
            with open(draft.skill_path, "w") as f:
                f.write(draft.content)
            self.log.info(f"Saved skill: {draft.skill_path}")

            # Write test file
            if draft.test_content:
                with open(draft.test_path, "w") as f:
                    f.write(draft.test_content)

            # Initialize stats
            self._fix_stats[draft.name] = SkillFixStats(
                skill_name=draft.name,
                created_at=datetime.now(),
            )

            return True

        except Exception as e:
            self.log.error(f"Failed to save skill {draft.name}: {e}")
            return False

    def save_all_skills(self, drafts: List[SkillDraft]) -> Tuple[int, int]:
        """Save all ready skill drafts. Returns (saved, total)"""
        saved = 0
        for draft in drafts:
            if self.save_skill(draft):
                saved += 1
        return saved, len(drafts)

    # ── Skill Stats ────────────────────────────

    def record_fix_result(self, skill_name: str, success: bool) -> None:
        """Record a fix result for skill promotion tracking"""
        stats = self._fix_stats.get(skill_name)
        if not stats:
            stats = SkillFixStats(skill_name=skill_name)
            self._fix_stats[skill_name] = stats

        stats.times_used += 1
        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
        stats.last_used = datetime.now()

        # Check promotion
        if stats.is_promotable:
            self._promote_skill(skill_name)

    def _promote_skill(self, skill_name: str) -> None:
        """Promote a skill from T3 to T2"""
        skill_path = os.path.join(self.output_dir, skill_name, "SKILL.md")
        if not os.path.exists(skill_path):
            return

        with open(skill_path) as f:
            content = f.read()

        content = content.replace(T3_VALIDATOR_MARKER, T2_VALIDATOR_MARKER)
        content += (
            "\n\n## Auto-Fix Activated\n\n"
            f"This skill has been promoted to T2 after "
            f"{PROMOTION_THRESHOLD}+ successful fixes.\n"
        )

        with open(skill_path, "w") as f:
            f.write(content)

        self.log.info(f"Skill promoted to T2: {skill_name}")

    def get_promotable_skills(self) -> List[str]:
        """Get list of skills ready for T3→T2 promotion"""
        return [
            name for name, stats in self._fix_stats.items()
            if stats.is_promotable
        ]

    def stats_summary(self) -> Dict[str, Any]:
        """Summary of skill statistics"""
        return {
            "total_generated": len(self._fix_stats),
            "promotable": len(self.get_promotable_skills()),
            "total_uses": sum(s.times_used for s in self._fix_stats.values()),
            "overall_success_rate": (
                sum(s.success_count for s in self._fix_stats.values())
                / max(sum(s.times_used for s in self._fix_stats.values()), 1)
            ),
            "skills": {
                name: {
                    "uses": s.times_used,
                    "success_rate": s.success_rate,
                    "is_promotable": s.is_promotable,
                }
                for name, s in self._fix_stats.items()
            },
        }
