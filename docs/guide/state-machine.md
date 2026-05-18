# State Machine Guide

Prodinamik Engine includes a formal, compile-time validated state machine system that models product pipelines as directed graphs of states and transitions. State machines are defined declaratively in YAML, validated at load time through a multi-pass verification system, and executed by a lightweight runtime with timeout watchers, guards, and lifecycle hooks.

## What Is a State Machine and Why Use It?

A state machine (or finite-state machine, FSM) models a system as a finite set of **states** and the **transitions** between them. At any given moment the system occupies exactly one state. Transitions define which state comes next and under what conditions.

In the Prodinamik Engine, every **run** follows a state machine. The state machine determines the possible paths a run can take — from creation through validation, processing, and finally completion or error recovery. This gives you:

- **Deterministic behavior** — Every run follows the same rules.
- **Enforced lifecycle** — Invalid transitions are rejected before they happen.
- **Auditability** — Every state change is logged and traceable.
- **Recoverability** — Error states and compensation transitions let you define failure handling up front.

## Defining a State Machine in YAML

State machines are defined as YAML documents and parsed by `StateMachineParser` (engine/sm_parser.py). Here is a complete example:

```yaml
profile: software
name: software-delivery
version: 1.0.0

states:
  backlog:
    type: initial
    max_reentries: 1
    entry:
      - notify_team
  development:
    type: intermediate
    max_reentries: 5
    timeout: 604800
    entry:
      - assign_developer
      - create_branch
    exit:
      - validate_commit
    validators:
      - check_code_quality
  review:
    type: intermediate
    max_reentries: 3
    requires_manual: true
  staging:
    type: intermediate
    max_reentries: 2
    entry:
      - deploy_staging
      - run_integration_tests
  released:
    type: terminal
    max_reentries: 0
  rollback:
    type: error
    max_reentries: 1
    entry:
      - notify_oncall

transitions:
  backlog -> development:
    type: REVERSIBLE
    condition: "prototype_passes(spec)"
  development -> review:
    type: REVERSIBLE
    action: "create_pull_request"
    requires_human: true
  review -> staging:
    type: REVERSIBLE
    condition: "human_approved"
  staging -> released:
    type: IRREVERSIBLE
    condition: "iterations >= 1"
  staging -> rollback:
    type: COMPENSABLE
    condition: "drift_detected"
  rollback -> development:
    type: REVERSIBLE
    condition: "manual_unblock"
  development -> development:
    type: REVERSIBLE
    condition: "changes_requested"

temporal_constraints:
  - rule: "eventually(released)"
    within: 1209600
  - rule: "globally(not(released U development))"
  - rule: "after(staging, released)"

formal_properties:
  termination:
    max_steps: 100
```

### Profile Registration

In your profile Python class, reference the YAML by path or embed it as a string:

```python
from engine.profile import ProductProfile

class SoftwareProfile(ProductProfile):
    name = "software"
    version = "1.0.0"
    state_machine_yaml = "profiles/software-delivery.yaml"
```

## State Types

The engine supports four state types, defined in the `StateType` enum (engine/sm_types.py):

| Type | Description | Rules |
|------|-------------|-------|
| **initial** | Entry point of the state machine. Every machine must have at least one initial state. | Must have outgoing transitions. `max_reentries` must be 0 or 1. |
| **intermediate** | Processing states between initial and terminal. Most states fall here. | Must have at least one outgoing transition. Should have a `timeout_seconds` to detect stalls. |
| **terminal** | End states that represent completion. | Must have **zero** outgoing transitions. `max_reentries` must be 0. The machine stops here. |
| **error** | Error/recovery states reached from intermediate states on failure. | Can have outgoing transitions (e.g., back to an intermediate state). Limited `max_reentries` is recommended to prevent infinite retry loops. |

### State Properties

Each state definition supports these optional properties:

- **max_reentries** — Maximum number of times the run can cycle back to this same state (self-transitions). Default: unlimited if omitted, but a warning is raised during validation.
- **timeout_seconds** — Maximum wall-clock duration a run can stay in this state before a timeout watcher triggers.
- **entry_hooks** — List of hook names called when transitioning *into* this state.
- **exit_hooks** — List of hook names called when transitioning *out of* this state.
- **validators** — Named validators invoked before allowing the transition out.
- **temporal_max_duration** — (Temporal integration) Maximum state duration in seconds.
- **temporal_on_timeout** — Target state to transition to on temporal timeout.
- **reminders** — List of reminder configurations for manual states.
- **requires_manual** — Boolean; if true, the state expects human intervention.

## Transition Types

Transitions between states are typed to control the direction and reversibility of flow:

| Transition Type | Value | Behavior |
|----------------|-------|----------|
| **REVERSIBLE** | `reversible` | Standard forward/backward transition. Can be traversed multiple times within `max_reentries`. |
| **COMPENSABLE** | `compensable` | A compensating action transition. Used for rollback or undo scenarios (e.g., staging → rollback). |
| **IRREVERSIBLE** | `irreversible` | One-way transition. Once taken, the run cannot return to the source state. Used for gates like staging → released. |

### Transition Properties

- **condition** — A guard expression (string) evaluated at runtime. The transition is blocked if the condition returns false.
- **action** — A named action to execute during the transition.
- **requires_human** — Boolean. If true, `can_transition()` returns false unless explicitly overridden (used for manual approval states).

## Guards and Conditions

Conditions are string expressions evaluated by `_evaluate_condition()` on the `StateMachine` class. Built-in condition evaluators include:

| Condition Pattern | Behavior |
|-------------------|----------|
| `drift_detected` | Always returns true (placeholders for external drift detection). |
| `iterations >= N` | True when `runtime.iteration_count >= N`. |
| `iterations > N` | True when `runtime.iteration_count > N`. |
| `iterations < N` | True when `runtime.iteration_count < N`. |
| `prototype_passes(spec)` | Always returns true (placeholder — override for real validation). |
| `human_approved` | Returns false unless explicitly authorized. Used with manual gates. |
| `changes_requested` | Returns false by default. |
| `manual_unblock` | Returns false by default. |
| `max_iterations` | Returns false by default. Prevents runaway loops. |
| `consecutive_failures` | Returns false by default. |

For production use, subclass the `StateMachine` and override `_evaluate_condition()` to implement your own condition logic.

## Lifecycle Hooks

The state machine supports three types of lifecycle hooks: **entry hooks** (on_entry), **exit hooks** (on_exit), and **transition actions** (on_transition). These are defined as string names in the YAML definition.

### on_entry Hooks

Called when a run enters a state. Example configuration:

```yaml
states:
  development:
    type: intermediate
    entry:
      - assign_developer
      - create_branch
      - notify_team
```

The engine invokes these hooks in order when the run transitions into `development`. If a hook raises an exception, the transition is rolled back.

### on_exit Hooks

Called when a run leaves a state:

```yaml
states:
  development:
    type: intermediate
    exit:
      - validate_commit
```

Exit hooks fire before the transition executes. If validation fails, the transition is blocked.

### Transition Actions

Each transition can specify an action:

```yaml
transitions:
  development -> review:
    type: REVERSIBLE
    action: "create_pull_request"
```

The action is executed during the transition, after any exit hooks and before entry hooks on the target state.

## Validation: 7-Pass System

Every state machine is validated at compile time (when the `StateMachine` object is constructed) through a seven-pass verification system in `StateMachine.validate()`:

### Pass 1 — Initial State Validation

Checks that every `initial` state has at least one outgoing transition. An initial state with no transitions would be a dead end.

### Pass 2 — Intermediate State Validation

Checks that every `intermediate` state has at least one outgoing transition. An intermediate state without exits would cause a run to get stuck permanently.

### Pass 3 — Terminal State Validation

Checks that every `terminal` state has **zero** outgoing transitions (they are terminal). Also verifies `max_reentries=0` for terminal states.

### Pass 4 — Cycle Detection (Dead-End Cycles)

Uses DFS cycle detection (`_find_cycles()`) to identify cycles where every transition points back into the same cycle. These are dead-end cycles — once entered, the run can never exit. The error message lists the cycle path, e.g.:

```
Dead-end cycle detected: A → B → C → A.
All transitions in cycle point back into the cycle.
```

Cycles of length 1 (self-transitions) are allowed if they have a valid exit condition.

### Pass 5 — Reachability Analysis

Uses BFS (`_find_reachable_states()`) starting from all initial states to determine which states are reachable. Any unreachable non-initial state is flagged:

```
Unreachable state: 'staging'. No path from any initial state.
```

### Pass 6 — max_reentries Warning

Flags states that are missing `max_reentries` (unless they are terminal or error). This is a WARNING-level issue — the engine will work, but runtime behavior is undefined for self-transition limits.

### Pass 7 — Transition Target Validation

Validates that all transition `from_state` and `to_state` values refer to actual defined states. Catches typos and dangling references:

```
Transition target 'staginng' not found in state definitions
```

### Validation Errors

Errors are collected into a `List[ValidationError]` with `field`, `message`, and `severity` fields. Errors with `severity="ERROR"` raise `StateMachineValidationError` on construction, blocking the machine from loading. Warnings are logged but do not block loading.

## Graph Traversal Algorithms

The state machine includes two built-in graph algorithms for analysis:

### find_paths()

Uses BFS from all initial states to discover all states reachable through the transition graph. This is the core of the reachability pass. The implementation:

```python
def _find_reachable_states(self) -> Set[str]:
    reachable = set()
    queue = list(self.config.initial_states ...)
    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        for t in self._transition_map.get(current, []):
            if t.to_state not in reachable:
                queue.append(t.to_state)
    return reachable
```

### find_cycles()

Uses DFS with path tracking to find all cycles in the state graph. Results are canonicalized (rotated to a standard starting point) to avoid duplicate detection. Cycles are returned as `List[List[str]]` where each inner list is a cycle path.

## Runtime Execution

### Timeout Watcher

The runtime tracks the time a run has spent in its current state via `get_state_elapsed()`. If a state defines `timeout_seconds`, the CLI debug command displays remaining time:

```
prodinamik debug my-run
# Timeout: 582340s remaining (limit: 604800s)
```

The `RuntimeState` dataclass maintains:
- `current_state` — The active state name.
- `previous_state` — The previous state before the last transition.
- `reentry_count` — Number of times the current state has been re-entered.
- `iteration_count` — Total iteration count (for loop conditions).
- `entered_at` — Timestamp when the current state was entered.
- `last_transition_at` — Timestamp of the last transition.

### create_runtime()

Initializes a `RuntimeState` from the machine's initial states:

```python
machine = StateMachine(config)
rt = machine.create_runtime()  # Starts at first initial state
```

### can_transition()

Checks whether a transition is valid:

```python
allowed, reason = machine.can_transition("development", "review", rt)
if not allowed:
    print(f"Transition blocked: {reason}")
```

Checks performed:
1. Source and target states exist.
2. Source state is not terminal.
3. A matching transition definition exists.
4. Transition does not require human approval (unless overridden).
5. Runtime reentry limits have not been exceeded.
6. The condition guard evaluates to true.

Results are cached in an LRU cache (default size: 128 entries) for stateless (runtime=None) checks.

## CLI Commands

### Validate a State Machine YAML

```bash
prodinamik sm validate profiles/software-delivery.yaml
```

This loads the YAML, parses it with `StateMachineParser`, constructs a `StateMachine` object (which triggers the 7-pass validation), and reports any errors or warnings.

### Generate a Graph Visualization

```bash
prodinamik sm graph profiles/software-delivery.yaml
```

Outputs a DOT-format graph of the state machine for use with Graphviz or other graph visualization tools. States are color-coded by type: green for initial, blue for intermediate, red for terminal, orange for error.

### Runtime Debug

```bash
prodinamik debug my-run-slug
# State:   development
# Elapsed: 3420s in state
# Timeout: 604800s limit, 601380s remaining
```

## Best Practices

### State Naming

- Use lowercase, descriptive names: `backlog`, `development`, `review`, `staging`, `released`.
- Use `snake_case` for multi-word state names: `code_review`, `user_acceptance_test`.
- Avoid generic names like `step1`, `step2`, `done` — encode the *semantic* meaning.

### Transition Density

- Keep the transition graph sparse. Most states should have 1–3 outgoing transitions. More than 5 suggests the state could be decomposed.
- Self-transitions (A → A) are useful for retry/iterative processing but always set a `max_reentries` limit and pair with a `condition` guard.
- Avoid "star" topologies where a single state connects to many others — consider intermediate hub states.

### Error States

- Every intermediate state should have at least one path to an error state or compensating transition.
- Error states should have a clear recovery path (back to the originating state or a safe terminal state).
- Set low `max_reentries` on error states (usually 1) to prevent infinite error loops.

### Temporal Constraints

- Use LTL-style rules sparingly: 1–3 top-level constraints is typical.
- Document your temporal rules with comments in the YAML — they encode business-critical invariants.
- The `max_steps` setting under `formal_properties.termination` is a safety net. Set it to 2× the maximum expected path length.

### Versioning

- Always set a `version` field on your state machine YAML.
- Use semantic versioning: bump major for breaking structural changes, minor for new states/transitions, patch for condition or hook changes.
- Keep old state machine versions available for archived runs that may need to be restored in their original context.
