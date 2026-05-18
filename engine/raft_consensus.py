"""
Prodinamik Engine v1.1 — Hybrid Raft Consensus Core

StateCRDT, DistributedStateMachine, OfflineManager, HybridConsensusNode.
"""

import json
import time
import random
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any, Tuple

from .raft_types import (
    NodeRole, LogEntry, NodeState, Snapshot,
    PendingOperation, ClusterNode,
)


# ──────────────────────────────────────────────
# CRDT Merge (Conflict-free Replicated Data Type)
# ──────────────────────────────────────────────

class StateCRDT:
    """
    CRDT for distributed state.
    Uses version vectors for conflict detection.
    """

    @staticmethod
    def merge(local: NodeState, remote: NodeState,
              state_machine_transitions: Dict[str, List[str]] = None) -> NodeState:
        if state_machine_transitions is None:
            state_machine_transitions = {}

        if remote.version > local.version:
            return remote
        if local.version > remote.version:
            return local

        if remote.current_state == local.current_state:
            return local

        # Concurrent: state machine path'ine göre merge
        if StateCRDT._is_on_same_path(local.current_state,
                                       remote.current_state,
                                       state_machine_transitions):
            path = StateCRDT._find_path(local.current_state,
                                         remote.current_state,
                                         state_machine_transitions)
            if path and path[-1] == remote.current_state:
                return remote
            return local

        return local  # Default: local koru

    @staticmethod
    def _is_on_same_path(a: str, b: str, transitions: Dict[str, List[str]]) -> bool:
        if not transitions:
            return False
        path = StateCRDT._find_path(a, b, transitions)
        if path:
            return True
        path = StateCRDT._find_path(b, a, transitions)
        if path:
            return True
        return False

    @staticmethod
    def _find_path(start: str, end: str,
                   transitions: Dict[str, List[str]],
                   visited: set = None) -> Optional[List[str]]:
        if visited is None:
            visited = set()
        if start == end:
            return [end]
        if start in visited:
            return None
        visited.add(start)
        for next_state in transitions.get(start, []):
            path = StateCRDT._find_path(next_state, end, transitions, visited)
            if path:
                return [start] + path
        return None


# ──────────────────────────────────────────────
# Distributed State Machine
# ──────────────────────────────────────────────

class DistributedStateMachine:
    """
    Distributed state machine backed by Raft+CRDT.
    State machine SADECE Leader'da çalışır.
    Follower'lar Leader'ın log'unu replicate eder.
    """

    def __init__(self, node_id: str, peers: List[str] = None,
                 state_dir: str = ".hermes/raft/"):
        self.node_id = node_id
        self.peers = peers or []
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self._lock = threading.RLock()

        # Raft state
        self.role = NodeRole.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = self._load_log()
        self.commit_index = -1
        self.last_applied = -1
        self.state_machine: Dict[str, NodeState] = self._load_snapshot()

        # Election
        self.election_timeout = random.uniform(1.5, 3.0)
        self.last_heartbeat = time.time()

        # Transitions (state machine DAG)
        self.transitions: Dict[str, List[str]] = {}

        # Leader election callbacks (for CoordinatorRaftBridge)
        self.on_leader_elected: Optional[Callable[[str], None]] = None
        self.on_step_down: Optional[Callable[[], None]] = None

        # Peer communication callbacks (set by HybridConsensusNode)
        self._request_vote_callback: Optional[Callable[[str], bool]] = None
        self._heartbeat_callback: Optional[Callable[[], None]] = None
        self._replicate_callback: Optional[Callable[[str], None]] = None

        # Pending ACKs for majority commit tracking
        self._pending_acks: Dict[int, set] = {}

    def configure_transitions(self, transitions: Dict[str, List[str]]):
        self.transitions = transitions

    # ── Raft Core ──

    def become_follower(self, term: int):
        with self._lock:
            was_leader = self.role == NodeRole.LEADER
            self.role = NodeRole.FOLLOWER
            self.current_term = term
            self.voted_for = None
            self.last_heartbeat = time.time()
            if was_leader and self.on_step_down:
                self.on_step_down()

    def become_candidate(self):
        with self._lock:
            self.role = NodeRole.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id
            self.last_heartbeat = time.time()
            votes = 1
            for peer in self.peers:
                if self._request_vote(peer):
                    votes += 1
            if votes > len(self.peers) // 2:
                self.become_leader()

    def become_leader(self):
        with self._lock:
            self.role = NodeRole.LEADER
            self._broadcast_heartbeat()
            if self.on_leader_elected:
                self.on_leader_elected(self.node_id)

    def _start_election(self):
        """Force an election cycle"""
        self.become_candidate()
        if self.role == NodeRole.CANDIDATE:
            pass  # Already candidate, no redundant call

    def append_entries(self, entries: List[LogEntry],
                       prev_log_index: int, prev_log_term: int,
                       leader_commit: int) -> Tuple[bool, int, int]:
        with self._lock:
            if prev_log_index >= 0 and prev_log_index < len(self.log):
                if self.log[prev_log_index].term != prev_log_term:
                    return False, prev_log_index, self.log[prev_log_index].term
            for i, entry in enumerate(entries):
                idx = prev_log_index + 1 + i
                if idx < len(self.log):
                    if self.log[idx].term != entry.term:
                        self.log = self.log[:idx]
                        self.log.append(entry)
                else:
                    self.log.append(entry)
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log) - 1)
                self._apply_committed()
            self.last_heartbeat = time.time()
            self._save_log()
            return True, 0, 0

    def request_vote(self, candidate_term: int, candidate_id: str,
                     last_log_index: int, last_log_term: int) -> bool:
        with self._lock:
            if candidate_term < self.current_term:
                return False
            if candidate_term > self.current_term:
                self.become_follower(candidate_term)
            if (self.voted_for is None or self.voted_for == candidate_id) \
               and last_log_term >= self._last_log_term():
                self.voted_for = candidate_id
                self.last_heartbeat = time.time()
                return True
            return False

    # ── State Machine Apply ──

    def _apply_committed(self):
        with self._lock:
            while self.last_applied < self.commit_index:
                self.last_applied += 1
                entry = self.log[self.last_applied]
                self._apply_command(entry.command)

    def _apply_command(self, command: dict):
        slug = command.get("slug")
        if not slug:
            return
        if slug not in self.state_machine:
            self.state_machine[slug] = NodeState()
        cmd_type = command.get("type")
        if cmd_type == "transition":
            to_state = command.get("to_state")
            if to_state:
                self.state_machine[slug].current_state = to_state
                self.state_machine[slug].version += 1
        elif cmd_type == "create":
            initial_state = command.get("initial_state", "start")
            self.state_machine[slug] = NodeState(
                current_state=initial_state, version=1
            )
        elif cmd_type == "archive":
            self.state_machine[slug] = NodeState(
                current_state="archived",
                version=self.state_machine[slug].version + 1
            )

    def get_state(self, slug: str) -> Optional[NodeState]:
        return self.state_machine.get(slug)

    def propose(self, command: dict) -> Tuple[bool, Optional[str]]:
        with self._lock:
            if self.role != NodeRole.LEADER:
                return False, "Not leader"
            entry = LogEntry(
                term=self.current_term,
                index=len(self.log),
                command=command,
            )
            self.log.append(entry)
            self._save_log()

            # Track leader's own acknowledgment
            index = entry.index
            self._pending_acks[index] = {self.node_id}

            # Commit if we have majority (leader ack alone may be enough for 1-node clusters)
            if self._check_majority(index):
                self.commit_index = index
                self._apply_committed()
                self._save_log()

            # Replicate to peers
            for peer in self.peers:
                self._replicate_to(peer)
        return True, None

    def _check_majority(self, index: int) -> bool:
        """Check if a log entry has been acknowledged by a majority of nodes."""
        acks = self._pending_acks.get(index, set())
        return len(acks) >= len(self.peers) // 2 + 1

    def ack_entry(self, index: int, peer_id: str) -> bool:
        """Peer acknowledges a log entry. Returns True if majority reached."""
        with self._lock:
            if index not in self._pending_acks:
                self._pending_acks[index] = set()
            self._pending_acks[index].add(peer_id)
            if self._check_majority(index):
                if index > self.commit_index:
                    self.commit_index = index
                    self._apply_committed()
                    self._save_log()
                return True
            return False

    # ── Persistence ──

    def _load_log(self) -> List[LogEntry]:
        path = self.state_dir / f"raft_log_{self.node_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return [LogEntry(**e) for e in data]
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_log(self):
        with self._lock:
            path = self.state_dir / f"raft_log_{self.node_id}.json"
            path.write_text(
                json.dumps([
                    {"term": e.term, "index": e.index,
                     "command": e.command, "timestamp": e.timestamp}
                    for e in self.log
                ], indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

    def _load_snapshot(self) -> Dict[str, NodeState]:
        path = self.state_dir / f"raft_snapshot_{self.node_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {k: NodeState(**v) for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def save_snapshot(self):
        path = self.state_dir / f"raft_snapshot_{self.node_id}.json"
        path.write_text(
            json.dumps({
                k: {"current_state": v.current_state, "version": v.version}
                for k, v in self.state_machine.items()
            }, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _last_log_term(self) -> int:
        if self.log:
            return self.log[-1].term
        return 0

    # ── Peer Communication (simüle) ──

    def _request_vote(self, peer: str) -> bool:
        if self._request_vote_callback is not None:
            return self._request_vote_callback(peer)
        return True

    def _broadcast_heartbeat(self):
        if self._heartbeat_callback is not None:
            self._heartbeat_callback()

    def _replicate_to(self, peer: str):
        if self._replicate_callback is not None:
            self._replicate_callback(peer)

    def provide_merge(self, slug: str, merged_state: NodeState) -> Tuple[bool, Optional[str]]:
        if self.role != NodeRole.LEADER:
            return False, "Not leader"
        self.state_machine[slug] = merged_state
        self.save_snapshot()
        return True, None

    # ── Display ──

    def status(self) -> str:
        return (
            f"📡 **Raft Node:** `{self.node_id}`\n"
            f"   Role: `{self.role.value}`\n"
            f"   Term: `{self.current_term}`\n"
            f"   Log entries: `{len(self.log)}`\n"
            f"   Committed: `{self.commit_index}`\n"
            f"   States tracked: `{len(self.state_machine)}`\n"
            f"   Peers: `{self.peers}`"
        )


# ──────────────────────────────────────────────
# Offline Manager
# ──────────────────────────────────────────────

class OfflineManager:
    """
    Offline mode: optimistic local writes.
    Reconnect: pending log → Leader approval → CRDT merge.
    """

    def __init__(self, local_node: DistributedStateMachine):
        self.local_node = local_node
        self.pending: List[PendingOperation] = []
        self.is_offline = False

    def go_offline(self):
        self.is_offline = True
        self.local_node.role = NodeRole.OFFLINE

    def go_online(self, leader: DistributedStateMachine):
        self.is_offline = False
        self.local_node.role = NodeRole.RECONNECTING
        self._sync_with_leader(leader)
        self.local_node.role = NodeRole.FOLLOWER

    def apply_pending(self, command: dict) -> NodeState:
        slug = command.get("slug")
        if not slug:
            return NodeState()
        if slug not in self.local_node.state_machine:
            self.local_node.state_machine[slug] = NodeState()
        old_version = self.local_node.state_machine[slug].version

        self.pending.append(PendingOperation(
            command=command,
            timestamp=datetime.now().isoformat(),
            local_version=old_version,
        ))

        # Optimistic: local cache'i güncelle
        if command.get("type") == "transition":
            self.local_node.state_machine[slug].current_state = \
                command.get("to_state", self.local_node.state_machine[slug].current_state)
            self.local_node.state_machine[slug].version += 1
        return self.local_node.state_machine[slug]

    def _sync_with_leader(self, leader: DistributedStateMachine):
        for op in self.pending:
            if op.applied:
                continue
            success, error = leader.propose(op.command)
            if success:
                op.applied = True
            else:
                local_state = self.local_node.get_state(op.command["slug"])
                remote_state = leader.get_state(op.command["slug"])
                if local_state and remote_state:
                    merged = StateCRDT.merge(
                        local_state, remote_state,
                        self.local_node.transitions
                    )
                    leader.provide_merge(op.command["slug"], merged)

    @property
    def pending_count(self) -> int:
        return sum(1 for p in self.pending if not p.applied)

    @property
    def status(self) -> str:
        return (
            f"📱 **Offline Manager:**\n"
            f"   Mode: `{'OFFLINE' if self.is_offline else 'ONLINE'}`\n"
            f"   Pending ops: `{self.pending_count}`\n"
            f"   Total ops: `{len(self.pending)}`"
        )


# ──────────────────────────────────────────────
# Hybrid Consensus Node (Review #5)
# ──────────────────────────────────────────────

class HybridConsensusNode:
    """
    Raft + Offline + CRDT hybrid model.

    Online:  Raft consensus (Leader writes, Follower replicates)
    Offline: Optimistic local writes (pending log)
    Reconnect: 5-adımlı sync prosedürü
    """

    def __init__(self, node_id: str, peers: List[str] = None,
                 state_dir: str = ".hermes/raft/",
                 raft_host: str = "0.0.0.0", raft_port: int = 9001,
                 enable_transport: bool = False):
        self.raft = DistributedStateMachine(node_id, peers, state_dir)
        self.offline = OfflineManager(self.raft)
        self.crdt = StateCRDT()

        # Wire peer communication callbacks
        self.raft._request_vote_callback = lambda peer: self._check_vote(peer)
        self.raft._heartbeat_callback = lambda: self._do_heartbeat()
        self.raft._replicate_callback = lambda peer: self._do_replicate(peer)

        # TCP transport
        self._transport = None
        self._raft_host = raft_host
        self._raft_port = raft_port
        self._enable_transport = enable_transport
        self._peer_transport: Dict[str, str] = {}  # node_id → host:port

    @property
    def transport(self):
        """Lazy-init TCP transport"""
        if self._enable_transport and self._transport is None:
            from .raft_transport import RaftTCPServer
            self._transport = RaftTCPServer(
                node_id=self.raft.node_id,
                host=self._raft_host,
                port=self._raft_port,
                handler=self._handle_raft_message,
            )
            self._transport.start()
        return self._transport

    def register_peer_transport(self, peer_id: str, address: str):
        """Register a peer's TCP address (e.g., 'node-2' → '192.168.1.2:9001')"""
        self._peer_transport[peer_id] = address

    def _handle_raft_message(self, msg) -> Optional[object]:
        """Handle incoming Raft messages from TCP transport"""
        from .raft_transport import (
            RaftMessage, build_vote_response, build_append_response,
            RAFT_MSG_REQUEST_VOTE, RAFT_MSG_APPEND_ENTRIES,
            RAFT_MSG_HEARTBEAT, RAFT_MSG_HEALTH,
        )
        if msg.type == RAFT_MSG_REQUEST_VOTE:
            d = msg.data or {}
            granted = self.raft.request_vote(
                msg.term, msg.sender_id,
                d.get("last_log_index", 0), d.get("last_log_term", 0),
            )
            return build_vote_response(self.raft.node_id, msg.term, granted)

        elif msg.type == RAFT_MSG_APPEND_ENTRIES:
            d = msg.data or {}
            from .raft_types import LogEntry
            entries = [LogEntry(**e) for e in d.get("entries", [])]
            success, ci, ct = self.raft.append_entries(
                entries, d.get("prev_log_index", -1),
                d.get("prev_log_term", 0), d.get("leader_commit", -1),
            )
            return build_append_response(self.raft.node_id, msg.term, success, ci, ct)

        elif msg.type == RAFT_MSG_HEARTBEAT:
            d = msg.data or {}
            self.raft.last_heartbeat = __import__("time").time()
            if d.get("leader_commit", -1) > self.raft.commit_index:
                from .raft_types import LogEntry
                self.raft.commit_index = min(d["leader_commit"], len(self.raft.log) - 1)
                self.raft._apply_committed()
            return RaftMessage(
                type="HeartbeatResponse",
                sender_id=self.raft.node_id,
                term=self.raft.current_term,
                data={"ok": True},
            )

        elif msg.type == RAFT_MSG_HEALTH:
            h = self.health()
            return RaftMessage(type="HealthResponse", sender_id=self.raft.node_id,
                               data=h)

        return None

    def start_transport(self):
        """Enable and start TCP transport"""
        self._enable_transport = True
        return self.transport is not None

    def stop_transport(self):
        """Stop TCP transport"""
        if self._transport:
            self._transport.stop()

    def apply(self, command: dict) -> Tuple[bool, Optional[str]]:
        if self.offline.is_offline:
            self.offline.apply_pending(command)
            return True, None
        return self.raft.propose(command)

    def _check_vote(self, peer_id: str) -> bool:
        """Check vote from a specific peer. Uses TCP if available, otherwise returns True (simulated)."""
        if peer_id in self._peer_transport:
            from .raft_transport import RaftTCPClient, build_vote_request
            addr = self._peer_transport[peer_id]
            msg = build_vote_request(
                self.raft.node_id, self.raft.current_term,
                len(self.raft.log) - 1, self.raft._last_log_term(),
            )
            resp = RaftTCPClient.send_message(addr, msg)
            if resp and resp.data and resp.data.get("vote_granted"):
                return True
            return False
        # Simulated: backward-compatible default
        return True

    def _do_heartbeat(self):
        """Broadcast heartbeat to registered TCP peers (no fallback to avoid recursion)."""
        from .raft_transport import RaftTCPClient, build_heartbeat

        for peer_id in self.raft.peers:
            if peer_id in self._peer_transport:
                addr = self._peer_transport[peer_id]
                msg = build_heartbeat(
                    self.raft.node_id, self.raft.current_term,
                    self.raft.commit_index,
                )
                RaftTCPClient.send_message(addr, msg)

    def _do_replicate(self, peer_id: str):
        """Replicate log to a peer via TCP if registered (no fallback to avoid recursion)."""
        if peer_id in self._peer_transport:
            from .raft_transport import RaftTCPClient, build_append_entries
            addr = self._peer_transport[peer_id]
            entries = [{"term": e.term, "index": e.index,
                        "command": e.command, "timestamp": e.timestamp}
                       for e in self.raft.log]
            msg = build_append_entries(
                self.raft.node_id, self.raft.current_term,
                entries, len(self.raft.log) - 1,
                self.raft._last_log_term(), self.raft.commit_index,
            )
            RaftTCPClient.send_message(addr, msg)

    def raft_request_vote(self) -> int:
        """
        Request votes from peers via TCP (if transport enabled).
        Returns total votes received (including self).
        """
        from .raft_transport import RaftTCPClient, build_vote_request

        votes = 1  # Self vote
        for peer_id in self.raft.peers:
            if peer_id in self._peer_transport:
                addr = self._peer_transport[peer_id]
                msg = build_vote_request(
                    self.raft.node_id, self.raft.current_term,
                    len(self.raft.log) - 1, self.raft._last_log_term(),
                )
                resp = RaftTCPClient.send_message(addr, msg)
                if resp and resp.data and resp.data.get("vote_granted"):
                    votes += 1
            else:
                # Fallback to simulated
                if self.raft._request_vote(peer_id):
                    votes += 1
        return votes

    def raft_broadcast_heartbeat(self):
        """Broadcast heartbeat to all peers via TCP (if available)"""
        # Use _do_heartbeat to avoid recursion through callback
        self._do_heartbeat()

    def raft_replicate_to(self, peer_id: str):
        """Replicate log to a specific peer via TCP (if available)"""
        # Use _do_replicate to avoid recursion through callback
        self._do_replicate(peer_id)

    def raft_peer_health(self, peer_id: str) -> Optional[dict]:
        """Check peer health via TCP"""
        from .raft_transport import RaftTCPClient

        if peer_id in self._peer_transport:
            addr = self._peer_transport[peer_id]
            return RaftTCPClient.health_check(addr)
        return None

    def reconnect(self, leader: "HybridConsensusNode"):
        print(f"   🔄 Reconnecting: {self.raft.node_id} → {leader.raft.node_id}")

        # 1. Raft state sync
        self.raft.log = list(leader.raft.log)
        self.raft.commit_index = len(self.raft.log) - 1
        self.raft._apply_committed()
        print(f"   ✅ Step 1: Raft state synced ({len(self.raft.log)} entries)")

        # 2. Pending log'u Leader'a gönder
        pending_count = len(self.offline.pending)
        for op in self.offline.pending:
            if op.applied:
                continue
            success, error = leader.raft.propose(op.command)
            if success:
                op.applied = True
        print(f"   ✅ Step 2: {pending_count} pending ops sent to leader")

        # 3. CRDT merge (conflict varsa)
        conflicts = 0
        for op in self.offline.pending:
            if not op.command.get("slug"):
                continue
            local = self.raft.get_state(op.command["slug"])
            remote = leader.raft.get_state(op.command["slug"])
            if local and remote and local.version != remote.version:
                merged = self.crdt.merge(
                    local, remote, self.raft.transitions
                )
                if merged != local:
                    conflicts += 1
                    leader.raft.provide_merge(op.command["slug"], merged)
        print(f"   ✅ Step 3-4: {conflicts} conflict(s) resolved via CRDT merge")

        # 5. Nihai state'i al
        self.raft.state_machine = dict(leader.raft.state_machine)
        self.raft.save_snapshot()
        self.offline.pending.clear()
        self.offline.is_offline = False
        self.raft.role = NodeRole.FOLLOWER
        print(f"   ✅ Step 5: Final state synced ready")

    def get_state(self, slug: str) -> Optional[NodeState]:
        return self.raft.get_state(slug)

    def status(self) -> str:
        return f"{self.raft.status()}\n{self.offline.status}"

    # ── Cluster Health (Phase 5) ──

    def health(self) -> dict:
        return {
            "node_id": self.raft.node_id,
            "role": self.raft.role.value,
            "term": self.raft.current_term,
            "commit_index": self.raft.commit_index,
            "log_length": len(self.raft.log),
            "state_count": len(self.raft.state_machine),
            "is_offline": self.offline.is_offline,
            "pending_count": len(self.offline.pending),
            "peers": self.raft.peers,
        }

    def is_leader(self) -> bool:
        return self.raft.role == NodeRole.LEADER

    def force_election(self) -> bool:
        if self.raft.role != NodeRole.LEADER:
            self.raft._start_election()
            return self.raft.role == NodeRole.LEADER
        return False
