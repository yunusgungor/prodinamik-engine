# State Machine Parser

Prodinamik Engine v1.1 — StateMachine YAML Parser

Parses formal state machine definitions from YAML documents into typed Python objects.

**Module:** `engine.sm_parser.py` (110 lines)

---

## Overview

`StateMachineParser` is a class-method-only parser that converts YAML state machine definitions into a [`StateMachineConfig`](sm_types.md#statemachineconfig) instance. It handles:

- State definitions with type classification, hooks, validators, and temporal constraints
- Transition definitions with type, guard conditions, and human-approval flags
- LTL temporal constraint rules
- Formal properties (termination bounds)

The parser validates structure during parsing — invalid state types, missing transition arrows, and empty documents raise early errors.

---

## YAML Format

State machines are defined in YAML with the following top-level sections:

```yaml
profile: software            # Profile identifier
name: dev-workflow           # Machine name
version: 1.0.0               # Semantic version

states:                      # Dictionary of state definitions
  state_name:                # Unique state identifier
    type: initial            # One of: initial, intermediate, terminal, error
    max_reentries: 3         # Optional: max re-entry limit
    timeout: 300             # Optional: state timeout in seconds
    entry:                   # Optional: entry hook names
      - on_enter_state
    exit:                    # Optional: exit hook names
      - on_exit_state
    validators:              # Optional: validator names
      - validate_transition_allowed
    temporal:                # Optional: LTL temporal constraints
      max_duration: 600
      on_timeout: next_state
      reminders:
        - at: 300
          message: "Still working..."
    requires_manual: false   # Optional: requires human intervention

transitions:                 # List or dictionary of transitions
  - backlog -> working       # "from -> to" syntax (ASCII arrow)
  - working -> review        # Or use "→" (Unicode arrow)
  - review -> done

temporal_constraints:        # Optional: LTL rules
  - expression: "G (working → F done)"
    within: 3600

formal_properties:           # Optional: global machine bounds
  termination:
    max_steps: 100
```

### State Definitions (`states`)

Each key under `states` is a unique state name mapped to an object with these optional fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | `"intermediate"` | One of `initial`, `intermediate`, `terminal`, `error` |
| `max_reentries` | `int` or `null` | `null` | Max times state can be re-entered |
| `timeout` | `int` or `null` | `null` | Timeout in seconds |
| `entry` | `list[str]` | `[]` | Entry hook names |
| `exit` | `list[str]` | `[]` | Exit hook names |
| `validators` | `list[str]` | `[]` | Validator names |
| `temporal.max_duration` | `int` or `null` | `null` | Max duration for LTL |
| `temporal.on_timeout` | `str` or `null` | `null` | Target state on timeout |
| `temporal.reminders` | `list[dict]` | `[]` | Reminders with `at` and `message` |
| `requires_manual` | `bool` | `false` | Manual intervention required |

### Transition Definitions (`transitions`)

Transitions can be specified as a **list of strings** (simple form) or a **dictionary** (with metadata):

**List form** (default type is `REVERSIBLE`):

```yaml
transitions:
  - backlog -> working
  - working -> review
  - review -> done
```

**Dictionary form** (with metadata):

```yaml
transitions:
  backlog -> working:
    type: REVERSIBLE
    condition: "ready_for_work"
    action: "assign_task"
    requires_human: false
```

Transition strings use `" -> "` (space-arrow-space) or `"→"` as separator. The parser splits on either.

Transition metadata fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | `"REVERSIBLE"` | One of `REVERSIBLE`, `COMPENSABLE`, `IRREVERSIBLE` |
| `condition` | `str` or `null` | `null` | Guard expression evaluated at runtime |
| `action` | `str` or `null` | `null` | Action executed during transition |
| `requires_human` | `bool` | `false` | Human approval required |

### Temporal Constraints (`temporal_constraints`)

List of LTL rules that constrain state machine behavior:

```yaml
temporal_constraints:
  - expression: "G (working → F done)"
    within: 3600         # Optional: seconds
  - "F terminal"         # String-only form (no within bound)
```

### Formal Properties (`formal_properties`)

```yaml
formal_properties:
  termination:
    max_steps: 100       # Max total transitions before forced stop
```

---

## Class: `StateMachineParser`

All methods are `@classmethod` — the class holds no instance state.

### `parse_file(path: str) -> StateMachineConfig`

Reads a YAML file from disk and parses it into a `StateMachineConfig`.

```python
from engine.sm_parser import StateMachineParser

config = StateMachineParser.parse_file("workflow.yaml")
print(config.name)        # "dev-workflow"
print(config.profile)     # "software"
```

**Raises:**
- `FileNotFoundError` — if the path does not exist
- `ValueError` — if the YAML content is empty or contains invalid state types

### `parse_string(yaml_str: str) -> StateMachineConfig`

Parses a YAML string directly without touching the filesystem.

```python
yaml_content = """
profile: test
name: test-machine
version: 0.1.0
states:
  idle:
    type: initial
  running:
    type: intermediate
  done:
    type: terminal
transitions:
  - idle -> running
  - running -> done
"""

config = StateMachineParser.parse_string(yaml_content)
print(config.initial_states)     # [StateDefinition(name='idle', ...)]
print(len(config.transitions))   # 2
```

### `_parse_dict(raw: dict) -> StateMachineConfig` (internal)

Internal method that performs the actual conversion from a parsed YAML dictionary to `StateMachineConfig`. Called by both `parse_file` and `parse_string`.

**Parsing stages:**

1. **States** — Iterates `raw["states"]`, resolves string `type` to `StateType` enum via `STATE_TYPE_MAP`, constructs `StateDefinition` objects with all optional fields.
2. **Transitions** — Splits transition strings on `" -> "` or `"→"`, resolves optional metadata from dictionary form, constructs `TransitionDefinition` objects.
3. **LTL rules** — Reads `raw["temporal_constraints"]`, supports both string-only and dict-with-metadata forms.
4. **Formal properties** — Extracts `max_steps` from `formal_properties.termination`.

**Internal mappings:**

```python
STATE_TYPE_MAP = {
    "initial": StateType.INITIAL,
    "intermediate": StateType.INTERMEDIATE,
    "terminal": StateType.TERMINAL,
    "error": StateType.ERROR,
}

TRANSITION_TYPE_MAP = {
    "REVERSIBLE": TransitionType.REVERSIBLE,
    "COMPENSABLE": TransitionType.COMPENSABLE,
    "IRREVERSIBLE": TransitionType.IRREVERSIBLE,
}
```

---

## Validation During Parse

The parser performs structural validation during the parsing phase:

| Check | Error |
|-------|-------|
| Empty YAML | `ValueError("Empty YAML")` |
| Invalid state type string | `ValueError("Invalid state type for '{name}': {type}")` |
| File not found | `FileNotFoundError` |
| Missing `" -> "` or `"→"` in transition | `ValueError` (from unpacking) |

These are distinct from the deeper semantic validations performed by `StateMachine.validate()` (reachability, cycle exits, max_reentries consistency, etc.). The parser validates the **structure**; the runtime validates the **semantics**.

---

## Usage Examples

### Full workflow — parse and inspect

```python
from engine.sm_parser import StateMachineParser

config = StateMachineParser.parse_string("""
profile: software
name: review-cycle
version: 2.0.0
states:
  backlog:
    type: initial
    max_reentries: 1
  in_review:
    type: intermediate
    max_reentries: 3
    timeout: 86400
    temporal:
      max_duration: 7200
      on_timeout: backlog
      reminders:
        - at: 3600
          message: "Review taking longer than expected"
  approved:
    type: terminal
    max_reentries: 0
transitions:
  backlog -> in_review:
    type: REVERSIBLE
    condition: "ready_for_review"
  in_review -> approved:
    type: IRREVERSIBLE
    condition: "review_passed"
  in_review -> backlog:
    type: REVERSIBLE
temporal_constraints:
  - expression: "G (in_review → F (approved ∨ backlog))"
    within: 7200
formal_properties:
  termination:
    max_steps: 20
""")

print(f"Machine: {config.name} v{config.version}")
print(f"States: {list(config.states.keys())}")
print(f"Transitions: {len(config.transitions)}")
print(f"LTL rules: {[r.expression for r in config.ltl_rules]}")
```

### Parsing from file

```python
config = StateMachineParser.parse_file("./workflows/deploy-pipeline.yaml")
```

---

## Cross-References

- **Types:** [`sm_types`](sm_types.md) — all data types produced by the parser
- **Runtime:** [`state_machine.StateMachine`](state_machine.md) — consumes `StateMachineConfig` for validation and execution
- **Guide:** [State Machine Guide](../guide/state-machine.md) — conceptual overview and YAML authoring best practices
