# Plugin Base System

Prodinamik Engine v1.1 — Plugin Base System

Abstract base classes and data structures for the plugin ecosystem.
Every plugin implements PluginBase and declares a PluginManifest.

Architecture:
    PluginBase (ABC)
        ├── built-in plugins (shipped with engine)
        ├── local plugins (~/.hermes/plugins/, ./plugins/)
        └── community plugins (installed from registry)

Lifecycle:
    INSTALLED → DISABLED → ENABLED → DISABLED → UNINSTALLED
                              ↓
                          ERROR (recoverable)

**Module:** `engine.plugin.py`

## Classes

### `PluginStatus`(Enum)

Lifecycle status of a plugin

### `PluginHookType`(Enum)

Hook types a plugin can register against

### `PluginType`(Enum)

Classification of plugin

### `PluginManifest`

Declarative metadata for a plugin

**Methods:**

- `validate()`
  — Validate manifest completeness. Returns list of issues.

### `PluginTool`

A tool exposed by a plugin for Hermes integration

### `PluginHook`

A hook registration from a plugin

### `PluginState`

Runtime state of a plugin instance

**Methods:**

- `is_enabled()`
- `is_error()`

### `PluginBase`(ABC)

Abstract base class for all Prodinamik Engine plugins

Subclasses must implement:
    - manifest property (class-level or instance)
    - on_install / on_uninstall  (can be no-op)
    - on_enable / on_disable      (can be no-op)

Subclasses may override:
    - get_tools()     → return list of PluginTool
    - get_hooks()     → return list of PluginHook
    - get_validators() → return list of validator callables
    - on_error(error)  → custom error handler

**Methods:**

- `__init__(engine)`
- `manifest()`
  — Return the plugin manifest
- `get_manifest()`
  — Override if manifest needs dynamic construction
- `async on_install()`
  — Called when plugin is first installed
- `async on_uninstall()`
  — Called when plugin is being removed
- `async on_enable()`
  — Called when plugin transitions from disabled → enabled
- `async on_disable()`
  — Called when plugin transitions from enabled → disabled
- `async on_error(error)`
  — Called when an error occurs in the plugin
- `get_tools()`
  — Return list of tools this plugin exposes
- `get_hooks()`
  — Return list of hooks this plugin registers
- `get_validators()`
  — Return list of validator functions
- `get_adapters()`
  — Return dict of adapter instances keyed by name
- `configure(config)`
  — Apply configuration to the plugin
- `_apply_config()`
  — Apply current config (override in subclasses)
- `get_config(key, default)`
  — Get a config value
- `state()`
- `status()`
- `is_healthy()`
  — Override for custom health checks
- `async health_check()`
  — Return health check result. Override in subclasses.
- `register_hooks(registry)`
  — Register hooks with an engine HookRegistry
- `__repr__()`

### `BuiltinPluginMeta`(type)

Metaclass for built-in plugins that auto-creates manifest

**Methods:**

- `__new__(mcs, name, bases, namespace)`

### `LoggingPlugin`(PluginBase)

Built-in plugin that logs state transitions

**Methods:**

- `manifest()`
- `__init__(engine)`
- `get_hooks()`

## Functions

### `discover_plugin_classes(module)`

Discover all PluginBase subclasses in a module

### `load_plugin_from_file(filepath)`

Load a plugin class from a Python file
