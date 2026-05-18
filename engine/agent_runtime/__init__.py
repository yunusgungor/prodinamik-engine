"""Prodinamik Engine — Agent Runtime Subpackage

Phase 1: Runtime Layer — Warm Agent, Loop Engine, Tools, Context, Memory
Phase 2: Orchestration Layer — Coordinator, Task Queue, Scheduler, Registry
Phase 3: Human Loop Layer — Approval Gate, Budget Controller, Human Loop
"""

from .supervisor import (
    AgentSupervisor,
    SupervisorConfig,
    NodeIdentity,
    WorkerInfo,
    WorkerStatus,
)
from .context import (
    ContextManager,
    ContextConfig,
    ContextEntry,
)
from .tool_executor import (
    ToolExecutor,
    ToolHandler,
    ToolCache,
    ToolExecutionRecord,
    ToolStatus,
)
from .worker import (
    AgentWorker,
    StepType,
    StepRecord,
)
from .memory import (
    EphemeralMemory,
    LocalMemory,
    MemoryEntry,
    MemoryStore,
)
from .task_queue import (
    TaskQueue,
    Task,
    TaskStatus,
    PrioritizedTask,
)
from .agent_registry import (
    AgentRegistry,
    NodeInfo,
    CapabilityQuery,
)
from .coordinator import (
    CoordinatorNode,
    CoordinatorConfig,
    CoordinatorStatus,
)
from .scheduler import Scheduler
from .human_loop import (
    HumanLoopManager,
    EscalatedItem,
    EscalationReason,
    ReviewStatus,
)
from .approval_gate import (
    ApprovalGate,
    PausedTask,
    PauseReason,
    ApprovalStatus,
    ActionLog,
)
from .budget_controller import (
    BudgetController,
    BudgetThreshold,
    BudgetLevel,
    TaskCostRecord,
)
from .global_memory import (
    GlobalMemory,
    CRDTEntry,
)

__all__ = [
    # Phase 1: Runtime
    "AgentSupervisor",
    "SupervisorConfig",
    "NodeIdentity",
    "WorkerInfo",
    "WorkerStatus",
    "ContextManager",
    "ContextConfig",
    "ContextEntry",
    "ToolExecutor",
    "ToolHandler",
    "ToolCache",
    "ToolExecutionRecord",
    "ToolStatus",
    "AgentWorker",
    "StepType",
    "StepRecord",
    "EphemeralMemory",
    "LocalMemory",
    "MemoryEntry",
    "MemoryStore",
    # Phase 2: Orchestration
    "TaskQueue",
    "Task",
    "TaskStatus",
    "PrioritizedTask",
    "AgentRegistry",
    "NodeInfo",
    "CapabilityQuery",
    "CoordinatorNode",
    "CoordinatorConfig",
    "CoordinatorStatus",
    "Scheduler",
    "HumanLoopManager",
    "EscalatedItem",
    "EscalationReason",
    "ReviewStatus",
    # Phase 3: Human Loop
    "ApprovalGate",
    "PausedTask",
    "PauseReason",
    "ApprovalStatus",
    "ActionLog",
    "BudgetController",
    "BudgetThreshold",
    "BudgetLevel",
    "TaskCostRecord",
    "GlobalMemory",
    "CRDTEntry",
]
