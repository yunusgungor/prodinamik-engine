"""Prodinamik Engine v1.3

Product-Agnostic Pipeline Engine.

State machine, validator pipeline, event sourcing,
cost tracking, budget enforcement, graceful degradation,
and distributed consensus for multi-profile pipelines.
"""

__version__ = "1.3.0"
__author__ = "Yunus Güngör"
__license__ = "MIT"

from .config import ProdinamikConfig, LLMConfig
from .runtime import AsyncEngine, RuntimeConfig, LifecycleHooks, run_engine
from .engine import ProdinamikEngine
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
from .hooks import HookRegistry
from .shell import ProdinamikShell
from .bench import Benchmark, BenchmarkResult
from .metrics import MetricsRegistry
from .dashboard import Dashboard
from .audit import AuditLog
from .auth import AuthManager
from .ratelimit import RateLimiter
from .server import ProdinamikServer
from .raft import HybridConsensusNode, RaftCluster
from .raft_transport import RaftTCPServer, RaftTCPClient, RaftMessage
from .chaos import ChaosEngine, ScenarioResult

from .alert import AlertManager, Alert

from .distributed import DistributedRunCoordinator, DistributedRun
from .elector import ExternalLeaderElector

from .plugin import (
    PluginBase,
    PluginManifest,
    PluginState,
    PluginStatus,
    PluginType,
    PluginHookType,
    PluginTool,
    PluginHook,
    LoggingPlugin,
)
from .plugin_registry import PluginRegistry, PLUGIN_DIRS
from .hermes_bridge import HermesPluginBridge
from .plugin_repo import PluginRepository, RepositoryPlugin, InstallRecord

from .aidetect import (
    AIDriftDetector,
    DriftEvent,
    DriftPattern,
    DriftType,
    DriftSeverity,
    EmergenceCandidate,
    TrendDirection,
)
from .predict import (
    AIDegradationForecaster,
    MetricPoint,
    ForecastResult,
    DegradationPrediction,
    DegradationLevel,
)
from .skillforge import AutoSkillForge, SkillDraft
from .recommend import AIRecommender, Recommendation
from .autofix import AutoRemediator, FailureSignature, FailureClass, RemediationPlan

# ── StateGuard Bridge ──
from .stateguard_bridge import (
    StateGuardValidator,
    make_stateguard_def,
)
# ── StateGuard Dimension Plugins ──
from plugins.stateguard_dimensions import (
    StructuralPlugin,
    SemanticPlugin,
    QuantitativePlugin,
    BehavioralPlugin,
    SecurityPlugin,
)
# ── HITL Bridge ──
from .hitl_bridge import ProdinamikHITLHandler
# ── StateGuard Profile Config ──
from .stateguard_config import (
    STATEGUARD_PROFILE_CONFIG,
    make_profile_validators,
    list_profile_configs,
)

# ── LLM & Agent Plugin Infrastructure ──
from .llm_base import (
    LLMProviderPlugin,
    LLMProviderConfig,
    LLMProviderError,
    LLMProviderAuthError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from .llm_registry import LLMProviderRegistry, LLMUsageStats
from .agent_base import AgentPlugin, AgentStep, AgentResult

__all__ = [
    "ProdinamikEngine",
    "ProdinamikConfig",
    "LLMConfig",
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
    # Phase 2: Runtime
    "AsyncEngine",
    "RuntimeConfig",
    "HookRegistry",
    # Phase 3: Developer Experience
    "ProdinamikShell",
    "Benchmark",
    "BenchmarkResult",
    # Phase 4: Observability
    "MetricsRegistry",
    "Dashboard",
    "AuditLog",
    # Phase 5: Security & Distribution
    "AuthManager",
    "RateLimiter",
    "ProdinamikServer",
    "HybridConsensusNode",
    "RaftCluster",
    # Phase 7: Raft TCP Transport
    "RaftTCPServer",
    "RaftTCPClient",
    "RaftMessage",
    # Phase 6: Chaos Engineering
    "ChaosEngine",
    "ScenarioResult",
    # Phase 7: Monitoring & Alerting
    "AlertManager",
    "Alert",
    # Phase 8: Distributed & Election
    "DistributedRunCoordinator",
    "DistributedRun",
    "ExternalLeaderElector",
    # Phase 9: Plugin Ecosystem
    "PluginBase",
    "PluginManifest",
    "PluginState",
    "PluginStatus",
    "PluginType",
    "PluginHookType",
    "PluginTool",
    "PluginHook",
    "LoggingPlugin",
    "PluginRegistry",
    "PLUGIN_DIRS",
    "HermesPluginBridge",
    "PluginRepository",
    "RepositoryPlugin",
    "InstallRecord",
    # Phase 10: AI-Native Features
    "AIDriftDetector",
    "DriftEvent",
    "DriftPattern",
    "DriftType",
    "DriftSeverity",
    "EmergenceCandidate",
    "TrendDirection",
    "AIDegradationForecaster",
    "MetricPoint",
    "ForecastResult",
    "DegradationPrediction",
    "DegradationLevel",
    "AutoSkillForge",
    "SkillDraft",
    "AIRecommender",
    "Recommendation",
    "AutoRemediator",
    "FailureSignature",
    "FailureClass",
    "RemediationPlan",
    # StateGuard Bridge
    "StateGuardValidator",
    "make_stateguard_def",
    # StateGuard Dimension Plugins
    "StructuralPlugin",
    "SemanticPlugin",
    "QuantitativePlugin",
    "BehavioralPlugin",
    "SecurityPlugin",
    # HITL Bridge
    "ProdinamikHITLHandler",
    # StateGuard Profile Config
    "STATEGUARD_PROFILE_CONFIG",
    "make_profile_validators",
    "list_profile_configs",
    # LLM & Agent Plugin Infrastructure
    "LLMProviderPlugin",
    "LLMProviderConfig",
    "LLMProviderError",
    "LLMProviderAuthError",
    "LLMProviderRateLimitError",
    "LLMProviderTimeoutError",
    "LLMProviderRegistry",
    "LLMUsageStats",
    "AgentPlugin",
    "AgentStep",
    "AgentResult",
    # Agent Runtime (AI Grid — Phase 1)
    "AgentSupervisor",
    "SupervisorConfig",
    "NodeIdentity",
    "WorkerInfo",
    "WorkerStatus",
    "AgentWorker",
    "StepType",
    "StepRecord",
    "ToolExecutor",
    "ToolHandler",
    "ToolExecutionRecord",
    "ToolStatus",
    "ContextManager",
    "ContextConfig",
    "EphemeralMemory",
    "LocalMemory",
    "MemoryEntry",
    "MemoryStore",
    "create_agent_state_machine",
    "AGENT_STATES",
    "AGENT_TRANSITIONS",
    "VALID_AGENT_STATES",
    "VALID_AGENT_TRANSITIONS",
    # Agent Runtime (AI Grid — Phase 2: Orchestration)
    "CoordinatorNode",
    "CoordinatorConfig",
    "CoordinatorStatus",
    "TaskQueue",
    "Task",
    "TaskStatus",
    "AgentRegistry",
    "NodeInfo",
    "CapabilityQuery",
    "Scheduler",
    "HumanLoopManager",
    "EscalatedItem",
    "EscalationReason",
    "ReviewStatus",
    "GlobalMemory",
    "CRDTEntry",
]
