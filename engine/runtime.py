"""Prodinamik Engine v1.0 — Async Runtime

Asyncio main loop, component wiring, state timeout watcher,
lifecycle hooks, and graceful shutdown.
"""

import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, List, Any, Set
from pathlib import Path

from .config import ProdinamikConfig
from .log import get_logger
from .run_manager import RunManager, Run, RunMeta, RunStatus
from .hooks import HookRegistry
from .profile import ProductProfile
from .event_store import EventStore, CostAwareEvent
from .cost import CostTracker
from .degradation import DegradationManager, DegradationLevel
from .budget import BudgetEnforcer
from .safety import EventBus, RuntimeSafetyMonitor
from .autofix import AutoRemediator, FailureMatcher
from .aidetect import AIDriftDetector, DriftType, DriftSeverity, TrendDirection
from .skillforge import AutoSkillForge
from .agent_coordinator import WarmAgentCoordinator, AgentTaskType
from .state_machine import RuntimeState


# ──────────────────────────────────────────────
# Runtime Configuration
# ──────────────────────────────────────────────

@dataclass
class RuntimeConfig:
    """Async runtime configuration"""
    poll_interval: float = 5.0          # Timeout check interval (seconds)
    health_check_interval: float = 60.0  # Health check interval
    max_shutdown_wait: float = 10.0     # Max wait for graceful shutdown
    auto_recover: bool = True            # Auto-recover from DEGRADED → FULL
    enable_timeout_watcher: bool = True


# ──────────────────────────────────────────────
# Lifecycle Hooks
# ──────────────────────────────────────────────

@dataclass
class LifecycleHooks:
    """Per-state lifecycle hooks. Each is optional."""
    on_enter: Optional[Callable] = None     # async (run, state) -> None
    on_exit: Optional[Callable] = None      # async (run, from_state, to_state) -> None
    on_timeout: Optional[Callable] = None   # async (run, state) -> None


# ──────────────────────────────────────────────
# Async Engine
# ──────────────────────────────────────────────

class AsyncEngine:
    """
    Async runtime that wires all components together.

    - Main event loop (asyncio)
    - State timeout watcher (background task)
    - Health checker (background task)
    - Lifecycle hooks (per-state)
    - Graceful shutdown (signal handler)
    """

    def __init__(self, config: ProdinamikConfig,
                 runtime_config: Optional[RuntimeConfig] = None):
        self.config = config
        self.rt_config = runtime_config or RuntimeConfig()
        self.log = get_logger()
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

        # Core components
        self.run_manager = RunManager(base_path=config.data_dir)
        self.cost_tracker = CostTracker()
        self.degradation = DegradationManager(base_path=config.data_dir)
        self.budget = BudgetEnforcer(
            cost_tracker=self.cost_tracker,
            degradation_manager=self.degradation,
        )
        self.event_bus = EventBus()
        self.safety = RuntimeSafetyMonitor(event_bus=self.event_bus)

        # Budget defaults from config
        self.budget.configure({
            "soft_limit_usd": config.budget.soft_limit_usd,
            "hard_limit_usd": config.budget.hard_limit_usd,
            "max_llm_calls_per_run": config.budget.max_llm_calls_per_run,
            "max_storage_mb": config.budget.max_storage_mb,
        })

        # Per-slug EventStore cache (lazy init)
        self._event_stores: Dict[str, EventStore] = {}

        # ── StateGuard Integration (lazy init) ──
        self._sg_event_store: Optional[EventStore] = None
        self._sg_decision_bridge: Any = None
        self._sg_hitl_handler: Any = None

        # Profile registry (lazy)
        self._profile_cache: Dict[str, ProductProfile] = {}

        # Hooks registry: state_name → HookRegistry
        self.hooks = HookRegistry()

        # HITL timeout callback'ları (Hermes plugin vs. register eder)
        self._hitl_timeout_callbacks: List[Callable] = []
        
        # Auto-remediation
        self._remediator = AutoRemediator()
        self._auto_remediation_enabled = True
        
        # ── C2: Skill Emergence (AI Grid) ──
        self._drift_detector = AIDriftDetector()
        self._skill_forge = AutoSkillForge(self._drift_detector)
        self._skill_emergence_enabled = True
        self._skill_callback: Optional[Callable] = None  # (SkillDraft) → Hermes skill_manage
        
        # ── C3: Warm Agent Coordinator ──
        self._agent_coordinator = WarmAgentCoordinator(
            data_dir=os.path.join(self.config.data_dir, "warm-agent"),
            engine_ref=self,
        )
        self._warm_agent_enabled = True
        
        # Track visited states per slug for timeout calculation
        self._state_entry_time: Dict[str, Dict[str, datetime]] = {}

    def on_hitl_timeout(self, callback: Callable):
        """Register a HITL timeout callback (Hermes plugin kullanır)"""
        self._hitl_timeout_callbacks.append(callback)

    # ── StateGuard Integration Properties ─────────

    @property
    def event_store(self) -> EventStore:
        """Lazy-initialised central :class:`EventStore` instance.

        Unlike ``_get_event_store(slug)`` (per-run stores), this returns
        a single engine-level store at ``{data_dir}/runs/engine/events``,
        used by DecisionBridge for persisting validation decisions.
        Created on first access — no overhead when StateGuard is unused.
        """
        if self._sg_event_store is None:
            base = self.config.data_dir
            self._sg_event_store = EventStore(base_path=base, slug="engine")
            self.log.debug(f"SG EventStore created: {self._sg_event_store.events_dir}")
        return self._sg_event_store

    @property
    def decision_bridge(self):
        """Lazy-initialised :class:`ProdinamikDecisionBridge` instance.

        Shares the engine-level EventStore so that all validation
        decisions are automatically persisted to durable storage.
        """
        if self._sg_decision_bridge is None:
            from .decision_bridge import ProdinamikDecisionBridge
            self._sg_decision_bridge = ProdinamikDecisionBridge(
                event_store=self.event_store,
                run_slug="engine",
            )
            self.log.debug("SG DecisionBridge initialized")
        return self._sg_decision_bridge

    @property
    def hitl_handler(self):
        """Lazy-initialised :class:`ProdinamikHITLHandler` instance.

        Pipeline HITL escalations flow through this handler.
        The Hermes plugin can also register ``on_hitl_timeout``
        callbacks via the existing ``on_hitl_timeout()`` method.
        """
        if self._sg_hitl_handler is None:
            from .hitl_bridge import ProdinamikHITLHandler
            self._sg_hitl_handler = ProdinamikHITLHandler(
                timeout_minutes=5,
            )
            self.log.debug("SG HITLHandler initialized")
        return self._sg_hitl_handler

    def _check_auto_remediation(self, slug: str, from_state: str, to_state: str) -> Optional[dict]:
        """Check if auto-remediation is needed after a transition.
        
        Detects failure patterns like:
        - Repeated rejections (draft_review → drafting loop)
        - Drift escalation (drift_count too high)
        - Chain loop guard triggered
        """
        if not self._auto_remediation_enabled:
            return None
        
        # Detect repeated rejection loop (draft_review → drafting → draft_review)
        if from_state == "draft_review" and to_state == "drafting":
            snapshot = self.run_manager._load_snapshot()
            slug_data = snapshot.get(slug, {})
            rejection_count = slug_data.get("rejection_count", 0)
            self.run_manager._update_snapshot(slug, {
                "rejection_count": rejection_count + 1,
            })
            if rejection_count + 1 >= 3:
                plan = self._remediator.create_plan("repeated rejection: draft_review → drafting loop")
                if plan:
                    self.log.info(f"Auto-remediation: {slug} repeated rejection ({rejection_count+1})")
                    return plan.to_dict()
        
        # Detect drift escalation
        run = self.run_manager.get_run(slug)
        if run:
            rt = RuntimeState(current_state=to_state)
            if rt.drift_count >= 5:
                plan = self._remediator.create_plan(f"drift escalation: drift_count={rt.drift_count}")
                if plan:
                    self.log.info(f"Auto-remediation: {slug} drift escalation ({rt.drift_count})")
                    return plan.to_dict()
        
        return None

    # ── C2: Skill Emergence ──────────────────
    
    def record_drift(self, slug: str, drift_type: DriftType,
                     severity: DriftSeverity, state: str,
                     description: str, **metadata) -> None:
        """Record a drift event for emergence analysis"""
        if not self._skill_emergence_enabled:
            return
        self._drift_detector.record_drift(
            drift_id=f"{slug}-{state}-{len(self._drift_detector.collector._events)}",
            drift_type=drift_type,
            severity=severity,
            run_id=slug,
            state=state,
            description=description,
            **metadata,
        )
    
    def check_emergence(self) -> List[dict]:
        """Check for emergence candidates (3+ same drift type)
        
        Returns list of emergence candidates that qualify as skills."""
        if not self._skill_emergence_enabled:
            return []
        
        candidates = self._drift_detector.find_emergence_candidates(min_occurrences=3)
        if not candidates:
            return []
        
        drafts = self._skill_forge.generate_skills(min_confidence=0.65)
        results = []
        for draft in drafts:
            saved = self._skill_forge.save_skill(draft)
            results.append({
                "name": draft.name,
                "description": draft.description,
                "confidence": draft.confidence,
                "is_ready": draft.is_ready,
                "saved": saved,
                "skill_path": draft.skill_path,
            })
            # Hermes callback (if registered)
            if saved and self._skill_callback:
                try:
                    self._skill_callback(draft)
                except Exception as e:
                    self.log.warning(f"Skill callback failed for {draft.name}: {e}")
        
        return results
    
    def on_skill_emerged(self, callback: Callable) -> None:
        """Register a callback for when a skill is auto-generated.
        Hermes plugin uses this to call skill_manage()."""
        self._skill_callback = callback
    
    def record_drift_from_remediation(self, slug: str, from_state: str,
                                       to_state: str, pattern_name: str) -> None:
        """Record a drift event when auto-remediation triggers.
        
        Bridges C1 (Auto-Remediation) → C2 (Skill Emergence):
        each remediation action creates a drift record for emergence analysis."""
        drift_type = DriftType.VALIDATION
        severity = DriftSeverity.HIGH
        self.record_drift(
            slug=slug,
            drift_type=drift_type,
            severity=severity,
            state=to_state,
            description=f"Auto-remediation triggered: {pattern_name} ({from_state}→{to_state})",
            from_state=from_state,
            remediation_pattern=pattern_name,
        )
    
    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    async def start(self):
        """Start the async runtime"""
        self.log.info("AsyncEngine starting...")
        self._running = True

        # Register signal handlers
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.stop(s)))
        except NotImplementedError:
            self.log.debug("Signal handlers not available (Windows?)")

        # Start background tasks
        self._tasks = []
        if self.rt_config.enable_timeout_watcher:
            self._tasks.append(asyncio.create_task(
                self._timeout_watcher(), name="timeout-watcher"
            ))
        self._tasks.append(asyncio.create_task(
            self._health_checker(), name="health-checker"
        ))
        
        # ── C3: Warm Agent Coordinator ──
        if self._warm_agent_enabled:
            self._agent_coordinator.setup_default_tasks(self)
            await self._agent_coordinator.start()
            self.log.info("Warm Agent Coordinator started")

        # Recovery: replay WAL on startup
        self._recover()

        self.log.info("AsyncEngine started: "
                       f"{len(self._profile_cache)} profiles, "
                       f"{len(self.run_manager.list_runs())} active runs")

    async def stop(self, signum: Optional[int] = None):
        """Graceful shutdown"""
        sig_name = signal.Signals(signum).name if signum else "manual"
        self.log.info(f"AsyncEngine stopping (signal={sig_name})...")
        self._running = False

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        
        # ── C3: Stop Warm Agent Coordinator ──
        if self._warm_agent_enabled:
            await self._agent_coordinator.stop()

        # Flush: compact WAL to snapshot
        snapshot = self.run_manager._load_snapshot()
        self.run_manager._compact_wal(snapshot)
        self.log.info(f"AsyncEngine stopped. {len(snapshot)} runs in snapshot.")

        # Signal shutdown complete
        self._shutdown_event.set()

    async def wait_for_shutdown(self):
        """Block until shutdown signal received"""
        await self._shutdown_event.wait()

    # ──────────────────────────────────────────────
    # Background Tasks
    # ──────────────────────────────────────────────

    async def _timeout_watcher(self):
        """
        Background task: periodically checks all active runs
        for state timeouts. Triggers on_timeout hook when exceeded.
        """
        while self._running:
            try:
                await asyncio.sleep(self.rt_config.poll_interval)
                await self._check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Timeout watcher error: {e}")

    async def _check_timeouts(self):
        """Check all active runs for state timeouts"""
        now = datetime.now()
        runs = self.run_manager.list_runs()

        for meta in runs:
            if meta.status != RunStatus.ACTIVE.value:
                continue

            profile = self._get_profile(meta.profile)
            if not profile or not profile.state_machine:
                continue

            state_def = profile.state_machine.config.states.get(meta.state)
            if not state_def or not state_def.timeout_seconds:
                continue

            # Get entry time for this state
            slug_entries = self._state_entry_time.get(meta.slug, {})
            entered = slug_entries.get(meta.state)

            if entered is None:
                # Use updated_at from meta as fallback
                try:
                    entered = datetime.fromisoformat(meta.updated_at)
                except (ValueError, TypeError):
                    continue
                self._track_entry(meta.slug, meta.state, entered)

            elapsed = (now - entered).total_seconds()
            if elapsed > state_def.timeout_seconds:
                self.log.warning(
                    f"State timeout: {meta.slug} in '{meta.state}' "
                    f"for {elapsed:.0f}s (limit: {state_def.timeout_seconds}s)"
                )
                # Trigger timeout hook
                self.hooks.trigger_sync(meta.state, "on_timeout", meta, meta.state)

                # ── HITL/PAUSE state timeout politikası ──
                is_pause = (state_def.state_type.value == "pause" 
                           if hasattr(state_def, 'state_type') else False)
                on_timeout_policy = "proceed"  # default
                
                # HITL on_timeout policy'yi al
                if state_def.hitl:
                    on_timeout_policy = state_def.hitl.on_timeout
                
                # Escalation: elapsed süresine göre reminder seviyesi
                reminder_level = ""
                reminders = []
                if hasattr(state_def, 'reminders'):
                    reminders = state_def.reminders or []
                for rem in reminders:
                    if elapsed > rem.get("after", float('inf')):
                        reminder_level = f"⏰ {rem.get('message', 'Reminder')}"
                
                if is_pause:
                    self.log.info(
                        f"HITL timeout: {meta.slug} in PAUSE state '{meta.state}'. "
                        f"Policy: {on_timeout_policy}"
                    )
                    if reminder_level:
                        self.log.info(f"   Reminder: {reminder_level}")
                    
                    # Send notification via engine hook registry
                    self.hooks.trigger_sync(
                        meta.state, "on_hitl_timeout", meta, meta.state,
                        elapsed=elapsed, policy=on_timeout_policy,
                        reminder=reminder_level,
                    )
                    
                    # Send notification via external callbacks (Hermes plugin)
                    for cb in self._hitl_timeout_callbacks:
                        try:
                            cb(
                                slug=meta.slug,
                                state=meta.state,
                                elapsed=elapsed,
                                policy=on_timeout_policy,
                                reminder=reminder_level,
                            )
                        except Exception as e:
                            self.log.warning(f"HITL timeout callback failed: {e}")
                    
                    # Apply on_timeout policy
                    if on_timeout_policy == "proceed":
                        # Proceed: find first available transition and take it
                        sm = profile.state_machine
                        next_states = sm.get_next_states(meta.state)
                        for ns in next_states:
                            if ns != meta.state:  # skip self-loop
                                try:
                                    self._do_transition(meta.slug, ns)
                                    self.log.info(
                                        f"HITL timeout auto-proceed: "
                                        f"{meta.state} → {ns} (policy: proceed)"
                                    )
                                    break
                                except ValueError:
                                    continue
                    elif on_timeout_policy == "abort":
                        # Abort: transition to cancelled or first terminal state
                        try:
                            self._do_transition(meta.slug, "cancelled",
                                                runtime_overrides={
                                                    "project_abandoned": True,
                                                })
                            self.log.info(
                                f"HITL timeout abort: {meta.state} → cancelled"
                            )
                        except ValueError:
                            # Try archived
                            try:
                                self._do_transition(meta.slug, "archived")
                            except ValueError:
                                pass
                    elif on_timeout_policy.startswith("default:"):
                        # Default answer: use provided value
                        default_value = on_timeout_policy.split(":", 1)[1]
                        try:
                            self.resume_run(meta.slug, {"answer": default_value})
                            self.log.info(
                                f"HITL timeout default answer: "
                                f"'{default_value}' for {meta.state}"
                            )
                        except Exception as e:
                            self.log.warning(
                                f"HITL timeout default failed: {e}"
                            )
                    # "hold" = do nothing, keep waiting
                
                # Auto-transition to error state if defined (legacy)
                if state_def.temporal_on_timeout and not is_pause:
                    try:
                        run = self._do_transition(meta.slug,
                                                  state_def.temporal_on_timeout)
                        self.log.info(f"Timeout auto-transition: "
                                      f"{meta.state} → {state_def.temporal_on_timeout}")
                    except ValueError as e:
                        self.log.warning(f"Timeout transition failed: {e}")

    async def _health_checker(self):
        """
        Background task: periodic health checks via DegradationManager + Safety.
        """
        while self._running:
            try:
                await asyncio.sleep(self.rt_config.health_check_interval)

                # Collect engine state
                engine_state = {
                    "consecutive_llm_failures": self.cost_tracker.total_llm_calls,
                    "consecutive_adapter_failures": 0,
                    "budget_hard_limit_reached":
                        self.budget.limits.get("total_cost", None) is not None
                        and self.budget.limits["total_cost"].hard_exceeded,
                }

                # Degradation check
                old_level = self.degradation.current_level
                self.degradation.evaluate(engine_state)

                if self.rt_config.auto_recover \
                   and old_level == DegradationLevel.DEGRADED \
                   and self.degradation.current_level == DegradationLevel.FULL:
                    self.log.info("Auto-recovered from DEGRADED to FULL")

                # Safety invariants
                violations = self.safety.check_all(
                    bus=self.event_bus,
                    degradation=self.degradation,
                )
                if violations:
                    self.log.warning(
                        f"Health check: {len(violations)} invariant violation(s)")
                    for v in violations[:3]:
                        self.log.debug(f"  [{v.severity}] {v.name}: {v.message}")

                # Periodic cleanup of archived run state entries (memory leak prevention)
                self._cleanup_state_entries()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Health checker error: {e}")

    # ──────────────────────────────────────────────
    # Run Operations
    # ──────────────────────────────────────────────

    def _get_profile(self, name: str) -> Optional[ProductProfile]:
        """Get (cached) initialized profile"""
        if name not in self._profile_cache:
            cls = _PROFILE_REGISTRY.get(name)
            if not cls:
                self.log.warning(f"Profile '{name}' not found")
                return None
            profile = cls()
            profile.initialize()
            self._profile_cache[name] = profile
        return self._profile_cache[name]

    def create_run(self, profile_name: str, title: str,
                   slug: Optional[str] = None) -> Run:
        """Create a new run (synchronous — fast path)"""
        profile = self._get_profile(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found. "
                             f"Available: {self.list_profiles()}")

        run = self.run_manager.create_run(title, profile, slug)

        # Record event
        store = self._get_event_store(run.meta.slug)
        store.append(CostAwareEvent.from_transition(
            0, run.meta.slug, "", run.meta.state))

        # Track entry time
        self._track_entry(run.meta.slug, run.meta.state)

        # Trigger on_enter hook
        self.hooks.trigger_sync(run.meta.state, "on_enter", run.meta, run.meta.state)

        return run

    async def create_run_async(self, profile_name: str, title: str,
                                slug: Optional[str] = None) -> Run:
        """Create run with async hook support"""
        run = self.create_run(profile_name, title, slug)

        # Async hooks (create_run already fires sync hooks)
        await self.hooks.trigger(run.meta.state, "on_enter", run.meta, run.meta.state)

        return run

    def _do_transition(self, slug: str, to_state: str,
                       runtime_overrides: Dict[str, Any] = None) -> Run:
        """Internal: perform state transition with full wiring"""
        run = self.run_manager.get_run(slug)
        if not run:
            raise ValueError(f"Run '{slug}' not found")
        from_state = run.meta.state

        profile = self._get_profile(run.meta.profile)
        if not profile:
            raise ValueError(f"Profile '{run.meta.profile}' not found")

        # on_exit hook (sync)
        self.hooks.trigger_sync(from_state, "on_exit", run.meta, from_state, to_state)

        # Do transition (with runtime overrides if any)
        run = self.run_manager.update_state(slug, to_state, profile,
                                            runtime_overrides=runtime_overrides)

        # Record event
        store = self._get_event_store(slug)
        store.append(CostAwareEvent.from_transition(
            store._last_sequence + 1, slug, from_state, to_state))

        # Track entry time for new state
        self._track_entry(slug, to_state)

        # Cleanup archived runs from state tracking to prevent memory leak
        profile_state_types = profile.state_machine.config.states if profile.state_machine else {}
        if to_state in profile_state_types:
            state_def = profile_state_types[to_state]
            if hasattr(state_def, 'state_type') and str(state_def.state_type) in ('TERMINAL', 'terminal'):
                self._cleanup_state_entries()

        # on_enter hook (sync)
        self.hooks.trigger_sync(to_state, "on_enter", run.meta, to_state)

        # Auto-remediation check
        try:
            remediation = self._check_auto_remediation(slug, from_state, to_state)
            if remediation:
                self.log.info(f"Auto-remediation triggered for {slug}: {remediation.get('signature', '?')}")
                # C1 → C2 bridge: record drift from remediation
                self.record_drift_from_remediation(
                    slug=slug,
                    from_state=from_state,
                    to_state=to_state,
                    pattern_name=remediation.get('signature', 'unknown'),
                )
        except Exception as e:
            self.log.warning(f"Auto-remediation check failed: {e}")

        return run

    async def transition_async(self, slug: str, to_state: str) -> Run:
        """Transition with async hook support"""
        # _do_transition handles all sync hooks internally
        run = self._do_transition(slug, to_state)
        return run

    def transition_with_hitl(self, slug: str, to_state: str,
                              answers: dict = None) -> dict:
        """Transition + HITL kontrolü.

        1. State transition yap
        2. Yeni state HITL gerektiriyorsa soruları döndür
        
        Chain-loop guard: max 5 ardışık HITL adımını geçerse
        otomatik olarak bypass eder ve normal transition yapar.

        Returns dict with awaiting_input, questions, etc.
        """
        # Chain-loop guard: HITL döngü sayacını kontrol et
        run_before = self.run_manager.get_run(slug)
        current_hitl_count = 0
        if run_before:
            # Snapshot'tan hitl_loop_count oku
            snapshot = self.run_manager._load_snapshot()
            slug_data = snapshot.get(slug, {})
            current_hitl_count = slug_data.get('hitl_loop_count', 0)
        
        try:
            run = self._do_transition(slug, to_state)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        profile = self._get_profile(run.meta.profile)
        sm = profile.state_machine if profile else None
        current_state = run.meta.state

        if not sm:
            return {"success": True, "run_slug": slug, "current_state": current_state}

        if sm.is_pause_state(current_state):
            # Chain-loop guard: max 5 HITL adımı
            MAX_HITL_LOOP = 5
            if current_hitl_count >= MAX_HITL_LOOP:
                self.log.warning(
                    f"Chain-loop guard: {slug} exceeded {MAX_HITL_LOOP} HITL steps. "
                    f"Bypassing HITL at '{current_state}'."
                )
                return {
                    "success": True,
                    "run_slug": slug,
                    "current_state": current_state,
                    "awaiting_input": False,
                    "chain_loop_guard": True,
                    "message": f"Maksimum HITL adımı ({MAX_HITL_LOOP}) aşıldı. Otomatik devam ediliyor.",
                }

            rt = RuntimeState(
                current_state=current_state,
                iteration_count=run.meta.iteration_count,
                user_answers=answers or {},
            )
            questions = sm.get_hitl_questions(current_state, rt)
            if questions:
                state_def = sm.config.states.get(current_state)
                timeout = 300
                if state_def and state_def.hitl:
                    for au in state_def.hitl.ask_user:
                        timeout = max(timeout, au.timeout_seconds)

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

    def resume_run(self, slug: str, answers: dict) -> dict:
        """Resume a paused run with user answers.

        HITL: Kullanıcı cevaplarını al, resume_transitions'a göre
        bir sonraki state'i belirle ve geçiş yap.
        """
        run = self.run_manager.get_run(slug)
        if not run:
            raise ValueError(f"Run '{slug}' not found")

        profile = self._get_profile(run.meta.profile)
        if not profile or not profile.state_machine:
            raise ValueError(f"Profile for run '{slug}' not found or has no state machine")

        sm = profile.state_machine
        current_state = run.meta.state

        if not sm.is_pause_state(current_state):
            return {
                "status": "not_paused",
                "message": f"Run '{slug}' current state '{current_state}' is not a pause state",
            }

        # resume_transitions mapping'ine göre next state belirle
        next_state = sm.evaluate_resume_transition(current_state, answers)

        # Chain-loop guard: HITL sayacını artır (snapshot'tan oku +1)
        snapshot = self.run_manager._load_snapshot()
        current_count = snapshot.get(slug, {}).get('hitl_loop_count', 0)
        self.run_manager._update_snapshot(slug, {
            "hitl_loop_count": current_count + 1,
            "updated_at": datetime.now().isoformat(),
        })

        if not next_state:
            # Mapping yoksa, cevapları kaydet ve agent'a bırak
            self.run_manager._update_snapshot(slug, {
                "user_answers": answers,
                "updated_at": datetime.now().isoformat(),
            })
            return {
                "status": "answers_recorded",
                "message": "Answers recorded. No automatic transition defined.",
                "answers": answers,
            }

        # Hedef state'e geç
        # Akıllı condition override: sadece hedef state'in ihtiyaç duyduğu
        # flag'leri set et (blunt "ikisini de set et" yerine)
        overrides = {}
        sm = profile.state_machine
        transition_defs = sm.config.transitions if hasattr(sm, 'config') else []
        for td in transition_defs:
            if hasattr(td, 'from_state') and td.from_state == current_state and td.to_state == next_state:
                if td.condition:
                    # Transition'ın condition'ında hangi flag varsa onu set et
                    if "human_approved" in td.condition:
                        overrides["human_approved"] = True
                    if "changes_requested" in td.condition:
                        overrides["changes_requested"] = True
                break

        try:
            run = self._do_transition(slug, next_state,
                                      runtime_overrides=overrides if overrides else None)
        except ValueError as e:
            return {"status": "transition_failed", "message": str(e)}

        # Yeni state de pause ise soruları döndür
        if sm.is_pause_state(next_state):
            rt = RuntimeState(
                current_state=next_state,
                iteration_count=run.meta.iteration_count,
            )
            questions = sm.get_hitl_questions(next_state, rt)
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

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _track_entry(self, slug: str, state: str,
                     time: Optional[datetime] = None):
        """Track when a run entered a state"""
        if slug not in self._state_entry_time:
            self._state_entry_time[slug] = {}
        self._state_entry_time[slug][state] = time or datetime.now()

    def _cleanup_state_entries(self):
        """Remove state entry tracking for archived/non-active runs.
        Prevents memory leak from _state_entry_time growing unbounded."""
        active_slugs = {
            r.slug for r in self.run_manager.list_runs(include_archived=False)
        }
        archived = [
            slug for slug in self._state_entry_time
            if slug not in active_slugs
        ]
        for slug in archived:
            del self._state_entry_time[slug]
        if archived:
            self.log.debug(f"Cleaned up state entries for {len(archived)} archived run(s)")

    def _get_event_store(self, slug: str) -> EventStore:
        """Lazy-init EventStore per slug"""
        if slug not in self._event_stores:
            self._event_stores[slug] = EventStore(
                base_path=self.config.data_dir, slug=slug)
        return self._event_stores[slug]

    def _recover(self):
        """WAL recovery on startup"""
        snapshot = self.run_manager.recover()
        active_count = sum(
            1 for v in snapshot.values()
            if v.get("status") == RunStatus.ACTIVE.value
        )
        if active_count:
            self.log.info(f"Recovery: {active_count} active run(s) restored")

    def list_profiles(self) -> List[str]:
        return list(_PROFILE_REGISTRY.keys())

    def get_run(self, slug: str) -> Optional[Run]:
        return self.run_manager.get_run(slug)

    def list_runs(self, include_archived: bool = False) -> List[RunMeta]:
        return self.run_manager.list_runs(include_archived=include_archived)

    @property
    def health_snapshot(self) -> dict:
        """Engine health at a glance"""
        runs = self.run_manager.list_runs()
        return {
            "running": self._running,
            "profiles": self.list_profiles(),
            "degradation": self.degradation.current_level.value,
            "health_score": self.safety.health_score,
            "active_runs": len([r for r in runs if r.status == "active"]),
            "total_runs": len(runs),
            "event_stores": len(self._event_stores),
            "total_cost": round(self.cost_tracker.total_usd, 4),
        }
    
    # ── C3: Warm Agent Methods ─────────────────
    
    def agent_status(self) -> dict:
        """Get Warm Agent Coordinator status"""
        if not self._warm_agent_enabled:
            return {"enabled": False, "message": "Warm Agent is disabled"}
        return {
            "enabled": True,
            "coordinator": self._agent_coordinator.report().to_dict(),
        }
    
    def agent_queue(self) -> dict:
        """List all agent tasks with their status"""
        if not self._warm_agent_enabled:
            return {"enabled": False, "tasks": []}
        tasks = self._agent_coordinator.list_tasks()
        return {
            "enabled": True,
            "tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
        }


# ──────────────────────────────────────────────
# Profile Discovery (lazy import)
# ──────────────────────────────────────────────

_PROFILE_REGISTRY: Dict[str, type] = {}


def _discover_profiles():
    if _PROFILE_REGISTRY:
        return _PROFILE_REGISTRY

    known = {
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
            _PROFILE_REGISTRY[name] = cls
        except (ImportError, AttributeError) as e:
            get_logger().warning(f"Profile '{name}' unavailable: {e}")

    return _PROFILE_REGISTRY


# Initialize on import
_discover_profiles()


# ──────────────────────────────────────────────
# Helper: run engine from CLI
# ──────────────────────────────────────────────

def run_engine(config_path: Optional[str] = None):
    """Synchronous entry point — creates engine, starts, waits for shutdown"""
    from .config import ProdinamikConfig

    cfg = ProdinamikConfig.load(config_path) if config_path else ProdinamikConfig.load()
    engine = AsyncEngine(cfg)

    async def _main():
        await engine.start()
        await engine.wait_for_shutdown()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass

    return engine
