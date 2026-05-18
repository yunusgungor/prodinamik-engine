"""Prodinamik Engine v1.0 — Lifecycle Hooks

Per-state lifecycle hooks: on_enter, on_exit, on_timeout.
Hooks can be sync or async functions.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any
from .log import get_logger


@dataclass
class HookRegistration:
    """Registration of a lifecycle hook for a specific state"""
    state: str
    hook_type: str  # "on_enter" | "on_exit" | "on_timeout"
    handler: Callable
    description: str = ""


class HookRegistry:
    """
    Central registry for lifecycle hooks.

    Hooks are registered per-state and can be sync or async callables.

    Usage:
        registry = HookRegistry()
        registry.register("captured", "on_enter", my_handler)
        registry.trigger("captured", "on_enter", run_meta, "captured")
    """

    VALID_TYPES = {"on_enter", "on_exit", "on_timeout"}

    def __init__(self):
        # state -> hook_type -> [handler, ...]
        self._hooks: Dict[str, Dict[str, list]] = {}
        self.log = get_logger()

    def register(self, state: str, hook_type: str,
                 handler: Callable, description: str = ""):
        """Register a hook for a state"""
        if hook_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid hook type: {hook_type}. "
                             f"Valid: {self.VALID_TYPES}")

        if state not in self._hooks:
            self._hooks[state] = {t: [] for t in self.VALID_TYPES}
        self._hooks[state][hook_type].append(handler)

        self.log.debug(f"Hook registered: {state}.{hook_type} "
                       f"({description or handler.__name__})")

    def unregister(self, state: str, hook_type: str, handler: Callable):
        """Remove a specific hook registration"""
        if state in self._hooks and hook_type in self._hooks[state]:
            self._hooks[state][hook_type] = [
                h for h in self._hooks[state][hook_type]
                if h is not handler
            ]

    def clear(self, state: Optional[str] = None):
        """Clear hooks for a state or all states"""
        if state:
            self._hooks.pop(state, None)
        else:
            self._hooks.clear()

    async def trigger(self, state: str, hook_type: str, *args, **kwargs):
        """
        Trigger all hooks for a state+type.

        Handles both sync and async handlers.
        Errors in one handler don't affect others.
        """
        if state not in self._hooks:
            return
        handlers = self._hooks[state].get(hook_type, [])
        if not handlers:
            return

        import asyncio
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                self.log.error(f"Hook {state}.{hook_type} "
                               f"({handler.__name__}) failed: {e}")

    def trigger_sync(self, state: str, hook_type: str, *args, **kwargs):
        """
        Synchronous version of trigger.
        Only calls sync handlers (skips async ones to avoid coroutine leaks).
        """
        import asyncio
        if state not in self._hooks:
            return
        handlers = self._hooks[state].get(hook_type, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                continue  # Skip async handlers in sync mode
            try:
                handler(*args, **kwargs)
            except Exception as e:
                self.log.error(f"Hook {state}.{hook_type} "
                               f"({handler.__name__}) failed: {e}")

    @property
    def stats(self) -> dict:
        """Registry statistics"""
        total = 0
        by_type = {t: 0 for t in self.VALID_TYPES}
        for state, hooks in self._hooks.items():
            for htype, handlers in hooks.items():
                count = len(handlers)
                by_type[htype] = by_type.get(htype, 0) + count
                total += count

        return {
            "total_hooks": total,
            "states_with_hooks": len(self._hooks),
            "by_type": by_type,
        }
