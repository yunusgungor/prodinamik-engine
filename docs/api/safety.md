# Safety Monitor

Prodinamik Engine v0.5 — Event Bus + Runtime Safety Invariants

Event Bus (Review #4):
- Trace ID + max hop count (5 hops)
- Duplicate detection
- Cross-profile cycle safety

Runtime Safety Invariants (Review #8):
- 10 runtime invariants across 5 categories
- Automatic action on each invariant violation
- Health report with score 0.0–1.0

**Module:** `engine.safety.py` (502 lines, 4 classes, 18 functions)

---

## Overview

The `engine.safety` module provides two complementary safety subsystems:

1. **Event Bus (`EventBus`)** — A cross-profile pub/sub message bus with
   cycle detection via trace IDs, hop counting, and duplicate suppression.
   Designed for safe event propagation across product profiles without
   infinite loops or message storms.

2. **Runtime Safety Monitor (`RuntimeSafetyMonitor`)** — A comprehensive
   invariant checking engine that continuously validates 10 runtime safety
   invariants across 5 categories. Each invariant has a defined severity
   (WARNING, CRITICAL, FATAL) and an automatic action that fires on
   violation (pause run, block transition, degrade to survival, compact
   event store, notify user, escalate to human, or reset the event bus).

### Architecture

```
                    ┌─────────────────────────────────┐
                    │      RuntimeSafetyMonitor        │
                    │  (10 invariants, action matrix)  │
                    └──┬──────────────────────────────-┘
                       │ check_all() triggers actions
          ┌────────────┼────────────────┬───────────────┐
          │            │                │               │
     ┌────▼────┐  ┌────▼────┐    ┌─────▼──────┐  ┌─────▼─────┐
     │EventBus  │  │State    │    │EventStore  │  │Degradation│
     │(cycle    │  │Machine  │    │(compact,   │  │Manager    │
     │ safety)  │  │(valid   │    │ orphan     │  │(level     │
     └──────────┘  │trans.)  │    │ check)     │  │ check)    │
                   └─────────┘    └────────────┘  └───────────┘
```

---

## Classes

### `BusEvent`

Represents a single event on the cross-profile event bus.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | *required* | Event type string (e.g., `"release.published"`, `"run.completed"`) |
| `source_profile` | `str` | *required* | Name of the originating profile (e.g., `"software"`, `"content"`) |
| `source_slug` | `str` | *required* | Slug of the originating run or entity |
| `data` | `dict` | `{}` | Arbitrary event payload (version numbers, metadata, etc.) |
| `timestamp` | `str` | `""` | ISO-8601 timestamp. Auto-populated in `__post_init__` if empty. |
| `trace_id` | `str` | `""` | UUIDv4 trace identifier for cycle tracking. Auto-generated if empty. |
| `hop_count` | `int` | `0` | Number of profile-to-profile hops this event has traversed. |
| `cost_usd` | `float` | `0.0` | Estimated cost in USD associated with this event. |

**`__post_init__()`**

Called automatically after initialization. Fills in `timestamp` with
`datetime.now().isoformat()` and `trace_id` with `str(uuid.uuid4())`
if they were left empty.

---

### `EventBus`

Cross-profile event bus with cycle safety through trace tracking,
hop counting, and duplicate detection.

**Constants:**

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_HOPS` | `5` | Maximum number of sequential profile hops before an event is silently dropped. |

**Constructor:**

```python
EventBus()
```

**Internal State:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `subscribers` | `Dict[str, List[Callable]]` | Maps event type strings to lists of handler callables. Uses `defaultdict(list)`. |
| `cycle_warnings` | `List[dict]` | Accumulated cycle/hop/duplicate/error warnings for diagnostics. |
| `_seen_traces` | `Set[str]` | Set of `"{trace_id}:{event_type}"` strings for duplicate detection. |

#### Methods

**`subscribe(event_type: str, handler: Callable)`**

Subscribe a handler function to a specific event type. Handlers can be
sync or async callables. The handler receives a single `BusEvent`
argument.

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | `str` | Event type to subscribe to (e.g., `"release.published"`) |
| `handler` | `Callable` | Async or sync function accepting `(BusEvent) -> None` |

**`unsubscribe(event_type: str, handler: Callable)`**

Remove a previously registered handler from an event type.

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | `str` | Event type to unsubscribe from |
| `handler` | `Callable` | The exact handler function previously registered |

**`emit(event: BusEvent)`**

Publish an event to all subscribed handlers. The emission process:

1. **Hop count check** — If `event.hop_count >= MAX_HOPS`, the event
   is logged as a cycle warning and silently dropped. This prevents
   infinite cross-profile loops.

2. **Duplicate detection** — A composite key `"{trace_id}:{type}"` is
   checked against `_seen_traces`. If already seen, the event is logged
   as a duplicate warning and dropped. Otherwise, the key is added to
   the set.

3. **Subscriber dispatch** — Each matching handler is called via
   `_safe_call()`, which wraps execution in `asyncio.create_task()`
   for async handlers, ensuring non-blocking delivery.

| Parameter | Type | Description |
|-----------|------|-------------|
| `event` | `BusEvent` | The event to publish |

**`async _safe_call(handler: Callable, event: BusEvent)`**

Safely invoke a subscriber handler. Detects whether the handler is a
coroutine function (`asyncio.iscoroutinefunction`) and awaits it if so.
Catches all exceptions and logs them as cycle warnings with the
handler name and error message.

| Parameter | Type | Description |
|-----------|------|-------------|
| `handler` | `Callable` | The subscriber's handler function |
| `event` | `BusEvent` | The event to pass to the handler |

**`clear_traces()`**

Periodic cleanup method. Clears the `_seen_traces` set to prevent
unbounded memory growth from accumulated trace IDs. Safe to call
after any checkpoint or compaction cycle.

**`has_cycles` (property) -> `bool`**

Returns `True` if any cycle warnings (hop limit, duplicate, or handler
error) have been recorded since the last `clear_traces()`. Used by the
`cross_profile_no_cycle` invariant in `RuntimeSafetyMonitor`.

**`stats` (property) -> `dict`**

Returns a diagnostic snapshot:

```python
{
    "subscribers": {"release.published": 2, "run.completed": 1},
    "total_subscribers": 3,
    "cycle_warnings": 0,
    "seen_traces": 42,
}
```

---

### `InvariantViolation`

Dataclass representing a single runtime invariant violation.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Invariant name (e.g., `"state_exists"`, `"budget_respected"`) |
| `category` | `str` | Category: `"state_machine"`, `"progress"`, `"resources"`, `"data_integrity"`, `"drift"`, `"safety"`, or `"system"` |
| `severity` | `str` | Severity level: `"WARNING"`, `"CRITICAL"`, or `"FATAL"` |
| `message` | `str` | Human-readable description of the violation |
| `timestamp` | `str` | ISO-8601 timestamp of when the violation was detected |
| `resolved` | `bool` | `False` by default; set to `True` by `resolve_violation()` |
| `resolved_at` | `Optional[str]` | ISO-8601 timestamp of when the violation was resolved, or `None` |

---

### `RuntimeSafetyMonitor`

Continuously evaluates 10 runtime safety invariants across 5 categories
every health check cycle. Each invariant has a defined check function,
severity, and automatic action.

#### Invariant Definitions (`INVARIANTS`)

| Name | Category | Severity | Action | Check |
|------|----------|----------|--------|-------|
| `state_exists` | `state_machine` | CRITICAL | `pause` | Target state exists in `state_machine.all_states` |
| `valid_transition` | `state_machine` | CRITICAL | `pause` | Target state is in `transitions[from_state]` |
| `no_state_leak` | `state_machine` | CRITICAL | `pause` | All `current_states` are in `all_states` |
| `monotonic_progress` | `progress` | CRITICAL | `block` | `iteration_count <= max_iterations` |
| `budget_respected` | `resources` | FATAL | `degrade_survival` | `total_usd <= hard_limit` |
| `event_count_reasonable` | `resources` | WARNING | `compact` | `event_count < 10000` |
| `no_orphan_events` | `data_integrity` | WARNING | `compact` | All indexed events are retrievable |
| `cache_fresh` | `data_integrity` | WARNING | `notify` | Cache hit rate > 30% when at FULL degradation |
| `drift_not_exploding` | `drift` | CRITICAL | `escalate` | `drift.instant_rate < 0.9` |
| `cross_profile_no_cycle` | `safety` | FATAL | `bus_reset` | Event bus has no cycles |

#### Action Matrix (`ACTIONS`)

| Action | Icon | Description |
|--------|------|-------------|
| `pause` | ⏸️ | Pause the affected run |
| `block` | 🚫 | Block the pending state transition |
| `degrade_survival` | 🆘 | Degrade engine to SURVIVAL mode |
| `compact` | 🧹 | Compact the event store |
| `notify` | 🔔 | Notify the user |
| `escalate` | 📢 | Escalate to a human operator |
| `bus_reset` | 🔄 | Reset the event bus trace set |

#### Constructor

```python
RuntimeSafetyMonitor(event_bus: Optional[EventBus] = None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_bus` | `Optional[EventBus]` | Reference to the global event bus, used as fallback for `cross_profile_no_cycle` check. |

#### Methods

**`check_all(state_machine=None, run=None, store=None, cache=None, bus=None, degradation=None) -> List[InvariantViolation]`**

Evaluate all 10 invariants against the provided context objects. For
each invariant:

1. The check function is introspected via `inspect.signature` to
   determine which context parameters it needs
2. Matching parameters from the context dict (`sm`, `run`, `store`,
   `cache`, `bus`, `deg`) are passed to the lambda
3. If the check returns `False`, an `InvariantViolation` is created
   with the invariant's category, severity, and current timestamp
4. The automatic action is triggered via `_take_action()`
5. If the check itself raises an exception, it's caught and recorded
   as a `"system"` category violation with `"CRITICAL"` severity

Returns the list of newly detected violations.

**`_call_with_context(check_fn, context, name) -> bool`**

Introspects the check function's signature and dynamically builds
keyword arguments from the context dict. This allows each invariant's
lambda to declare only the parameters it actually uses while ignoring
the rest.

| Parameter | Type | Description |
|-----------|------|-------------|
| `check_fn` | `Callable` | The invariant check lambda |
| `context` | `dict` | Context dict with keys `sm`, `run`, `store`, `cache`, `bus`, `deg` |
| `name` | `str` | Invariant name (for error messages) |

**`_take_action(action: str, invariant_name: str, context: dict)`**

Executes the automatic action associated with a violated invariant.
Currently implemented actions:

- `"compact"` — spawns `_async_compact(store)` as an asyncio task
- `"bus_reset"` — calls `context["bus"].clear_traces()`
- Other actions (`pause`, `block`, `degrade_survival`, `notify`,
  `escalate`) are documented action targets for external handling
  but do not have automated implementations in this module

| Parameter | Type | Description |
|-----------|------|-------------|
| `action` | `str` | Action key from `ACTIONS` dict |
| `invariant_name` | `str` | Name of the violating invariant |
| `context` | `dict` | Context dict with references to store, bus, etc. |

**`async _async_compact(store)`**

Fire-and-forget async task that calls `store.compact()`. Wrapped in
a try/except to silently swallow any compaction errors.

| Parameter | Type | Description |
|-----------|------|-------------|
| `store` | `EventStore` | The event store to compact |

**`resolve_violation(name: str)`**

Mark a specific violation as resolved by setting `resolved = True`
and `resolved_at` to the current ISO-8601 timestamp.

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Invariant name to resolve. Only the first unresolved match is updated. |

**`active_violations` (property) -> `List[InvariantViolation]`**

Returns a filtered list of all unresolved violations (`resolved == False`).

**`health_score` (property) -> `float`**

Calculates a health score between 0.0 (critical) and 1.0 (perfect):

- Any active FATAL violation → score is immediately 0.0
- Each active CRITICAL violation → subtract 0.3
- Each active WARNING violation → subtract 0.1
- Score is clamped to a minimum of 0.0

**`health_report()` -> `str`**

Generates a formatted health report string for user-facing display.
The report includes:

- Score with emoji indicator (✅ ≥ 0.8, ⚠️ ≥ 0.3, 🆘 < 0.3)
- Count of active violations and total checks performed
- Up to 5 most recent violations with severity icon, name, category,
  and the resulting action description
- Category summary showing violation counts by category

The report uses a monospace-friendly format suitable for both
terminal output and markdown rendering.

---

## Functions

### `async async_demo()`

Interactive demo that exercises both the Event Bus and Runtime Safety
Monitor subsystems:

1. Creates an `EventBus` instance
2. Subscribes an async handler to `"release.published"`
3. Emits a valid event and prints the handler confirmation
4. Emits a duplicate event (same trace_id + type) and confirms it is
   silently dropped
5. Emits an event with `hop_count >= MAX_HOPS` and confirms cycle
   detection
6. Prints bus statistics
7. Creates a `RuntimeSafetyMonitor` wired to the bus
8. Runs `check_all()` and prints the health report
9. Prints active violations count and health score

**Usage:**

```python
from engine.safety import async_demo
import asyncio
asyncio.run(async_demo())
```

### `demo()`

Synchronous wrapper around `async_demo()`. Calls `asyncio.run()` to
execute the async demo. Intended for quick REPL or test usage.

**Usage:**

```python
from engine.safety import demo
demo()
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Handler raises exception in `emit()` | Caught by `_safe_call()`, logged as cycle warning with error message |
| Invariant check function itself fails | Caught by `check_all()`, recorded as CRITICAL system violation |
| Event store compaction failure | Silently caught in `_async_compact()` |
| Event with 5+ hops | Silently dropped, cycle warning appended |
| Duplicate event (same trace_id + type) | Silently dropped, cycle warning appended |

---

## Thread Safety

The `EventBus.emit()` method schedules async handler execution via
`asyncio.create_task()`, making it safe for single-threaded asyncio
usage. The `_seen_traces` set and `cycle_warnings` list are accessed
only from the event loop thread. The `clear_traces()` method should
be called from the same event loop.

The `RuntimeSafetyMonitor` is fully synchronous (except optional
async compaction) and is designed to be called from the health
checker background task which runs on the same asyncio event loop.
