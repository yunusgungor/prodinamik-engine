"""
Prodinamik Engine v1.1 — Raft Data Types

Review #5: Raft + Offline + CRDT çelişkisi çözümü.
All data types extracted from raft.py for modularity.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
import json


class NodeRole(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"


@dataclass
class LogEntry:
    """Raft log entry"""
    term: int
    index: int
    command: dict
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def checksum(self) -> str:
        import hashlib
        return hashlib.sha256(
            f"{self.term}:{self.index}:{json.dumps(self.command, sort_keys=True)}".encode()
        ).hexdigest()[:16]


@dataclass
class NodeState:
    """Bir node'un state bilgisi"""
    current_state: str = ""
    version: int = 0


@dataclass
class Snapshot:
    """Raft snapshot (state machine'in anlık görüntüsü)"""
    last_included_index: int
    last_included_term: int
    state_data: Dict[str, NodeState]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class PendingOperation:
    """Offline'ta biriken işlem"""
    command: dict
    timestamp: str = ""
    local_version: int = 0
    applied: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ClusterNode:
    """Discovered cluster node"""
    node_id: str
    address: str = ""
    role: str = "unknown"
    last_seen: float = 0.0
    healthy: bool = False
    log_length: int = 0
    state_count: int = 0
