# Async Runtime

Prodinamik Engine v1.0 — Async Runtime

Asyncio main loop, component wiring, state timeout watcher,
lifecycle hooks, and graceful shutdown.

**Module:** `engine.runtime.py` (467 lines, 3 classes, 13 functions)

---

## Overview

The `engine.runtime` module is the central nervous system of the Prodinamik
Engine. It wires together all core components — `RunManager`, `CostTracker`,
`DegradationManager`, `BudgetEnforcer`, `EventBus`, and `RuntimeSafetyMonitor`
— into a single async event loop with graceful start/stop semantics.

### Architecture Flow

```
                   ┌─────────────────────────────┐
                   │       AsyncEngine            │
                   │  (main event loop owner)     │
                   └──────┬──────────────────────-┘
                          │ owns / orchestrates
          ┌───────────────┼───────────────────────────┐
          │               │                           │
     ┌────▼────┐   ┌─────▼─────┐              ┌──────▼─────┐
     │RunManager│   │CostTracker│              │Degradation │
     │          │   │ + Budget  │              │Manager     │
     └──────────┘   └───────────┘              └────────────┘
          │                                       │
     ┌────▼────┐                           ┌──────▼─────┐
     │EventStore│                          │SafetyMonitor│
     └──────────┘                          └────────────┘
          │                                       │
     ┌────▼────┐                           ┌──────▼─────┐
     │EventBus  │◄──────────────────────────│Health Check│
     └──────────┘                           └────────────┘
```

Background tasks spawned at `start()`:
- **Timeout Watcher** — polls active runs for state timeouts
- **Health Checker** — evaluates degradation + safety invariants

---

## Classes

### `RuntimeConfig`

Async runtime configuration dataclass.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `poll_interval` | `float` | `5.0` | Timeout check interval in seconds. Controls how frequently the timeout watcher examines active runs for state timeouts. |
| `health_check_interval` | `float` | `60.0` | Health check interval in seconds. Controls how frequently the health checker evaluates degradation and safety invariants. |
| `max_shutdown_wait` | `float` | `10.0` | Maximum wait time in seconds for graceful shutdown of all background tasks. |
| `auto_recover` | `bool` | `True` | When `True`, the engine automatically transitions from `DEGRADED` back to `FULL` once degradation conditions clear. |
| `enable_timeout_watcher` | `bool` | `True` | Enables or disables the background timeout watcher task entirely. |

**Usage:**

```python
from engine.runtime import RuntimeConfig

config = RuntimeConfig(
    poll_interval=2.0,          # Check timeouts every 2 seconds
    health_check_interval=30.0, # Health check every 30 seconds
    auto_recover=False,         # Manual recovery only
)
```

---

### `LifecycleHooks`

Per-state lifecycle hooks. Each field is an optional async callable
fired at specific state machine transitions.

**Fields:**

| Field | Signature | Description |
|-------|-----------|-------------|
| `on_enter` | `async (run_meta, state) -> None` | Called when a run enters this state. Receives the `RunMeta` and the state name string. |
| `on_exit` | `async (run_meta, from_state, to_state) -> None` | Called when a run exits this state. Receives the `RunMeta`, the previous state, and the upcoming state. |
| `on_timeout` | `async (run_meta, state) -> None` | Called when a run has been in this state longer than `timeout_seconds` allows. Receives the `RunMeta` and the timed-out state name. |

**Note:** These hooks are the high-level per-state hooks passed into
`AsyncEngine`. The actual dispatching mechanism lives in `engine.hooks.py`
via `HookRegistry`. The `LifecycleHooks` dataclass provides a structured
way to define hooks for a specific state definition.

**Usage:**

```python
from engine.runtime import LifecycleHooks

hooks = LifecycleHooks(
    on_enter=my_enter_handler,
    on_timeout=my_timeout_handler,
)
```

---

### `AsyncEngine`

The main async runtime class. Owns and wires all components into a
coherent event loop with background task management, signal handling,
WAL recovery, and graceful shutdown.

**Constructor:**

```python
AsyncEngine(config: ProdinamikConfig,
            runtime_config: Optional[RuntimeConfig] = None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `ProdinamikConfig` | Global engine configuration loaded from `prodinamik.yaml`. Provides data directory, budget limits, and profile settings. |
| `runtime_config` | `Optional[RuntimeConfig]` | Override default runtime settings (poll interval, health check, auto-recovery). Defaults to `RuntimeConfig()` if not provided. |

**Internal State:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `_running` | `bool` | Engine running state flag. Set `True` by `start()`, `False` by `stop()`. |
| `_tasks` | `List[asyncio.Task]` | Background asyncio tasks (timeout watcher, health checker). Canceled on shutdown. |
| `_shutdown_event` | `asyncio.Event` | Fired when shutdown completes. `wait_for_shutdown()` blocks on this. |
| `_state_entry_time` | `Dict[str, Dict[str, datetime]]` | Tracks when each run entered its current state, keyed by `slug → state → datetime`. Used by the timeout watcher. |
| `_event_stores` | `Dict[str, EventStore]` | Lazy-initialized per-slug event stores for cost-aware event recording. |
| `_profile_cache` | `Dict[str, ProductProfile]` | Lazy-initialized and cached product profiles. Populated on first `_get_profile()` call. |

#### Methods

##### Lifecycle Methods

**`async start()`**

Start the async runtime. This method:
1. Sets the `_running` flag to `True`
2. Registers `SIGINT` and `SIGTERM` signal handlers (non-Windows only) that initiate graceful shutdown
3. Spawns the background timeout watcher task (if `enable_timeout_watcher` is `True`)
4. Spawns the background health checker task
5. Runs WAL recovery via `_recover()` — replays Write-Ahead Log entries to restore active runs
6. Logs the final engine state: number of cached profiles and active runs

**`async stop(signum: Optional[int] = None)`**

Graceful shutdown. This method:
1. Sets `_running` to `False`
2. Cancels all background asyncio tasks and awaits their completion (with `return_exceptions=True`)
3. Compacts the WAL into a snapshot via `run_manager._compact_wal()`
4. Sets the `_shutdown_event` to signal any waiters

| Parameter | Type | Description |
|-----------|------|-------------|
| `signum` | `Optional[int]` | Signal number (e.g., `signal.SIGINT`) for logging purposes. `None` indicates manual shutdown. |

**`async wait_for_shutdown()`**

Block indefinitely (or until the `_shutdown_event` is set). Intended for
the main coroutine in a `run_engine()` style entry point.

##### Background Tasks

**`async _timeout_watcher()`**

Internal background task. Runs an infinite loop that:
1. Sleeps for `rt_config.poll_interval` seconds
2. Calls `_check_timeouts()` to examine all active runs
3. Handles `asyncio.CancelledError` cleanly on shutdown
4. Catches and logs any unexpected exceptions to prevent the task from dying silently

**`async _check_timeouts()`**

Examines all runs returned by `run_manager.list_runs()` that have
`status == "active"`. For each active run:

1. Loads the associated product profile (from cache or `_PROFILE_REGISTRY`)
2. Looks up the current state definition in the profile's state machine
3. If the state has a `timeout_seconds` defined, compares elapsed time
4. Elapsed time is computed from `_state_entry_time` tracking, falling back
   to `meta.updated_at` if no explicit entry time is recorded
5. If elapsed > `timeout_seconds`:
   - Logs a warning with slug, state, elapsed, and limit
   - Triggers the `on_timeout` hook synchronously via `hooks.trigger_sync()`
   - If `state_def.temporal_on_timeout` is defined, auto-transitions the
     run to the timeout fallback state

**`async _health_checker()`**

Internal background task. Runs an infinite loop that:
1. Sleeps for `rt_config.health_check_interval` seconds
2. Collects engine state metrics (LLM failures, budget hard limit)
3. Calls `degradation.evaluate(engine_state)` to evaluate degradation level
4. If `auto_recover` is enabled and the system moved from `DEGRADED` to `FULL`,
   logs the recovery event
5. Calls `safety.check_all(bus=..., degradation=...)` to evaluate all
   10 runtime safety invariants
6. Logs any invariant violations (up to 3 in debug level)
7. Handles `CancelledError` and unexpected exceptions gracefully

##### Run Operations

**`_get_profile(name: str) -> Optional[ProductProfile]`**

Get a cached and initialized product profile by name.

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Profile name (e.g., `"content"`, `"software"`, `"research"`, `"design"`) |

Returns `None` if the profile name is not found in `_PROFILE_REGISTRY`.
On first access, the profile class is instantiated and `profile.initialize()`
is called, then cached for subsequent calls.

**`create_run(profile_name: str, title: str, slug: Optional[str] = None) -> Run`**

Synchronous fast-path run creation. This method:

1. Resolves the product profile via `_get_profile()`
2. Delegates to `run_manager.create_run()` to persist the run
3. Appends a `CostAwareEvent` to the per-slug `EventStore`
4. Tracks the entry time for the initial state
5. Triggers the synchronous `on_enter` hook

| Parameter | Type | Description |
|-----------|------|-------------|
| `profile_name` | `str` | Name of the profile to use |
| `title` | `str` | Human-readable title for this run |
| `slug` | `Optional[str]` | Optional unique slug. Auto-generated if `None`. |

Raises `ValueError` if the profile name is not registered.

**`async create_run_async(profile_name: str, title: str, slug: Optional[str] = None) -> Run`**

Async variant of `create_run()`. Calls `create_run()` synchronously first
(which fires sync hooks), then additionally fires async hooks via
`hooks.trigger()`.

**`_do_transition(slug: str, to_state: str) -> Run`**

Internal method that performs a complete state transition with full wiring:

1. Loads the run via `run_manager.get_run()`
2. Resolves the product profile
3. Fires the synchronous `on_exit` hook on the current state
4. Delegates to `run_manager.update_state()` for persistence
5. Appends a `CostAwareEvent` to the per-slug `EventStore`
6. Tracks entry time for the new state
7. Fires the synchronous `on_enter` hook on the new state

| Parameter | Type | Description |
|-----------|------|-------------|
| `slug` | `str` | Unique run slug |
| `to_state` | `str` | Target state name |

Raises `ValueError` if the run or profile is not found.

**`async transition_async(slug: str, to_state: str) -> Run`**

Async wrapper around `_do_transition()`. Currently handles all hooks
(sync and async) internally via `_do_transition()`.

##### Helpers

**`_track_entry(slug: str, state: str, time: Optional[datetime] = None)`**

Records the timestamp when a run entered a particular state. Used by
the timeout watcher to compute elapsed time.

| Parameter | Type | Description |
|-----------|------|-------------|
| `slug` | `str` | Run slug |
| `state` | `str` | State name |
| `time` | `Optional[datetime]` | Entry timestamp. Defaults to `datetime.now()` if not provided. |

**`_get_event_store(slug: str) -> EventStore`**

Lazy-initializes and returns an `EventStore` for the given run slug.
The event store persists cost-aware events to disk under
`config.data_dir / slug / "events"`.

**`_recover()`**

WAL recovery called on startup. Delegates to `run_manager.recover()`
to replay the Write-Ahead Log and restore any active runs that were
persisted during the last engine session. Logs the number of
recovered active runs.

**`list_profiles() -> List[str]`**

Returns a list of all registered profile names from `_PROFILE_REGISTRY`.

**`get_run(slug: str) -> Optional[Run]`**

Retrieve a run by slug. Delegates to `run_manager.get_run()`.

**`list_runs(include_archived: bool = False) -> List[RunMeta]`**

List all runs, optionally including archived ones.

| Parameter | Type | Description |
|-----------|------|-------------|
| `include_archived` | `bool` | If `True`, archived runs are included in results. |

**`health_snapshot` (property)**

Returns a dictionary with the engine's current health status:

| Key | Type | Description |
|-----|------|-------------|
| `running` | `bool` | Engine running state |
| `profiles` | `List[str]` | Registered profile names |
| `degradation` | `str` | Current degradation level (`full`, `degraded`, `survival`) |
| `health_score` | `float` | Safety monitor health score (0.0–1.0) |
| `active_runs` | `int` | Count of currently active runs |
| `total_runs` | `int` | Total run count including inactive |
| `event_stores` | `int` | Number of lazy-initialized event stores |
| `total_cost` | `float` | Total accumulated cost in USD (rounded to 4 decimal places) |

---

### Profile Discovery

**`_PROFILE_REGISTRY: Dict[str, type]`**

Module-level dictionary mapping profile names to their class types.
Populated by `_discover_profiles()` on module import.

**Known profiles:**

| Name | Module Path | Class |
|------|-------------|-------|
| `content` | `profiles.content` | `ContentProfile` |
| `software` | `profiles.software` | `SoftwareProfile` |
| `research` | `profiles.research` | `ResearchProfile` |
| `design` | `profiles.design` | `DesignProfile` |

**`_discover_profiles() -> Dict[str, type]`**

Lazy-imports each known profile class using `importlib.import_module()`.
Gracefully handles `ImportError` / `AttributeError` — if a profile
module is unavailable, it logs a warning and skips it. Returns the
populated `_PROFILE_REGISTRY` dict.

**Note:** `_discover_profiles()` is called once automatically at module
import time, so profiles are available immediately when `AsyncEngine`
is instantiated.

---

## Functions

### `run_engine(config_path: Optional[str] = None)`

Synchronous entry point for running the engine from the CLI or REPL.

**Flow:**

1. Loads `ProdinamikConfig` — either from a custom path or from the
   default location (`prodinamik.yaml` in the current directory)
2. Creates an `AsyncEngine` instance with the loaded config
3. Starts the engine via `engine.start()` (registers signals, spawns
   background tasks, runs WAL recovery)
4. Blocks on `engine.wait_for_shutdown()` until SIGINT or SIGTERM
   is received
5. Handles `KeyboardInterrupt` gracefully
6. Returns the stopped engine instance for inspection

| Parameter | Type | Description |
|-----------|------|-------------|
| `config_path` | `Optional[str]` | Path to a custom `prodinamik.yaml` config file. `None` uses default discovery. |

**Usage:**

```python
from engine.runtime import run_engine

engine = run_engine("config/prodinamik.yaml")
print(f"Engine ran with {engine.health_snapshot['total_cost']} cost")
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Profile not found | `create_run()` raises `ValueError` with available profile list |
| Run not found | `_do_transition()` raises `ValueError` |
| Signal registration fails (Windows) | Logged at DEBUG level, signals skipped |
| Timeout watcher exception | Logged at ERROR level, task continues |
| Health checker exception | Logged at ERROR level, task continues |
| WAL recovery active runs | Logged at INFO level with count |
| Keyboard interrupt in `run_engine()` | Caught and suppressed gracefully |

---

## Thread Safety

The `AsyncEngine` is designed for single-threaded asyncio usage. All
background tasks are asyncio tasks within the same event loop. The
`_state_entry_time` and `_event_stores` dictionaries are accessed
only from the main event loop thread.
