# Async Runtime

Prodinamik Engine v1.0 — Async Runtime

Asyncio main loop, component wiring, state timeout watcher,
lifecycle hooks, and graceful shutdown.

**Module:** `engine.runtime.py`

## Classes

### `RuntimeConfig`

Async runtime configuration

### `LifecycleHooks`

Per-state lifecycle hooks. Each is optional.

### `AsyncEngine`

Async runtime that wires all components together.

- Main event loop (asyncio)
- State timeout watcher (background task)
- Health checker (background task)
- Lifecycle hooks (per-state)
- Graceful shutdown (signal handler)

**Methods:**

- `__init__(config, runtime_config)`
- `async start()`
  — Start the async runtime
- `async stop(signum)`
  — Graceful shutdown
- `async wait_for_shutdown()`
  — Block until shutdown signal received
- `async _timeout_watcher()`
  — Background task: periodically checks all active runs
- `async _check_timeouts()`
  — Check all active runs for state timeouts
- `async _health_checker()`
  — Background task: periodic health checks via DegradationManager + Safety.
- `_get_profile(name)`
  — Get (cached) initialized profile
- `create_run(profile_name, title, slug)`
  — Create a new run (synchronous — fast path)
- `async create_run_async(profile_name, title, slug)`
  — Create run with async hook support
- `_do_transition(slug, to_state)`
  — Internal: perform state transition with full wiring
- `async transition_async(slug, to_state)`
  — Transition with async hook support
- `_track_entry(slug, state, time)`
  — Track when a run entered a state
- `_get_event_store(slug)`
  — Lazy-init EventStore per slug
- `_recover()`
  — WAL recovery on startup
- `list_profiles()`
- `get_run(slug)`
- `list_runs(include_archived)`
- `health_snapshot()`
  — Engine health at a glance

## Functions

### `run_engine(config_path)`

Synchronous entry point — creates engine, starts, waits for shutdown
