"""Prodinamik AI Grid — Context Manager

Manages LLM context budget with sliding window and summarization.

Architecture:
    ContextManager
    ├── Sliding Window (keep last N steps full fidelity)
    ├── Summarization (compress older steps)
    ├── Token Budget (track usage, truncate when needed)
    └── Priority Queue (important steps preserved longer)

Usage:
    mgr = ContextManager(max_tokens=8000)
    messages = mgr.summarize(steps)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..log import get_logger


# ── Context Window Config ──

@dataclass
class ContextConfig:
    """Configuration for context window management"""
    max_tokens: int = 8000                    # Total token budget
    reserve_tokens: int = 500                  # Always reserve for system prompt
    full_fidelity_steps: int = 5              # Keep last N steps verbatim
    summary_max_tokens: int = 500             # Max tokens for a summary
    warn_threshold: float = 0.85              # Warn at 85% usage
    truncate_threshold: float = 0.95          # Start truncating at 95%


# ── Context Entry ──

@dataclass
class ContextEntry:
    """A single entry in the context"""
    role: str  # system | user | assistant
    content: str
    priority: int = 0      # Higher = more important, less likely to truncate
    tokens: int = 0
    step_number: int = 0
    is_summary: bool = False


# ── Context Manager ──

class ContextManager:
    """
    Manages LLM context budget for agent conversations.
    
    - Keeps last N steps at full fidelity (sliding window)
    - Summarizes older steps into compressed form
    - Prioritizes important steps (tool results, critical decisions)
    - Warns when approaching token limit
    - Gracefully truncates when exceeded
    """
    
    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.log = get_logger()
        self._entries: List[ContextEntry] = []
        self._total_tokens = 0
        
        # Overhead estimates
        self._OVERHEAD_PER_STEP = 8  # Role + formatting tokens
    
    def add_entry(
        self,
        role: str,
        content: str,
        priority: int = 0,
        step_number: int = 0,
        is_summary: bool = False,
    ) -> None:
        """Add a context entry"""
        tokens = self._estimate_tokens(content)
        entry = ContextEntry(
            role=role,
            content=content,
            priority=priority,
            tokens=tokens,
            step_number=step_number,
            is_summary=is_summary,
        )
        self._entries.append(entry)
        self._total_tokens += tokens
        
        if self._total_tokens > self.config.max_tokens * self.config.truncate_threshold:
            self._truncate()
    
    def summarize(
        self,
        steps: List[Any],  # List[StepRecord] from worker
    ) -> List[Dict[str, str]]:
        """
        Convert worker steps to a context-friendly message list.
        Uses sliding window: last N verbatim, older summarized.
        """
        if not steps:
            return []
        
        messages: List[Dict[str, str]] = []
        
        # Determine split point
        split = max(0, len(steps) - self.config.full_fidelity_steps)
        
        # Old steps: summarize
        old_steps = steps[:split]
        if old_steps:
            summary = self._compile_step_summary(old_steps)
            if summary:
                messages.append({
                    "role": "system",
                    "content": f"[Previous steps summary]: {summary[:self.config.summary_max_tokens]}",
                })
        
        # Recent steps: full fidelity
        recent_steps = steps[split:]
        for step in recent_steps:
            msg = self._step_to_message(step)
            if msg:
                messages.append(msg)
        
        # Check token budget
        total = sum(self._estimate_tokens(m.get("content", "")) for m in messages)
        available = self.config.max_tokens - self.config.reserve_tokens
        
        if total > available:
            self.log.debug(f"Context budget: {total}/{available} tokens")
            # Truncate oldest non-essential messages
            messages = self._trim_messages(messages, available)
        elif total > self.config.max_tokens * self.config.warn_threshold:
            self.log.debug(f"Context budget warning: {total}/{available}")
        
        return messages
    
    def token_budget(self) -> int:
        """Remaining token budget after reserve"""
        return self.config.max_tokens - self.config.reserve_tokens - self._total_tokens
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (character-based heuristic)"""
        if not text:
            return 0
        # ~3.5 chars per token for code, ~4.5 for prose
        return max(1, int(len(text) / 4))
    
    def _step_to_message(self, step) -> Optional[Dict[str, str]]:
        """Convert a StepRecord to an LLM message"""
        step_type = step.step_type.value if hasattr(step, 'step_type') and hasattr(step.step_type, 'value') else getattr(step, 'step_type', '')
        
        if step_type in ("thought", "report"):
            return {"role": "assistant", "content": step.content[:1500]}
        elif step_type == "tool_call":
            return {
                "role": "assistant",
                "content": f"Tool: {step.tool_name}({json.dumps(step.tool_input)[:200]})",
            }
        elif step_type == "tool_result":
            result_str = json.dumps(step.tool_output)[:500] if hasattr(step, 'tool_output') else str(getattr(step, 'output', ''))[:500]
            return {"role": "user", "content": f"Tool result: {result_str}"}
        elif step_type == "observation":
            return {"role": "user", "content": f"[Observe] {step.content[:500]}"}
        return None
    
    def _compile_step_summary(self, steps: List[Any]) -> str:
        """Compile a summary of old steps"""
        if not steps:
            return ""
        
        tool_calls = sum(1 for s in steps if hasattr(s, 'step_type') and 
                         (getattr(s, 'step_type', None) == "tool_call" or 
                          (hasattr(s.step_type, 'value') and s.step_type.value == "tool_call")))
        thoughts = sum(1 for s in steps if hasattr(s, 'step_type') and 
                       (getattr(s, 'step_type', None) == "thought" or 
                        (hasattr(s.step_type, 'value') and s.step_type.value == "thought")))
        
        # Extract key conclusions from report steps
        conclusions = []
        for s in steps:
            if hasattr(s, 'step_type') and (getattr(s, 'step_type', None) == "report" or 
                (hasattr(s.step_type, 'value') and s.step_type.value == "report")):
                conclusions.append(s.content[:200])
        
        parts = [f"{len(steps)} steps executed ({thoughts} thoughts, {tool_calls} tool calls)."]
        if conclusions:
            parts.append(f"Key findings: {'; '.join(conclusions[:3])}")
        
        return " ".join(parts)
    
    def _trim_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
    ) -> List[Dict[str, str]]:
        """Trim messages to fit within token budget"""
        trimmed = []
        total = 0
        
        # Keep system messages (first ones), trim user/assistant from middle
        for msg in reversed(messages):
            tokens = self._estimate_tokens(msg.get("content", ""))
            if total + tokens <= max_tokens:
                trimmed.insert(0, msg)
                total += tokens
            elif msg["role"] == "system":
                # Keep system messages but truncate content
                truncated = msg["content"][:max(100, max_tokens // 4)]
                trimmed.insert(0, {"role": "system", "content": truncated + "..."})
                total += len(truncated) // 4
            # else: drop this message
        
        return trimmed
    
    def _truncate(self) -> None:
        """Truncate low-priority entries to stay within token budget.
        
        Strategy: remove lowest-priority non-summary entries first,
        then compress oldest summary entries.
        """
        budget = self.config.max_tokens - self.config.reserve_tokens
        
        # Separate entries by priority and type
        priority_entries = sorted(
            [e for e in self._entries if not e.is_summary],
            key=lambda e: (e.priority, e.step_number),
        )
        summary_entries = [e for e in self._entries if e.is_summary]
        
        # Remove lowest-priority entries until under budget
        while self._total_tokens > budget and priority_entries:
            victim = priority_entries.pop(0)  # Lowest priority, oldest
            if victim in self._entries:
                self._entries.remove(victim)
                self._total_tokens -= victim.tokens
        
        # If still over budget, start dropping summaries (oldest first)
        while self._total_tokens > budget and summary_entries:
            victim = summary_entries.pop(0)
            if victim in self._entries:
                self._entries.remove(victim)
                self._total_tokens -= victim.tokens
    
    def reset(self) -> None:
        """Reset context"""
        self._entries.clear()
        self._total_tokens = 0
    
    @property
    def usage(self) -> float:
        """Context usage as ratio (0.0 - 1.0)"""
        return self._total_tokens / self.config.max_tokens if self.config.max_tokens > 0 else 0.0
    
    @property
    def is_near_limit(self) -> bool:
        return self.usage >= self.config.warn_threshold
