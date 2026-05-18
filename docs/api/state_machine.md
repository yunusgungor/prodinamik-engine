# State Machine Runtime

Prodinamik Engine v1.1 — StateMachine Runtime (Facade)

Formal state machine runtime with compile-time validation, graph algorithms, and runtime transition rules. Backward-compatible — re-exports all types from `sm_types` and `sm_parser` so existing imports continue to work.

**Module:** `engine.state_machine.py` (343 lines)

---

## Overview

`StateMachine` is the primary runtime facade for the state machine ecosystem. It provides:

- **Loading** — accepts a [`StateMachineConfig`](sm_types.md#statemachineconfig) (produced by [`StateMachineParser`](sm_parser.md))
- **Compile-time validation** — seven validation passes checking structural and semantic correctness
- **Graph algorithms** — cycle detection and reachability analysis
- **Runtime operations** — guarded transition checks with LRU caching, condition evaluation, and reentry limit enforcement
- **Inspection** — snapshot serialization and runtime state factory

---

## Class: `StateMachine`

### `__init__(config: StateMachineConfig, lru_size: int = 128)`

Constructs a `StateMachine` from a parsed configuration. Performs automatic compile-time validation — if critical errors are found, `StateMachineValidationError` is raised immediately.

```python
from engine.sm_parser import StateMachineParser
from engine.state_machine import StateMachine

config = StateMachineParser.parse_string(yaml_string)
machine = StateMachine(config)  # validates on construction
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `config` | `StateMachineConfig` | — | Parsed state machine configuration |
| `lru_size` | `int` | `128` | Max entries in the transition LRU cache |

**Raises:** `StateMachineValidationError` — if critical validation errors are found.

**Initialization sequence:**

1. Store config reference
2. Build transition map (`_build_transition_map`) — groups transitions by source state
3. Run full validation (`_validate_or_raise`) — raises on any ERROR-severity issue

---

### Internal Data Structures

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `StateMachineConfig` | The parsed configuration |
| `_transition_map` | `Dict[str, List[TransitionDefinition]]` | Transitions grouped by `from_state` for O(1) lookup |
| `_transition_cache` | `OrderedDict` | LRU cache for `can_transition` and `get_next_states` results |
| `_lru_size` | `int` | Maximum LRU cache entries (default 128) |

---

## Compile-Time Validation

All validation methods return `List[ValidationError]`. The `validate()` method runs all seven passes and is called automatically during `__init__()` via `_validate_or_raise()` (which filters to ERROR-severity issues).

### `validate() -> List[ValidationError]`

Runs all validation passes and returns the combined error list. Warnings are included but do not block construction.

### Validation Passes

#### `_validate_initial_states()`

Every `INITIAL` state must have at least one outgoing transition.

```python
# Error example: Initial state 'idle' has no outgoing transitions
```

#### `_validate_intermediate_states()`

Every `INTERMEDIATE` state must have at least one outgoing transition. (Incoming is implied by reachability — a state with no incoming edges would be caught by reachability validation.)

```python
# Error example: Intermediate state 'working' has no exit transitions
```

#### `_validate_terminal_states()`

Terminal states must have **zero** outgoing transitions and `max_reentries` must be `0`.

```python
# Error examples:
# Terminal state 'done' should have no outgoing transitions
# Terminal state 'done' must have max_reentries=0
```

#### `_validate_cycle_exits()`

Detects **dead-end cycles** — cycles where every transition in every node of the cycle points back into the cycle. A cycle must have at least one edge leading out.

Uses `_find_cycles()` internally, then checks each cycle (length > 1) for exit edges.

```python
# Error example: Dead-end cycle detected: working → review → working.
# All transitions in cycle point back into the cycle.
```

#### `_validate_reachability()`

Uses `_find_reachable_states()` to BFS from all initial states. Any non-initial state that is unreachable is flagged.

```python
# Error example: Unreachable state: 'archived'.
# No path from any initial state.
```

#### `_validate_max_reentries()`

Warns when a non-terminal, non-error state does not have `max_reentries` set. This is a `WARNING` severity — informational rather than blocking.

```python
# Warning example: State 'working' missing max_reentries
```

#### `_validate_transition_targets()`

Ensures every transition's `from_state` and `to_state` reference a state that exists in the state definitions.

```python
# Error examples:
# Transition target 'nonexistent' not found in state definitions
# Transition source 'missing' not found in state definitions
```

---

## Graph Algorithms

### `_find_cycles() -> List[List[str]]`

DFS-based cycle detection that finds all elementary cycles in the state machine graph. Uses canonical cycle representation to avoid duplicates (rotates each cycle to its lexicographically smallest form).

**Returns:** A list of cycles, each cycle being a list of state names.

```python
# Example
machine = StateMachine(config)
cycles = machine._find_cycles()
# [['working', 'review'], ['backlog', 'working', 'review']]
```

### `_find_reachable_states() -> Set[str]`

BFS traversal from all initial states to determine which states are reachable.

**Returns:** A set of reachable state names.

```python
reachable = machine._find_reachable_states()
# {'backlog', 'working', 'review', 'done'}
```

---

## Runtime Operations

### `get_next_states(current_state: str) -> List[str]`

Returns the list of valid target state names from a given state. Results are LRU-cached for performance.

```python
next_states = machine.get_next_states("working")
# ['review', 'backlog']
```

**Caching:** Results are cached under key `"next:{current_state}"`. Cache uses LRU eviction based on `_lru_size`.

### `can_transition(from_state: str, to_state: str, runtime: RuntimeState = None) -> Tuple[bool, str]`

Validates whether a transition is permitted. Returns `(allowed, reason)` tuple.

**Static checks (always performed):**

1. Source state exists in config
2. Target state exists in config
3. Source state is not terminal
4. A matching transition definition exists
5. Transition does not require human approval

**Runtime checks (only when `runtime` is provided):**

6. Reentry limit — if `from_state == to_state` and `reentry_count >= max_reentries`, block
7. Guard condition — evaluates the condition expression against runtime state

```python
from engine.sm_types import RuntimeState

runtime = RuntimeState(current_state="working", reentry_count=2)

allowed, reason = machine.can_transition("working", "review", runtime)
print(allowed, reason)
# (True, "Transition allowed")

allowed, reason = machine.can_transition("working", "working", runtime)
print(allowed, reason)
# (False, "Max reentries (3) exceeded for state 'working'")
```

**LRU Caching:** Static-only calls (without `runtime`) are cached under key `"{from_state}→{to_state}"`. Runtime-inclusive calls bypass caching.

### `_evaluate_condition(condition: str, runtime: RuntimeState) -> bool`

Evaluates a guard condition expression against the current runtime state. Supports the following condition patterns:

| Condition Pattern | Behavior |
|-------------------|----------|
| `"drift_detected"` | Always returns `True` (placeholder) |
| `"iterations >= N"` | `runtime.iteration_count >= N` |
| `"iterations > N"` | `runtime.iteration_count > N` |
| `"iterations < N"` | `runtime.iteration_count < N` |
| `"consecutive_failures"` | Always returns `False` (placeholder) |
| `"prototype_passes(spec)"` | Always returns `True` (placeholder) |
| `"human_approved"` | Always returns `False` (placeholder) |
| `"changes_requested"` | Always returns `False` (placeholder) |
| `"manual_unblock"` | Always returns `False` (placeholder) |
| `"project_abandoned"` | Always returns `False` (placeholder) |
| `"max_iterations..."` | Always returns `False` (placeholder) |
| Unknown condition | Returns `True` (permissive default) |

```python
# Guard condition examples from YAML
# backlog -> working:
#   condition: "iterations >= 3"
```

### `get_transition_type(from_state: str, to_state: str) -> TransitionType`

Returns the `TransitionType` enum for a specific transition edge. If no matching transition is found, returns `TransitionType.REVERSIBLE` as default.

```python
from engine.sm_types import TransitionType

tt = machine.get_transition_type("in_review", "approved")
# TransitionType.IRREVERSIBLE
```

### `create_runtime(initial_state: str = None) -> RuntimeState`

Factory method that creates a `RuntimeState` instance initialized to the first available initial state (or a specified one).

```python
# Auto-select first initial state
runtime = machine.create_runtime()
# RuntimeState(current_state='backlog', ...)

# Specify initial state
runtime = machine.create_runtime("idle")
# RuntimeState(current_state='idle', ...)
```

**Raises:** `ValueError` — if no initial state exists in configuration and none is provided.

### `snapshot() -> dict`

Returns a serializable dictionary snapshot of the entire state machine configuration — useful for inspection, debugging, and API responses.

```python
snap = machine.snapshot()
# {
#     "profile": "software",
#     "name": "dev-workflow",
#     "version": "1.0.0",
#     "states": ["backlog", "working", "review", "done"],
#     "transitions": [
#         "backlog→working (reversible)",
#         "working→review (reversible)",
#         "review→done (irreversible)"
#     ],
#     "ltl_rules": ["G (working → F done)"],
# }
```

### `__repr__() -> str`

Compact representation suitable for logging.

```python
repr(machine)
# "StateMachine(profile=software, name=dev-workflow, states=4, transitions=3)"
```

---

## Usage Examples

### Full lifecycle: parse → validate → inspect

```python
from engine.sm_parser import StateMachineParser
from engine.state_machine import StateMachine

yaml_str = """
profile: software
name: code-review
version: 2.1.0
states:
  draft:
    type: initial
    max_reentries: 3
  in_review:
    type: intermediate
    max_reentries: 5
    timeout: 604800
  approved:
    type: terminal
    max_reentries: 0
  changes_requested:
    type: intermediate
    max_reentries: 10
transitions:
  draft -> in_review
  in_review -> approved:
    type: IRREVERSIBLE
    condition: "review_passed"
  in_review -> changes_requested
  changes_requested -> in_review
temporal_constraints:
  - expression: "G (in_review → F (approved ∨ changes_requested))"
    within: 604800
"""

config = StateMachineParser.parse_string(yaml_str)
machine = StateMachine(config)  # auto-validates

# Inspection
print(machine)
print(f"Has cycles: {len(machine._find_cycles()) > 0}")
print(f"Reachable states: {machine._find_reachable_states()}")

# Runtime checks
runtime = machine.create_runtime("draft")
ok, reason = machine.can_transition("draft", "in_review", runtime)
print(f"Can transition: {ok} — {reason}")

# Get next states
print(f"From 'in_review' go to: {machine.get_next_states('in_review')}")

# Snapshot
import json
print(json.dumps(machine.snapshot(), indent=2))
```

### Manual validation before construction

```python
from engine.state_machine import StateMachine
from engine.sm_types import ValidationError, StateMachineConfig

config = StateMachineParser.parse_string(yaml_str)

# Validate without raising (inspect errors first)
# Create a throwaway machine to validate
try:
    machine = StateMachine(config)
except ... as e:
    # Or validate directly:
    pass

# For validation-only, temporarily suppress auto-validate
errors = []
machine = StateMachine.__new__(StateMachine)
machine.config = config
machine._build_transition_map()
errors = machine.validate()
for e in errors:
    print(f"[{e.severity}] {e.field}: {e.message}")
```

### Runtime loop simulation

```python
from engine.sm_types import RuntimeState
from datetime import datetime, timedelta

def simulate(machine: StateMachine, start: str, steps: int = 5):
    runtime = machine.create_runtime(start)
    print(f"Starting at: {runtime.current_state}")

    for i in range(steps):
        current = runtime.current_state
        next_states = machine.get_next_states(current)

        if not next_states:
            print(f"Reached terminal: {current}")
            break

        # Take first allowed transition
        for target in next_states:
            ok, reason = machine.can_transition(current, target, runtime)
            if ok:
                runtime.current_state = target
                runtime.previous_state = current
                runtime.iteration_count += 1
                runtime.last_transition_at = datetime.now()
                print(f"Step {i+1}: {current} → {target}")
                break
        else:
            print(f"Stuck at {current}")
            break

simulate(machine, "draft", 10)
```

---

## Errors

### `StateMachineValidationError`

Raised during `__init__()` when critical (ERROR-severity) validation issues are found. The exception message lists all errors with field paths.

```
StateMachineValidationError: StateMachine validation failed with 2 error(s):
  • states.draft: Initial state 'draft' has no outgoing transitions
  • states.done: Terminal state 'done' must have max_reentries=0
```

### `TransitionError`

Defined in `sm_types` but not currently raised internally — reserved for future runtime enforcement.

---

## Cross-References

- **Types:** [`sm_types`](sm_types.md) — all enums, dataclasses, and exceptions
- **Parser:** [`sm_parser.StateMachineParser`](sm_parser.md) — produces `StateMachineConfig` from YAML
- **Guide:** [State Machine Guide](../guide/state-machine.md) — conceptual overview and YAML authoring best practices
