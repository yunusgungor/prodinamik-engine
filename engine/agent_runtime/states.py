"""Prodinamik AI Grid — Agent State Machine States

Agent-specific states and transitions for the O→T→A→O loop.
Integrates with Prodinamik Engine's existing StateMachine.

Agent State Lifecycle:
    agent:pending → agent:initializing → agent:observing →
    agent:thinking → agent:acting → agent:observing (loop) →
    agent:reporting → agent:completed
                                 ↓
                           agent:failed

Integration:
    These states are registered with the Prodinamik StateMachine
    via StateMachineConfig (StateDefinition + TransitionDefinition).
    State names use namespace prefix 'agent:' to avoid collisions
    with profile states (software:, content:, etc.)

    Virtual state types map to Prodinamik enums:
        initial    → StateType.INITIAL
        processing → StateType.INTERMEDIATE
        final      → StateType.TERMINAL
        error      → StateType.ERROR
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..sm_types import (
    StateType,
    TransitionType,
    StateDefinition,
    TransitionDefinition,
    StateMachineConfig,
)
from ..state_machine import StateMachine
from ..log import get_logger

logger = get_logger()


# ── Virtual → Formal State Type Mapping ──

_STATE_TYPE_MAP: Dict[str, StateType] = {
    "initial": StateType.INITIAL,
    "processing": StateType.INTERMEDIATE,
    "final": StateType.TERMINAL,
    "error": StateType.ERROR,
}

# ── Agent State Definitions ──

# All agent states follow the namespace convention 'agent:{name}'
# to avoid collisions with profile states

AGENT_STATES: Dict[str, Dict[str, Any]] = {
    "agent:pending": {
        "type": "initial",
        "description": "Task queued, waiting for assignment",
        "timeout_seconds": 300,  # 5 min max in queue
        "temporal_on_timeout": "agent:failed",
        "max_reentries": 1,
    },
    "agent:initializing": {
        "type": "processing",
        "description": "Worker initializing components",
        "timeout_seconds": 30,
        "temporal_on_timeout": "agent:failed",
        "max_reentries": 3,
    },
    "agent:observing": {
        "type": "processing",
        "description": "Gathering current state (memory, tools, environment)",
        "timeout_seconds": 15,
        "temporal_on_timeout": "agent:thinking",  # Skip to thinking on timeout
        "max_reentries": 50,
    },
    "agent:thinking": {
        "type": "processing",
        "description": "LLM call: reasoning about next action",
        "timeout_seconds": 120,  # LLM calls can be slow
        "temporal_on_timeout": "agent:failed",
        "max_reentries": 50,
    },
    "agent:acting": {
        "type": "processing",
        "description": "Executing a tool call",
        "timeout_seconds": 60,
        "temporal_on_timeout": "agent:failed",
        "max_reentries": 100,
    },
    "agent:reporting": {
        "type": "processing",
        "description": "Compiling results and updating memory",
        "timeout_seconds": 30,
        "temporal_on_timeout": "agent:completed",  # Skip to completed
        "max_reentries": 1,
    },
    "agent:completed": {
        "type": "final",
        "description": "Task completed successfully",
        "max_reentries": 0,
    },
    "agent:failed": {
        "type": "error",
        "description": "Task failed (max retries, timeout, error)",
        "max_reentries": 0,
    },
    "agent:cancelled": {
        "type": "error",
        "description": "Task cancelled by user or system",
        "max_reentries": 0,
    },
}


# ── State Transitions ──

# Transition type key mapping: human-readable → TransitionType enum
_TRANSITION_TYPE_MAP: Dict[str, TransitionType] = {
    "normal": TransitionType.REVERSIBLE,
    "reversible": TransitionType.REVERSIBLE,
    "compensable": TransitionType.COMPENSABLE,
    "irreversible": TransitionType.IRREVERSIBLE,
}

AGENT_TRANSITIONS: List[Dict[str, str]] = [
    # Queue → execute
    {"from": "agent:pending", "to": "agent:initializing", "type": "normal"},
    {"from": "agent:pending", "to": "agent:cancelled", "type": "normal"},
    # Initialize → observe
    {"from": "agent:initializing", "to": "agent:observing", "type": "normal"},
    {"from": "agent:initializing", "to": "agent:failed", "type": "normal"},
    # O→T→A→O loop
    {"from": "agent:observing", "to": "agent:thinking", "type": "normal"},
    {"from": "agent:thinking", "to": "agent:acting", "type": "normal"},
    {"from": "agent:acting", "to": "agent:observing", "type": "normal"},  # Loop back
    {"from": "agent:acting", "to": "agent:reporting", "type": "normal"},  # Goal achieved
    # Report → complete/fail
    {"from": "agent:reporting", "to": "agent:completed", "type": "normal"},
    {"from": "agent:reporting", "to": "agent:failed", "type": "normal"},
    # Error recovery
    {"from": "agent:failed", "to": "agent:pending", "type": "normal"},  # Retry
    {"from": "agent:failed", "to": "agent:cancelled", "type": "normal"},
]


# ── Build StateDefinition / TransitionDefinition Objects ──


def _build_state_definitions() -> Dict[str, StateDefinition]:
    """Convert AGENT_STATES dicts to StateDefinition objects.

    Returns a dict of {state_name: StateDefinition} suitable for
    StateMachineConfig.states.
    """
    defs: Dict[str, StateDefinition] = {}
    for name, s in AGENT_STATES.items():
        defs[name] = StateDefinition(
            name=name,
            state_type=_STATE_TYPE_MAP[s["type"]],
            max_reentries=s.get("max_reentries"),
            timeout_seconds=s.get("timeout_seconds"),
            temporal_on_timeout=s.get("temporal_on_timeout"),
        )
    return defs


def _build_transition_definitions() -> List[TransitionDefinition]:
    """Convert AGENT_TRANSITIONS dicts to TransitionDefinition objects.

    Returns a list suitable for StateMachineConfig.transitions.
    """
    defs: List[TransitionDefinition] = []
    for t in AGENT_TRANSITIONS:
        defs.append(
            TransitionDefinition(
                from_state=t["from"],
                to_state=t["to"],
                transition_type=_TRANSITION_TYPE_MAP.get(t["type"], TransitionType.REVERSIBLE),
            )
        )
    return defs


# ── Pre-built lookup helpers for validation/diagnostics ──

# Map each state name to its list of valid next states
_VALID_NEXT_STATES: Dict[str, List[str]] = {}
for t in AGENT_TRANSITIONS:
    _VALID_NEXT_STATES.setdefault(t["from"], []).append(t["to"])

# Map each state name to its list of valid previous states
_VALID_PREV_STATES: Dict[str, List[str]] = {}
for t in AGENT_TRANSITIONS:
    _VALID_PREV_STATES.setdefault(t["to"], []).append(t["from"])


# ── Agent State Machine Factory ──


def create_agent_state_machine() -> StateMachine:
    """Create a StateMachine pre-configured with agent states.

    Builds a StateMachineConfig from AGENT_STATES and AGENT_TRANSITIONS,
    then instantiates and validates a StateMachine.

    Returns:
        StateMachine instance ready for runtime use.
    """
    config = StateMachineConfig(
        profile="agent",
        name="agent-task",
        version="1.0.0",
        states=_build_state_definitions(),
        transitions=_build_transition_definitions(),
        ltl_rules=[],
    )

    sm = StateMachine(config)
    logger.info(
        "Agent state machine created",
        extra={
            "state_count": len(config.states),
            "transition_count": len(config.transitions),
            "machine_name": config.name,
        },
    )
    return sm


# ── Convenience Exports ──

AGENT_STATE_NAMES: List[str] = list(AGENT_STATES.keys())
"""All registered agent state names in definition order."""

AGENT_TRANSITION_COUNT: int = len(AGENT_TRANSITIONS)
"""Total number of explicit agent state transitions."""

VALID_AGENT_STATES: List[str] = AGENT_STATE_NAMES
"""Alias for quick reference — all valid agent state names."""

VALID_AGENT_TRANSITIONS: List[Tuple[str, str]] = [
    (t["from"], t["to"]) for t in AGENT_TRANSITIONS
]
"""Alias for quick reference — all valid (from → to) transition pairs."""

STATES_WITH_DESCRIPTIONS: Dict[str, str] = {
    name: s["description"] for name, s in AGENT_STATES.items()
}
"""State names with their human-readable descriptions."""
