"""Prodinamik Engine v1.0 — Main Engine

Orchestrates all components:
- Config loading
- Profile discovery
- Run management
- Event store
- Cost tracking
- Degradation
"""

import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from .config import ProdinamikConfig
from .log import get_logger
from .run_manager import RunManager, RunMeta
from .profile import ProductProfile
from .state_machine import RuntimeState

# Lazy-import registration
_PROFILES: Dict[str, type] = {}


def _discover_profiles():
    """Import and register all known profiles"""
    if _PROFILES:
        return _PROFILES

    known = {
        "content": ("profiles.content", "ContentProfile"),
        "software": ("profiles.software", "SoftwareProfile"),
        "research": ("profiles.research", "ResearchProfile"),
        "design": ("profiles.design", "DesignProfile"),
    }

    for name, (module_path, class_name) in known.items():
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            _PROFILES[name] = cls
        except (ImportError, AttributeError) as e:
            get_logger().warning(f"Profile '{name}' unavailable: {e}")

    return _PROFILES


class ProdinamikEngine:
    """Main engine — wires config, profiles, run manager, cost, degradation"""

    def __init__(self, config: Optional[ProdinamikConfig] = None):
        self.config = config or ProdinamikConfig.load()
        self.log = get_logger()

        # Initialize run manager
        self.run_manager = RunManager(base_path=self.config.data_dir)

        # Discover profiles
        self.profile_registry = _discover_profiles()

        self.log.info(f"Engine initialized: {len(self.profile_registry)} profiles, "
                       f"data_dir={self.config.data_dir}")

    # ──────────────────────────────────────────────
    # Profile access
    # ──────────────────────────────────────────────

    def get_profile(self, name: str) -> Optional[ProductProfile]:
        """Get an initialized profile by name"""
        cls = self.profile_registry.get(name)
        if not cls:
            available = list(self.profile_registry.keys())
            self.log.warning(f"Profile '{name}' not found. Available: {available}")
            return None
        profile = cls()
        profile.initialize()
        return profile

    def list_profiles(self) -> List[str]:
        """List available profile names"""
        return list(self.profile_registry.keys())

    # ──────────────────────────────────────────────
    # Run lifecycle
    # ──────────────────────────────────────────────

    def create_run(self, profile_name: str, title: str,
                   slug: Optional[str] = None) -> "Run":
        """Create a new run with the given profile"""
        profile = self.get_profile(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found. "
                             f"Available: {self.list_profiles()}")

        return self.run_manager.create_run(title, profile, slug)

    def get_run(self, slug: str) -> Optional["Run"]:
        """Get a run by slug"""
        # Try each profile until we find the run
        for name in self.profile_registry:
            profile = self.get_profile(name)
            if profile:
                run = self.run_manager.get_run(slug, profile)
                if run and run.meta:
                    return run
        return None

    def transition(self, slug: str, to_state: str) -> "Run":
        """Transition a run to a new state"""
        # Find which profile manages this run
        run = self.get_run(slug)
        if not run:
            raise ValueError(f"Run '{slug}' not found")

        profile = self.get_profile(run.meta.profile)
        if not profile:
            raise ValueError(f"Profile '{run.meta.profile}' for run '{slug}' not found")

        return self.run_manager.update_state(slug, to_state, profile)

    def list_runs(self, include_archived: bool = False) -> List[RunMeta]:
        """List all runs"""
        return self.run_manager.list_runs(include_archived=include_archived)

    # ──────────────────────────────────────────────
    # Engine status
    # ──────────────────────────────────────────────

    def status(self) -> dict:
        """Engine health and stats"""
        return {
            "profiles": self.list_profiles(),
            "data_dir": self.config.data_dir,
            "active_runs": len(self.run_manager.list_runs()),
            "config": self.config.to_dict(),
        }
