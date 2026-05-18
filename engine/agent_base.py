"""Prodinamik Engine v1.3 — Agent Plugin Base

Abstract base class for autonomous agent plugins.
Agents can execute multi-step tasks using LLM providers,
Prodinamik Engine tools, and their own toolkits.

Usage:
    class MyAgent(AgentPlugin):
        @property
        def manifest(self):
            return PluginManifest(id="agent.myagent", ...)

        def run(self, goal, **kwargs):
            # Your agent loop here
            return {"result": "...", "steps": [...]}
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .plugin import PluginBase, PluginManifest, PluginType


@dataclass
class AgentStep:
    """A single step in an agent's execution plan"""
    step_id: str
    description: str
    tool: Optional[str] = None
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | running | completed | failed
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class AgentResult:
    """Result of an agent execution"""
    success: bool
    summary: str
    steps: List[AgentStep] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    total_duration_ms: float = 0.0


class AgentPlugin(PluginBase):
    """Base class for agent plugins.

    Subclasses must implement:
    - manifest (property)
    - run()

    Optionally implement:
    - chat()  (for interactive conversation)
    """

    plugin_type = PluginType.AGENT
    _abstract = True  # Mark as abstract for plugin discovery

    @abstractmethod
    def run(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_steps: int = 20,
        **kwargs,
    ) -> AgentResult:
        """Execute a multi-step task autonomously.

        Args:
            goal: The objective to accomplish
            context: Additional context (files, config, etc.)
            tools: Tool definitions available to the agent
            max_steps: Maximum planning/execution steps

        Returns:
            AgentResult with execution summary, steps, and output
        """
        ...

    def chat(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> str:
        """Interactive chat with the agent. Optional override.

        Args:
            message: User message
            history: Conversation history

        Returns:
            Agent response text
        """
        raise NotImplementedError("Chat not supported by this agent")
