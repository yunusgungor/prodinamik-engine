"""Prodinamik Engine — Agent Runtime Subpackage

Warm Agent pattern: lightweight supervisor per node + worker pool.
Context management with sliding window and summarization.
Tool Executor converts Plugin Registry tools into callable agent functions.
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

__all__ = [
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
]
