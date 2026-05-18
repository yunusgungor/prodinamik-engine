"""Prodinamik AI Grid — Agent Worker (Loop Engine)

Full Observe→Think→Act→Observe cycle for autonomous task execution.

Lifecycle:
    worker:pending → worker:initializing → worker:observing → 
    worker:thinking → worker:acting → worker:observing (loop) →
    worker:reporting → worker:completed / worker:failed

The worker:
1. OBSERVE: Read current state (context, memory, tools available)
2. THINK: LLM call → plan next action(s)
3. ACT: Execute tool call or produce output
4. OBSERVE: Read tool result / environment response
5. REPEAT until goal achieved or max_steps exceeded
6. REPORT: Summarize results, update memory
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..log import get_logger


# ── Agent Step Type ──


class StepType(Enum):
    """Categorisation of a single step in the agent's execution trace"""
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    OBSERVATION = "observation"
    REPORT = "report"


@dataclass
class StepRecord:
    """A single step in the agent's execution trace"""
    step_number: int
    step_type: StepType
    content: str = ""
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    token_count: int = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ── Agent Worker ──


class AgentWorker:
    """
    Full Loop Engine implementing Observe→Think→Act→Observe.

    Each worker instance handles one task autonomously.
    Uses LLM provider for thinking, ToolExecutor for actions,
    ContextManager for token budget management, and Memory for persistence.

    Usage:
        worker = AgentWorker(worker_id="w-abc", goal="...", ...)
        result = await worker.execute()
    """

    def __init__(
        self,
        worker_id: str,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        llm_provider: Optional[Any] = None,  # LLMProviderPlugin instance
        max_steps: int = 20,
        timeout: float = 300.0,
    ) -> None:
        self.worker_id = worker_id
        self.goal = goal
        self.context = context or {}
        self.tools = tools or []
        self.llm_provider = llm_provider
        self.max_steps = max_steps
        self.timeout = timeout
        self.log = get_logger()

        # Execution trace
        self.steps: List[StepRecord] = []
        self._step_count = 0

        # Internal components (lazy init)
        self._context_mgr: Optional[Any] = None
        self._memory: Optional[Any] = None
        self._tool_executor: Optional[Any] = None

        # System prompt (built from goal + context + tools)
        self._system_prompt: str = ""

        # Token tracking
        self.total_tokens: int = 0
        self.total_cost_estimate: float = 0.0

        # Output
        self._final_output: Dict[str, Any] = {}

    # ── Public API ──

    async def execute(self) -> Any:
        """Run the full O→T→A→O loop. Returns AgentResult from agent_base."""
        from ..agent_base import AgentResult

        start_time = time.time()

        try:
            # 1. Initialize components
            self._initialize()

            # 2. Build system prompt
            self._build_system_prompt()

            # 3. Main loop
            for step_idx in range(1, self.max_steps + 1):
                self._step_count = step_idx

                # === OBSERVE phase ===
                observation = await self._observe()
                self._record_step(StepType.OBSERVATION, observation, duration_ms=0)

                # === THINK phase ===
                thought = await self._think()
                self._record_step(
                    StepType.THOUGHT,
                    thought.get("content", ""),
                    token_count=thought.get("usage", {}).get("total_tokens", 0),
                )

                # === ACT phase ===
                action = thought.get("action", {})
                action_type = action.get("type", "none")

                if action_type == "tool_call":
                    result = await self._act(action)
                    self._record_step(
                        StepType.TOOL_CALL,
                        content=f"Tool: {action.get('tool_name', 'unknown')}",
                        tool_name=action.get("tool_name", ""),
                        tool_input=action.get("parameters", {}),
                        tool_output=result,
                        duration_ms=result.get("_duration_ms", 0),
                    )
                elif action_type == "complete":
                    # Goal achieved
                    self._final_output = action.get("output", {})
                    self._record_step(
                        StepType.REPORT,
                        action.get("summary", "Goal achieved"),
                    )
                    break
                elif action_type == "error":
                    self._record_step(
                        StepType.REPORT,
                        action.get("error", "Unknown error"),
                    )
                    return AgentResult(
                        success=False,
                        summary=action.get("error", "Agent encountered an error"),
                        steps=self._convert_steps(),
                        error=action.get("error"),
                        output=self._final_output,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )
                else:
                    # Continue (thinking only, no action needed)
                    pass

                await asyncio.sleep(0)  # Yield to event loop

            # 4. Build final result
            elapsed_ms = (time.time() - start_time) * 1000

            # Check if max steps reached without completion
            if self._step_count >= self.max_steps:
                summary = f"Max steps ({self.max_steps}) reached"
                return AgentResult(
                    success=False,
                    summary=summary,
                    steps=self._convert_steps(),
                    output=self._final_output,
                    total_duration_ms=elapsed_ms,
                )

            # Final memory save (async)
            if self._memory:
                try:
                    self._memory.save_run_memory(self.worker_id, {
                        "goal": self.goal,
                        "summary": self._final_output.get("summary", ""),
                        "steps_count": self._step_count,
                        "total_tokens": self.total_tokens,
                        "completed_at": datetime.now().isoformat(),
                    })
                except Exception as e:
                    self.log.debug(f"Memory save skipped: {e}")

            return AgentResult(
                success=True,
                summary=self._final_output.get("summary", "Task completed"),
                steps=self._convert_steps(),
                output=self._final_output,
                total_duration_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            self.log.error(
                f"Worker {self.worker_id} execution error: {e}\n{traceback.format_exc()}"
            )
            return AgentResult(
                success=False,
                summary=f"Execution error: {e}",
                error=str(e),
                output=self._final_output,
                total_duration_ms=elapsed_ms,
            )

    # ── Initialization ──

    def _initialize(self) -> None:
        """Lazy-init internal components"""
        # Context Manager
        if not self._context_mgr:
            try:
                from .context import ContextManager, ContextConfig  # type: ignore[import-untyped]
                self._context_mgr = ContextManager(config=ContextConfig(max_tokens=8000))
            except ImportError:
                self._context_mgr = None  # Will work without

        # Memory
        if not self._memory:
            try:
                from .memory import EphemeralMemory  # type: ignore[import-untyped]
                self._memory = EphemeralMemory()
            except ImportError:
                self._memory = None  # Will work without

        # Tool Executor
        if not self._tool_executor:
            try:
                from .tool_executor import ToolExecutor  # type: ignore[import-untyped]
                self._tool_executor = ToolExecutor()
            except ImportError:
                self._tool_executor = None  # Will work without

    # ── System Prompt Construction ──

    def _build_system_prompt(self) -> None:
        """Build the system prompt for the LLM"""
        parts: List[str] = [
            "You are an autonomous AI agent in the Prodinamik AI Grid."
        ]
        parts.append(f"\n## Goal\n{self.goal}")

        if self.context:
            parts.append(f"\n## Context\n{json.dumps(self.context, indent=2)}")

        if self.tools:
            parts.append("\n## Available Tools")
            for tool in self.tools:
                name = tool.get("name", "unknown")
                desc = tool.get("description", "")
                params_raw = tool.get("parameters", {})
                params_str = json.dumps(params_raw, indent=2)[:200]
                parts.append(f"\n### {name}\n{desc}\nParameters: {params_str}")

            parts.append(
                """
## Tool Calling Format
To call a tool, respond with a JSON action:
```json
{"action": {"type": "tool_call", "tool_name": "...", "parameters": {...}}}
```

To complete:
```json
{"action": {"type": "complete", "summary": "...", "output": {...}}}
```

To report an error:
```json
{"action": {"type": "error", "error": "..."}}
```
"""
            )

        parts.append(
            """
## Response Format
First, think step by step in your response text. Then provide your action as JSON at the end.

Available tools for each call:
"""
        )

        # Add tool descriptions explicitly
        for tool in self.tools:
            parts.append(f"- **{tool.get('name')}**: {tool.get('description', '')}")

        parts.append(
            "\n## Rules\n"
            "- One tool call per response\n"
            "- Wait for tool result before next step\n"
            "- Complete when goal is achieved"
        )

        self._system_prompt = "\n".join(parts)

    # ── OBSERVE phase ──

    async def _observe(self) -> str:
        """OBSERVE phase: gather current state"""
        observations: List[str] = []

        # Check memory for relevant past learnings
        if self._memory:
            try:
                memories = self._memory.search(self.goal, limit=3)
                if memories:
                    observations.append(
                        f"Relevant memories found: {len(memories)}"
                    )
                    for m in memories[:3]:
                        summary = m.get("summary", "")[:100]
                        observations.append(f"- {summary}")
            except Exception:
                pass

        # Check context manager for token budget
        if self._context_mgr:
            budget = self._context_mgr.token_budget()
            if budget < 500:
                observations.append("WARNING: Token budget running low")

        # Check tool execution status
        if self._tool_executor:
            tool_status = self._tool_executor.get_status()
            if tool_status:
                observations.append(f"Tool system: {tool_status}")

        observations.append(f"Step {self._step_count}/{self.max_steps}")

        return "\n".join(observations) if observations else "System nominal."

    # ── THINK phase ──

    async def _think(self) -> Dict[str, Any]:
        """THINK phase: call LLM to plan next action"""
        if not self.llm_provider:
            return self._fallback_think()

        # Build message context
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]

        # Add conversation history (summarized if possible)
        if self._context_mgr:
            history = self._context_mgr.summarize(self.steps)
            for msg in history:
                messages.append(msg)
        else:
            # Simple history: last 10 steps
            for step in self.steps[-10:]:
                role = (
                    "assistant"
                    if step.step_type in (StepType.THOUGHT, StepType.REPORT)
                    else "user"
                )
                messages.append({"role": role, "content": step.content[:500]})

        # Add current goal reminder
        messages.append({
            "role": "user",
            "content": (
                f"Continue working on: {self.goal}\n"
                f"Current step: {self._step_count}/{self.max_steps}"
            ),
        })

        try:
            response = await self.llm_provider.complete(
                messages=messages,
                temperature=0.3,
            )

            content: str = response.get("content", "")
            usage: Dict[str, Any] = response.get("usage", {})
            self.total_tokens += usage.get("total_tokens", 0)

            # Parse action from response
            action = self._parse_action(content)

            return {
                "content": content,
                "action": action,
                "usage": usage,
            }
        except Exception as e:
            self.log.error(f"LLM think failed: {e}")
            return self._fallback_think()

    def _fallback_think(self) -> Dict[str, Any]:
        """Fallback when no LLM provider is available"""
        return {
            "content": "No LLM provider available. Operating in fallback mode.",
            "action": {
                "type": "complete",
                "summary": "Fallback mode — no action taken",
                "output": {"note": "LLM provider not configured"},
            },
        }

    def _parse_action(self, content: str) -> Dict[str, Any]:
        """Parse JSON action block from LLM response"""
        # Try to find JSON block in fenced code
        json_match = re.search(
            r'```(?:json)?\s*\n({.*?})\n\s*```', content, re.DOTALL
        )
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                action = data.get("action", {})
                if action:
                    return action
            except json.JSONDecodeError:
                pass

        # Try standalone JSON object containing "action" key
        json_match = re.search(
            r'\{[^{}]*"action"[^{}]*\}', content, re.DOTALL
        )
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                action = data.get("action", {})
                if action:
                    return action
            except json.JSONDecodeError:
                pass

        # No action found — treat response as complete
        return {
            "type": "complete",
            "summary": content[:200],
            "output": {"raw_response": content[:500]},
        }

    # ── ACT phase ──

    async def _act(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """ACT phase: execute a tool call"""
        tool_name = action.get("tool_name", "")
        parameters = action.get("parameters", {})

        if not tool_name:
            return {"error": "No tool name specified", "_duration_ms": 0}

        if not self._tool_executor:
            return {"error": "No ToolExecutor available", "_duration_ms": 0}

        start = time.time()
        try:
            result = await self._tool_executor.execute(tool_name, parameters)
            duration_ms = (time.time() - start) * 1000
            result["_duration_ms"] = duration_ms
            return result
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return {"error": str(e), "_duration_ms": duration_ms, "tool_name": tool_name}

    # ── Step Recording ──

    def _record_step(
        self,
        step_type: StepType,
        content: str = "",
        tool_name: str = "",
        tool_input: Optional[Dict[str, Any]] = None,
        tool_output: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        token_count: int = 0,
    ) -> None:
        """Record a step in the execution trace"""
        record = StepRecord(
            step_number=len(self.steps) + 1,
            step_type=step_type,
            content=content[:1000],
            tool_name=tool_name,
            tool_input=tool_input or {},
            tool_output=tool_output or {},
            duration_ms=duration_ms,
            token_count=token_count,
        )
        self.steps.append(record)

    def _convert_steps(self) -> list:
        """Convert StepRecords to AgentStep for AgentResult"""
        from ..agent_base import AgentStep

        return [
            AgentStep(
                step_id=f"step_{s.step_number}",
                description=s.content[:200],
                tool=s.tool_name or None,
                input=s.tool_input,
                output=s.tool_output,
                status="completed" if not s.error else "failed",
                error=s.error,
                duration_ms=s.duration_ms,
            )
            for s in self.steps
        ]
