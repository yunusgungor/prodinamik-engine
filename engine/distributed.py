"""
Prodinamik Engine v1.1 — Distributed Run Coordinator

Multi-node run coordination using Raft consensus.
Ensures run operations are distributed, consistent, and fault-tolerant.

Architecture:
  - One Raft leader coordinates run operations
  - Followers redirect run requests to the leader
  - On leader failure, a new leader is elected via Raft
  - Run state is replicated across all nodes via Raft log
"""

import json
import time
import threading
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class DistributedRun:
    """Run state replicated across cluster"""
    slug: str
    profile: str
    title: str
    current_state: str
    owner_node: str  # Node responsible for this run
    created_at: str = ""
    updated_at: str = ""
    version: int = 0
    status: str = "active"  # active | archived | migrated

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class DistributedRunCoordinator:
    """
    Coordinates run operations across a Raft cluster.

    Each node has a coordinator. Only the leader node's coordinator
    is authoritative. Followers proxy requests to the leader via Raft.

    Usage:
        coordinator = DistributedRunCoordinator(raft_node)
        run = coordinator.create_run("software", "FFT impl")
        run = coordinator.transition_run("fft-impl", "review")
    """

    def __init__(self, raft_node=None):
        self.raft = raft_node  # HybridConsensusNode
        self._runs: Dict[str, DistributedRun] = {}
        self._lock = threading.Lock()
        self._leader_cache: Optional[str] = None
        self._leader_cache_time: float = 0
        self._leader_cache_ttl: float = 5.0  # seconds

    # ── Cluster Awareness ──

    @property
    def is_leader(self) -> bool:
        """Check if this node is the cluster leader"""
        if self.raft:
            return self.raft.is_leader()
        return True  # Standalone mode

    def get_leader(self) -> Optional[str]:
        """
        Get current cluster leader node ID.
        Uses cache to avoid repeated TCP calls.
        """
        now = time.time()
        if self._leader_cache and (now - self._leader_cache_time) < self._leader_cache_ttl:
            return self._leader_cache

        if self.raft:
            leader_id = None
            # Try Raft cluster health
            if hasattr(self.raft, 'raft_peer_health'):
                for peer_id in self.raft.raft.peers:
                    health = self.raft.raft_peer_health(peer_id)
                    if health and health.get("role") == "leader":
                        leader_id = peer_id
                        break

            if not leader_id and self.is_leader:
                leader_id = self.raft.raft.node_id

            self._leader_cache = leader_id
            self._leader_cache_time = now
            return leader_id
        return "standalone"

    # ── Run Operations ──

    def create_run(self, profile: str, title: str,
                   slug: str = None) -> Tuple[Optional[DistributedRun], str]:
        """
        Create a run on the cluster.
        Returns (run, error_message).
        """
        if not slug:
            import re
            slug = re.sub(r'[^a-z0-9-]+', '-', title.lower()).strip('-')
            slug = f"{slug}-{int(time.time() * 1000)}"

        with self._lock:
            if slug in self._runs:
                return None, f"Run '{slug}' already exists"

            run = DistributedRun(
                slug=slug,
                profile=profile,
                title=title,
                current_state="created",
                owner_node=self.raft.raft.node_id if self.raft else "standalone",
            )

            # Replicate via Raft
            if self.raft and self.is_leader:
                success, err = self.raft.apply({
                    "type": "distributed_create",
                    "slug": slug,
                    "profile": profile,
                    "title": title,
                    "owner": run.owner_node,
                })
                if not success:
                    return None, f"Raft replication failed: {err}"

            self._runs[slug] = run
            return run, ""

    def get_run(self, slug: str) -> Optional[DistributedRun]:
        """Get run by slug"""
        with self._lock:
            return self._runs.get(slug)

    def list_runs(self, status: str = None) -> List[DistributedRun]:
        """List all runs, optionally filtered by status"""
        with self._lock:
            runs = list(self._runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    def transition_run(self, slug: str, new_state: str) -> Tuple[bool, str]:
        """
        Transition a run to a new state.

        If the run is owned by another node, the transition is
        proposed to the Raft leader for replication.
        """
        with self._lock:
            run = self._runs.get(slug)
            if not run:
                return False, f"Run '{slug}' not found"

            # Check ownership
            if self.raft and run.owner_node != self.raft.raft.node_id:
                # Propose via Raft
                success, err = self.raft.apply({
                    "type": "distributed_transition",
                    "slug": slug,
                    "to_state": new_state,
                })
                if not success:
                    return False, f"Raft propose failed: {err}"

            run.current_state = new_state
            run.updated_at = datetime.now().isoformat()
            run.version += 1
            return True, ""

    def archive_run(self, slug: str) -> Tuple[bool, str]:
        """Archive a run"""
        with self._lock:
            run = self._runs.get(slug)
            if not run:
                return False, f"Run '{slug}' not found"
            run.status = "archived"
            run.updated_at = datetime.now().isoformat()
            return True, ""

    def sync_from_raft(self, command: dict):
        """
        Apply a Raft-replicated command to local state.
        Called when new Raft entries are committed.
        """
        cmd_type = command.get("type", "")

        if cmd_type == "distributed_create":
            slug = command["slug"]
            run = DistributedRun(
                slug=slug,
                profile=command["profile"],
                title=command["title"],
                current_state="created",
                owner_node=command.get("owner", "unknown"),
            )
            with self._lock:
                self._runs[slug] = run

        elif cmd_type == "distributed_transition":
            slug = command["slug"]
            new_state = command["to_state"]
            with self._lock:
                if slug in self._runs:
                    self._runs[slug].current_state = new_state
                    self._runs[slug].updated_at = datetime.now().isoformat()
                    self._runs[slug].version += 1

    # ── Cluster Sync ──

    def sync_from_leader(self, leader_coordinator: "DistributedRunCoordinator"):
        """
        Full state sync from leader.
        Used during reconnection or initial join.
        """
        leader_runs = leader_coordinator.list_runs()
        with self._lock:
            self._runs = {r.slug: r for r in leader_runs}

    def cluster_status(self) -> dict:
        """Return cluster coordination status"""
        return {
            "is_leader": self.is_leader,
            "leader": self.get_leader(),
            "local_node": self.raft.raft.node_id if self.raft else "standalone",
            "run_count": len(self._runs),
            "active_runs": sum(1 for r in self._runs.values() if r.status == "active"),
        }
