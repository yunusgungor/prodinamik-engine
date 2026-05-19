"""
Prodinamik Engine v1.1 — StateMachine Data Types

All type definitions, enums, dataclasses, and exceptions
extracted from state_machine.py for modularity.
"""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class TransitionType(Enum):
    REVERSIBLE = "reversible"
    COMPENSABLE = "compensable"
    IRREVERSIBLE = "irreversible"


class StateType(Enum):
    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    TERMINAL = "terminal"
    ERROR = "error"
    PAUSE = "pause"  # Human-in-the-loop: kullanıcı cevabı bekler


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class AskDirective:
    """State-level soru direktifi — kullanıcıya sorulacak soru"""
    question: str
    type: str = "open"           # "yes_no" | "multiple_choice" | "open"
    choices: List[str] = field(default_factory=list)
    required: bool = True
    timeout_seconds: int = 300   # Cevap gelmezse timeout politikası devreye girer


@dataclass
class ConditionalAsk:
    """Koşullu soru — sadece belli bir condition sağlanırsa sorulur"""
    condition: str
    question: str
    type: str = "yes_no"
    choices: List[str] = field(default_factory=list)
    on_timeout: str = "proceed"  # "proceed" | "hold" | "abort" | "default:<value>"


@dataclass
class HITLConfig:
    """Human-In-The-Loop konfigürasyonu — state seviyesinde"""
    pause: bool = False                          # Bu state bir bekleme noktası mı?
    ask_user: List[AskDirective] = field(default_factory=list)    # Sabit sorular
    ask_if: List[ConditionalAsk] = field(default_factory=list)    # Koşullu sorular
    on_timeout: str = "proceed"                  # Cevap gelmezse ne olacak?
    resume_transitions: Dict[str, str] = field(default_factory=dict)  # Cevap → state mapping

    def has_questions(self) -> bool:
        return bool(self.ask_user) or bool(self.ask_if)


@dataclass
class StateDefinition:
    """Tek bir state'in formal tanımı"""
    name: str
    state_type: StateType
    max_reentries: Optional[int] = None
    timeout_seconds: Optional[int] = None
    entry_hooks: List[str] = field(default_factory=list)
    exit_hooks: List[str] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)
    temporal_max_duration: Optional[int] = None
    temporal_on_timeout: Optional[str] = None
    reminders: List[dict] = field(default_factory=list)
    requires_manual: bool = False
    hitl: Optional[HITLConfig] = None  # Human-In-The-Loop config

    def __post_init__(self):
        if self.state_type == StateType.TERMINAL and self.max_reentries is not None:
            assert self.max_reentries == 0, \
                f"Terminal state '{self.name}' must have max_reentries=0"
        if self.state_type == StateType.INITIAL and self.max_reentries is not None:
            assert self.max_reentries <= 1, \
                f"Initial state '{self.name}' cannot have max_reentries > 1"


@dataclass
class TransitionDefinition:
    """İki state arasındaki geçişin formal tanımı"""
    from_state: str
    to_state: str
    transition_type: TransitionType = TransitionType.REVERSIBLE
    condition: Optional[str] = None
    action: Optional[str] = None
    requires_human: bool = False


@dataclass
class LTLRule:
    """Linear Temporal Logic constraint"""
    expression: str
    within_seconds: Optional[int] = None


@dataclass
class StateMachineConfig:
    """Complete state machine configuration from YAML"""
    profile: str
    name: str
    version: str
    states: Dict[str, StateDefinition]
    transitions: List[TransitionDefinition]
    ltl_rules: List[LTLRule]
    max_steps: int = 100

    @property
    def initial_states(self) -> List[StateDefinition]:
        return [s for s in self.states.values() if s.state_type == StateType.INITIAL]

    @property
    def terminal_states(self) -> List[StateDefinition]:
        return [s for s in self.states.values() if s.state_type == StateType.TERMINAL]

    @property
    def intermediate_states(self) -> List[StateDefinition]:
        return [s for s in self.states.values() if s.state_type == StateType.INTERMEDIATE]


# ──────────────────────────────────────────────
# Validation Errors
# ──────────────────────────────────────────────

@dataclass
class ValidationError:
    field: str
    message: str
    severity: str = "ERROR"


# ──────────────────────────────────────────────
# Runtime State
# ──────────────────────────────────────────────

@dataclass
class RuntimeState:
    """Bir run'ın anlık state bilgisi"""
    current_state: str
    previous_state: Optional[str] = None
    reentry_count: int = 0
    iteration_count: int = 0
    entered_at: datetime = field(default_factory=datetime.now)
    last_transition_at: datetime = field(default_factory=datetime.now)
    version: int = 0
    drift_count: int = 0
    human_approved: bool = False
    consecutive_failures: int = 0
    total_iterations: int = 0
    changes_requested: bool = False
    manual_unblock: bool = False
    project_abandoned: bool = False
    ltl_history: dict = field(default_factory=dict)
    
    # HITL fields
    awaiting_input: bool = False
    user_answers: dict = field(default_factory=dict)
    hitl_timeout_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class StateMachineValidationError(Exception):
    """State machine validation hatası — compile-time"""
    pass


class TransitionError(Exception):
    """Geçersiz transition — runtime"""
    pass
