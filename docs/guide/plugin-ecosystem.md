# Plugin Ecosystem

Prodinamik Engine v1.2 introduced a **full plugin system** that allows extending the engine with custom validators, hooks, tools, and adapters. Plugins can be auto-discovered, installed from local or remote sources, and bridged to Hermes Agent.

## Architecture

```
┌─────────────────────────────────────────────┐
│               PluginRegistry                  │
│  ├── discover()  → Built-in + path scan       │
│  ├── enable()    → Wires hooks + tools        │
│  ├── disable()   → Graceful shutdown          │
│  └── resolve()   → Topological dependency sort │
├─────────────────────────────────────────────┤
│  PluginBase (ABC)                              │
│  ├── PluginManifest  (id, name, version, ...)  │
│  ├── get_tools()     → PluginTool[]            │
│  ├── get_hooks()     → PluginHook[]            │
│  ├── get_validators() → Validator callables    │
│  └── on_enable/on_disable/on_install/uninstall  │
├─────────────────────────────────────────────┤
│  HermesPluginBridge                            │
│  ├── build_tool_defs()   → Hermes tool schemas │
│  ├── export_as_skill()   → SKILL.md generation │
│  └── discover_hermes_skills()                  │
├─────────────────────────────────────────────┤
│  PluginRepository                              │
│  ├── remote index refresh                      │
│  ├── local/remote install                      │
│  ├── checksum verification                     │
│  └── search()                                  │
└─────────────────────────────────────────────┘
```

## Plugin Types

| Type | Description | Use Case |
|------|-------------|----------|
| `VALIDATOR` | Custom validation logic | Add domain-specific rules |
| `ADAPTER` | External system adapter | Connect to Slack, Jira, etc. |
| `HOOK` | Lifecycle hooks | Log state changes |
| `TOOL` | Hermes-compatible tool | Expose engine capabilities |
| `PROFILE` | Full product profile | New pipeline type |
| `STORE` | Storage backend | Custom persistence |
| `UI` | Dashboard/UI extension | Custom dashboard widgets |
| `INTEGRATION` | External service integration | API integrations |
| `OTHER` | Uncategorized | Anything else |

## Writing a Plugin

```python
from engine.plugin import PluginBase, PluginManifest, PluginType, PluginTool

class SlackPlugin(PluginBase):
    """Notify Slack on errors and state changes"""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="prodinamik.slack",
            name="Slack Integration",
            version="1.0.0",
            description="Send notifications to Slack channels",
            author="Yunus Güngör",
            plugin_type=PluginType.INTEGRATION,
            hooks=["on_error", "on_degrade"],
            provides_tools=["slack_send"],
            tags=["slack", "notifications"],
        )

    async def on_enable(self):
        self.log.info("Slack plugin enabled")
        # Initialize Slack client

    def get_tools(self):
        return [
            PluginTool(
                name="slack_send",
                description="Send a message to Slack channel",
                handler=self._send_message,
                parameters={
                    "channel": {"type": "string", "description": "Channel name"},
                    "message": {"type": "string", "description": "Message text"},
                },
            )
        ]

    async def _send_message(self, channel, message):
        # Implementation
        return {"ok": True, "channel": channel}
```

## Plugin Lifecycle

```
INSTALLED → DISABLED → ENABLED → DISABLED → UNINSTALLED
                           ↓
                       ERROR (recoverable)
```

## CLI Usage

```bash
# Discovery
prodinamik plugin discover                    # Scan built-in + plugin dirs
prodinamik plugin list                        # Show all plugins
prodinamik plugin list --enabled              # Only enabled
prodinamik plugin list --type integration     # Filter by type

# Management
prodinamik plugin enable prodinamik.slack     # Enable
prodinamik plugin disable prodinamik.slack    # Disable
prodinamik plugin info prodinamik.slack       # Show details
prodinamik plugin info prodinamik.slack --json # JSON output

# Installation
prodinamik plugin install my-plugin --source ./plugin.py
prodinamik plugin uninstall my-plugin

# Maintenance
prodinamik plugin reload                      # Hot-reload all
prodinamik plugin reload --plugin-id x        # Specific plugin
prodinamik plugin health                      # Health check all
```

## Hermes Agent Integration

Plugins can be automatically bridged to Hermes Agent through `HermesPluginBridge`:

```python
from engine.hermes_bridge import HermesPluginBridge
from engine.plugin_registry import PluginRegistry

registry = PluginRegistry(engine)
registry.discover()
asyncio.run(registry.enable("prodinamik.slack"))

bridge = HermesPluginBridge(registry=registry)

# Convert all plugin tools to Hermes-compatible tool definitions
tool_defs = bridge.build_tool_defs()
# → feeds directly into Hermes AIAgent

# Export as Hermes skill
bridge.export_as_skill("prodinamik.slack")
# → Creates ~/.hermes/skills/prodinamik-slack/SKILL.md
```

## Built-in Plugins

| Plugin ID | Name | Type | Description |
|-----------|------|------|-------------|
| `prodinamik.logging` | Logging Plugin | HOOK | Logs all state transitions and errors |

## Plugin Search Paths

Plugins are auto-discovered from:

1. **Built-in** — Shipped with the engine (e.g., `LoggingPlugin`)
2. **`./plugins/`** — Project-relative plugins
3. **`~/.hermes/plugins/`** — User-level plugins
4. **`/opt/hermes/plugins/`** — System-level plugins

## Configuration

Plugin configuration can be stored in `~/.hermes/config.yaml`:

```yaml
plugins:
  prodinamik.slack:
    enabled: true
    webhook_url: "https://hooks.slack.com/..."
    default_channel: "#alerts"
```
