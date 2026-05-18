"""Prodinamik Engine v1.1 — Phase 9: Plugin Ecosystem Tests

Tests for:
- Plugin base class, manifest, types (engine/plugin.py)
- Plugin registry (engine/plugin_registry.py)
- Hermes bridge (engine/hermes_bridge.py)
- Plugin repository (engine/plugin_repo.py)
"""

import os
import json
import tempfile
import shutil
import asyncio
from pathlib import Path

import pytest


# ══════════════════════════════════════════════
# Plugin Base Tests
# ══════════════════════════════════════════════


class TestPluginManifest:
    """Plugin manifest data validation"""

    def test_manifest_defaults(self):
        from engine.plugin import PluginManifest, PluginType

        m = PluginManifest(
            id="test.my-plugin",
            name="My Plugin",
            version="1.0.0",
        )
        assert m.id == "test.my-plugin"
        assert m.name == "My Plugin"
        assert m.version == "1.0.0"
        assert m.plugin_type == PluginType.OTHER
        assert m.license == "MIT"
        assert m.dependencies == []
        assert m.hooks == []

    def test_manifest_validation_empty_id(self):
        from engine.plugin import PluginManifest

        m = PluginManifest(id="", name="", version="")
        issues = m.validate()
        assert len(issues) >= 1
        assert any("ID" in i for i in issues)

    def test_manifest_full(self):
        from engine.plugin import PluginManifest, PluginType

        m = PluginManifest(
            id="prodinamik.slack",
            name="Slack Integration",
            version="2.1.0",
            description="Slack adapter for notifications",
            author="Yunus Güngör",
            license="MIT",
            plugin_type=PluginType.INTEGRATION,
            dependencies=["prodinamik.webhook"],
            hooks=["on_error", "on_degrade"],
            provides_tools=["slack_send", "slack_search"],
            tags=["slack", "notifications", "chat"],
        )
        assert m.plugin_type == PluginType.INTEGRATION
        assert "prodinamik.webhook" in m.dependencies
        assert "slack_send" in m.provides_tools
        assert len(m.tags) == 3


class TestPluginBase:
    """PluginBase ABC implementation"""

    def test_minimal_plugin(self):
        """A minimal plugin with mandatory fields"""
        from engine.plugin import PluginBase, PluginManifest, PluginStatus

        class MinimalPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(
                    id="test.minimal",
                    name="Minimal Plugin",
                    version="0.1.0",
                )

        p = MinimalPlugin()
        assert p.manifest.id == "test.minimal"
        assert p.status == PluginStatus.INSTALLED
        assert not p.is_healthy  # INSTALLED != ENABLED
        assert repr(p) == "<Plugin test.minimal v0.1.0 [installed]>"

    def test_plugin_lifecycle(self):
        """Test enable/disable lifecycle"""
        from engine.plugin import PluginBase, PluginManifest, PluginStatus

        enabled_called = False
        disabled_called = False

        class LifecyclePlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.lifecycle", name="Lifecycle", version="1.0.0")

            async def on_enable(self):
                nonlocal enabled_called
                enabled_called = True

            async def on_disable(self):
                nonlocal disabled_called
                disabled_called = True

        p = LifecyclePlugin()
        assert p.status == PluginStatus.INSTALLED

        # Enable
        asyncio.run(p.on_enable())
        assert enabled_called

        # Disable
        asyncio.run(p.on_disable())
        assert disabled_called

    def test_plugin_install_uninstall(self):
        """Test install/uninstall lifecycle hooks"""
        from engine.plugin import PluginBase, PluginManifest

        installed = False
        uninstalled = False

        class InstallPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.install", name="Install Test", version="1.0.0")

            async def on_install(self):
                nonlocal installed
                installed = True

            async def on_uninstall(self):
                nonlocal uninstalled
                uninstalled = True

        p = InstallPlugin()
        asyncio.run(p.on_install())
        assert installed

        asyncio.run(p.on_uninstall())
        assert uninstalled

    def test_plugin_tools(self):
        """Plugin tool registration"""
        from engine.plugin import PluginBase, PluginManifest, PluginTool

        class ToolPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.tools", name="Tool Plugin", version="1.0.0")

            def get_tools(self):
                return [
                    PluginTool(
                        name="greet",
                        description="Greet a user",
                        handler=lambda name: f"Hello {name}!",
                        parameters={"name": {"type": "string", "description": "User name"}},
                    ),
                    PluginTool(
                        name="ping",
                        description="Health check ping",
                        handler=lambda: "pong",
                    ),
                ]

        p = ToolPlugin()
        tools = p.get_tools()
        assert len(tools) == 2

        t1 = tools[0]
        assert t1.name == "greet"
        assert "Greet" in t1.description
        assert "name" in t1.parameters

        t2 = tools[1]
        assert t2.name == "ping"

    def test_plugin_hooks(self):
        """Plugin hook registration"""
        from engine.plugin import PluginBase, PluginManifest, PluginHook, PluginHookType

        class HookPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(
                    id="test.hooks", name="Hook Plugin", version="1.0.0",
                    hooks=["on_state_enter", "on_error"],
                )

            def get_hooks(self):
                return [
                    PluginHook(PluginHookType.ON_STATE_ENTER, "review", lambda: None),
                    PluginHook(PluginHookType.ON_ERROR, "", lambda e: None),
                ]

        p = HookPlugin()
        hooks = p.get_hooks()
        assert len(hooks) == 2

        h1 = hooks[0]
        assert h1.hook_type == PluginHookType.ON_STATE_ENTER
        assert h1.state == "review"

        h2 = hooks[1]
        assert h2.hook_type == PluginHookType.ON_ERROR

    def test_plugin_validators(self):
        """Plugin validator registration"""
        from engine.plugin import PluginBase, PluginManifest

        class ValidatorPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.validators", name="Validator", version="1.0.0")

            def get_validators(self):
                def check_content(content):
                    return {"pass": True, "score": 10}

                def check_format(content):
                    return {"pass": True}

                return [check_content, check_format]

        p = ValidatorPlugin()
        validators = p.get_validators()
        assert len(validators) == 2

    def test_plugin_config(self):
        """Plugin configuration"""
        from engine.plugin import PluginBase, PluginManifest

        class ConfigPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.config", name="Config", version="1.0.0")

        p = ConfigPlugin()
        assert p.get_config("key") is None
        assert p.get_config("key", "default") == "default"

        p.configure({"api_key": "abc123", "timeout": 30})
        assert p.get_config("api_key") == "abc123"
        assert p.get_config("timeout") == 30

    def test_plugin_health_check(self):
        """Plugin health check"""
        from engine.plugin import PluginBase, PluginManifest, PluginStatus

        class HealthyPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.health", name="Health", version="1.0.0")

        p = HealthyPlugin()
        result = asyncio.run(p.health_check())
        assert "healthy" in result
        assert "status" in result

    def test_logging_plugin_builtin(self):
        """Built-in LoggingPlugin works"""
        from engine.plugin import LoggingPlugin

        p = LoggingPlugin()
        assert p.manifest.id == "prodinamik.logging"
        assert p.manifest.plugin_type.value == "hook"

        hooks = p.get_hooks()
        assert len(hooks) == 3

        tools = p.get_tools()
        assert len(tools) == 0

        # Not yet enabled, so is_healthy returns False by default
        assert not p.is_healthy


class TestPluginTypes:
    """Plugin type enum and tools"""

    def test_all_plugin_types(self):
        from engine.plugin import PluginType

        types = [t.value for t in PluginType]
        assert "validator" in types
        assert "adapter" in types
        assert "hook" in types
        assert "tool" in types
        assert "profile" in types
        assert "integration" in types
        assert "other" in types

    def test_plugin_hook_types(self):
        from engine.plugin import PluginHookType

        types = [t.value for t in PluginHookType]
        assert "on_state_enter" in types
        assert "on_state_exit" in types
        assert "on_validate" in types
        assert "on_error" in types
        assert "on_startup" in types
        assert "on_shutdown" in types


class TestPluginLoader:
    """Plugin loading utilities"""

    def test_discover_plugin_classes_empty(self):
        """Discover from empty module yields empty list"""
        from engine.plugin import discover_plugin_classes

        import types
        mod = types.ModuleType("test_empty")
        mod.SomeClass = type("SomeClass", (), {})
        mod.NotAPlugin = "string"

        plugins = discover_plugin_classes(mod)
        assert plugins == []

    def test_load_plugin_from_file(self):
        """Load a plugin from a .py file"""
        from engine.plugin import load_plugin_from_file, PluginBase

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('''
from engine.plugin import PluginBase, PluginManifest

class FilePlugin(PluginBase):
    @property
    def manifest(self):
        return PluginManifest(id="test.file-loaded", name="File Plugin", version="1.0.0")
''')
            f.flush()
            plugin_cls = load_plugin_from_file(f.name)

        os.unlink(f.name)

        assert plugin_cls is not None
        assert issubclass(plugin_cls, PluginBase)

        instance = plugin_cls()
        assert instance.manifest.id == "test.file-loaded"

    def test_load_plugin_nonexistent_file(self):
        """Loading from nonexistent file returns None"""
        from engine.plugin import load_plugin_from_file

        assert load_plugin_from_file("/nonexistent/plugin.py") is None


# ══════════════════════════════════════════════
# Plugin Registry Tests
# ══════════════════════════════════════════════


class FakeEngine:
    """Minimal engine stub for registry tests"""
    def __init__(self):
        self.hooks = None
        self.validators = None


class TestPluginRegistry:
    """PluginRegistry lifecycle"""

    def setup_method(self):
        # Reset singleton
        from engine.plugin_registry import PluginRegistry
        PluginRegistry._instance = None

    def test_singleton(self):
        """PluginRegistry is a singleton"""
        from engine.plugin_registry import PluginRegistry

        engine = FakeEngine()
        r1 = PluginRegistry(engine)
        r2 = PluginRegistry.get_instance(engine)

        assert r1 is r2

    def test_singleton_double_init_raises(self):
        """Double init raises RuntimeError"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        engine = FakeEngine()
        PluginRegistry(engine)

        with pytest.raises(RuntimeError, match="singleton"):
            PluginRegistry(FakeEngine())

    def test_initial_state(self):
        """Fresh registry has no plugins"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())

        assert registry.count == 0
        assert registry.enabled_count == 0
        assert registry.plugin_ids == []

    def test_discover_builtin(self):
        """Discover built-in plugins (LoggingPlugin)"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())

        count = registry.discover()
        assert count >= 1  # At least LoggingPlugin

        logging_state = registry.get("prodinamik.logging")
        assert logging_state is not None
        assert logging_state.manifest.name == "Logging Plugin"

    def test_enable_disable_plugin(self):
        """Enable and disable a plugin"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginStatus

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        # Enable
        asyncio.run(registry.enable("prodinamik.logging"))
        state = registry.get("prodinamik.logging")
        assert state.status == PluginStatus.ENABLED

        # Disable
        asyncio.run(registry.disable("prodinamik.logging"))
        state = registry.get("prodinamik.logging")
        assert state.status == PluginStatus.DISABLED

    def test_enable_nonexistent(self):
        """Enabling a nonexistent plugin returns False"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())

        result = asyncio.run(registry.enable("nonexistent.plugin"))
        assert not result

    def test_enable_twice_is_noop(self):
        """Enabling an already-enabled plugin is a no-op"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginStatus

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        asyncio.run(registry.enable("prodinamik.logging"))
        asyncio.run(registry.enable("prodinamik.logging"))

        state = registry.get("prodinamik.logging")
        assert state.status == PluginStatus.ENABLED
        assert state.error_count == 0

    def test_list_plugins_filter(self):
        """List plugins with status filter"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginStatus

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        all_plugins = registry.list_plugins()
        disabled = registry.list_plugins(status=PluginStatus.DISABLED)
        enabled = registry.list_plugins(status=PluginStatus.ENABLED)

        assert len(all_plugins) >= 1
        assert len(disabled) >= 1  # Initially all disabled
        assert len(enabled) == 0

    def test_enabled_count(self):
        """Enabled count reflects active plugins"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        assert registry.enabled_count == 0
        asyncio.run(registry.enable("prodinamik.logging"))
        assert registry.enabled_count == 1

    def test_get_all_tools(self):
        """Aggregate tools from enabled plugins"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginBase, PluginManifest, PluginTool, PluginStatus, PluginState

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())

        # Register plugin with tools
        class TooledPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(id="test.tooled", name="Tooled", version="1.0.0")
            def get_tools(self):
                return [PluginTool(name="test_tool", description="Test", handler=lambda: None)]

        tooled = TooledPlugin(FakeEngine())
        ps = PluginState(
            status=PluginStatus.ENABLED,
            manifest=tooled.manifest,
            instance=tooled,
        )
        registry._plugins["test.tooled"] = ps

        tools = registry.get_all_tools()
        assert len(tools) == 1
        assert tools[0].name == "test_tool"

    def test_snapshot_metrics(self):
        """Metrics snapshot works"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        metrics = registry.snapshot_metrics()
        assert "total" in metrics
        assert "enabled" in metrics
        assert "disabled" in metrics
        assert "error" in metrics
        assert "by_type" in metrics
        assert metrics["total"] >= 1

    def test_to_dict(self):
        """Serialization to dict works"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        data = registry.to_dict()
        assert "prodinamik.logging" in data
        assert data["prodinamik.logging"]["name"] == "Logging Plugin"

    def test_change_callback(self):
        """Change callbacks fire"""
        from engine.plugin_registry import PluginRegistry

        callback_called = [False]

        def on_change(reg):
            callback_called[0] = True

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.on_change(on_change)
        registry.discover()

        assert callback_called[0]

    def test_health_check_all(self):
        """Health check for all plugins"""
        from engine.plugin_registry import PluginRegistry

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        results = asyncio.run(registry.health_check_all())
        assert "prodinamik.logging" in results

    def test_find_by_type(self):
        """Find plugins by type"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginType

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()

        hook_plugins = registry.find_by_type(PluginType.HOOK)
        assert len(hook_plugins) >= 1  # LoggingPlugin is HOOK type

    def test_shutdown(self):
        """Shutdown disables all plugins"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginStatus

        PluginRegistry._instance = None
        registry = PluginRegistry(FakeEngine())
        registry.discover()
        asyncio.run(registry.enable("prodinamik.logging"))

        registry.shutdown()

        state = registry.get("prodinamik.logging")
        assert state.status == PluginStatus.DISABLED


class TestDependencyResolution:
    """Plugin dependency resolution"""

    def test_resolve_no_deps(self):
        """Plugins with no dependencies"""
        from engine.plugin_registry import resolve_dependencies
        from engine.plugin import PluginManifest

        plugins = {
            "a": PluginManifest(id="a", name="A", version="1.0.0"),
            "b": PluginManifest(id="b", name="B", version="1.0.0"),
        }
        ordered, unresolved = resolve_dependencies(plugins)
        assert len(ordered) == 2
        assert unresolved == []

    def test_resolve_simple_deps(self):
        """Simple dependency chain a -> b -> c"""
        from engine.plugin_registry import resolve_dependencies
        from engine.plugin import PluginManifest

        plugins = {
            "a": PluginManifest(id="a", name="A", version="1.0.0", dependencies=["b"]),
            "b": PluginManifest(id="b", name="B", version="1.0.0", dependencies=["c"]),
            "c": PluginManifest(id="c", name="C", version="1.0.0"),
        }
        ordered, unresolved = resolve_dependencies(plugins)
        # c must come before b before a
        assert ordered.index("c") < ordered.index("b")
        assert ordered.index("b") < ordered.index("a")
        assert unresolved == []

    def test_resolve_circular_deps(self):
        """Circular dependency is detected"""
        from engine.plugin_registry import resolve_dependencies
        from engine.plugin import PluginManifest

        plugins = {
            "a": PluginManifest(id="a", name="A", version="1.0.0", dependencies=["b"]),
            "b": PluginManifest(id="b", name="B", version="1.0.0", dependencies=["a"]),
        }
        ordered, unresolved = resolve_dependencies(plugins)
        assert len(unresolved) >= 1
        assert any("Cycle" in u for u in unresolved)

    def test_resolve_missing_dep(self):
        """Missing dependency is reported"""
        from engine.plugin_registry import resolve_dependencies
        from engine.plugin import PluginManifest

        plugins = {
            "a": PluginManifest(id="a", name="A", version="1.0.0", dependencies=["b"]),
        }
        ordered, unresolved = resolve_dependencies(plugins)
        assert len(unresolved) >= 1
        assert any("Missing" in u for u in unresolved)


# ══════════════════════════════════════════════
# Hermes Bridge Tests
# ══════════════════════════════════════════════


class TestHermesPluginBridge:
    """HermesPluginBridge conversion and discovery"""

    def setup_method(self):
        from engine.plugin_registry import PluginRegistry
        PluginRegistry._instance = None

    def test_bridge_init(self):
        """Bridge initializes without error"""
        from engine.hermes_bridge import HermesPluginBridge

        bridge = HermesPluginBridge(hermes_home="/tmp/hermes-test")
        assert bridge.hermes_home == "/tmp/hermes-test"
        assert bridge.metrics["tools_built"] == 0

    def test_build_tool_defs_empty(self):
        """No tools when no registry or plugins"""
        from engine.hermes_bridge import HermesPluginBridge

        bridge = HermesPluginBridge()
        tools = bridge.build_tool_defs()
        assert tools == []

    def test_build_tool_defs(self):
        """Build tool defs from registry with LoggingPlugin"""
        from engine.plugin_registry import PluginRegistry
        from engine.hermes_bridge import HermesPluginBridge

        registry = PluginRegistry(FakeEngine())
        registry.discover()
        asyncio.run(registry.enable("prodinamik.logging"))

        bridge = HermesPluginBridge(registry=registry)
        tools = bridge.build_tool_defs()

        # LoggingPlugin has no tools, so empty
        assert tools == []

    def test_convert_tool(self):
        """Convert PluginTool to HermesToolDef"""
        from engine.plugin import PluginTool, PluginManifest, PluginType
        from engine.hermes_bridge import HermesPluginBridge

        plugin_tool = PluginTool(
            name="test_op",
            description="Test operation",
            handler=lambda x: x,
            parameters={"x": {"type": "integer", "description": "Input"}},
        )
        manifest = PluginManifest(
            id="test.manifest", name="Test", version="1.0.0",
            plugin_type=PluginType.TOOL,
        )

        bridge = HermesPluginBridge()
        hermes_tool = bridge._convert_tool(plugin_tool, manifest)

        assert hermes_tool.name.startswith("prodinamik__")
        assert "Test" in hermes_tool.description
        assert "properties" in hermes_tool.parameters
        assert "x" in hermes_tool.parameters["properties"]
        assert hermes_tool.timeout == 30

    def test_discover_hermes_skills_nonexistent(self):
        """Discover skills from nonexistent directory returns empty"""
        from engine.hermes_bridge import HermesPluginBridge

        bridge = HermesPluginBridge(hermes_home="/nonexistent-hermes")
        skills = bridge.discover_hermes_skills()
        assert skills == []

    def test_discover_hermes_skills(self):
        """Discover skills from a temp Hermes directory"""
        from engine.hermes_bridge import HermesPluginBridge

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock prodinamik skill
            skill_dir = Path(tmpdir) / "skills" / "prodinamik-logging"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---
name: prodinamik-logging
description: "Prodinamik Logging Plugin Skill"
version: 1.0.0
tags: ["prodinamik", "logging", "plugin"]
category: prodinamik-plugins
---

# Logging Skill
"""
            )

            bridge = HermesPluginBridge(hermes_home=tmpdir)
            skills = bridge.discover_hermes_skills()

            assert len(skills) == 1
            assert skills[0]["name"] == "prodinamik-logging"

    def test_export_as_skill(self):
        """Export plugin as Hermes skill file"""
        from engine.plugin_registry import PluginRegistry
        from engine.hermes_bridge import HermesPluginBridge

        registry = PluginRegistry(FakeEngine())
        registry.discover()

        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = HermesPluginBridge(registry=registry, hermes_home=tmpdir)
            skill_path = bridge.export_as_skill("prodinamik.logging", output_dir=tmpdir)

            assert skill_path is not None
            assert os.path.exists(skill_path)

            content = Path(skill_path).read_text()
            assert "Logging Plugin" in content
            assert "prodinamik-logging" in content

    def test_export_nonexistent(self):
        """Exporting nonexistent plugin returns None"""
        from engine.hermes_bridge import HermesPluginBridge

        bridge = HermesPluginBridge()
        result = bridge.export_as_skill("nonexistent.plugin")
        assert result is None

    def test_bridge_metrics(self):
        """Bridge metrics accumulate correctly"""
        from engine.hermes_bridge import HermesPluginBridge

        bridge = HermesPluginBridge()
        assert bridge.metrics["tools_built"] == 0
        assert bridge.metrics["bridge_errors"] == 0

        bridge._bridge_metrics["tools_built"] += 3
        assert bridge.metrics["tools_built"] == 3

    def test_parse_simple_yaml(self):
        """Simple YAML parse works for config"""
        from engine.hermes_bridge import HermesPluginBridge

        bridge = HermesPluginBridge()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write('''
plugins:
  prodinamik.logging:
    enabled: true
    level: debug
''')
            f.flush()
            config = bridge._parse_simple_yaml(f.name)

        os.unlink(f.name)

        assert "plugins" in config
        assert "prodinamik.logging" in config["plugins"]
        assert config["plugins"]["prodinamik.logging"]["enabled"] is True


# ══════════════════════════════════════════════
# Plugin Repository Tests
# ══════════════════════════════════════════════


class TestPluginRepository:
    """PluginRepository management"""

    def test_init(self):
        """Repository initializes with storage directory"""
        from engine.plugin_repo import PluginRepository, PLUGIN_STORAGE_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            assert os.path.exists(tmpdir)
            assert repo.list_installed() == []

    def test_list_installed_empty(self):
        """Fresh install has no plugins"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            assert repo.list_installed() == []

    def test_list_available_empty(self):
        """Available plugins is empty before refresh"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            assert repo.list_available() == []

    def test_search_empty(self):
        """Search returns empty when no index loaded"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            results = repo.search("slack")
            assert results == []

    def test_is_installed(self):
        """Not-installed check returns False"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            assert not repo.is_installed("nonexistent")

    def test_local_install(self):
        """Install plugin from local directory"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=os.path.join(tmpdir, "plugins"))

            # Create a source plugin
            src = Path(tmpdir) / "source-plugin"
            src.mkdir()
            (src / "__init__.py").write_text('# Test plugin')

            success, msg = repo.install_local(str(src), plugin_id="test.local")
            assert success
            assert "installed" in msg
            assert repo.is_installed("test.local")

    def test_local_install_file(self):
        """Install plugin from a .py file"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=os.path.join(tmpdir, "plugins"))

            src = Path(tmpdir) / "my_plugin.py"
            src.write_text('# file plugin')

            success, msg = repo.install_local(str(src), plugin_id="test.file")
            assert success

    def test_local_install_nonexistent(self):
        """Installing nonexistent source returns error"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            success, msg = repo.install_local("/nonexistent")
            assert not success
            assert "not found" in msg

    def test_local_install_already_exists(self):
        """Installing over existing returns error"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=os.path.join(tmpdir, "plugins"))

            src = Path(tmpdir) / "source"
            src.mkdir()
            (src / "__init__.py").write_text('')

            repo.install_local(str(src), plugin_id="test.dup")
            success, msg = repo.install_local(str(src), plugin_id="test.dup")
            assert not success
            assert "already installed" in msg

    def test_uninstall(self):
        """Uninstall removes plugin"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=os.path.join(tmpdir, "plugins"))

            src = Path(tmpdir) / "source"
            src.mkdir()
            (src / "__init__.py").write_text('')

            repo.install_local(str(src), plugin_id="test.to-remove")
            assert repo.is_installed("test.to-remove")

            success, msg = repo.uninstall("test.to-remove")
            assert success
            assert not repo.is_installed("test.to-remove")

    def test_uninstall_nonexistent(self):
        """Uninstalling nonexistent returns error"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            success, msg = repo.uninstall("nonexistent")
            assert not success
            assert "not installed" in msg

    def test_register_index(self):
        """Register a remote index URL"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            repo.register_index("https://example.com/plugins.json")
            assert "https://example.com/plugins.json" in repo.index_urls

    def test_local_index_snapshot(self):
        """Local index snapshot structure"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=os.path.join(tmpdir, "plugins"))

            snapshot = repo.local_index_snapshot()
            assert "installed" in snapshot
            assert "available_remote" in snapshot
            assert "plugins" in snapshot

    def test_checksum_computation(self):
        """Checksum computation for files and directories"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)

            # Single file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello world")
            checksum = repo._compute_checksum(str(test_file))
            assert len(checksum) == 64  # SHA256 hex

            # Directory
            checksum_dir = repo._compute_checksum(tmpdir)
            assert len(checksum_dir) == 64

    def test_detect_version(self):
        """Detect version from __init__.py"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)
            path = Path(tmpdir) / "test-pkg"
            path.mkdir()
            (path / "__init__.py").write_text('''
__version__ = "2.0.0"
''')

            version = repo._detect_version(path)
            assert version == "2.0.0"

    def test_engine_compatibility(self):
        """Engine version compatibility checks"""
        from engine.plugin_repo import PluginRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PluginRepository(storage_dir=tmpdir)

            # >=1.0.0 should be compatible with 1.2.0
            assert repo._check_engine_compatibility(">=1.0.0")
            # ==1.2.0 should be compatible
            assert repo._check_engine_compatibility("==1.2.0")
            # ==2.0.0 should NOT be compatible
            assert not repo._check_engine_compatibility("==2.0.0")


# ══════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════


class TestPluginIntegration:
    """End-to-end plugin workflows"""

    def setup_method(self):
        from engine.plugin_registry import PluginRegistry
        PluginRegistry._instance = None

    def test_full_lifecycle(self):
        """Full plugin lifecycle: discover → enable → disable → uninstall"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginStatus

        registry = PluginRegistry(FakeEngine())

        # Discover
        registry.discover()
        assert registry.count >= 1

        # Enable
        asyncio.run(registry.enable("prodinamik.logging"))
        assert registry.get("prodinamik.logging").status == PluginStatus.ENABLED

        # Get tools
        tools = registry.get_all_tools()
        assert isinstance(tools, list)

        # Get hooks
        hooks = registry.get_all_hooks()
        assert isinstance(hooks, list)

        # Health check
        health = asyncio.run(registry.health_check_all())
        assert "prodinamik.logging" in health

        # Disable
        asyncio.run(registry.disable("prodinamik.logging"))
        assert registry.get("prodinamik.logging").status == PluginStatus.DISABLED

    def test_custom_plugin_registration(self):
        """Register and manage a custom plugin via registry"""
        from engine.plugin_registry import PluginRegistry
        from engine.plugin import PluginBase, PluginManifest, PluginStatus

        registry = PluginRegistry(FakeEngine())

        # Create and register a custom plugin
        class CustomPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(
                    id="custom.test",
                    name="Custom Test Plugin",
                    version="0.5.0",
                )

        plugin = CustomPlugin(FakeEngine())
        ps = type('PluginState', (), {
            'status': PluginStatus.DISABLED,
            'manifest': plugin.manifest,
            'instance': plugin,
            'error': None,
            'enabled_at': None,
            'last_error_at': None,
            'error_count': 0,
            'metrics': {},
            'is_enabled': False,
            'is_error': False,
        })()
        registry._plugins["custom.test"] = ps

        assert registry.get("custom.test") is not None
        assert registry.get("custom.test").manifest.version == "0.5.0"

        # Enable
        asyncio.run(registry.enable("custom.test"))
        assert registry.get("custom.test").status == PluginStatus.ENABLED

    def test_hermes_bridge_full_cycle(self):
        """Hermes bridge: registry → tool defs → export → discover"""
        from engine.plugin_registry import PluginRegistry
        from engine.hermes_bridge import HermesPluginBridge
        from engine.plugin import PluginBase, PluginManifest, PluginTool, PluginStatus

        registry = PluginRegistry(FakeEngine())
        registry.discover()

        # Add a plugin with tools
        class ToolPlugin(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(
                    id="test.tool-plugin",
                    name="Tool Plugin",
                    version="1.0.0",
                    provides_tools=["custom_op"],
                )
            def get_tools(self):
                return [
                    PluginTool(
                        name="custom_op",
                        description="Custom operation",
                        handler=lambda x: x * 2,
                        parameters={"x": {"type": "integer"}},
                    )
                ]

        tool_plugin = ToolPlugin(FakeEngine())
        ps = type('PluginState', (), {
            'status': PluginStatus.ENABLED,
            'manifest': tool_plugin.manifest,
            'instance': tool_plugin,
            'error': None,
            'enabled_at': None,
            'last_error_at': None,
            'error_count': 0,
            'metrics': {},
            'is_enabled': True,
            'is_error': False,
        })()
        registry._plugins["test.tool-plugin"] = ps

        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = HermesPluginBridge(registry=registry, hermes_home=tmpdir)

            # Build tool defs
            tools = bridge.build_tool_defs()
            assert len(tools) >= 1

            # Export as skill
            skill_path = bridge.export_as_skill("test.tool-plugin", output_dir=tmpdir)
            assert skill_path is not None

            # Discover skills
            skills = bridge.discover_hermes_skills()
            assert isinstance(skills, list)
