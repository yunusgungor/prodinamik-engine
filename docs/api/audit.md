# Audit Log

Prodinamik Engine v1.1 — Structured Audit Log

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

**Module:** `engine.audit.py`

## Classes

### `AuditEntry`

Single audit log entry

**Methods:**

- `__init__(event_type, data, trace_id, timestamp)`
- `to_dict()`
- `from_dict(cls, d)`
- `__repr__()`

### `AuditLog`

Append-only JSONL audit log with compaction.

Directory structure:
    /base_path/
        audit.log          # Active append log
        archive/            # Compacted segments
            audit_001.jsonl.gz
            audit_002.jsonl.gz
        index.json          # Segment index (start/end time + count)

**Methods:**

- `__init__(base_path, max_segment_size)`
- `record(event_type, data, trace_id)`
  — Record a new audit entry
- `query(since, until, event_type, limit)`
  — Query audit entries with filters
- `count(event_type)`
  — Count entries (optionally filtered by type)
- `latest(n)`
  — Get the N most recent entries
- `replay(target_state)`
  — Replay all events to reconstruct state.
- `_apply(entry, state)`
  — Apply an audit entry to a state dict
- `compact(older_than_days)`
  — Compact audit entries older than N days into gzipped archive.
- `stats()`
  — Return audit log statistics
- `export_json(indent)`
  — Export all entries as a JSON array
- `_open_active()`
  — Open or create the active segment file
- `_rotate()`
  — Rotate active log to archive
- `_rewrite_active(cutoff)`
  — Rewrite active log, keeping only entries >= cutoff
- `_iter_all()`
  — Iterate all entries (archived first, then active)
- `_load_index()`
  — Load archive index
- `_update_index(segment_info)`
  — Update archive index
- `close()`
  — Close active file handle
- `__del__()`
