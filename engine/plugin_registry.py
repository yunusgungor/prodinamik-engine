"""Prodinamik Engine v1.1 — Plugin Registry

Central registry for discovering, loading, and managing plugins.

Key features:
    - Directory-based auto-discovery (./plugins/, ~/.hermes/plugins/)
    - Dependency resolution (topological sort)
    - Plugin status management (enable/disable/error)
    - Hot-reload support (re-scan directories)
    - Metrics tracking per plugin
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from .log import get_logger
from .plugin import (
    PluginBase,
    PluginManifest,
    PluginState,
    PluginStatus,
    PluginHook,
    PluginTool,
    PluginType,
    discover_plugin_classes,
    load_plugin_from_file,
)
from .hooks import HookRegistry


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────


# Default plugin search paths (relative to engine root)
PLUGIN_DIRS = [
    "./plugins",
    "~/.hermes/plugins",
    "/opt/hermes/plugins",
]

# Built-in plugins shipped with the engine
BUILTIN_PLUGINS = [
    "engine.plugin.LoggingPlugin",
]


# ──────────────────────────────────────────────
# Dependency Resolution
# ──────────────────────────────────────────────


def resolve_dependencies(
    plugins: Dict[str, PluginManifest]
) -> Tuple[List[str], List[str]]:
    """Topological sort of plugin dependencies.

    Returns:
        (ordered_ids, unresolved)
    """
    visited: Set[str] = set()
    sorted_ids: List[str] = []
    unresolved: List[str] = []

    def visit(plugin_id: str, path: Set[str]):
        if plugin_id in visited:
            return
        if plugin_id in path:
            unresolved.append(f"Cycle detected: {' → '.join(path | {plugin_id})}")
            return

        manifest = plugins.get(plugin_id)
        if manifest is None:
            unresolved.append(f"Missing dependency: {plugin_id}")
            return

        path.add(plugin_id)
        for dep in manifest.dependencies:
            visit(dep, path)
        path.remove(plugin_id)

        visited.add(plugin_id)
        sorted_ids.append(plugin_id)

    for pid in plugins:
        if pid not in visited:
            visit(pid, set())

    return sorted_ids, unresolved


# ──────────────────────────────────────────────
# Plugin Registry
# ──────────────────────────────────────────────


class PluginRegistry:
    """Central registry for all plugins

    Singleton pattern — use PluginRegistry.get_instance() or
    access via engine.plugins.

    Usage:
        registry = PluginRegistry(engine)
        registry.discover()
        registry.enable("prodinamik.logging")
        registry.disable("prodinamik.myplugin")
    """

    _instance: Optional["PluginRegistry"] = None

    @classmethod
    def get_instance(cls, engine: Any = None) -> "PluginRegistry":
        """Get or create the singleton instance"""
        if cls._instance is None:
            if engine is None:
                raise RuntimeError("PluginRegistry not initialized. "
                                   "Call PluginRegistry(engine) first.")
            cls._instance = cls(engine)
        return cls._instance

    def __init__(self, engine: Any):
        if PluginRegistry._instance is not None:
            raise RuntimeError("PluginRegistry is a singleton. "
                               "Use PluginRegistry.get_instance()")
        PluginRegistry._instance = self

        self.engine = engine
        self.log = get_logger()
        self._plugins: Dict[str, PluginState] = {}
        self._search_paths: List[str] = list(PLUGIN_DIRS)
        self._hook_registry: Optional[HookRegistry] = getattr(
            engine, 'hooks', None
        )
        self._sorted_order: List[str] = []
        self._discovery_count: int = 0
        self._on_change_callbacks: List[Callable] = []

        self.log.info("PluginRegistry initialized")

    # ── Discovery ──────────────────────────────

    def discover(self, paths: Optional[List[str]] = None) -> int:
        """Discover plugins from search paths

        Returns count of newly discovered plugins.
        Scans: 1) built-in plugins, 2) configured search paths
        """
        if paths:
            self._search_paths = paths

        discovered = 0

        # 1. Built-in plugins
        for builtin_ref in BUILTIN_PLUGINS:
            plugin_cls = self._import_class(builtin_ref)
            if plugin_cls and issubclass(plugin_cls, PluginBase):
                if self._register_class(plugin_cls):
                    discovered += 1

        # 2. Search paths
        for search_path in self._search_paths:
            expanded = os.path.expanduser(search_path)
            if not os.path.isdir(expanded):
                continue
            count = self._discover_from_directory(expanded)
            discovered += count

        # 3. Resolve dependencies & order
        self._resolve()

        self._discovery_count += 1
        if discovered:
            self.log.info(f"Discovered {discovered} new plugins "
                          f"(total: {len(self._plugins)})")
            self._notify_change()

        return discovered

    def _discover_from_directory(self, directory: str) -> int:
        """Scan a directory for plugin files"""
        count = 0
        dir_path = Path(directory)

        # .py files
        for py_file in dir_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                plugin_classes = load_plugin_from_file(str(py_file))
                if plugin_classes:
                    if self._register_class(plugin_classes):
                        count += 1
            except Exception as e:
                self.log.warning(f"Failed to load {py_file}: {e}")

        # Subdirectories with __init__.py
        for subdir in dir_path.iterdir():
            if not subdir.is_dir():
                continue
            init_file = subdir / "__init__.py"
            if not init_file.exists():
                continue
            try:
                module_name = f"_plugin_pkg_{subdir.name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, str(init_file)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    for cls in discover_plugin_classes(module):
                        if self._register_class(cls):
                            count += 1
            except Exception as e:
                self.log.warning(f"Failed to load plugin package "
                                 f"{subdir.name}: {e}")

        return count

    def _import_class(self, dotted_path: str) -> Optional[Type[PluginBase]]:
        """Import a class from a dotted path like 'engine.plugin.LoggingPlugin'"""
        try:
            parts = dotted_path.split(".")
            module_path = ".".join(parts[:-1])
            class_name = parts[-1]
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name, None)
            if cls and inspect.isclass(cls) and issubclass(cls, PluginBase) and not inspect.isabstract(cls):
                return cls
            return None
        except Exception as e:
            self.log.debug(f"Failed to import {dotted_path}: {e}")
            return None

    def _register_class(self, plugin_cls: Type[PluginBase]) -> bool:
        """Register a plugin class. Returns True if newly registered."""
        try:
            # Instantiate to get manifest
            instance = plugin_cls(self.engine)
            manifest = instance.get_manifest()

            if manifest.id in self._plugins:
                existing = self._plugins[manifest.id]
                if existing.manifest and existing.manifest.version == manifest.version:
                    return False  # Already registered with same version

            state = PluginState(
                status=PluginStatus.DISABLED,
                manifest=manifest,
                instance=instance,
            )
            self._plugins[manifest.id] = state
            self.log.debug(f"Registered plugin: {manifest.id} v{manifest.version}")
            return True

        except Exception as e:
            self.log.warning(f"Failed to register {plugin_cls.__name__}: {e}")
            return False

    def _resolve(self) -> None:
        """Resolve dependency ordering"""
        manifests = {
            pid: state.manifest
            for pid, state in self._plugins.items()
            if state.manifest
        }
        ordered, unresolved = resolve_dependencies(manifests)
        self._sorted_order = ordered

        for issue in unresolved:
            self.log.warning(f"Dependency resolution: {issue}")

    # ── Plugin Management ──────────────────────

    async def enable(self, plugin_id: str) -> bool:
        """Enable a plugin by ID. Returns True on success."""
        state = self._plugins.get(plugin_id)
        if state is None:
            self.log.warning(f"Plugin not found: {plugin_id}")
            return False

        if state.status == PluginStatus.ENABLED:
            return True

        if state.status == PluginStatus.ERROR:
            state.error = None  # Reset error

        try:
            instance = state.instance
            if instance is None:
                return False

            await instance.on_enable()

            # Auto-register LLM providers
            if state.manifest.plugin_type == PluginType.LLM_PROVIDER:
                from .llm_registry import LLMProviderRegistry
                LLMProviderRegistry.get_instance().register(instance)

            # Register hooks if HookRegistry available
            if self._hook_registry:
                hooks = instance.get_hooks()
                for hook in hooks:
                    self._hook_registry.register(
                        state=f"plugin:{plugin_id}:{hook.state}",
                        hook_type=hook.hook_type.value,
                        handler=hook.handler,
                        description=hook.description,
                    )

            state.status = PluginStatus.ENABLED
            state.enabled_at = datetime.now()
            self.log.info(f"Plugin enabled: {plugin_id}")
            self._notify_change()
            return True

        except Exception as e:
            state.status = PluginStatus.ERROR
            state.error = str(e)
            state.last_error_at = datetime.now()
            state.error_count += 1
            self.log.error(f"Failed to enable plugin {plugin_id}: {e}")
            return False

    async def disable(self, plugin_id: str) -> bool:
        """Disable a plugin by ID. Returns True on success."""
        state = self._plugins.get(plugin_id)
        if state is None:
            return False

        if state.status != PluginStatus.ENABLED:
            return True

        try:
            instance = state.instance
            if instance:
                await instance.on_disable()

            state.status = PluginStatus.DISABLED
            self.log.info(f"Plugin disabled: {plugin_id}")
            self._notify_change()
            return True

        except Exception as e:
            self.log.error(f"Failed to disable plugin {plugin_id}: {e}")
            return False

    async def install(self, plugin_id: str, source: Optional[str] = None) -> bool:
        """Install a plugin (from source path or remote)."""
        if source and os.path.exists(source):
            # Install from local file
            plugin_cls = load_plugin_from_file(source)
            if plugin_cls and self._register_class(plugin_cls):
                state = self._plugins[plugin_id]
                if state.instance:
                    await state.instance.on_install()
                self.log.info(f"Plugin installed: {plugin_id} from {source}")
                self._notify_change()
                return True
            return False

        # Remote installation stub — would download from registry
        self.log.warning(f"Remote install not yet implemented for {plugin_id}")
        return False

    async def uninstall(self, plugin_id: str) -> bool:
        """Uninstall a plugin"""
        state = self._plugins.get(plugin_id)
        if state is None:
            return False

        try:
            if state.status == PluginStatus.ENABLED:
                await self.disable(plugin_id)

            instance = state.instance
            if instance:
                await instance.on_uninstall()

            del self._plugins[plugin_id]
            self._sorted_order = [p for p in self._sorted_order if p != plugin_id]
            self.log.info(f"Plugin uninstalled: {plugin_id}")
            self._notify_change()
            return True

        except Exception as e:
            self.log.error(f"Failed to uninstall plugin {plugin_id}: {e}")
            return False

    async def reload(self, plugin_id: str) -> bool:
        """Reload a plugin (disable → re-discover → enable)"""
        was_enabled = False
        state = self._plugins.get(plugin_id)
        if state and state.status == PluginStatus.ENABLED:
            was_enabled = True
            await self.disable(plugin_id)

        # Remove and re-register
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]

        # Re-discover from all paths
        self.discover()
        self._resolve()

        if was_enabled and plugin_id in self._plugins:
            return await self.enable(plugin_id)

        return plugin_id in self._plugins

    # ── Query ──────────────────────────────────

    def get(self, plugin_id: str) -> Optional[PluginState]:
        """Get plugin state by ID"""
        return self._plugins.get(plugin_id)

    def get_plugin_instance(self, plugin_id: str) -> Optional[PluginBase]:
        """Get plugin instance by ID"""
        state = self._plugins.get(plugin_id)
        return state.instance if state else None

    def list_plugins(
        self,
        status: Optional[PluginStatus] = None,
        plugin_type: Optional[PluginType] = None,
    ) -> List[PluginState]:
        """List plugins, optionally filtered"""
        plugins = list(self._plugins.values())
        if status:
            plugins = [p for p in plugins if p.status == status]
        if plugin_type:
            plugins = [
                p for p in plugins
                if p.manifest and p.manifest.plugin_type == plugin_type
            ]
        return plugins

    def get_enabled(self) -> List[PluginState]:
        """Get all enabled plugins"""
        return [p for p in self._plugins.values() if p.status == PluginStatus.ENABLED]

    @property
    def count(self) -> int:
        return len(self._plugins)

    @property
    def enabled_count(self) -> int:
        return sum(1 for p in self._plugins.values()
                   if p.status == PluginStatus.ENABLED)

    @property
    def plugin_ids(self) -> List[str]:
        return list(self._plugins.keys())

    def find_by_type(self, plugin_type: PluginType) -> List[PluginState]:
        """Find plugins by type"""
        return self.list_plugins(plugin_type=plugin_type)

    # ── Tools & Hooks Aggregation ──────────────

    def get_all_tools(self) -> List[PluginTool]:
        """Aggregate all tools from enabled plugins"""
        tools = []
        for state in self.get_enabled():
            if state.instance:
                tools.extend(state.instance.get_tools())
        return tools

    def get_all_hooks(self) -> List[PluginHook]:
        """Aggregate all hooks from enabled plugins"""
        hooks = []
        for state in self.get_enabled():
            if state.instance:
                hooks.extend(state.instance.get_hooks())
        return hooks

    def get_all_validators(self) -> List[Callable]:
        """Aggregate all validators from enabled plugins"""
        validators = []
        for state in self.get_enabled():
            if state.instance:
                validators.extend(state.instance.get_validators())
        return validators

    # ── Health & Metrics ───────────────────────

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Run health checks on all enabled plugins"""
        results = {}
        for pid, state in self._plugins.items():
            if state.instance:
                try:
                    results[pid] = await state.instance.health_check()
                except Exception as e:
                    results[pid] = {"healthy": False, "error": str(e)}
            else:
                results[pid] = {"healthy": False, "status": "no_instance"}
        return results

    def snapshot_metrics(self) -> Dict[str, Any]:
        """Snapshot of registry metrics for dashboard"""
        return {
            "total": self.count,
            "enabled": self.enabled_count,
            "disabled": self.count - self.enabled_count,
            "error": sum(1 for p in self._plugins.values()
                         if p.status == PluginStatus.ERROR),
            "by_type": self._count_by_type(),
        }

    def _count_by_type(self) -> Dict[str, int]:
        """Count plugins by type"""
        counts: Dict[str, int] = {}
        for state in self._plugins.values():
            if state.manifest:
                t = state.manifest.plugin_type.value
                counts[t] = counts.get(t, 0) + 1
        return counts

    # ── Serialization ──────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry state to dict"""
        return {
            k: {
                "id": v.manifest.id if v.manifest else k,
                "name": v.manifest.name if v.manifest else k,
                "version": v.manifest.version if v.manifest else "?",
                "status": v.status.value,
                "type": v.manifest.plugin_type.value if v.manifest else "unknown",
                "error": v.error,
                "enabled_at": v.enabled_at.isoformat() if v.enabled_at else None,
                "hooks": v.manifest.hooks if v.manifest else [],
                "tools": len(v.instance.get_tools()) if v.instance else 0,
            }
            for k, v in self._plugins.items()
        }

    # ── Events ─────────────────────────────────

    def on_change(self, callback: Callable) -> None:
        """Register callback for plugin state changes"""
        self._on_change_callbacks.append(callback)

    def _notify_change(self) -> None:
        """Notify all change listeners"""
        for cb in self._on_change_callbacks:
            try:
                cb(self)
            except Exception as e:
                self.log.error(f"PluginRegistry change callback error: {e}")

    # ── Engine Integration ─────────────────────

    def attach_to_engine(self) -> None:
        """Wire plugins into the engine runtime"""
        if not self.engine:
            return

        # Add plugin validators to engine's validator pipeline
        if hasattr(self.engine, 'validators'):
            pipeline = getattr(self.engine, 'validators', None)
            if pipeline and hasattr(pipeline, 'register'):
                for validator in self.get_all_validators():
                    pipeline.register(validator)

        # Emit startup hooks
        asyncio.ensure_future(self._emit_startup_hooks())

    async def _emit_startup_hooks(self):
        """Fire ON_STARTUP hooks for all enabled plugins"""
        for state in self.get_enabled():
            if state.instance:
                hook = PluginHook(
                    hook_type=type('t', (), {'value': 'on_startup'})(),
                    state="",
                    handler=lambda: None,
                )
                try:
                    await state.instance.on_enable()
                except Exception as e:
                    self.log.warning("Startup hook error for plugin %s: %s", pid, e)

    def shutdown(self) -> None:
        """Disable all plugins on shutdown"""
        for pid in list(self._plugins.keys()):
            state = self._plugins[pid]
            if state.status == PluginStatus.ENABLED:
                try:
                    if state.instance:
                        asyncio.run(state.instance.on_disable())
                except Exception as e:
                    self.log.error(f"Plugin shutdown error {pid}: {e}")
            state.status = PluginStatus.DISABLED
