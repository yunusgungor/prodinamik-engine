"""Prodinamik AI Grid — Memory System

3-Tier Memory Architecture:
    Tier 1: Ephemeral Memory  (in-RAM, task lifetime, <1μs access)
    Tier 2: Local Persistent  (SQLite, per-node, cross-session)
    Tier 3: Global Memory     (Coordinator, CRDT synced — FUTURE)

Usage:
    from .memory import EphemeralMemory, LocalMemory, create_memory_store

    # Tier 1: fast, temporary
    eph = EphemeralMemory()
    eph.store("key", "value")

    # Tier 2: persistent, cross-session
    local = LocalMemory(node_id="node-1", db_path="./data/agent_memory.db")
    await local.initialize()
    await local.save("workflow", {"name": "test", "result": "pass"})
    results = await local.query("workflow", limit=5)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from ..log import get_logger


# ════════════════════════════════════════════════
# Tier 1: Ephemeral Memory
# ════════════════════════════════════════════════

class EphemeralMemory:
    """
    Tier 1: In-memory, task-lifetime storage.

    - Sub-millisecond access
    - Auto-cleaned when task completes
    - No persistence
    - Use for: current conversation, recent tool outputs, temporary state
    """

    def __init__(self, max_entries: int = 100, max_tokens: int = 2000):
        self._store: Dict[str, Any] = {}
        self._tags: Dict[str, List[str]] = {}  # tag → list of keys
        self._max_entries = max_entries
        self._max_tokens = max_tokens
        self._access_count = 0
        self._lock = Lock()
        self.log = get_logger()

    def store(self, key: str, value: Any, tags: Optional[List[str]] = None) -> None:
        """Store a value with optional tags"""
        with self._lock:
            # Evict oldest if at capacity
            if len(self._store) >= self._max_entries and key not in self._store:
                self._evict_one()

            self._store[key] = {
                "value": value,
                "created_at": datetime.now().isoformat(),
                "accessed_at": datetime.now().isoformat(),
                "access_count": 0,
            }

            # Tags
            if tags:
                for tag in tags:
                    if tag not in self._tags:
                        self._tags[tag] = []
                    if key not in self._tags[tag]:
                        self._tags[tag].append(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key"""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            entry["access_count"] += 1
            entry["accessed_at"] = datetime.now().isoformat()
            self._access_count += 1
            return entry["value"]

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Simple keyword search over stored values"""
        query_lower = query.lower()
        results = []

        with self._lock:
            for key, entry in self._store.items():
                value_str = str(entry["value"]).lower()
                if query_lower in key.lower() or query_lower in value_str:
                    results.append({
                        "key": key,
                        "value": entry["value"],
                        "created_at": entry["created_at"],
                    })
                    if len(results) >= limit:
                        break

        return results

    def get_by_tag(self, tag: str) -> List[Tuple[str, Any]]:
        """Get all values with a given tag"""
        with self._lock:
            keys = self._tags.get(tag, [])
            return [(k, self._store[k]["value"]) for k in keys if k in self._store]

    def delete(self, key: str) -> bool:
        """Delete a key"""
        with self._lock:
            if key in self._store:
                del self._store[key]
                # Remove from tags
                for tag_keys in self._tags.values():
                    if key in tag_keys:
                        tag_keys.remove(key)
                return True
            return False

    def clear(self) -> None:
        """Clear all memory"""
        with self._lock:
            self._store.clear()
            self._tags.clear()
            self._access_count = 0

    def _evict_one(self) -> None:
        """Evict least recently accessed entry"""
        if not self._store:
            return
        # Evict any entry by LRU
        oldest_key = min(self._store.keys(), key=lambda k: self._store[k]["accessed_at"])
        # Remove from tags first
        old_entry = self._store.pop(oldest_key, None)
        if old_entry:
            for tag_keys in self._tags.values():
                if oldest_key in tag_keys:
                    tag_keys.remove(oldest_key)

    @property
    def count(self) -> int:
        return len(self._store)

    @property
    def keys(self) -> List[str]:
        return list(self._store.keys())

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self._store),
            "max_entries": self._max_entries,
            "access_count": self._access_count,
            "tags": len(self._tags),
        }

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        self.store(key, value)


# ════════════════════════════════════════════════
# Tier 2: Local Persistent Memory (SQLite)
# ════════════════════════════════════════════════

@dataclass
class MemoryEntry:
    """A persistent memory entry"""
    key: str
    value: Any
    namespace: str = "default"
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0


class LocalMemory:
    """
    Tier 2: Local persistent memory backed by SQLite.

    - Survives node restarts
    - Cross-session recall
    - Namespaced storage (for different agent types)
    - Tagged queries for flexible retrieval
    - Auto-vacuum to prevent bloat

    Usage:
        memory = LocalMemory(node_id="node-1", db_path="./data/agent_memory.db")
        await memory.initialize()
        await memory.save("workflow:test-1", {"status": "complete"}, namespace="workflow")
        results = await memory.query("workflow:", namespace="workflow")
    """

    def __init__(
        self,
        node_id: str = "default",
        db_path: Optional[str] = None,
        max_entries: int = 1000,
        vacuum_interval: int = 100,  # Run VACUUM every N writes
    ):
        self.node_id = node_id
        self.db_path = db_path or os.path.join(
            os.environ.get("PRODINAMIK_DATA_DIR", "./data"),
            f"agent_memory_{node_id}.db",
        )
        self.max_entries = max_entries
        self.vacuum_interval = vacuum_interval
        self.log = get_logger()

        self._conn: Optional[sqlite3.Connection] = None
        self._write_count = 0
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database and schema"""
        if self._initialized:
            return

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for concurrent reads
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        # Create schema
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 0,
                UNIQUE(node_id, namespace, key)
            );

            CREATE INDEX IF NOT EXISTS idx_memory_node
                ON agent_memory(node_id, namespace);
            CREATE INDEX IF NOT EXISTS idx_memory_key
                ON agent_memory(key);
            CREATE INDEX IF NOT EXISTS idx_memory_tags
                ON agent_memory(tags);

            CREATE TABLE IF NOT EXISTS agent_memory_meta (
                node_id TEXT PRIMARY KEY,
                last_cleanup TEXT,
                total_writes INTEGER DEFAULT 0,
                total_reads INTEGER DEFAULT 0
            );
        """)

        self._conn.commit()
        self._initialized = True
        self.log.debug(f"LocalMemory initialized: {self.db_path}")

    async def close(self) -> None:
        """Close database connection"""
        if self._conn:
            # Final vacuum if needed
            if self._write_count >= self.vacuum_interval:
                try:
                    self._conn.execute("PRAGMA optimize")
                except Exception:
                    pass
            self._conn.close()
            self._conn = None
            self._initialized = False

    async def save(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Save a value to persistent memory"""
        await self._ensure_init()

        value_json = json.dumps(value) if not isinstance(value, str) else value
        tags_str = ",".join(tags) if tags else ""
        now = datetime.now().isoformat()

        try:
            cur = self._conn.execute("""
                INSERT INTO agent_memory
                    (node_id, namespace, key, value, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id, namespace, key) DO UPDATE SET
                    value = excluded.value,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at,
                    access_count = access_count + 1
            """, (self.node_id, namespace, key, value_json, tags_str, now, now))

            self._conn.commit()
            self._write_count += 1

            # Periodic maintenance
            if self._write_count % self.vacuum_interval == 0:
                await self._maintenance()

            return True
        except Exception as e:
            self.log.error(f"Memory save failed: {e}")
            return False

    async def load(
        self,
        key: str,
        namespace: str = "default",
    ) -> Optional[Any]:
        """Load a value from persistent memory"""
        await self._ensure_init()

        try:
            cur = self._conn.execute(
                "SELECT value FROM agent_memory WHERE node_id=? AND namespace=? AND key=?",
                (self.node_id, namespace, key),
            )
            row = cur.fetchone()
            if row is None:
                return None

            # Update access count
            self._conn.execute(
                "UPDATE agent_memory SET access_count = access_count + 1 WHERE node_id=? AND namespace=? AND key=?",
                (self.node_id, namespace, key),
            )
            self._conn.commit()

            value = row["value"]
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            self.log.error(f"Memory load failed: {e}")
            return None

    async def query(
        self,
        key_pattern: str,
        namespace: str = "default",
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """Query memory entries by key pattern (LIKE)"""
        await self._ensure_init()

        pattern = key_pattern.replace("*", "%").replace("?", "_")
        if "%" not in pattern:
            pattern = f"%{pattern}%"

        try:
            cur = self._conn.execute(
                """SELECT * FROM agent_memory
                   WHERE node_id=? AND namespace=? AND key LIKE ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (self.node_id, namespace, pattern, limit),
            )

            results = []
            for row in cur.fetchall():
                value = row["value"]
                try:
                    parsed_value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    parsed_value = value

                tags = [t.strip() for t in row["tags"].split(",") if t.strip()] if row["tags"] else []

                results.append(MemoryEntry(
                    key=row["key"],
                    value=parsed_value,
                    namespace=row["namespace"],
                    tags=tags,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    access_count=row["access_count"],
                ))

            return results
        except Exception as e:
            self.log.error(f"Memory query failed: {e}")
            return []

    async def delete(
        self,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """Delete a memory entry"""
        await self._ensure_init()

        try:
            cur = self._conn.execute(
                "DELETE FROM agent_memory WHERE node_id=? AND namespace=? AND key=?",
                (self.node_id, namespace, key),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            self.log.error(f"Memory delete failed: {e}")
            return False

    async def save_run_memory(
        self,
        run_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Convenience: save a run's memory (goal, summary, metrics)"""
        await self.save(f"run:{run_id}", data, namespace="runs")

        # Also index by goal keywords
        goal = data.get("goal", "")
        if goal:
            words = goal.lower().split()[:5]
            for word in words:
                if len(word) > 3:
                    await self.save(f"index:{word}:{run_id[:8]}", run_id, namespace="index")

    async def recall(self, goal: str, limit: int = 5) -> List[MemoryEntry]:
        """Recall relevant past runs for a goal"""
        # Search by goal keywords
        keywords = [w.lower() for w in goal.split() if len(w) > 3]
        seen = set()
        results = []

        for word in keywords[:5]:
            entries = await self.query(f"index:{word}:", namespace="index", limit=limit)
            for entry in entries:
                run_id = entry.value
                if run_id in seen:
                    continue
                seen.add(run_id)
                run_data = await self.load(f"run:{run_id}", namespace="runs")
                if run_data:
                    results.append(MemoryEntry(
                        key=f"run:{run_id}",
                        value=run_data,
                        namespace="runs",
                    ))

        return results[:limit]

    async def count(self, namespace: str = "default") -> int:
        """Count entries in a namespace"""
        await self._ensure_init()
        cur = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_memory WHERE node_id=? AND namespace=?",
            (self.node_id, namespace),
        )
        row = cur.fetchone()
        return row["cnt"] if row else 0

    async def clear_namespace(self, namespace: str) -> int:
        """Clear all entries in a namespace"""
        await self._ensure_init()
        cur = self._conn.execute(
            "DELETE FROM agent_memory WHERE node_id=? AND namespace=?",
            (self.node_id, namespace),
        )
        self._conn.commit()
        return cur.rowcount

    async def clear_all(self) -> None:
        """Clear all memory"""
        await self._ensure_init()
        self._conn.execute("DELETE FROM agent_memory WHERE node_id=?", (self.node_id,))
        self._conn.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        await self._ensure_init()

        try:
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

            cur = self._conn.execute(
                "SELECT namespace, COUNT(*) as cnt FROM agent_memory WHERE node_id=? GROUP BY namespace",
                (self.node_id,),
            )
            namespace_counts = {row["namespace"]: row["cnt"] for row in cur.fetchall()}

            return {
                "db_path": self.db_path,
                "db_size_bytes": db_size,
                "total_entries": sum(namespace_counts.values()),
                "namespace_counts": namespace_counts,
                "write_count": self._write_count,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Internal ──

    async def _ensure_init(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def _maintenance(self) -> None:
        """Periodic maintenance"""
        try:
            # Enforce max entries per namespace
            cur = self._conn.execute(
                "SELECT namespace FROM agent_memory WHERE node_id=? GROUP BY namespace",
                (self.node_id,),
            )
            for row in cur.fetchall():
                ns = row["namespace"]
                cnt = self._conn.execute(
                    "SELECT COUNT(*) as cnt FROM agent_memory WHERE node_id=? AND namespace=?",
                    (self.node_id, ns),
                ).fetchone()["cnt"]

                if cnt > self.max_entries:
                    # Remove oldest entries
                    excess = cnt - self.max_entries
                    self._conn.execute(
                        """DELETE FROM agent_memory WHERE id IN (
                            SELECT id FROM agent_memory
                            WHERE node_id=? AND namespace=?
                            ORDER BY access_count ASC, updated_at ASC
                            LIMIT ?
                        )""",
                        (self.node_id, ns, excess),
                    )
                    self.log.debug(f"Cleaned {excess} old entries from namespace '{ns}'")

            self._conn.commit()
        except Exception as e:
            self.log.warning(f"Memory maintenance: {e}")


# ════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════

class MemoryStore:
    """Combined memory store with Tier 1 + Tier 2"""

    def __init__(
        self,
        node_id: str = "default",
        db_path: Optional[str] = None,
    ):
        self.ephemeral = EphemeralMemory()
        self.local = LocalMemory(node_id=node_id, db_path=db_path)
        self.log = get_logger()

    async def initialize(self) -> None:
        await self.local.initialize()

    async def store(self, key: str, value: Any, persistent: bool = False, **kwargs):
        """Store in Tier 1 (and optionally Tier 2)"""
        self.ephemeral.store(key, value, tags=kwargs.get("tags"))
        if persistent:
            await self.local.save(key, value, **kwargs)

    async def get(self, key: str, persistent: bool = False):
        """Read from Tier 1 first, fallback to Tier 2"""
        val = self.ephemeral.get(key)
        if val is not None:
            return val
        if persistent:
            return await self.local.load(key)
        return None

    async def query(self, pattern: str, **kwargs):
        """Query persistent memory"""
        return await self.local.query(pattern, **kwargs)

    async def recall(self, goal: str, limit: int = 5):
        """Recall relevant past runs"""
        return await self.local.recall(goal, limit)

    async def close(self):
        await self.local.close()
