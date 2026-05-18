# Plugin Registry

Prodinamik Engine v1.1 — Plugin Registry

Central registry for discovering, loading, and managing plugins.

Key features:
    - Directory-based auto-discovery (./plugins/, ~/.hermes/plugins/)
    - Dependency resolution (topological sort)
    - Plugin status management (enable/disable/error)
    - Hot-reload support (re-scan directories)
    - Metrics tracking per plugin

**Module:** `engine.plugin_registry.py`

## Classes

### `PluginRegistry`

Central registry for all plugins

Singleton pattern — use PluginRegistry.get_instance() or
access via engine.plugins.

Usage:
    registry = PluginRegistry(engine)
    registry.discover()
    registry.enable("prodinamik.logging")
    registry.disable("prodinamik.myplugin")

**Methods:**

- `get_instance(cls, engine)`
  — Get or create the singleton instance
- `__init__(engine)`
- `discover(paths)`
  — Discover plugins from search paths
- `_discover_from_directory(directory)`
  — Scan a directory for plugin files
- `_import_class(dotted_path)`
  — Import a class from a dotted path like 'engine.plugin.LoggingPlugin'
- `_register_class(plugin_cls)`
  — Register a plugin class. Returns True if newly registered.
- `_resolve()`
  — Resolve dependency ordering
- `async enable(plugin_id)`
  — Enable a plugin by ID. Returns True on success.
- `async disable(plugin_id)`
  — Disable a plugin by ID. Returns True on success.
- `async install(plugin_id, source)`
  — Install a plugin (from source path or remote).
- `async uninstall(plugin_id)`
  — Uninstall a plugin
- `async reload(plugin_id)`
  — Reload a plugin (disable → re-discover → enable)
- `get(plugin_id)`
  — Get plugin state by ID
- `get_plugin_instance(plugin_id)`
  — Get plugin instance by ID
- `list_plugins(status, plugin_type)`
  — List plugins, optionally filtered
- `get_enabled()`
  — Get all enabled plugins
- `count()`
- `enabled_count()`
- `plugin_ids()`
- `find_by_type(plugin_type)`
  — Find plugins by type
- `get_all_tools()`
  — Aggregate all tools from enabled plugins
- `get_all_hooks()`
  — Aggregate all hooks from enabled plugins
- `get_all_validators()`
  — Aggregate all validators from enabled plugins
- `async health_check_all()`
  — Run health checks on all enabled plugins
- `snapshot_metrics()`
  — Snapshot of registry metrics for dashboard
- `_count_by_type()`
  — Count plugins by type
- `to_dict()`
  — Serialize registry state to dict
- `on_change(callback)`
  — Register callback for plugin state changes
- `_notify_change()`
  — Notify all change listeners
- `attach_to_engine()`
  — Wire plugins into the engine runtime
- `async _emit_startup_hooks()`
  — Fire ON_STARTUP hooks for all enabled plugins
- `shutdown()`
  — Disable all plugins on shutdown

## Functions

### `resolve_dependencies(plugins)`

Topological sort of plugin dependencies.

Returns:
    (ordered_ids, unresolved)
