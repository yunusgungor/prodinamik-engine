# Hermes Agent Bridge

Prodinamik Engine v1.1 — Hermes Agent Bridge

Bridges Prodinamik Engine plugins to the Hermes Agent environment.

Key capabilities:
    - Convert PluginTools to Hermes-compatible tool definitions
    - Auto-discover Hermes skills and register as Prodinamik plugins
    - Plugin → Hermes skill mapping with on-demand installation
    - Tool execution proxy (engine state injection, error wrapping)
    - Hermes config integration (plugin config stored in ~/.hermes/config.yaml)

**Module:** `engine.hermes_bridge.py`

## Classes

### `HermesToolDef`

A tool definition compatible with Hermes Agent's tool format

### `HermesPluginBridge`

Bridge between Prodinamik PluginRegistry and Hermes Agent

Converts plugins to Hermes skills/tools and injects engine state
into tool execution context.

Usage:
    bridge = HermesPluginBridge(registry, hermes_home="~/.hermes")
    tools = bridge.build_tool_defs()
    # → feed tools into Hermes AIAgent

**Methods:**

- `__init__(registry, hermes_home)`
- `build_tool_defs()`
  — Build Hermes-compatible tool definitions from all enabled plugins
- `_convert_tool(plugin_tool, manifest)`
  — Convert a PluginTool to HermesToolDef with engine state injection
- `discover_hermes_skills()`
  — Scan Hermes skills directory for prodinamik-related skills
- `_parse_skill_frontmatter(skill_file)`
  — Parse YAML-style frontmatter from a SKILL.md file
- `_is_prodinamik_skill(meta)`
  — Check if a skill is related to Prodinamik Engine
- `export_as_skill(plugin_id, output_dir)`
  — Export a plugin as a Hermes-compatible skill
- `read_hermes_plugin_config()`
  — Read plugin config from Hermes config.yaml
- `_parse_simple_yaml(path)`
  — Simple nested YAML parser for config
- `install_from_hermes_skill(skill_name)`
  — Discover and install a Prodinamik plugin from a Hermes skill
- `metrics()`
  — Bridge metrics for dashboard
- `reset_metrics()`
  — Reset bridge metrics
