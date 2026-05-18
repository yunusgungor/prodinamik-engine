"""Prodinamik Engine v1.0

Product-Agnostic Pipeline Engine.

State machine, validator pipeline, event sourcing,
cost tracking, budget enforcement, graceful degradation,
and distributed consensus for multi-profile pipelines.
"""

__version__ = "1.0.0"
__author__ = "Yunus Güngör"
__license__ = "MIT"

from .config import ProdinamikConfig
from .runtime import AsyncEngine, RuntimeConfig, LifecycleHooks, run_engine
from .log import setup as setup_logging, get_logger
from .profile import ProductProfile, Budget, ValidatorDef, AdapterDef, StoreDef, ValidatorTier
from .state_machine import StateMachine, StateMachineConfig, StateType, TransitionType, RuntimeState
from .run_manager import RunManager
from .event_store import EventStore, Event, CostAwareEvent
from .validators import ValidatorPipeline, ContentAddressableCache, CachePolicy
from .degradation import DegradationManager, DegradationLevel
from .cost import CostTracker, EfficiencyTracker
from .budget import BudgetEnforcer, BudgetAction
from .safety import EventBus, RuntimeSafetyMonitor
from .debug_cli import DebugCLI
from .registry import ProfileRegistry

__all__ = [
    "ProdinamikEngine",
    "ProdinamikConfig",
    "ProductProfile",
    "StateMachine",
    "StateMachineConfig",
    "StateType",
    "TransitionType",
    "RuntimeState",
    "RunManager",
    "EventStore",
    "Event",
    "CostAwareEvent",
    "ValidatorPipeline",
    "ContentAddressableCache",
    "CachePolicy",
    "DegradationManager",
    "DegradationLevel",
    "CostTracker",
    "EfficiencyTracker",
    "BudgetEnforcer",
    "BudgetAction",
    "EventBus",
    "RuntimeSafetyMonitor",
    "DebugCLI",
    "ProfileRegistry",
    "Budget",
    "ValidatorDef",
    "AdapterDef",
    "StoreDef",
    "ValidatorTier",
    "setup_logging",
    "get_logger",
]
