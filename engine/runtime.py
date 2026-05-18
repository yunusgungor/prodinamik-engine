"""Prodinamik Engine v1.0 — Async Runtime

Asyncio main loop, component wiring, state timeout watcher,
lifecycle hooks, and graceful shutdown.
"""

import asyncio
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

        # Profile registry (lazy)
        self._profile_cache: Dict[str, ProductProfile] = {}

        # Hooks registry: state_name → HookRegistry
        self.hooks = HookRegistry()

        # Track visited states per slug for timeout calculation
        self._state_entry_time: Dict[str, Dict[str, datetime]] = {}

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

                # Auto-transition to error state if defined
                if state_def.temporal_on_timeout:
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

    def _do_transition(self, slug: str, to_state: str) -> Run:
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

        # Do transition
        run = self.run_manager.update_state(slug, to_state, profile)

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

        return run

    async def transition_async(self, slug: str, to_state: str) -> Run:
        """Transition with async hook support"""
        # _do_transition handles all sync hooks internally
        run = self._do_transition(slug, to_state)
        return run

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
