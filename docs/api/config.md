# Config

Prodinamik Engine v1.0 — Configuration

Config dataclass + YAML/config file parsing.
Environment variable override support.

**Module:** `engine.config.py`

## Classes

### `DegradationConfig`

### `BudgetDefaults`

### `EventStoreConfig`

### `StateMachineConfig`

### `LoggingConfig`

### `ProdinamikConfig`

Root configuration

**Methods:**

- `load(cls, path)`
  — Load config from YAML file, then apply env overrides
- `_merge(cfg, data)`
  — Merge YAML data into config, preserving defaults
- `_apply_env(cfg)`
  — Apply environment variable overrides
- `to_dict()`
