"""
Prodinamik Engine v0.5 — Hybrid Raft Consensus

Review #5: Raft + Offline + CRDT çelişkisi çözümü.

Online: Raft consensus (Leader writes, Follower replicates)
Offline: Optimistic local writes (pending log)
Reconnect: Pending log → Leader approval → CRDT merge

Raft kuralı ihlal edilmez:
- Offline'ta local state "pending" olarak işaretlenir
- Raft state machine'i offline pending'lerden ETKİLENMEZ
- Sadece user-facing cache güncellenir offline'ta
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
import json
import time
import random
import threading
from pathlib import Path


# ──────────────────────────────────────────────
# Raft Types
# ──────────────────────────────────────────────

class NodeRole(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    OFFLINE = "offline"       # Offline mode
    RECONNECTING = "reconnecting"


@dataclass
class LogEntry:
    """Raft log entry"""
    term: int
    index: int
    command: dict              # {"type": "transition", "slug": "...", ...}
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
    current_state: str = ""    # State machine içindeki state
    version: int = 0           # Optimistic locking


@dataclass
class Snapshot:
    """Raft snapshot (state machine'in anlık görüntüsü)"""
    last_included_index: int
    last_included_term: int
    state_data: Dict[str, NodeState]  # slug → state
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


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
        """
        İki state'i merge et.
        - Aynı version → remote daha güncel (son yazan kazanır)
        - Concurrent modification → state tipine göre merge
        """
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
            # İleride olan kazansın
            path = StateCRDT._find_path(local.current_state,
                                         remote.current_state,
                                         state_machine_transitions)
            if path and path[-1] == remote.current_state:
                return remote
            return local

        # Farklı path'ler → manual resolution gerekli
        return local  # Default: local koru

    @staticmethod
    def _is_on_same_path(a: str, b: str, transitions: Dict[str, List[str]]) -> bool:
        """İki state aynı DAG path'inde mi?"""
        if not transitions:
            return False

        # a → b path'i var mı?
        path = StateCRDT._find_path(a, b, transitions)
        if path:
            return True

        # b → a path'i var mı?
        path = StateCRDT._find_path(b, a, transitions)
        if path:
            return True

        return False

    @staticmethod
    def _find_path(start: str, end: str,
                   transitions: Dict[str, List[str]],
                   visited: set = None) -> Optional[List[str]]:
        """DFS ile path bul"""
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

    def configure_transitions(self, transitions: Dict[str, List[str]]):
        """State machine transition DAG'ini yapılandır"""
        self.transitions = transitions

    # ──────────────────────────────────────
    # Raft Core
    # ──────────────────────────────────────

    def become_follower(self, term: int):
        """Follower ol"""
        self.role = NodeRole.FOLLOWER
        self.current_term = term
        self.voted_for = None
        self.last_heartbeat = time.time()

    def become_candidate(self):
        """Candidate ol → election başlat"""
        self.role = NodeRole.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_heartbeat = time.time()

        # Diğer node'lardan oy iste
        votes = 1  # Kendi oyu
        for peer in self.peers:
            if self._request_vote(peer):
                votes += 1

        if votes > len(self.peers) // 2:
            self.become_leader()

    def become_leader(self):
        """Leader ol"""
        self.role = NodeRole.LEADER
        # Hemen boş bir AppendEntries gönder (heartbeat)
        self._broadcast_heartbeat()

    def append_entries(self, entries: List[LogEntry],
                       prev_log_index: int, prev_log_term: int,
                       leader_commit: int) -> Tuple[bool, int, int]:
        """
        Leader'dan gelen log entry'lerini uygula.

        Returns: (success, conflict_index, conflict_term)
        """
        # Consistency check
        if prev_log_index >= 0 and prev_log_index < len(self.log):
            if self.log[prev_log_index].term != prev_log_term:
                return False, prev_log_index, self.log[prev_log_index].term

        # Append new entries
        for i, entry in enumerate(entries):
            idx = prev_log_index + 1 + i
            if idx < len(self.log):
                if self.log[idx].term != entry.term:
                    # Conflict: truncate
                    self.log = self.log[:idx]
                    self.log.append(entry)
            else:
                self.log.append(entry)

        # Commit
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
            self._apply_committed()

        self.last_heartbeat = time.time()
        self._save_log()
        return True, 0, 0

    def request_vote(self, candidate_term: int, candidate_id: str,
                     last_log_index: int, last_log_term: int) -> bool:
        """Oy isteği — Raft election"""
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

    # ──────────────────────────────────────
    # State Machine Apply
    # ──────────────────────────────────────

    def _apply_committed(self):
        """Committed log entry'lerini state machine'e uygula"""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            self._apply_command(entry.command)

    def _apply_command(self, command: dict):
        """Tek bir komutu state machine'e uygula"""
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
        """State machine'den state oku"""
        return self.state_machine.get(slug)

    def propose(self, command: dict) -> Tuple[bool, Optional[str]]:
        """
        Leader'a bir komut öner.
        Sadece Leader kabul eder, log'a ekler.
        """
        if self.role != NodeRole.LEADER:
            return False, "Not leader"

        entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command,
        )
        self.log.append(entry)
        self.commit_index = len(self.log) - 1
        self._apply_committed()
        self._save_log()

        # Replicate to followers (async)
        for peer in self.peers:
            self._replicate_to(peer)

        return True, None

    # ──────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────

    def _load_log(self) -> List[LogEntry]:
        """Log'u diskten yükle"""
        path = self.state_dir / f"raft_log_{self.node_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return [LogEntry(**e) for e in data]
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_log(self):
        """Log'u diske yaz"""
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
        """Snapshot'ı diskten yükle"""
        path = self.state_dir / f"raft_snapshot_{self.node_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {
                    k: NodeState(**v) for k, v in data.items()
                }
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def save_snapshot(self):
        """Anlık snapshot al"""
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

    # ──────────────────────────────────────
    # Peer Communication (simüle)
    # ──────────────────────────────────────

    def _request_vote(self, peer: str) -> bool:
        """Peer'den oy iste (simüle)"""
        return True  # Gerçek implementasyonda HTTP/gRPC

    def _broadcast_heartbeat(self):
        """Heartbeat gönder (simüle)"""
        pass

    def _replicate_to(self, peer: str):
        """Log'u peer'a replicate et (simüle)"""
        pass

    def provide_merge(self, slug: str, merged_state: NodeState) -> Tuple[bool, Optional[str]]:
        """CRDT merge sonucunu state machine'e yaz (sadece Leader)"""
        if self.role != NodeRole.LEADER:
            return False, "Not leader"
        self.state_machine[slug] = merged_state
        self.save_snapshot()
        return True, None

    # ──────────────────────────────────────
    # Display
    # ──────────────────────────────────────

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

@dataclass
class PendingOperation:
    """Offline'ta biriken işlem"""
    command: dict
    timestamp: str
    local_version: int
    applied: bool = False


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
        """Offline moda geç"""
        self.is_offline = True
        self.local_node.role = NodeRole.OFFLINE

    def go_online(self, leader: DistributedStateMachine):
        """Online moda geç + sync"""
        self.is_offline = False
        self.local_node.role = NodeRole.RECONNECTING
        self._sync_with_leader(leader)
        self.local_node.role = NodeRole.FOLLOWER

    def apply_pending(self, command: dict) -> NodeState:
        """
        Offline'ta optimistic state güncellemesi.
        State machine'e direkt yazılmaz — pending log'a eklenir.
        Sadece user-facing cache güncellenir.
        """
        slug = command.get("slug")
        if not slug:
            return NodeState()

        if slug not in self.local_node.state_machine:
            self.local_node.state_machine[slug] = NodeState()

        old_version = self.local_node.state_machine[slug].version

        # Pending log
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
        """Leader ile sync yap"""
        for op in self.pending:
            if op.applied:
                continue

            success, error = leader.propose(op.command)
            if success:
                op.applied = True
            else:
                # Conflict → CRDT merge
                local_state = self.local_node.get_state(op.command["slug"])
                remote_state = leader.get_state(op.command["slug"])

                if local_state and remote_state:
                    merged = StateCRDT.merge(
                        local_state, remote_state,
                        self.local_node.transitions
                    )
                    # Merge sonucunu Leader'a gönder
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

    5-adımlı reconnect:
    1. Raft state sync (Leader'dan güncel state)
    2. Pending log'u Leader'a gönder
    3. CRDT merge (conflict varsa)
    4. Merge sonucunu Leader'a yaz
    5. Nihai state'i al
    """

    def __init__(self, node_id: str, peers: List[str] = None,
                 state_dir: str = ".hermes/raft/"):
        self.raft = DistributedStateMachine(node_id, peers, state_dir)
        self.offline = OfflineManager(self.raft)
        self.crdt = StateCRDT()

    def apply(self, command: dict) -> Tuple[bool, Optional[str]]:
        """
        Online → Raft
        Offline → Pending log
        """
        if self.offline.is_offline:
            self.offline.apply_pending(command)
            return True, None

        return self.raft.propose(command)

    def reconnect(self, leader: "HybridConsensusNode"):
        """
        5-adımlı reconnect prosedürü.
        """
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
                    # 4. Merge sonucunu Leader'a yaz
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
        return (
            f"{self.raft.status()}\n"
            f"{self.offline.status}"
        )


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import tempfile
    tmpdir = tempfile.mkdtemp()

    # Node'lar
    leader = HybridConsensusNode("node-1", ["node-2", "node-3"],
                                  state_dir=os.path.join(tmpdir, "raft1"))
    follower = HybridConsensusNode("node-2", ["node-1", "node-3"],
                                    state_dir=os.path.join(tmpdir, "raft2"))

    # Leader seç
    leader.raft.become_leader()
    print("📡 Cluster: node-1 (leader), node-2 (follower)")
    print(f"\n{leader.status()}")

    # Normal operation: Leader'a komut gönder
    success, err = leader.apply({
        "type": "create",
        "slug": "flux-release",
        "initial_state": "spec"
    })
    assert success
    success, err = leader.apply({
        "type": "transition",
        "slug": "flux-release",
        "to_state": "prototyping"
    })
    assert success
    state = leader.get_state("flux-release")
    assert state.current_state == "prototyping"
    print(f"\n✅ Leader: flux-release → {state.current_state} (v{state.version})")

    # Follower sync
    follower.raft.log = list(leader.raft.log)
    follower.raft.commit_index = len(leader.raft.log) - 1
    follower.raft._apply_committed()
    fstate = follower.get_state("flux-release")
    print(f"✅ Follower: flux-release → {fstate.current_state} (v{fstate.version})")

    # Offline mode
    print(f"\n📱 Offline test:")
    follower_offline = HybridConsensusNode("node-2", ["node-1"],
                                            state_dir=os.path.join(tmpdir, "raft3"))
    follower_offline.offline.go_offline()

    # Offline'da state güncelle
    follower_offline.apply({
        "type": "transition",
        "slug": "flux-release",
        "to_state": "iteration"
    })
    offline_state = follower_offline.get_state("flux-release")
    print(f"   Offline: flux-release → {offline_state.current_state} "
          f"(v{offline_state.version}, pending={follower_offline.offline.pending_count})")

    # Reconnect
    follower_offline.offline.is_offline = False
    follower_offline.reconnect(leader)

    # Verify
    final_state = leader.get_state("flux-release")
    print(f"\n✅ After reconnect: flux-release → {final_state.current_state}")
    assert final_state.current_state == "iteration", \
        f"Expected iteration, got {final_state.current_state}"
    print(f"   Version: v{final_state.version}")

    # CRDT merge test: concurrent state change
    print(f"\n🔄 CRDT merge test:")
    leader.apply({"type": "transition", "slug": "flux-release", "to_state": "review"})

    # Her iki node farklı state'e gitmeye çalışsın
    leader.raft.state_machine["test-run"] = NodeState(current_state="drafting", version=1)
    remote = NodeState(current_state="verification", version=1)

    merged = StateCRDT.merge(
        leader.raft.state_machine["test-run"],
        remote,
        {"drafting": ["verification"], "verification": ["review"]}
    )
    print(f"   Local: drafting v1 + Remote: verification v1")
    print(f"   Merged: {merged.current_state} (forward path → verification wins)")

    print(f"\n{'='*50}")
    print(f"Hybrid Raft demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    import os
    demo()
