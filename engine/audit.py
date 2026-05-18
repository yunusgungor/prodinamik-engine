"""Prodinamik Engine v1.1 — Structured Audit Log

JSONL-based audit trail with event replay and compaction.
Writes one JSON object per line, supports:
- Append-only writes (O(1))
- Time-range queries
- Event replay to reconstruct state
- Compaction (merge old entries)
- Cross-session traceability via trace_id

Usage:
    audit = AuditLog(base_path="/tmp/audit")
    audit.record("run.created", {"slug": "my-run", "profile": "software"})
    audit.record("run.transition", {"slug": "my-run", "from": "a", "to": "b"})
    for entry in audit.query(since="2026-01-01"):
        print(entry)
"""

import os
import json
import time
import gzip
import shutil
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Iterator, Generator


# ──────────────────────────────────────────────
# Audit Entry
# ──────────────────────────────────────────────


class AuditEntry:
    """Single audit log entry"""

    def __init__(self, event_type: str, data: dict,
                 trace_id: str = None, timestamp: str = None):
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.event_type = event_type
        self.data = data
        self.trace_id = trace_id or ""

    def to_dict(self) -> dict:
        return {
            "ts": self.timestamp,
            "type": self.event_type,
            "data": self.data,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AuditEntry":
        return cls(
            event_type=d.get("type", "unknown"),
            data=d.get("data", {}),
            trace_id=d.get("trace_id", ""),
            timestamp=d.get("ts", ""),
        )

    def __repr__(self) -> str:
        return f"AuditEntry(type={self.event_type}, ts={self.timestamp})"


# ──────────────────────────────────────────────
# Audit Log
# ──────────────────────────────────────────────


class AuditLog:
    """Append-only JSONL audit log with compaction.

    Directory structure:
        /base_path/
            audit.log          # Active append log
            archive/            # Compacted segments
                audit_001.jsonl.gz
                audit_002.jsonl.gz
            index.json          # Segment index (start/end time + count)
    """

    def __init__(self, base_path: str = None, max_segment_size: int = 10000):
        self.base_path = Path(base_path or "./audit")
        self.max_segment_size = max_segment_size
        self._lock = threading.Lock()
        self._segment_count = 0
        self._entry_count = 0
        self._active_file: Optional[Path] = None
        self._active_fh = None

        # Ensure directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "archive").mkdir(exist_ok=True)

        # Load index
        self._load_index()

        # Open active segment
        self._open_active()

    # ──────────────────────────────────────
    # Write
    # ──────────────────────────────────────

    def record(self, event_type: str, data: dict, trace_id: str = None) -> AuditEntry:
        """Record a new audit entry"""
        entry = AuditEntry(event_type=event_type, data=data, trace_id=trace_id)
        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"

        with self._lock:
            if self._active_fh is None or self._active_fh.closed:
                self._open_active()

            self._active_fh.write(line)
            self._active_fh.flush()
            self._entry_count += 1

            # Auto-rotate if needed
            if self._entry_count >= self.max_segment_size:
                self._rotate()

        return entry

    # ──────────────────────────────────────
    # Query
    # ──────────────────────────────────────

    def query(self, since: str = None, until: str = None,
              event_type: str = None, limit: int = 100) -> List[AuditEntry]:
        """Query audit entries with filters"""
        results = []
        for entry in self._iter_all():
            ts = entry.timestamp

            if since and ts < since:
                continue
            if until and ts > until:
                continue
            if event_type and entry.event_type != event_type:
                continue

            results.append(entry)
            if limit and len(results) >= limit:
                break

        return results

    def count(self, event_type: str = None) -> int:
        """Count entries (optionally filtered by type)"""
        if event_type:
            return sum(1 for e in self._iter_all() if e.event_type == event_type)
        return self._entry_count if self._active_fh else 0

    def latest(self, n: int = 10) -> List[AuditEntry]:
        """Get the N most recent entries"""
        all_entries = list(self._iter_all())
        return all_entries[-n:]

    # ──────────────────────────────────────
    # Replay
    # ──────────────────────────────────────

    def replay(self, target_state: dict = None) -> List[AuditEntry]:
        """Replay all events to reconstruct state.

        If target_state is provided, replay applies events to it.
        Returns all replayed entries in order.
        """
        entries = []
        for entry in self._iter_all():
            entries.append(entry)
            if target_state is not None:
                self._apply(entry, target_state)
        return entries

    @staticmethod
    def _apply(entry: AuditEntry, state: dict):
        """Apply an audit entry to a state dict"""
        et = entry.event_type
        d = entry.data

        if et == "run.created":
            slug = d.get("slug", "unknown")
            state[slug] = {"state": d.get("state", "created"), "events": 0}
        elif et == "run.transition":
            slug = d.get("slug", "")
            if slug in state:
                state[slug]["state"] = d.get("to", state[slug].get("state", ""))
                state[slug]["events"] = state[slug].get("events", 0) + 1
        elif et == "run.archived":
            slug = d.get("slug", "")
            if slug in state:
                state[slug]["status"] = "archived"
        elif et == "degradation.change":
            state["_degradation"] = d.get("to", "")
        elif et == "metric.recorded" and "prometheus" in d:
            state["_last_prometheus"] = d.get("prometheus", "")

    # ──────────────────────────────────────
    # Compaction
    # ──────────────────────────────────────

    def compact(self, older_than_days: int = 7) -> int:
        """Compact audit entries older than N days into gzipped archive.

        Returns number of entries compacted.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        compacted = 0
        segment_lines = []
        segment_start = None

        # Read active log, separate old vs new
        with self._lock:
            if self._active_fh and not self._active_fh.closed:
                self._active_fh.flush()

            if self._active_file and self._active_file.exists():
                with open(self._active_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            ts = d.get("ts", "")
                            if ts < cutoff:
                                segment_lines.append(line)
                                compacted += 1
                                if segment_start is None or ts < segment_start:
                                    segment_start = ts
                            else:
                                # Keep in active
                                pass  # Will rewrite
                        except json.JSONDecodeError:
                            continue

        if compacted == 0:
            return 0

        # Write compacted segment
        archive_dir = self.base_path / "archive"
        seg_num = len(list(archive_dir.glob("audit_*.jsonl.gz"))) + 1
        seg_path = archive_dir / f"audit_{seg_num:03d}.jsonl.gz"

        with gzip.open(seg_path, "wt", encoding="utf-8") as f:
            for line in segment_lines:
                f.write(line + "\n")

        # Update index
        self._update_index({
            "segment": f"audit_{seg_num:03d}.jsonl.gz",
            "start": segment_start,
            "end": cutoff,
            "count": compacted,
        })

        # Rewrite active log without compacted entries
        self._rewrite_active(cutoff)

        return compacted

    # ──────────────────────────────────────
    # Stats & Export
    # ──────────────────────────────────────

    def stats(self) -> dict:
        """Return audit log statistics"""
        archive = list((self.base_path / "archive").glob("*.jsonl.gz"))
        return {
            "active_entries": self._entry_count,
            "archive_segments": len(archive),
            "total_entries_estimate": self._entry_count,
            "base_path": str(self.base_path),
        }

    def export_json(self, indent: int = 2) -> str:
        """Export all entries as a JSON array"""
        entries = [e.to_dict() for e in self._iter_all()]
        return json.dumps(entries, ensure_ascii=False, indent=indent)

    # ──────────────────────────────────────
    # Internal
    # ──────────────────────────────────────

    def _open_active(self):
        """Open or create the active segment file"""
        self._active_file = self.base_path / "audit.log"
        self._active_fh = open(self._active_file, "a", encoding="utf-8")

    def _rotate(self):
        """Rotate active log to archive"""
        if self._active_fh:
            self._active_fh.close()

        if self._active_file and self._active_file.exists():
            # Compress current segment
            archive_dir = self.base_path / "archive"
            seg_num = len(list(archive_dir.glob("audit_*.jsonl.gz"))) + 1
            seg_path = archive_dir / f"audit_{seg_num:03d}.jsonl.gz"

            with open(self._active_file, "r") as f_in, gzip.open(seg_path, "wt") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # Clear active
            self._active_file.write_text("")

        self._entry_count = 0
        self._segment_count += 1
        self._open_active()

    def _rewrite_active(self, cutoff: str):
        """Rewrite active log, keeping only entries >= cutoff"""
        if self._active_fh:
            self._active_fh.close()

        temp_path = self.base_path / "audit.tmp"
        kept = 0

        if self._active_file and self._active_file.exists():
            with open(self._active_file, "r") as f, open(temp_path, "w") as out:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        if d.get("ts", "") >= cutoff:
                            out.write(line + "\n")
                            kept += 1
                    except json.JSONDecodeError:
                        continue

            temp_path.replace(self._active_file)

        self._entry_count = kept
        self._open_active()

    def _iter_all(self) -> Generator[AuditEntry, None, None]:
        """Iterate all entries (archived first, then active)"""
        # Archived segments (sorted)
        archive_dir = self.base_path / "archive"
        for seg_path in sorted(archive_dir.glob("audit_*.jsonl.gz")):
            try:
                with gzip.open(seg_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield AuditEntry.from_dict(json.loads(line))
                        except (json.JSONDecodeError, KeyError):
                            continue
            except Exception:
                continue

        # Active segment
        if self._active_fh:
            self._active_fh.flush()
        if self._active_file and self._active_file.exists():
            try:
                with open(self._active_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield AuditEntry.from_dict(json.loads(line))
                        except (json.JSONDecodeError, KeyError):
                            continue
            except Exception:
                pass

    def _load_index(self):
        """Load archive index"""
        index_path = self.base_path / "index.json"
        if index_path.exists():
            try:
                idx = json.loads(index_path.read_text())
                self._segment_count = idx.get("segment_count", 0)
            except Exception:
                self._segment_count = 0

    def _update_index(self, segment_info: dict):
        """Update archive index"""
        index_path = self.base_path / "index.json"
        index = {"segment_count": self._segment_count, "segments": []}
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text())
            except Exception:
                pass
        index["segments"].append(segment_info)
        index_path.write_text(json.dumps(index, indent=2))

    def close(self):
        """Close active file handle"""
        if self._active_fh and not self._active_fh.closed:
            self._active_fh.close()

    def __del__(self):
        self.close()
