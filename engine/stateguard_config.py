"""Profile → StateGuard Dimension Mapping Configuration.

Defines which StateGuard validation dimensions each Prodinamik
product profile should use and at which tier.

Usage::

    from engine.stateguard_config import STATEGUARD_PROFILE_CONFIG, make_profile_validators

    # Get StateGuard validators for a profile
    for v in make_profile_validators("content"):
        profile.add_validator(v)
"""

from __future__ import annotations

from typing import Any

from engine.profile import ValidatorDef, ValidatorTier
from engine.stateguard_bridge import make_stateguard_def


# ──────────────────────────────────────────────
# Profile → Dimension Map
# ──────────────────────────────────────────────

# Each profile specifies which StateGuard dimensions to enable,
# at which tier, and with what timeout / criticality.

STATEGUARD_PROFILE_CONFIG: dict[str, list[dict[str, Any]]] = {
    "content": [
        {
            "dimension": "structural",
            "tier": "T1",
            "critical": True,
            "timeout": 30,
            "reason": "JSON/format denetimi — her içerik parçası yapısal olarak tutarlı olmalı",
        },
        {
            "dimension": "semantic",
            "tier": "T2",
            "critical": True,
            "timeout": 120,
            "reason": "Anlamsal tutarlılık — içerik konudan sapmamalı",
        },
        {
            "dimension": "security",
            "tier": "T1",
            "critical": True,
            "timeout": 30,
            "reason": "Prompt injection tespiti — güvenlik kritik",
        },
    ],
    "software": [
        {
            "dimension": "structural",
            "tier": "T1",
            "critical": True,
            "timeout": 30,
            "reason": "Kod yapısı ve format kontrolü",
        },
        {
            "dimension": "quantitative",
            "tier": "T2",
            "critical": False,
            "timeout": 60,
            "reason": "Sayısal outlier tespiti — build süreleri, test sayıları",
        },
        {
            "dimension": "behavioral",
            "tier": "T2",
            "critical": True,
            "timeout": 60,
            "reason": "State machine uyumu — pipeline akışı tutarlı olmalı",
        },
    ],
    "haber": [
        {
            "dimension": "structural",
            "tier": "T1",
            "critical": True,
            "timeout": 30,
            "reason": "Haber JSON formatı denetimi",
        },
        {
            "dimension": "semantic",
            "tier": "T2",
            "critical": True,
            "timeout": 120,
            "reason": "Haber anlamsal tutarlılığı — kaynakla uyum",
        },
    ],
    "research": [
        {
            "dimension": "semantic",
            "tier": "T2",
            "critical": True,
            "timeout": 120,
            "reason": "Makale anlamsal bütünlüğü",
        },
        {
            "dimension": "quantitative",
            "tier": "T2",
            "critical": False,
            "timeout": 60,
            "reason": "İstatistiksel outlier tespiti — veri tutarlılığı",
        },
    ],
    "design": [
        {
            "dimension": "structural",
            "tier": "T1",
            "critical": True,
            "timeout": 30,
            "reason": "Tasarım çıktı formatı denetimi",
        },
        {
            "dimension": "semantic",
            "tier": "T2",
            "critical": False,
            "timeout": 120,
            "reason": "Tasarım brief'ine uygunluk",
        },
    ],
}


# ──────────────────────────────────────────────
# Tier name → ValidatorTier enum
# ──────────────────────────────────────────────

_TIER_MAP: dict[str, ValidatorTier] = {
    "T1": ValidatorTier.T1,
    "T2": ValidatorTier.T2,
    "T3": ValidatorTier.T3,
}


# ──────────────────────────────────────────────
# Public helpers
# ──────────────────────────────────────────────


def make_profile_validators(
    profile_name: str,
) -> list[ValidatorDef]:
    """Create a list of :class:`ValidatorDef` for a given profile.

    Each entry in :data:`STATEGUARD_PROFILE_CONFIG` becomes a
    :class:`ValidatorDef` with a unique name like
    ``\"stateguard.{dimension}\"``.

    Args:
        profile_name: One of ``\"content\"``, ``\"software\"``,
                      ``\"haber\"``, ``\"research\"``, ``\"design\"``.

    Returns:
        A list of :class:`ValidatorDef` instances suitable for
        passing to :meth:`ProductProfile.add_validator`.

    Raises:
        KeyError: If *profile_name* is not configured.
    """
    if profile_name not in STATEGUARD_PROFILE_CONFIG:
        raise KeyError(
            f"No StateGuard config for profile {profile_name!r}. "
            f"Available: {list(STATEGUARD_PROFILE_CONFIG)}"
        )

    defns: list[ValidatorDef] = []
    for entry in STATEGUARD_PROFILE_CONFIG[profile_name]:
        tier_name = entry["tier"]
        tier = _TIER_MAP.get(tier_name)
        if tier is None:
            raise ValueError(
                f"Invalid tier {tier_name!r} for {entry['dimension']}"
            )

        defn = make_stateguard_def(
            name=f"stateguard.{entry['dimension']}",
            tier=tier,
            critical=entry.get("critical", True),
            timeout_seconds=entry.get("timeout", 120),
        )
        defns.append(defn)

    return defns


def list_profile_configs() -> dict[str, list[str]]:
    """Return a summary of all configured profiles and their dimensions."""
    return {
        name: [e["dimension"] for e in entries]
        for name, entries in STATEGUARD_PROFILE_CONFIG.items()
    }
