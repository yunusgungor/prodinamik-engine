"""Prodinamik AI Grid — Agent Registry

Tracks worker node capabilities, skills, and load.
Each node registers with its capabilities when it starts.

Architecture:
    AgentRegistry (Coordinator)
    ├── Node Registration (capabilities, skills, labels)
    ├── Heartbeat Tracking (TTL-based liveness)
    ├── Load Tracking (active workers, capacity)
    └── Capability Query (find nodes by skill/tag)

Usage:
    registry = AgentRegistry()
    registry.register_node("node-1", capabilities=["llm", "search", "code"])
    registry.heartbeat("node-1", {"active_workers": 2, "max_workers": 3})
    nodes = registry.find_by_capability("llm")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from ..log import get_logger


@dataclass
class NodeInfo:
    """Information about a registered worker node"""
    node_id: str
    hostname: str = ""
    version: str = ""
    capabilities: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    max_workers: int = 3
    active_workers: int = 0
    last_heartbeat: Optional[float] = None
    first_seen: float = field(default_factory=time.time)
    is_healthy: bool = True
    last_error: Optional[str] = None

    @property
    def available_slots(self) -> int:
        return max(0, self.max_workers - self.active_workers)

    @property
    def load_ratio(self) -> float:
        return self.active_workers / self.max_workers if self.max_workers > 0 else 0.0

    def is_alive(self, ttl_seconds: float = 10.0) -> bool:
        if self.last_heartbeat is None:
            return False
        return (time.time() - self.last_heartbeat) < ttl_seconds


@dataclass
class CapabilityQuery:
    """Result of a capability query"""
    node_id: str
    hostname: str
    available_slots: int
    load_ratio: float
    is_alive: bool
    capabilities: List[str]
    skills: List[str]


class AgentRegistry:
    """
    Central registry for all worker nodes.

    Tracks:
    - Node identity and capabilities
    - Heartbeat-based liveness (TTL)
    - Current load (active workers / capacity)
    - Skills and labels

    Runs on the Coordinator node.
    """

    def __init__(self, heartbeat_ttl: float = 10.0):
        self.heartbeat_ttl = heartbeat_ttl
        self.log = get_logger()
        self._nodes: Dict[str, NodeInfo] = {}
        self._capability_index: Dict[str, Set[str]] = {}  # capability -> {node_ids}
        self._total_heartbeats_received: int = 0

    def register_node(
        self,
        node_id: str,
        hostname: str = "",
        version: str = "",
        capabilities: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
        max_workers: int = 3,
    ) -> NodeInfo:
        """Register or update a worker node"""
        existing = self._nodes.get(node_id)
        if existing:
            # Update existing
            existing.hostname = hostname or existing.hostname
            existing.version = version or existing.version
            existing.max_workers = max_workers or existing.max_workers
            if capabilities is not None:
                self._update_capability_index(node_id, existing.capabilities, capabilities)
                existing.capabilities = capabilities
            if skills is not None:
                existing.skills = skills
            if labels is not None:
                existing.labels.update(labels)
            existing.is_healthy = True
            info = existing
        else:
            # New node
            if capabilities:
                for cap in capabilities:
                    if cap not in self._capability_index:
                        self._capability_index[cap] = set()
                    self._capability_index[cap].add(node_id)

            info = NodeInfo(
                node_id=node_id,
                hostname=hostname,
                version=version,
                capabilities=capabilities or [],
                skills=skills or [],
                labels=labels or {},
                max_workers=max_workers or 3,
            )
            self._nodes[node_id] = info

        self.log.info(f"Node registered: {node_id} ({hostname}) — {len(info.capabilities)} capabilities")
        return info

    def _update_capability_index(self, node_id: str, old_caps: List[str], new_caps: List[str]):
        """Update capability index when a node changes capabilities"""
        old_set = set(old_caps)
        new_set = set(new_caps)

        # Removed capabilities
        for cap in old_set - new_set:
            if cap in self._capability_index and node_id in self._capability_index[cap]:
                self._capability_index[cap].discard(node_id)

        # Added capabilities
        for cap in new_set - old_set:
            if cap not in self._capability_index:
                self._capability_index[cap] = set()
            self._capability_index[cap].add(node_id)

    def unregister_node(self, node_id: str) -> bool:
        """Remove a node from the registry"""
        if node_id not in self._nodes:
            return False

        info = self._nodes.pop(node_id)
        # Remove from capability index
        for cap in info.capabilities:
            if cap in self._capability_index and node_id in self._capability_index[cap]:
                self._capability_index[cap].discard(node_id)

        self.log.info(f"Node unregistered: {node_id}")
        return True

    def heartbeat(self, node_id: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """Record a heartbeat from a worker node"""
        info = self._nodes.get(node_id)
        if not info:
            return False  # Node not registered

        info.last_heartbeat = time.time()
        info.is_healthy = True
        self._total_heartbeats_received += 1

        if data:
            info.active_workers = data.get("active_workers", info.active_workers)
            if data.get("worker_slots_available") is not None:
                info.max_workers = info.active_workers + data["worker_slots_available"]

        return True

    def mark_unhealthy(self, node_id: str, error: str = ""):
        """Mark a node as unhealthy"""
        info = self._nodes.get(node_id)
        if info:
            info.is_healthy = False
            info.last_error = error or "Unknown"

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        return self._nodes.get(node_id)

    def list_nodes(
        self,
        alive_only: bool = False,
        healthy_only: bool = False,
    ) -> List[NodeInfo]:
        nodes = list(self._nodes.values())
        if alive_only:
            nodes = [n for n in nodes if n.is_alive(self.heartbeat_ttl)]
        if healthy_only:
            nodes = [n for n in nodes if n.is_healthy]
        return sorted(nodes, key=lambda n: n.node_id)

    def get_alive_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.is_alive(self.heartbeat_ttl))

    def find_by_capability(self, capability: str) -> List[CapabilityQuery]:
        """Find nodes that have a specific capability"""
        node_ids = self._capability_index.get(capability, set())
        results = []
        for nid in node_ids:
            info = self._nodes.get(nid)
            if info and info.is_alive(self.heartbeat_ttl) and info.is_healthy:
                results.append(CapabilityQuery(
                    node_id=info.node_id,
                    hostname=info.hostname,
                    available_slots=info.available_slots,
                    load_ratio=info.load_ratio,
                    is_alive=True,
                    capabilities=info.capabilities,
                    skills=info.skills,
                ))
        return sorted(results, key=lambda r: r.load_ratio)  # Least loaded first

    def find_by_skill(self, skill: str) -> List[CapabilityQuery]:
        """Find nodes that have a specific skill"""
        results = []
        for info in self._nodes.values():
            if skill in info.skills and info.is_alive(self.heartbeat_ttl) and info.is_healthy:
                results.append(CapabilityQuery(
                    node_id=info.node_id,
                    hostname=info.hostname,
                    available_slots=info.available_slots,
                    load_ratio=info.load_ratio,
                    is_alive=True,
                    capabilities=info.capabilities,
                    skills=info.skills,
                ))
        return sorted(results, key=lambda r: r.load_ratio)

    def find_best_node(self, affinity: str = "", capability: str = "") -> Optional[str]:
        """
        Find the best node for a task.
        Uses round-robin among least-loaded matching nodes.
        """
        candidates = []
        if capability:
            candidates = self.find_by_capability(capability)
        elif affinity:
            # Try capability match first, then fall back
            candidates = self.find_by_capability(affinity)

        if not candidates:
            # Fall back: any alive healthy node
            candidates = [
                CapabilityQuery(
                    node_id=n.node_id, hostname=n.hostname,
                    available_slots=n.available_slots, load_ratio=n.load_ratio,
                    is_alive=True, capabilities=n.capabilities, skills=n.skills,
                )
                for n in self._nodes.values()
                if n.is_alive(self.heartbeat_ttl) and n.is_healthy and n.available_slots > 0
            ]

        if not candidates:
            return None

        # Pick least loaded
        candidates.sort(key=lambda c: c.load_ratio)
        return candidates[0].node_id

    def cleanup_stale_nodes(self) -> int:
        """Remove nodes that haven't sent heartbeat in TTL * 3"""
        stale_count = 0
        for node_id, info in list(self._nodes.items()):
            if info.last_heartbeat and (time.time() - info.last_heartbeat) > self.heartbeat_ttl * 3:
                self.unregister_node(node_id)
                stale_count += 1
        if stale_count:
            self.log.info(f"Cleaned up {stale_count} stale nodes")
        return stale_count

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self._nodes),
            "alive": self.get_alive_count(),
            "healthy": sum(1 for n in self._nodes.values() if n.is_healthy),
            "total_capabilities": len(self._capability_index),
            "heartbeats_received": self._total_heartbeats_received,
            "total_worker_slots": sum(n.max_workers for n in self._nodes.values()),
            "active_workers": sum(n.active_workers for n in self._nodes.values()),
        }
