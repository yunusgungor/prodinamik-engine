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
from datetime import datetime
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
        "devcycle": ("profiles.devcycle", "DevCycleProfile"),
        "haber": ("profiles.haber", "HaberProfile"),
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

        # ── EventStore & DecisionBridge (lazy — created on first access) ──
        self._event_store = None
        self._decision_bridge = None
        self._hitl_handler = None

        self.log.info(f"Engine initialized: {len(self.profile_registry)} profiles, "
                       f"data_dir={self.config.data_dir}")

    # ──────────────────────────────────────────────
    # EventStore & DecisionBridge
    # ──────────────────────────────────────────────

    @property
    def event_store(self):
        """Lazy-initialised :class:`EventStore` instance.

        Creates the EventStore at ``{data_dir}/runs/engine/events``
        on first access.  This avoids writing events when the engine
        is used as a library without a running pipeline.
        """
        if self._event_store is None:
            from engine.event_store import EventStore
            base = self.config.data_dir
            self._event_store = EventStore(base_path=base, slug="engine")
            self.log.debug(f"EventStore created: {self._event_store.events_dir}")
        return self._event_store

    @property
    def decision_bridge(self):
        """Lazy-initialised :class:`ProdinamikDecisionBridge` instance.

        Shares the engine's EventStore so that all validation decisions
        are automatically persisted.  The bridge is created on first
        access — no overhead if no pipeline uses validation logging.
        """
        if self._decision_bridge is None:
            from engine.decision_bridge import ProdinamikDecisionBridge
            self._decision_bridge = ProdinamikDecisionBridge(
                event_store=self.event_store,
                run_slug="engine",
            )
            self.log.debug("DecisionBridge initialized")
        return self._decision_bridge

    @property
    def hitl_handler(self):
        """Lazy-initialised :class:`ProdinamikHITLHandler` instance.

        Created on first access so that pipeline HITL escalations
        flow through the engine's HumanLoopManager.
        """
        if self._hitl_handler is None:
            from engine.hitl_bridge import ProdinamikHITLHandler
            self._hitl_handler = ProdinamikHITLHandler(
                timeout_minutes=5,
            )
            self.log.debug("HITLHandler initialized")
        return self._hitl_handler

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

    def transition_with_hitl(self, slug: str, to_state: str,
                               answers: dict = None) -> dict:
        """Transition + HITL kontrolü.
        
        1. State transition yap
        2. Yeni state HITL gerektiriyorsa soruları döndür
        
        Returns dict:
          - success: True/False
          - run_slug: str
          - current_state: str
          - awaiting_input: bool (True = sorular var)
          - questions: list (sadece awaiting_input=True ise)
        """
        try:
            run = self.transition(slug, to_state)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        profile = self.get_profile(run.meta.profile)
        sm = profile.state_machine if profile else None
        current_state = run.meta.state

        if not sm:
            return {"success": True, "run_slug": slug, "current_state": current_state}

        # HITL kontrolü
        if sm.is_pause_state(current_state):
            rt = RuntimeState(
                current_state=current_state,
                iteration_count=run.meta.iteration_count,
                user_answers=answers or {},
            )
            questions = sm.get_hitl_questions(current_state, rt)
            if questions:
                # Zaman aşımı hesapla
                from datetime import timedelta
                state_def = sm.config.states.get(current_state)
                timeout = 300  # default
                if state_def and state_def.hitl:
                    # Her sorunun kendi timeout'u var, en büyüğünü kullan
                    for au in state_def.hitl.ask_user:
                        timeout = max(timeout, au.timeout_seconds)

                # ── HITLHandler escalation (eğer initialized ise) ──
                if self._hitl_handler is not None:
                    try:
                        self._hitl_handler.request_approval({
                            "step": current_state,
                            "run_slug": slug,
                            "questions": questions,
                            "error": f"Run '{slug}' paused at '{current_state}' — awaiting input",
                            "timeout": timeout,
                        })
                        self.log.info(f"HITL escalation created for {slug} @ {current_state}")
                    except Exception as e:
                        self.log.warning(f"HITL escalation failed (non-blocking): {e}")

                return {
                    "success": True,
                    "run_slug": slug,
                    "current_state": current_state,
                    "awaiting_input": True,
                    "questions": questions,
                    "timeout": timeout,
                    "message": f"Run '{slug}' paused at '{current_state}' — waiting for your input.",
                }

        return {
            "success": True,
            "run_slug": slug,
            "current_state": current_state,
            "awaiting_input": False,
        }

    def resume(self, slug: str, answers: dict) -> dict:
        """Resume a paused run with user answers.
        
        HITL: Kullanıcı cevaplarını al, resume_transitions'a göre
        bir sonraki state'i belirle ve geçiş yap.
        
        Returns dict with status, next_state (varsa), questions (varsa).
        """
        run = self.get_run(slug)
        if not run:
            raise ValueError(f"Run '{slug}' not found")

        profile = self.get_profile(run.meta.profile)
        if not profile or not profile.state_machine:
            raise ValueError(f"Profile for run '{slug}' not found or has no state machine")

        sm = profile.state_machine
        current_state = run.meta.state

        # Run'un mevcut state'ini kontrol et
        if not sm.is_pause_state(current_state):
            return {
                "status": "not_paused",
                "message": f"Run '{slug}' current state '{current_state}' is not a pause state",
            }

        # Cevapları RuntimeState'e kaydet
        rt = RuntimeState(
            current_state=current_state,
            version=run.meta.version,
            iteration_count=run.meta.iteration_count,
            user_answers=answers,
        )

        # resume_transitions mapping'ine göre next state belirle
        next_state = sm.evaluate_resume_transition(current_state, answers)

        if not next_state:
            # Mapping yoksa, cevapları runtime'a yaz ve transition'ı agent'a bırak
            self.run_manager._update_snapshot(slug, {
                "user_answers": answers,
                "updated_at": datetime.now().isoformat(),
            })
            self.run_manager._append_wal({
                "action": "resume",
                "slug": slug,
                "answers": answers,
                "timestamp": datetime.now().isoformat(),
            })
            return {
                "status": "answers_recorded",
                "message": "Answers recorded. No automatic transition defined.",
                "answers": answers,
            }

        # Hedef state'e geç
        try:
            updated_run = self.run_manager.update_state(slug, next_state, profile, {
                "human_approved": True,  # Cevaplanmış soru = human approval
                "user_answers": str(answers),
            })
        except ValueError as e:
            return {
                "status": "transition_failed",
                "message": str(e),
            }

        # Yeni state de pause ise soruları döndür
        if sm.is_pause_state(next_state):
            new_rt = RuntimeState(
                current_state=next_state,
                iteration_count=updated_run.meta.iteration_count,
            )
            questions = sm.get_hitl_questions(next_state, new_rt)
            if questions:
                return {
                    "status": "awaiting_input",
                    "run_slug": slug,
                    "current_state": next_state,
                    "questions": questions,
                }

        return {
            "status": "transitioned",
            "run_slug": slug,
            "from_state": current_state,
            "to_state": next_state,
        }

    def list_runs(self, include_archived: bool = False) -> List[RunMeta]:
        """List all runs"""
        return self.run_manager.list_runs(include_archived=include_archived)

    # ──────────────────────────────────────────────
    # Engine status
    # ──────────────────────────────────────────────

    def status(self) -> dict:
        """Engine health and stats"""
        info = {
            "profiles": self.list_profiles(),
            "data_dir": self.config.data_dir,
            "active_runs": len(self.run_manager.list_runs()),
            "config": self.config.to_dict(),
        }
        # Add EventStore stats if initialized
        if self._event_store is not None:
            info["event_store"] = self._event_store.stats()
        return info
