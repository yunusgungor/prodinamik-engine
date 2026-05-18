"""Prodinamik AI Grid — Tool Executor

Converts Plugin Registry tools into callable functions for the agent.
Each enabled plugin's tools are discoverable and executable.

Architecture:
    ToolExecutor
    ├── PluginAdapter (wraps PluginBase → tool function)
    ├── ToolRegistry (maps tool_name → callable handler)
    ├── ToolExecution (async execution, timeout, error handling)
    └── ToolCache (optional result caching)

Usage:
    executor = ToolExecutor(plugin_registry)
    result = await executor.execute("tool_name", {"param": "value"})
"""

from __future__ import annotations

import asyncio
import inspect
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..log import get_logger
from ..plugin import PluginBase, PluginTool


# ── Tool Status ──


class ToolStatus(Enum):
    """Runtime status of a registered tool"""
    AVAILABLE = "available"
    BUSY = "busy"
    ERROR = "error"
    DISABLED = "disabled"


# ── Tool Execution Record ──


@dataclass
class ToolExecutionRecord:
    """Record of a single tool execution"""
    tool_name: str
    input_params: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ── Tool Handler ──


@dataclass
class ToolHandler:
    """Internal handler for a registered tool"""
    name: str
    handler: Callable
    timeout: float = 30.0
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


# ── Tool Executor ──


class ToolExecutor:
    """
    Executes tools from the Plugin Registry for agent use.

    Each enabled plugin's tools become callable functions.
    Supports:
    - PluginBase tools via PluginTool declarations
    - Direct callable registration
    - Async execution with timeout
    - Result caching
    - Execution history tracking
    - OpenAPI-style tool definitions for LLM consumption
    """

    def __init__(
        self,
        plugin_registry: Optional[Any] = None,  # PluginRegistry
        default_timeout: float = 30.0,
    ):
        self.plugin_registry = plugin_registry
        self.default_timeout = default_timeout
        self.log = get_logger()

        # Tool registry: tool_name → ToolHandler
        self._tools: Dict[str, ToolHandler] = {}
        self._history: List[ToolExecutionRecord] = []
        self._cache: Dict[str, Any] = {}
        self._status: Dict[str, ToolStatus] = {}

        # Auto-discover plugins if registry available
        if plugin_registry is not None:
            self._init_tools()

    # ── Initialization ──────────────────────────

    def _init_tools(self) -> None:
        """Auto-discover tools from plugin registry"""
        if not self.plugin_registry:
            return

        try:
            enabled = self.plugin_registry.get_enabled()
            for state in enabled:
                instance = state.instance
                if not instance:
                    continue

                # Get PluginTool declarations from the instance
                plugin_tools = instance.get_tools()
                for pt in plugin_tools:
                    self.register_plugin_tool(pt, instance)

                # Auto-register adapter methods as tools
                adapters = instance.get_adapters()
                for name, adapter in adapters.items():
                    self._register_adapter(name, adapter)

        except Exception as e:
            self.log.debug(f"Tool auto-discovery error: {e}")

    # ── Registration ────────────────────────────

    def register_plugin_tool(self, plugin_tool: PluginTool, instance: PluginBase) -> None:
        """Register a PluginTool from a plugin instance"""
        name = plugin_tool.name
        handler = plugin_tool.handler
        timeout = getattr(plugin_tool, 'timeout', self.default_timeout)

        # If handler is an unbound function that references instance methods,
        # try to bind it to the instance
        if hasattr(handler, '__name__') and not hasattr(handler, '__self__'):
            try:
                method_name = handler.__name__
                bound = getattr(instance, method_name, None)
                if bound is not None and callable(bound):
                    handler = bound
            except (AttributeError, TypeError):
                pass  # Use original handler

        desc = getattr(plugin_tool, 'description', '')
        params = getattr(plugin_tool, 'parameters', {})

        self._register(name, handler, timeout, desc, params)

    def register(
        self,
        name: str,
        handler: Callable,
        timeout: Optional[float] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a direct tool function"""
        self._register(
            name,
            handler,
            timeout or self.default_timeout,
            description,
            parameters or {},
        )

    def _register(
        self,
        name: str,
        handler: Callable,
        timeout: float,
        description: str,
        parameters: Dict[str, Any],
    ) -> None:
        """Internal registration"""
        self._tools[name] = ToolHandler(
            name=name,
            handler=handler,
            timeout=timeout,
            description=description,
            parameters=parameters,
        )
        self._status[name] = ToolStatus.AVAILABLE
        self.log.debug(f"Tool registered: {name}")

    def _register_adapter(self, name: str, adapter: Any) -> None:
        """Register adapter methods as tools"""
        if callable(adapter):
            self._register(
                name=name,
                handler=adapter,
                timeout=self.default_timeout,
                description=getattr(adapter, '__doc__', '') or f'Adapter: {name}',
                parameters={},
            )
        else:
            # Adapter is an object — register its public methods
            for method_name in dir(adapter):
                if method_name.startswith('_'):
                    continue
                method = getattr(adapter, method_name)
                if callable(method):
                    self._register(
                        name=f"{name}.{method_name}",
                        handler=method,
                        timeout=self.default_timeout,
                        description=method.__doc__ or f'{name}.{method_name}',
                        parameters={},
                    )

    # ── Execution ───────────────────────────────

    async def execute(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute a tool asynchronously

        Args:
            tool_name: Name of the registered tool.
            parameters: Keyword arguments to pass to the tool handler.
            timeout: Override the default timeout for this call.

        Returns:
            Result dict with keys: 'success', 'result' or 'error',
            plus metadata ('_tool', '_duration_ms').
        """
        handler = self._tools.get(tool_name)
        if not handler:
            available = list(self._tools.keys())
            return {
                "error": f"Tool '{tool_name}' not found",
                "available": available,
                "_tool": tool_name,
            }

        self._status[tool_name] = ToolStatus.BUSY
        params = parameters or {}
        start = time.time()
        effective_timeout = timeout or handler.timeout
        result: Any = None

        try:
            if asyncio.iscoroutinefunction(handler.handler):
                # Native async handler
                result = await asyncio.wait_for(
                    handler.handler(**params),
                    timeout=effective_timeout,
                )
            elif inspect.isgeneratorfunction(handler.handler):
                # Sync generator — run in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: list(handler.handler(**params))
                )
            else:
                # Plain sync function — run in executor
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: handler.handler(**params)),
                    timeout=effective_timeout,
                )

            duration_ms = (time.time() - start) * 1000

            # Normalize result to a dict
            result_dict = self._normalize_result(result, tool_name, duration_ms)
            result_dict["success"] = True

            # Record history
            self._history.append(ToolExecutionRecord(
                tool_name=tool_name,
                input_params=params,
                output=result_dict,
                duration_ms=duration_ms,
                success=True,
            ))

            self._status[tool_name] = ToolStatus.AVAILABLE
            return result_dict

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start) * 1000
            self._status[tool_name] = ToolStatus.AVAILABLE
            err = f"Tool '{tool_name}' timed out after {effective_timeout}s"
            self._history.append(ToolExecutionRecord(
                tool_name=tool_name,
                input_params=params,
                duration_ms=duration_ms,
                success=False,
                error=err,
            ))
            return {
                "error": err,
                "_tool": tool_name,
                "_duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self._status[tool_name] = ToolStatus.ERROR
            self._history.append(ToolExecutionRecord(
                tool_name=tool_name,
                input_params=params,
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            ))
            return {
                "error": str(e),
                "_trace": traceback.format_exc(),
                "_tool": tool_name,
                "_duration_ms": duration_ms,
            }

    def _normalize_result(
        self,
        result: Any,
        tool_name: str,
        duration_ms: float,
    ) -> Dict[str, Any]:
        """Normalize any result type to a consistent dict"""
        if result is None:
            result_dict: Dict[str, Any] = {"result": None}
        elif isinstance(result, dict):
            result_dict = dict(result)
        elif hasattr(result, 'model_dump'):
            # Pydantic v2
            result_dict = result.model_dump()
        elif hasattr(result, 'dict'):
            # Pydantic v1 or similar
            result_dict = result.dict()
        elif hasattr(result, '__dict__'):
            # Plain object
            result_dict = {"result": result.__dict__}
        else:
            result_dict = {"result": result}

        result_dict.setdefault("_tool", tool_name)
        result_dict.setdefault("_duration_ms", duration_ms)
        return result_dict

    # ── Tool Chaining ───────────────────────────

    async def chain(
        self,
        tool_definitions: List[Dict[str, Any]],
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Chain multiple tool executions, piping output → input

        Each tool definition:
            {"tool": "tool_name", "params": {...}, "map": {"from_key": "to_key"}}

        The ``map`` field renames output keys to input keys for the next tool.
        If ``params`` contains a string value that starts with ``$``, it is
        treated as a reference to a key from the previous tool output.
        """
        results: List[Dict[str, Any]] = []
        context = dict(initial_context or {})

        for definition in tool_definitions:
            tool_name = definition["tool"]
            params = dict(definition.get("params", {}))

            # Resolve parameter references from context
            for key, value in list(params.items()):
                if isinstance(value, str) and value.startswith("$"):
                    ref_key = value[1:]
                    params[key] = context.get(ref_key, value)

            # Execute the tool
            result = await self.execute(tool_name, params)

            # Apply output mapping to context
            output_map = definition.get("map", {})
            for from_key, to_key in output_map.items():
                if from_key in result:
                    context[to_key] = result[from_key]
                elif "result" in result and isinstance(result["result"], dict):
                    if from_key in result["result"]:
                        context[to_key] = result["result"][from_key]

            results.append(result)

        return results

    # ── LLM Integration ─────────────────────────

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAPI-style tool definitions for LLM consumption

        Returns a list of tool descriptors suitable for function-calling
        APIs (OpenAI, Anthropic, etc.).
        """
        return [
            {
                "name": h.name,
                "description": h.description,
                "parameters": h.parameters,
            }
            for h in self._tools.values()
        ]

    # ── Query ───────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get executor status overview"""
        return {
            "tools": {
                name: {
                    "status": self._status.get(name, ToolStatus.DISABLED).value,
                    "description": self._tools[name].description if name in self._tools else "",
                }
                for name in self._tools
            },
            "available_count": sum(
                1 for s in self._status.values() if s == ToolStatus.AVAILABLE
            ),
            "history_count": len(self._history),
            "cache_size": len(self._cache),
        }

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent tool execution history"""
        return [
            {
                "tool": r.tool_name,
                "duration_ms": r.duration_ms,
                "success": r.success,
                "error": r.error,
                "timestamp": r.timestamp,
            }
            for r in self._history[-limit:]
        ]

    def clear_history(self) -> None:
        """Clear execution history"""
        self._history.clear()

    def get_available_tools(self) -> List[str]:
        """Get list of registered tool names"""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered"""
        return name in self._tools

    @property
    def tool_count(self) -> int:
        """Number of registered tools"""
        return len(self._tools)


# ── Caching Decorator ──


class ToolCache:
    """Simple TTL-based result cache for tool executions

    Usage:
        cache = ToolCache(ttl=60)
        executor = ToolExecutor(registry)
        # Wrap execute to use cache
        original = executor.execute

        async def cached_execute(name, params=None, timeout=None):
            key = f"{name}:{json.dumps(params, sort_keys=True)}"
            return await cache.get_or_set(key, lambda: original(name, params, timeout))

        executor.execute = cached_execute
    """

    def __init__(self, ttl: float = 60.0):
        self._store: Dict[str, tuple[float, Any]] = {}
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if still fresh"""
        entry = self._store.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if time.time() > expiry:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Cache a value"""
        self._store[key] = (time.time() + (ttl or self.ttl), value)

    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: Optional[float] = None,
    ) -> Any:
        """Get cached value or compute and cache it"""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
        self.set(key, value, ttl)
        return value

    def invalidate(self, key: str) -> None:
        """Remove a specific cache entry"""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Clear all cached entries"""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
