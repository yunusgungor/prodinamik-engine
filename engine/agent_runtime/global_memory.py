"""Prodinamik AI Grid — Global Memory (Tier 3)

CRDT-based eventually consistent global memory shared across nodes.
Uses a Last-Writer-Wins (LWW) register for simplicity.
Sync via Coordinator node.

Architecture:
    GlobalMemory (Coordinator)
    ├── LWW Register (key → {value, timestamp, node_id})
    ├── CRDT Merge (Last-Writer-Wins for conflicts)
    ├── Namespace Isolation (per-agent, per-task)
    └── Sync API (pull/push from worker nodes)

Usage:
    gmem = GlobalMemory(coordinator_node_id="node-1")
    await gmem.set("key", "value", namespace="shared")
    value = await gmem.get("key", namespace="shared")
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ..log import get_logger


@dataclass(order=True)
class CRDTEntry:
    """A CRDT register entry with timestamp for LWW merge"""
    key: str
    value: Any = None
    namespace: str = "default"
    timestamp: float = 0.0  # Unix timestamp for LWW
    node_id: str = ""
    deleted: bool = False

    def merge_with(self, other: CRDTEntry) -> CRDTEntry:
        """LWW merge: the one with later timestamp wins"""
        if other.timestamp > self.timestamp:
            return other
        return self


class GlobalMemory:
    """
    Tier 3: Global memory shared across all nodes in the cluster.
    
    - Last-Writer-Wins (LWW) CRDT for conflict resolution
    - Namespace isolation for different agents/tasks
    - Deletion tombstone support
    - Periodic sync via coordinator
    
    Usage:
        gmem = GlobalMemory(node_id="coordinator-1")
        await gmem.set("config", {"model": "gpt-4"}, namespace="agents")
        value = await gmem.get("config", namespace="agents")
        all_configs = await gmem.list_namespace("agents")
    """
    
    def __init__(
        self,
        node_id: str = "default",
        max_entries_per_ns: int = 1000,
    ):
        self.node_id = node_id
        self.max_entries = max_entries_per_ns
        self.log = get_logger()
        
        # Main store: namespace → {key: CRDTEntry}
        self._store: Dict[str, Dict[str, CRDTEntry]] = {}
        
        # Sync tracking
        self._last_sync: Optional[float] = None
        self._version_vector: Dict[str, float] = {}  # node_id → max timestamp seen
        self._total_writes: int = 0
        self._total_reads: int = 0
    
    async def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        node_id: Optional[str] = None,
    ) -> None:
        """Set a value with LWW semantics"""
        if namespace not in self._store:
            self._store[namespace] = {}
        
        entry = CRDTEntry(
            key=key,
            value=self._serialize(value),
            namespace=namespace,
            timestamp=time.time(),
            node_id=node_id or self.node_id,
        )
        
        existing = self._store[namespace].get(key)
        if existing:
            entry = existing.merge_with(entry)
        
        self._store[namespace][key] = entry
        self._total_writes += 1
        self._version_vector[entry.node_id] = max(
            self._version_vector.get(entry.node_id, 0),
            entry.timestamp,
        )
    
    async def get(
        self,
        key: str,
        namespace: str = "default",
    ) -> Optional[Any]:
        """Get a value by key"""
        ns = self._store.get(namespace, {})
        entry = ns.get(key)
        if entry is None or entry.deleted:
            return None
        self._total_reads += 1
        return entry.value
    
    async def delete(
        self,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """Delete a key (tombstone LWW)"""
        ns = self._store.get(namespace, {})
        if key not in ns:
            return False
        
        entry = ns[key]
        entry.deleted = True
        entry.timestamp = time.time()
        self._total_writes += 1
        return True
    
    async def list_namespace(
        self,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """List all non-deleted entries in a namespace"""
        ns = self._store.get(namespace, {})
        return {
            k: e.value for k, e in ns.items()
            if not e.deleted
        }
    
    async def list_namespaces(self) -> List[str]:
        return list(self._store.keys())
    
    async def clear_namespace(self, namespace: str) -> int:
        """Clear all entries in a namespace"""
        ns = self._store.get(namespace, {})
        count = len(ns)
        for entry in ns.values():
            entry.deleted = True
            entry.timestamp = time.time()
        return count
    
    async def merge(self, entries: List[CRDTEntry]) -> int:
        """Merge remote entries (CRDT sync)"""
        merged = 0
        for entry in entries:
            if entry.namespace not in self._store:
                self._store[entry.namespace] = {}
            
            existing = self._store[entry.namespace].get(entry.key)
            if existing:
                merged_entry = existing.merge_with(entry)
                if merged_entry is entry:
                    merged += 1
                self._store[entry.namespace][entry.key] = merged_entry
            else:
                self._store[entry.namespace][entry.key] = entry
                merged += 1
            
            self._version_vector[entry.node_id] = max(
                self._version_vector.get(entry.node_id, 0),
                entry.timestamp,
            )
        
        return merged
    
    async def get_changes_since(
        self,
        node_id: str,
        since_timestamp: float = 0,
    ) -> List[CRDTEntry]:
        """Get all changes since a timestamp for sync"""
        changes = []
        for ns in self._store.values():
            for entry in ns.values():
                if entry.timestamp > since_timestamp and entry.node_id != node_id:
                    changes.append(entry)
        return changes
    
    async def sync_snapshot(self) -> Dict[str, List[Dict]]:
        """Full snapshot for initial sync"""
        snapshot = {}
        for namespace, entries in self._store.items():
            snapshot[namespace] = [
                {
                    "key": e.key,
                    "value": e.value,
                    "timestamp": e.timestamp,
                    "node_id": e.node_id,
                    "deleted": e.deleted,
                }
                for e in entries.values()
                if not e.deleted
            ]
        return snapshot
    
    async def get_stats(self) -> Dict[str, Any]:
        ns_counts = {
            ns: len({k: e for k, e in entries.items() if not e.deleted})
            for ns, entries in self._store.items()
        }
        return {
            "namespaces": len(self._store),
            "entries_per_ns": ns_counts,
            "total_active": sum(ns_counts.values()),
            "total_writes": self._total_writes,
            "total_reads": self._total_reads,
            "nodes_tracked": list(self._version_vector.keys()),
            "last_sync": self._last_sync,
        }
    
    def _serialize(self, value: Any) -> Any:
        """Ensure value is JSON-serializable"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (dict, list)):
            try:
                json.dumps(value)
                return value
            except (TypeError, ValueError):
                return str(value)
        return str(value)
