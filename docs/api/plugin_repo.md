# Plugin Repository

Prodinamik Engine v1.1 — Plugin Repository & Community Registry

Local plugin index and remote plugin repository concept.

Architecture:
    Local Index          Community Registry
    ├── ~/plugins/       ├── GitHub-based index
    ├── ./plugins/       ├── Plugin manifest registry
    └── installed.json   └── Download + install flow

Design:
    - Community registry is a URL index of plugin manifests
    - Plugins are downloaded as Python modules/tarballs
    - Cryptographic hash verification on install
    - Dependency resolution across repository plugins

**Module:** `engine.plugin_repo.py`

## Classes

### `RepositoryPlugin`

A plugin available in the community repository

### `InstallRecord`

Record of an installed plugin

### `PluginRepository`

Plugin repository manager — local index + remote registry

Manages the lifecycle of plugin installation from remote sources.
Works in conjunction with PluginRegistry for enable/disable.

Usage:
    repo = PluginRepository()
    repo.refresh_index()           # Fetch remote plugin index
    plugins = repo.search("slack") # Search available plugins
    repo.install("prodinamik.slack")

**Methods:**

- `__init__(storage_dir, index_urls)`
- `_local_index_path()`
- `_load_local_index()`
  — Load installed plugins index from disk
- `_save_local_index()`
  — Save installed plugins index to disk
- `refresh_index()`
  — Fetch remote plugin index from all configured URLs
- `_fetch_index(url)`
  — Fetch and parse a plugin index from URL
- `_load_cached_remote_index()`
  — Load a cached copy of the remote index
- `_cache_remote_index()`
  — Cache the current remote index to disk
- `search(query)`
  — Search available plugins by name, description, or ID
- `list_available()`
  — List all plugins available in the repository
- `list_installed()`
  — List all locally installed plugins
- `get_available(plugin_id)`
  — Get a plugin from the remote index by ID
- `get_installed(plugin_id)`
  — Get install record for a locally installed plugin
- `is_installed(plugin_id)`
  — Check if a plugin is installed locally
- `install(plugin_id)`
  — Install a plugin from the repository
- `uninstall(plugin_id)`
  — Uninstall a plugin
- `install_local(source_path, plugin_id)`
  — Install a plugin from a local directory or .py file
- `_check_engine_compatibility(version_spec)`
  — Check if the current engine version satisfies the requirement
- `_download_plugin(plugin, target_dir)`
  — Download a plugin from its download URL
- `_compute_checksum(path)`
  — Compute SHA256 checksum of a directory or file
- `_detect_version(path)`
  — Try to detect version from plugin files
- `register_index(url)`
  — Register an additional remote index URL
- `local_index_snapshot()`
  — Snapshot of local plugin index for dashboard
