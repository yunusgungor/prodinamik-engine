# State Machine Types

Prodinamik Engine v1.1 — StateMachine Data Types

All type definitions, enums, dataclasses, and exceptions extracted from `state_machine.py` for modularity.

**Module:** `engine.sm_types.py` (139 lines)

---

## Overview

The `sm_types` module defines the core data model for the state machine ecosystem. It provides:

- **Enums** — `TransitionType` and `StateType` for classifying states and transitions
- **Dataclasses** — `StateDefinition`, `TransitionDefinition`, `LTLRule`, `StateMachineConfig`, `ValidationError`, `RuntimeState`
- **Exceptions** — `StateMachineValidationError` (compile-time) and `TransitionError` (runtime)
- **Helper properties** — `initial_states()`, `terminal_states()`, `intermediate_states()` on `StateMachineConfig`

These types are consumed by [`StateMachineParser`](sm_parser.md) (which produces a `StateMachineConfig`) and the [`StateMachine`](state_machine.md) runtime facade (which operates on that config).

---

## Enums

### `TransitionType`

Classification of transitions based on reversibility semantics.

| Member | Value | Description |
|--------|-------|-------------|
| `REVERSIBLE` | `"reversible"` | Transition can be reversed; the system can return to the previous state |
| `COMPENSABLE` | `"compensable"` | Not directly reversible, but a compensating action can undo the effects |
| `IRREVERSIBLE` | `"irreversible"` | Permanent — once taken, the system cannot return |

Used in `TransitionDefinition.transition_type` and in runtime checks via `StateMachine.get_transition_type()`.

### `StateType`

Classification of states within the state machine lifecycle.

| Member | Value | Description |
|--------|-------|-------------|
| `INITIAL` | `"initial"` | Entry point(s) of the machine; must have at least one outgoing transition |
| `INTERMEDIATE` | `"intermediate"` | Mid-lifecycle states; must have both incoming and outgoing transitions |
| `TERMINAL` | `"terminal"` | End state; must have `max_reentries=0` and zero outgoing transitions |
| `ERROR` | `"error"` | Error / exception state; special handling in validation |

---

## Dataclasses

### `StateDefinition`

Formal definition of a single state in the state machine.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Unique state identifier |
| `state_type` | `StateType` | — | Classification (initial, intermediate, terminal, error) |
| `max_reentries` | `Optional[int]` | `None` | Maximum times the state can be re-entered; `0` for terminal, `<=1` for initial |
| `timeout_seconds` | `Optional[int]` | `None` | Max time allowed in this state before forced transition |
| `entry_hooks` | `List[str]` | `[]` | Hook names executed on state entry |
| `exit_hooks` | `List[str]` | `[]` | Hook names executed on state exit |
| `validators` | `List[str]` | `[]` | Validator names that check state constraints |
| `temporal_max_duration` | `Optional[int]` | `None` | LTL-bounded max duration in this state (seconds) |
| `temporal_on_timeout` | `Optional[str]` | `None` | Target state to transition to on temporal timeout |
| `reminders` | `List[dict]` | `[]` | Reminder definitions (message + delay pairs) |
| `requires_manual` | `bool` | `False` | Whether the state requires manual/human intervention to leave |

**Post-init validation (`__post_init__`):**

- If `state_type` is `TERMINAL` and `max_reentries` is set, it must be `0`.
- If `state_type` is `INITIAL` and `max_reentries` is set, it must be `<= 1`.

### `TransitionDefinition`

Formal definition of a transition between two states.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `from_state` | `str` | — | Source state name |
| `to_state` | `str` | — | Target state name |
| `transition_type` | `TransitionType` | `REVERSIBLE` | Reversibility classification |
| `condition` | `Optional[str]` | `None` | Guard condition expression (e.g. `"iterations >= 5"`, `"drift_detected"`) |
| `action` | `Optional[str]` | `None` | Action name executed during transition |
| `requires_human` | `bool` | `False` | Whether human approval is mandatory |

### `LTLRule`

A Linear Temporal Logic constraint on the state machine.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `expression` | `str` | — | LTL formula string (e.g. `"G (working → F done)"`) |
| `within_seconds` | `Optional[int]` | `None` | Time bound for the constraint |

LTL rules are parsed from the `temporal_constraints` section of the YAML definition and enforced conceptually via temporal duration checks on states.

### `StateMachineConfig`

Complete configuration container produced by YAML parsing and consumed by the `StateMachine` runtime. This is the central data transfer object for the state machine ecosystem.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `profile` | `str` | — | Profile identifier (e.g. `"software"`, `"content"`) |
| `name` | `str` | — | Machine name for identification |
| `version` | `str` | — | Semantic version string |
| `states` | `Dict[str, StateDefinition]` | — | All state definitions, keyed by name |
| `transitions` | `List[TransitionDefinition]` | — | All transition definitions |
| `ltl_rules` | `List[LTLRule]` | — | Temporal logic constraints |
| `max_steps` | `int` | `100` | Maximum execution steps before forced termination |

**Properties:**

| Property | Returns | Description |
|----------|---------|-------------|
| `initial_states` | `List[StateDefinition]` | All states with `StateType.INITIAL` |
| `terminal_states` | `List[StateDefinition]` | All states with `StateType.TERMINAL` |
| `intermediate_states` | `List[StateDefinition]` | All states with `StateType.INTERMEDIATE` |

### `ValidationError`

A single validation issue produced by compile-time checks.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `field` | `str` | — | Dot-notation path to the offending field (e.g. `"states.idle.max_reentries"`) |
| `message` | `str` | — | Human-readable error description |
| `severity` | `str` | `"ERROR"` | `"ERROR"` (blocks construction) or `"WARNING"` (advisory) |

### `RuntimeState`

Mutable state snapshot for a running state machine instance.

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `current_state` | `str` | — | Name of the currently active state |
| `previous_state` | `Optional[str]` | `None` | Name of the immediately prior state |
| `reentry_count` | `int` | `0` | Number of times current state has been re-entered |
| `iteration_count` | `int` | `0` | Total iteration counter (incremented on each transition) |
| `entered_at` | `datetime` | `now` | Timestamp when the current state was entered |
| `last_transition_at` | `datetime` | `now` | Timestamp of the last transition |
| `version` | `int` | `0` | Monotonic version counter for optimistic concurrency |

---

## Exceptions

### `StateMachineValidationError`

Raised at compile-time when critical validation errors are detected during `StateMachine.__init__()`. Inherits from `Exception`.

```
StateMachineValidationError: StateMachine validation failed with 2 error(s):
  • states.idle: Initial state 'idle' has no outgoing transitions
  • states.done: Terminal state 'done' should have no outgoing transitions
```

### `TransitionError`

Raised at runtime when an invalid transition is attempted. Inherits from `Exception`.

```
TransitionError: Cannot transition from terminal state 'done'
```

---

## Usage Examples

### Building a `StateMachineConfig` programmatically

```python
from engine.sm_types import (
    StateDefinition, TransitionDefinition, LTLRule,
    StateMachineConfig, StateType, TransitionType
)

config = StateMachineConfig(
    profile="software",
    name="dev-workflow",
    version="1.0.0",
    states={
        "backlog": StateDefinition("backlog", StateType.INITIAL, max_reentries=1),
        "working": StateDefinition("working", StateType.INTERMEDIATE, max_reentries=5),
        "done": StateDefinition("done", StateType.TERMINAL, max_reentries=0),
    },
    transitions=[
        TransitionDefinition("backlog", "working"),
        TransitionDefinition("working", "done"),
        TransitionDefinition("working", "backlog",
                             transition_type=TransitionType.REVERSIBLE),
    ],
    ltl_rules=[
        LTLRule("G (working → F done)", within_seconds=3600),
    ],
    max_steps=50,
)

print(config.initial_states)      # [StateDefinition(name='backlog', ...)]
print(config.terminal_states)     # [StateDefinition(name='done', ...)]
print(config.intermediate_states) # [StateDefinition(name='working', ...)]
```

### Filtering states with helpers

```python
from engine.sm_types import initial_states, terminal_states, intermediate_states

states = config.states
initials = initial_states(states)       # list of StateDefinition
terminals = terminal_states(states)
intermediates = intermediate_states(states)
```

---

## Cross-References

- **Parser:** [`sm_parser.StateMachineParser`](sm_parser.md) — produces `StateMachineConfig` from YAML
- **Runtime:** [`state_machine.StateMachine`](state_machine.md) — consumes `StateMachineConfig` for validation and execution
- **Guide:** [State Machine Guide](../guide/state-machine.md) — conceptual overview
