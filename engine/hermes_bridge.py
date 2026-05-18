"""Prodinamik Engine v1.1 — Hermes Agent Bridge

Bridges Prodinamik Engine plugins to the Hermes Agent environment.

Key capabilities:
    - Convert PluginTools to Hermes-compatible tool definitions
    - Auto-discover Hermes skills and register as Prodinamik plugins
    - Plugin → Hermes skill mapping with on-demand installation
    - Tool execution proxy (engine state injection, error wrapping)
    - Hermes config integration (plugin config stored in ~/.hermes/config.yaml)
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from .log import get_logger
from .plugin import (
    PluginBase,
    PluginManifest,
    PluginTool,
    PluginHook,
    PluginHookType,
    PluginType,
    PluginStatus,
)
from .plugin_registry import PluginRegistry


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────


HERMES_SKILLS_DIR = "~/.hermes/skills"
HERMES_CONFIG_PATH = "~/.hermes/config.yaml"
HERMES_PLUGIN_CONFIG_SECTION = "plugins"

PRODINAMIK_SKILL_NAMESPACE = "prodinamik"


# ──────────────────────────────────────────────
# Hermes Tool Definition Format
# ──────────────────────────────────────────────


@dataclass
class HermesToolDef:
    """A tool definition compatible with Hermes Agent's tool format"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable
    category: str = "plugin"
    timeout: int = 30


# ──────────────────────────────────────────────
# Hermes Plugin Bridge
# ──────────────────────────────────────────────


class HermesPluginBridge:
    """Bridge between Prodinamik PluginRegistry and Hermes Agent

    Converts plugins to Hermes skills/tools and injects engine state
    into tool execution context.

    Usage:
        bridge = HermesPluginBridge(registry, hermes_home="~/.hermes")
        tools = bridge.build_tool_defs()
        # → feed tools into Hermes AIAgent
    """

    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        hermes_home: str = "~/.hermes",
    ):
        self.registry = registry
        self.hermes_home = os.path.expanduser(hermes_home)
        self.skills_dir = os.path.join(self.hermes_home, "skills")
        self.log = get_logger()
        self._tool_cache: Dict[str, HermesToolDef] = {}
        self._bridge_metrics = {
            "tools_built": 0,
            "skills_scanned": 0,
            "skills_imported": 0,
            "bridge_errors": 0,
        }

    # ── Tool Conversion ────────────────────────

    def build_tool_defs(self) -> List[HermesToolDef]:
        """Build Hermes-compatible tool definitions from all enabled plugins

        Returns list of HermesToolDef for use in AIAgent tool schemas.
        """
        tool_defs: List[HermesToolDef] = []

        if not self.registry:
            return tool_defs

        for state in self.registry.get_enabled():
            if not state.instance:
                continue

            plugin_tools = state.instance.get_tools()
            for pt in plugin_tools:
                hermes_tool = self._convert_tool(pt, state.manifest)
                tool_defs.append(hermes_tool)
                self._tool_cache[hermes_tool.name] = hermes_tool
                self._bridge_metrics["tools_built"] += 1

        return tool_defs

    def _convert_tool(
        self,
        plugin_tool: PluginTool,
        manifest: Optional[PluginManifest],
    ) -> HermesToolDef:
        """Convert a PluginTool to HermesToolDef with engine state injection"""
        original_handler = plugin_tool.handler

        async def wrapped_handler(**kwargs):
            """Wrapper that injects engine state and handles errors"""
            try:
                # Inject engine context if requested
                if plugin_tool.requires_engine and self.registry:
                    engine = getattr(self.registry, 'engine', None)
                    if engine:
                        kwargs['_engine'] = engine
                        kwargs['_plugin_id'] = manifest.id if manifest else "unknown"

                # Execute with timeout
                if plugin_tool.timeout > 0:
                    result = await asyncio.wait_for(
                        original_handler(**kwargs),
                        timeout=plugin_tool.timeout,
                    )
                else:
                    result = await original_handler(**kwargs)

                return result

            except asyncio.TimeoutError:
                self.log.warning(
                    f"Plugin tool '{plugin_tool.name}' timed out "
                    f"({plugin_tool.timeout}s)"
                )
                return {"error": f"Tool timed out after {plugin_tool.timeout}s",
                        "tool": plugin_tool.name}
            except Exception as e:
                self._bridge_metrics["bridge_errors"] += 1
                self.log.error(f"Plugin tool '{plugin_tool.name}' error: {e}")
                return {"error": str(e), "tool": plugin_tool.name}

        # Build JSON schema from parameters
        properties = {}
        required = []
        for param_name, param_def in plugin_tool.parameters.items():
            if isinstance(param_def, dict):
                properties[param_name] = param_def
                if param_def.get("required", False):
                    required.append(param_name)
            else:
                properties[param_name] = {"type": "string", "description": str(param_def)}

        return HermesToolDef(
            name=f"{PRODINAMIK_SKILL_NAMESPACE}__{plugin_tool.name}",
            description=(
                f"[Plugin: {manifest.name if manifest else 'unknown'}] "
                f"{plugin_tool.description}"
            ),
            parameters={
                "type": "object",
                "properties": properties,
                "required": required if required else None,
            },
            handler=wrapped_handler,
            timeout=plugin_tool.timeout,
        )

    # ── Hermes Skills Discovery ────────────────

    def discover_hermes_skills(self) -> List[Dict[str, Any]]:
        """Scan Hermes skills directory for prodinamik-related skills

        Returns list of skill metadata dicts.
        """
        skills = []
        skills_path = Path(self.skills_dir)

        if not skills_path.exists():
            return skills

        for skill_dir in skills_path.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            # Read skill metadata from frontmatter
            meta = self._parse_skill_frontmatter(skill_file)
            if meta and self._is_prodinamik_skill(meta):
                skills.append({
                    "name": skill_dir.name,
                    "path": str(skill_dir),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "?"),
                    "tags": meta.get("tags", []),
                })

        self._bridge_metrics["skills_scanned"] = len(skills)
        return skills

    def _parse_skill_frontmatter(self, skill_file: Path) -> Optional[Dict[str, Any]]:
        """Parse YAML-style frontmatter from a SKILL.md file"""
        try:
            content = skill_file.read_text(errors="replace")
            if not content.startswith("---"):
                return None

            # Simple frontmatter parser (no YAML dependency)
            _, fm, _ = content.split("---", 2)
            meta = {}
            for line in fm.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    # Parse lists: [a, b, c]
                    if value.startswith("[") and value.endswith("]"):
                        items = [x.strip().strip('"').strip("'")
                                 for x in value[1:-1].split(",")]
                        value = items

                    meta[key] = value
            return meta
        except Exception as e:
            self.log.debug("Failed to parse skill frontmatter %s: %s", skill_file, e)
            return None

    def _is_prodinamik_skill(self, meta: Dict[str, Any]) -> bool:
        """Check if a skill is related to Prodinamik Engine"""
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        name = meta.get("name", "").lower()
        description = meta.get("description", "").lower()

        prodinamik_keywords = ["prodinamik", "state machine", "validator pipeline",
                               "engine", "profile", "content-os", "dev-cycle",
                               "haber-kurator"]

        for keyword in prodinamik_keywords:
            if keyword in name or keyword in description:
                return True
            if isinstance(tags, list):
                if any(keyword in tag.lower() for tag in tags):
                    return True
        return False

    # ── Plugin → Hermes Skill Export ───────────

    def export_as_skill(self, plugin_id: str, output_dir: Optional[str] = None) -> Optional[str]:
        """Export a plugin as a Hermes-compatible skill

        Creates a SKILL.md file in the Hermes skills directory.
        Returns path to the created skill file, or None on failure.
        """
        if not self.registry:
            return None

        state = self.registry.get(plugin_id)
        if not state or not state.manifest or not state.instance:
            return None

        manifest = state.manifest
        instance = state.instance

        skill_dir = output_dir or os.path.join(
            self.skills_dir, f"{PRODINAMIK_SKILL_NAMESPACE}-{manifest.id.replace('.', '-')}"
        )
        os.makedirs(skill_dir, exist_ok=True)

        skill_path = os.path.join(skill_dir, "SKILL.md")

        # Generate tools documentation
        tools_doc = ""
        for tool in instance.get_tools():
            params = ", ".join(tool.parameters.keys()) if tool.parameters else "none"
            tools_doc += f"- `{tool.name}({params})` — {tool.description}\n"

        hooks_doc = ""
        for hook in instance.get_hooks():
            hooks_doc += f"- `{hook.hook_type.value}` on '{hook.state}' — {hook.description}\n"

        skill_content = f"""---
name: {PRODINAMIK_SKILL_NAMESPACE}-{manifest.id.replace('.', '-')}
description: "{manifest.description}"
version: {manifest.version}
tags: [{', '.join([f'"{t}"' for t in manifest.tags])}]
category: prodinamik-plugins
---

# {manifest.name} v{manifest.version}

> {manifest.description}

## Plugin Details

| Field | Value |
|-------|-------|
| **ID** | `{manifest.id}` |
| **Type** | {manifest.plugin_type.value} |
| **Author** | {manifest.author} |
| **License** | {manifest.license} |
| **Homepage** | {manifest.homepage} |

## Tools

{tools_doc if tools_doc else "_No tools exported_"}""".strip()

        # Add hooks section if present
        if hooks_doc:
            skill_content += f"\n\n## Hooks\n\n{hooks_doc}"

        with open(skill_path, "w") as f:
            f.write(skill_content)

        self._bridge_metrics["skills_imported"] += 1
        self.log.info(f"Exported plugin {plugin_id} as skill: {skill_path}")
        return skill_path

    # ── Hermes Config Integration ──────────────

    def read_hermes_plugin_config(self) -> Dict[str, Any]:
        """Read plugin config from Hermes config.yaml"""
        config_path = os.path.join(self.hermes_home, "config.yaml")
        if not os.path.exists(config_path):
            return {}

        try:
            # Simple YAML-like parser
            config = self._parse_simple_yaml(config_path)
            return config.get(HERMES_PLUGIN_CONFIG_SECTION, {})
        except Exception as e:
            self._bridge_metrics["bridge_errors"] += 1
            self.log.warning(f"Failed to read Hermes config: {e}")
            return {}

    def _parse_simple_yaml(self, path: str) -> Dict[str, Any]:
        """Simple nested YAML parser for config"""
        result: Dict[str, Any] = {}
        current = result
        stack: List[Dict[str, Any]] = []

        with open(path) as f:
            for line in f:
                stripped = line.rstrip()
                if not stripped or stripped.startswith("#"):
                    continue

                indent = len(line) - len(line.lstrip())
                content = stripped.strip()

                if content.endswith(":"):
                    key = content[:-1].strip()
                    new_dict = {}
                    # Adjust nesting based on indentation
                    while stack and len(stack) > indent // 2:
                        stack.pop()
                    if stack:
                        stack[-1][key] = new_dict
                    else:
                        result[key] = new_dict
                    stack.append(new_dict)
                elif ":" in content:
                    key, value = content.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    # Parse booleans and numbers
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    while stack and len(stack) > indent // 2:
                        stack.pop()
                    if stack:
                        stack[-1][key] = value
                    else:
                        result[key] = value

        return result

    # ── Plugin Installation from Hermes Context ─

    def install_from_hermes_skill(self, skill_name: str) -> bool:
        """Discover and install a Prodinamik plugin from a Hermes skill

        Scans the Hermes skill directory for the given skill and
        attempts to find and register any Prodinamik plugin within it.
        """
        skill_path = Path(self.skills_dir) / skill_name
        if not skill_path.exists():
            self.log.warning(f"Hermes skill not found: {skill_name}")
            return False

        # Look for .py files with PluginBase subclasses
        found = False
        for py_file in skill_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                from .plugin import load_plugin_from_file
                plugin_cls = load_plugin_from_file(str(py_file))
                if plugin_cls and self.registry:
                    self.registry._register_class(plugin_cls)
                    found = True
                    self.log.info(f"Installed plugin from skill {skill_name}: "
                                  f"{py_file.name}")
            except Exception as e:
                self.log.warning(f"Failed to load {py_file}: {e}")

        return found

    # ── Metrics ────────────────────────────────

    @property
    def metrics(self) -> Dict[str, Any]:
        """Bridge metrics for dashboard"""
        return dict(self._bridge_metrics)

    def reset_metrics(self) -> None:
        """Reset bridge metrics"""
        for key in self._bridge_metrics:
            self._bridge_metrics[key] = 0
