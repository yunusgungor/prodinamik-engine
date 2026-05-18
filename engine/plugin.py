"""Prodinamik Engine v1.1 — Plugin Base System

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
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type


# ──────────────────────────────────────────────
# Enums & Constants
# ──────────────────────────────────────────────


class PluginStatus(Enum):
    """Lifecycle status of a plugin"""
    INSTALLED = "installed"
    DISABLED = "disabled"
    ENABLED = "enabled"
    ERROR = "error"
    UNINSTALLED = "uninstalled"


class PluginHookType(Enum):
    """Hook types a plugin can register against"""
    ON_STATE_ENTER = "on_state_enter"
    ON_STATE_EXIT = "on_state_exit"
    ON_VALIDATE = "on_validate"
    ON_TRANSITION = "on_transition"
    ON_RUN_CREATED = "on_run_created"
    ON_RUN_COMPLETED = "on_run_completed"
    ON_ERROR = "on_error"
    ON_DEGRADE = "on_degrade"
    ON_METRICS_POLL = "on_metrics_poll"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"


class PluginType(Enum):
    """Classification of plugin"""
    VALIDATOR = "validator"        # Custom validation logic
    ADAPTER = "adapter"            # External system adapter
    HOOK = "hook"                  # Lifecycle hooks
    TOOL = "tool"                  # Hermes-compatible tool
    PROFILE = "profile"            # Full product profile
    STORE = "store"                # Storage backend
    UI = "ui"                      # Dashboard/UI extension
    INTEGRATION = "integration"    # External service integration
    OTHER = "other"                # Uncategorized


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class PluginManifest:
    """Declarative metadata for a plugin"""
    id: str                              # Unique plugin ID (e.g., "prodinamik.slack")
    name: str                            # Human-readable name
    version: str                         # SemVer (e.g., "1.0.0")
    description: str = ""
    author: str = ""
    license: str = "MIT"
    plugin_type: PluginType = PluginType.OTHER
    homepage: str = ""
    repository: str = ""

    # Dependencies
    requires_python: str = ">=3.10"
    requires_engine: str = ">=1.1.0"
    dependencies: List[str] = field(default_factory=list)  # Plugin IDs
    optional_dependencies: List[str] = field(default_factory=list)

    # Registration
    hooks: List[str] = field(default_factory=list)          # Hook types
    states: List[str] = field(default_factory=list)         # States to hook into
    provides_tools: List[str] = field(default_factory=list) # Tool names
    provides_adapters: List[str] = field(default_factory=list)
    provides_validators: List[str] = field(default_factory=list)

    # Compatibility
    hermes_skill_name: str = ""          # Corresponding Hermes skill
    tags: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        """Validate manifest completeness. Returns list of issues."""
        issues = []
        if not self.id or not isinstance(self.id, str):
            issues.append("Plugin ID is required and must be a string")
        if not self.name:
            issues.append("Plugin name is required")
        if not self.version:
            issues.append("Plugin version is required")
        return issues


@dataclass
class PluginTool:
    """A tool exposed by a plugin for Hermes integration"""
    name: str
    description: str
    handler: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    requires_engine: bool = True
    timeout: int = 30


@dataclass
class PluginHook:
    """A hook registration from a plugin"""
    hook_type: PluginHookType
    state: str                          # Target state (empty = all)
    handler: Callable
    priority: int = 0                   # Higher = earlier execution
    description: str = ""
    async_mode: bool = True             # True = await, False = fire-and-forget


@dataclass
class PluginState:
    """Runtime state of a plugin instance"""
    status: PluginStatus = PluginStatus.INSTALLED
    manifest: Optional[PluginManifest] = None
    instance: Optional["PluginBase"] = None
    module: Any = None
    error: Optional[str] = None
    enabled_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    error_count: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_enabled(self) -> bool:
        return self.status == PluginStatus.ENABLED

    @property
    def is_error(self) -> bool:
        return self.status == PluginStatus.ERROR


# ──────────────────────────────────────────────
# Plugin Base Class
# ──────────────────────────────────────────────


class PluginBase(ABC):
    """Abstract base class for all Prodinamik Engine plugins

    Subclasses must implement:
        - manifest property (class-level or instance)
        - on_install / on_uninstall  (can be no-op)
        - on_enable / on_disable      (can be no-op)

    Subclasses may override:
        - get_tools()     → return list of PluginTool
        - get_hooks()     → return list of PluginHook
        - get_validators() → return list of validator callables
        - on_error(error)  → custom error handler
    """

    def __init__(self, engine: Any = None):
        self.engine = engine
        self._logger = None
        self._state = PluginState(manifest=self.get_manifest())
        self._config: Dict[str, Any] = {}

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return the plugin manifest"""
        ...

    def get_manifest(self) -> PluginManifest:
        """Override if manifest needs dynamic construction"""
        return self.manifest

    # ── Lifecycle ──────────────────────────────

    async def on_install(self) -> None:
        """Called when plugin is first installed"""
        pass

    async def on_uninstall(self) -> None:
        """Called when plugin is being removed"""
        pass

    async def on_enable(self) -> None:
        """Called when plugin transitions from disabled → enabled"""
        pass

    async def on_disable(self) -> None:
        """Called when plugin transitions from enabled → disabled"""
        pass

    async def on_error(self, error: Exception) -> None:
        """Called when an error occurs in the plugin"""
        self._state.last_error_at = datetime.now()
        self._state.error_count += 1
        self._state.error = str(error)

    # ── Plugin Capabilities ────────────────────

    def get_tools(self) -> List[PluginTool]:
        """Return list of tools this plugin exposes"""
        return []

    def get_hooks(self) -> List[PluginHook]:
        """Return list of hooks this plugin registers"""
        return []

    def get_validators(self) -> List[Callable]:
        """Return list of validator functions"""
        return []

    def get_adapters(self) -> Dict[str, Any]:
        """Return dict of adapter instances keyed by name"""
        return {}

    # ── Configuration ──────────────────────────

    def configure(self, config: Dict[str, Any]) -> None:
        """Apply configuration to the plugin"""
        self._config.update(config)
        self._apply_config()

    def _apply_config(self) -> None:
        """Apply current config (override in subclasses)"""
        pass

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a config value"""
        return self._config.get(key, default)

    # ── Runtime Status ─────────────────────────

    @property
    def state(self) -> PluginState:
        return self._state

    @property
    def status(self) -> PluginStatus:
        return self._state.status

    @property
    def is_healthy(self) -> bool:
        """Override for custom health checks"""
        return self._state.status == PluginStatus.ENABLED

    async def health_check(self) -> Dict[str, Any]:
        """Return health check result. Override in subclasses."""
        return {
            "healthy": self.is_healthy,
            "status": self.status.value,
            "error": self._state.error,
        }

    # ── Registration Helpers ───────────────────

    def register_hooks(self, registry: "HookRegistry") -> None:
        """Register hooks with an engine HookRegistry"""
        for hook in self.get_hooks():
            registry.register(
                state=hook.state or "*",
                hook_type=hook.hook_type.value,
                handler=hook.handler,
                description=hook.description,
            )

    # ── Internal ───────────────────────────────

    def __repr__(self) -> str:
        m = self.get_manifest()
        return f"<Plugin {m.id} v{m.version} [{self.status.value}]>"


# ──────────────────────────────────────────────
# Built-in Plugin Metadata
# ──────────────────────────────────────────────


class BuiltinPluginMeta(type):
    """Metaclass for built-in plugins that auto-creates manifest"""

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        # Auto-generate manifest for built-in plugins
        if not getattr(cls, 'abstract', False) and not inspect.isabstract(cls):
            if not hasattr(cls, 'manifest') or isinstance(cls.manifest, PluginManifest):
                pass  # Already defined
        return cls


# ──────────────────────────────────────────────
# Example Plugin: Logging Plugin
# ──────────────────────────────────────────────


class LoggingPlugin(PluginBase):
    """Built-in plugin that logs state transitions"""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="prodinamik.logging",
            name="Logging Plugin",
            version="1.0.0",
            description="Logs all state transitions and errors",
            plugin_type=PluginType.HOOK,
            hooks=["on_state_enter", "on_state_exit", "on_error"],
        )

    def __init__(self, engine=None):
        super().__init__(engine)
        from .log import get_logger
        self.log = get_logger()

    def get_hooks(self) -> List[PluginHook]:
        async def log_enter(state: str, run_id: str, **kwargs):
            self.log.info(f"[Plugin:Logging] Run {run_id} entered state {state}")

        async def log_exit(state: str, run_id: str, **kwargs):
            self.log.debug(f"[Plugin:Logging] Run {run_id} exited state {state}")

        async def log_error(error: Exception, context: dict):
            self.log.error(f"[Plugin:Logging] Error: {error}", extra=context)

        return [
            PluginHook(PluginHookType.ON_STATE_ENTER, "*", log_enter, description="Log state enter"),
            PluginHook(PluginHookType.ON_STATE_EXIT, "*", log_exit, description="Log state exit"),
            PluginHook(PluginHookType.ON_ERROR, "", log_error, description="Log errors"),
        ]


# ──────────────────────────────────────────────
# Plugin Loader Utilities
# ──────────────────────────────────────────────


def discover_plugin_classes(module: Any) -> List[Type[PluginBase]]:
    """Discover all PluginBase subclasses in a module"""
    plugins = []
    for name, obj in inspect.getmembers(module):
        if (inspect.isclass(obj)
                and issubclass(obj, PluginBase)
                and obj is not PluginBase
                and not getattr(obj, '_abstract', False)):
            plugins.append(obj)
    return plugins


def load_plugin_from_file(filepath: str) -> Optional[Type[PluginBase]]:
    """Load a plugin class from a Python file"""
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        return None

    module_name = f"_plugin_{os.path.splitext(os.path.basename(filepath))[0]}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    plugins = discover_plugin_classes(module)
    return plugins[0] if plugins else None
