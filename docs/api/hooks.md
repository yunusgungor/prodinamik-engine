# Lifecycle Hooks

Prodinamik Engine v1.0 — Lifecycle Hooks

Per-state lifecycle hooks: on_enter, on_exit, on_timeout.
Hooks can be sync or async functions.

**Module:** `engine.hooks.py`

## Classes

### `HookRegistration`

Registration of a lifecycle hook for a specific state

### `HookRegistry`

Central registry for lifecycle hooks.

Hooks are registered per-state and can be sync or async callables.

Usage:
    registry = HookRegistry()
    registry.register("captured", "on_enter", my_handler)
    registry.trigger("captured", "on_enter", run_meta, "captured")

**Methods:**

- `__init__()`
- `register(state, hook_type, handler, description)`
  — Register a hook for a state
- `unregister(state, hook_type, handler)`
  — Remove a specific hook registration
- `clear(state)`
  — Clear hooks for a state or all states
- `async trigger(state, hook_type)`
  — Trigger all hooks for a state+type.
- `trigger_sync(state, hook_type)`
  — Synchronous version of trigger.
- `stats()`
  — Registry statistics
