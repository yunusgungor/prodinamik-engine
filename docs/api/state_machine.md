# State Machine Runtime

Prodinamik Engine v1.1 — StateMachine Runtime (Facade)

Formal state machine runtime with compile-time validation,
graph algorithms, and runtime transition rules.

Backward-compatible: re-exports all types from sm_types
and sm_parser so existing imports continue to work.

**Module:** `engine.state_machine.py`

## Classes

### `StateMachine`

Formal state machine runtime.
- YAML'den yüklenir (via StateMachineParser)
- Compile-time validate edilir
- Runtime'da transition kurallarını uygular

**Methods:**

- `__init__(config, lru_size)`
- `_build_transition_map()`
  — Transition'ları from_state bazında grupla (hızlı lookup için)
- `validate()`
- `_validate_initial_states()`
- `_validate_intermediate_states()`
- `_validate_terminal_states()`
- `_validate_cycle_exits()`
- `_validate_reachability()`
- `_validate_max_reentries()`
- `_validate_transition_targets()`
- `_validate_or_raise()`
- `_find_cycles()`
- `_find_reachable_states()`
- `get_next_states(current_state)`
  — Bir state'ten gidilebilecek state'leri listele (cached)
- `can_transition(from_state, to_state, runtime)`
- `_evaluate_condition(condition, runtime)`
- `get_transition_type(from_state, to_state)`
- `create_runtime(initial_state)`
- `snapshot()`
- `__repr__()`
