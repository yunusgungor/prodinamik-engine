# State Machine Types

Prodinamik Engine v1.1 — StateMachine Data Types

All type definitions, enums, dataclasses, and exceptions
extracted from state_machine.py for modularity.

**Module:** `engine.sm_types.py`

## Classes

### `TransitionType`(Enum)

### `StateType`(Enum)

### `StateDefinition`

Tek bir state'in formal tanımı

**Methods:**

- `__post_init__()`

### `TransitionDefinition`

İki state arasındaki geçişin formal tanımı

### `LTLRule`

Linear Temporal Logic constraint

### `StateMachineConfig`

Complete state machine configuration from YAML

**Methods:**

- `initial_states()`
- `terminal_states()`
- `intermediate_states()`

### `ValidationError`

### `RuntimeState`

Bir run'ın anlık state bilgisi

### `StateMachineValidationError`(Exception)

State machine validation hatası — compile-time

### `TransitionError`(Exception)

Geçersiz transition — runtime
