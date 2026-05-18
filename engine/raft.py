"""
Prodinamik Engine v1.1 — Hybrid Raft Consensus (Facade)

Backward-compatible re-exports from submodules:
  - raft_types      → NodeRole, LogEntry, NodeState, Snapshot, PendingOperation, ClusterNode
  - raft_consensus  → StateCRDT, DistributedStateMachine, OfflineManager, HybridConsensusNode
  - raft_cluster    → RaftCluster, demo
"""

from .raft_types import (
    NodeRole, LogEntry, NodeState, Snapshot,
    PendingOperation, ClusterNode,
)

from .raft_consensus import (
    StateCRDT, DistributedStateMachine,
    OfflineManager, HybridConsensusNode,
)

from .raft_cluster import (
    RaftCluster, demo,
)

__all__ = [
    "NodeRole", "LogEntry", "NodeState", "Snapshot",
    "PendingOperation", "ClusterNode",
    "StateCRDT", "DistributedStateMachine",
    "OfflineManager", "HybridConsensusNode",
    "RaftCluster", "demo",
]
