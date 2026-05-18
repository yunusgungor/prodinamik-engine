# Run Management

Runs are the fundamental unit of work in the Prodinamik Engine. A run represents a single execution of a product profile from creation through its state machine lifecycle to completion or failure. The Run Manager (`engine/run_manager.py`) handles the full CRUD lifecycle, state persistence, crash recovery via Write-Ahead Log (WAL), and search/archive operations.

## Run Lifecycle

Every run progresses through a well-defined lifecycle:

```
created → validating → active → completed / failed / cancelled → archived
```

State transitions follow the profile's state machine configuration. The Run Manager enforces that:

- A run must be in a valid initial state from the profile's state machine.
- State transitions are validated against the state machine's `can_transition()` rules, including condition guards, reentry limits, and human-approval requirements.
- Runs in a terminal state cannot transition further.
- Archived runs are read-only but can be restored to active.

### Core Lifecycle States

| Phase | Description |
|-------|-------------|
| **created** | Run has been initialized in the first initial state of the profile's state machine. Metadata written to disk. |
| **active** | Run is progressing through intermediate states. Each `update_state()` call moves to a new active state. |
| **completed** | Run reached a terminal state (e.g., `released`, `done`). No further transitions allowed. |
| **failed** | Run entered an error state with no recovery path, or hit `max_reentries`. |
| **cancelled** | Run was manually terminated via the CLI or API. |
| **archived** | Run directory moved from `.hermes/runs/active/` to `.hermes/runs/archive/`. Read-only. |

## Directory Structure

Each run lives in its own directory under the `.hermes/runs/` hierarchy:

```
.hermes/
├── runs/
│   ├── active/
│   │   └── {slug}/
│   │       ├── content-object.md      # Run metadata (frontmatter)
│   │       ├── events/                # Event store
│   │       │   ├── 0000000001.json
│   │       │   └── ...
│   │       └── artifacts/            # Run-generated files
│   │           └── ...
│   └── archive/
│       └── {slug}/                    # Archived runs (same structure)
├── state/
│   └── runs_state.json               # Global snapshot (atomic writes)
├── wal/
│   ├── wal_20260518_120000_123456.log
│   └── wal_20260518_120001_789012.log
```

### content-object.md Format

The `content-object.md` file is the primary metadata store for each run. It uses YAML frontmatter:

```yaml
---
slug: my-software-run
profile: software
title: Release v2.1.0
created_at: 2026-05-18T12:00:00
updated_at: 2026-05-18T14:32:15
status: active
state: development
version: 3
---
```

Fields:
- **slug** — Unique URL-safe identifier for the run.
- **profile** — Name of the `ProductProfile` this run belongs to.
- **title** — Human-readable title.
- **created_at / updated_at** — ISO 8601 timestamps.
- **status** — One of: `active`, `archived`, `error`.
- **state** — Current state in the state machine.
- **version** — Optimistic locking counter, incremented on every update.

### WAL (Write-Ahead Log)

The WAL directory (`wal/`) contains immutable, timestamped log files recording every state change. Each entry is a JSON object:

```json
{
  "action": "transition",
  "slug": "my-software-run",
  "from": "development",
  "to": "review",
  "version": 3,
  "timestamp": "2026-05-18T14:32:15.123456",
  "checksum": "a1b2c3d4e5f6a7b8"
}
```

Entry types:
- **create** — Run creation record.
- **transition** — State transition record with `from`/`to` fields.
- **archive** — Run archival record.

Each entry includes a SHA-256 checksum (first 16 hex chars) for integrity verification during crash recovery.

## CRUD Operations

### Create a Run

```bash
prodinamik run my-profile "Release v2.1.0"
```

Or with a custom slug:

```bash
prodinamik run my-profile "Release v2.1.0" --slug release-v2-1-0
```

Programmatic API:

```python
from engine.run_manager import RunManager
from engine.profile import ProductProfile

mgr = RunManager(base_path="/path/to/.hermes")
profile = ProductProfile.from_name("my-profile")
run = mgr.create_run("Release v2.1.0", profile)
print(f"Created: {run.meta.slug} → {run.meta.state}")
```

The creation process:
1. Generates a URL-safe slug from the title (or validates the provided slug).
2. Resolves the initial state from the profile's state machine.
3. Creates the run directory with `events/` and `artifacts/` subdirectories.
4. Writes `content-object.md` with YAML frontmatter.
5. Records a `create` entry in the WAL.
6. Updates the global snapshot (atomic write).

### Get a Run

```bash
prodinamik run get my-software-run
```

Or programmatically:

```python
run = mgr.get_run("my-software-run", profile)
if run:
    print(f"State: {run.meta.state}, Status: {run.meta.status}")
```

The get operation first checks `active/{slug}`, then falls back to `archive/{slug}`.

### Update State (Transition)

```bash
prodinamik transition my-software-run review
```

Programmatic:

```python
run = mgr.update_state("my-software-run", "review", profile)
```

The update sequence:
1. Validates the run exists in the active directory.
2. Reads the current metadata (including version counter).
3. Calls `profile.state_machine.can_transition(from_state, to_state, runtime)` to validate the transition.
4. If allowed, increments the version counter.
5. Records a `transition` entry in the WAL with `from`/`to` fields.
6. Atomically updates the global snapshot.
7. Rewrites `content-object.md` with the new state and version.

If the state machine rejects the transition (condition not met, reentry limit exceeded, requires human approval, etc.), a `ValueError` is raised with the reason.

### Delete a Run

```bash
prodinamik run delete my-software-run
```

This moves the run directory from active/ to a trash location. Note: runs are soft-deleted — the archive preserves them for the recovery window.

### List Runs

```bash
prodinamik list
prodinamik list --include-archived
```

Results are sorted by `updated_at` descending (most recently updated first):

```python
runs = mgr.list_runs(include_archived=True)
for r in runs:
    print(f"{r.slug} [{r.state}] ({r.profile})")
```

### Search Runs

```bash
prodinamik run search "release"
```

Performs case-insensitive substring matching against `title`, `slug`, and `profile`:

```python
results = mgr.search_runs("release")
print(f"Found {len(results)} runs")
```

### Archive a Run

```bash
prodinamik run archive my-software-run
```

Archive moves the run from active to archive via filesystem move:

1. Verifies the run exists in `active/{slug}/`.
2. Creates `archive/` parent directory if needed.
3. Removes any previous archive of the same slug (cleanup).
4. Uses `shutil.move()` to relocate the directory.
5. Updates the global snapshot with `status: archived`.
6. Records an `archive` entry in the WAL.

### Restore a Run

```bash
prodinamik run restore my-software-run
```

Restore reverses the archive operation:

1. Locates the run in `archive/{slug}/`.
2. Moves it back to `active/{slug}/`.
3. Updates the snapshot status to `active`.

## State Locking and Concurrency

The Run Manager uses **optimistic locking** via a version counter on each run:

- Every `content-object.md` carries a `version` field.
- Before a state update, the manager reads the current version.
- The version is incremented on every write.
- If two processes attempt to update simultaneously, the second one reads a stale version — but since WAL entries are appended (not overwritten), the final snapshot reflects the last atomic write.

For distributed scenarios, the `transaction_id` parameter can be passed to lock a run's state before modification:

```python
with mgr.lock_run("my-software-run") as lock:
    run = mgr.update_state("my-software-run", "review", profile, transaction_id=lock.txn_id)
```

The lock prevents concurrent transitions on the same run, ensuring consistency in multi-worker deployments.

## Crash Recovery with WAL

The WAL provides crash-safe persistence. If the engine terminates unexpectedly (power loss, process kill, segfault), the `recover()` method can reconstruct state:

```python
recovered = mgr.recover()
# Recovered dict contains all runs with their last known state
```

### Recovery Algorithm

1. **Load snapshot** — Read `runs_state.json` from disk.
2. **Scan WAL** — Iterate over all `wal_*.log` files in chronological order.
3. **Verify checksums** — Each WAL entry's SHA-256 checksum is validated. Corrupted entries are skipped with a warning.
4. **Replay entries** — Apply each WAL entry to the snapshot state:
   - `create` entries set initial state and mark the run as active.
   - `transition` entries update the run's state to `to`.
   - `archive` entries mark the run as archived.
5. **Compact WAL** — After successful replay, old WAL files (with timestamps before the latest snapshot modification) are deleted.

This guarantees that no state transition is lost, even if the snapshot file was not yet updated when the crash occurred.

### WAL Compaction

The `_compact_wal()` method removes WAL entries that are older than the latest snapshot modification time. This prevents unbounded WAL growth while preserving the crash recovery guarantee.

## Batch Operations

The Run Manager supports batch WAL writes for high-throughput scenarios:

```python
entries = [
    {"action": "create", "slug": "run-1", ...},
    {"action": "create", "slug": "run-2", ...},
]
mgr._append_wal_batch(entries)
```

Batch writes aggregate multiple entries into a single `.batch` file with one atomic write. Benchmarks show ~5× faster throughput for batches of 10+ entries compared to individual WAL writes.

## CLI Reference

All run management operations are available via the CLI:

| Command | Description |
|---------|-------------|
| `prodinamik run <profile> <title>` | Create a new run |
| `prodinamik run get <slug>` | Show run details |
| `prodinamik run update <slug> <state>` | Transition to new state |
| `prodinamik run delete <slug>` | Soft-delete a run |
| `prodinamik run list` | List active runs |
| `prodinamik run search <query>` | Search runs by text |
| `prodinamik run archive <slug>` | Archive a completed run |
| `prodinamik run restore <slug>` | Restore from archive |
| `prodinamik transition <slug> <state>` | Shorthand for update |
| `prodinamik list` | Shorthand for run list |
| `prodinamik debug <slug>` | Detailed run info with elapsed time |

## Best Practices

### Slug Design

- Use descriptive, human-readable slugs: `release-v2-1-0`, `hotfix-auth-timeout`.
- Keep slugs under 80 characters. The `slugify()` method truncates automatically.
- Avoid special characters — only lowercase alphanumeric, hyphens, and underscores are preserved.
- For CI/CD integration, use the build ID or commit SHA as part of the slug.

### Version Counter Discipline

- Always read the latest version before updating state in concurrent environments.
- The version counter is your safety net against lost updates.
- Monitor for version mismatch errors — they indicate concurrent access that should be reviewed.

### WAL and Archival

- Run periodic WAL compaction (the engine does this automatically on recovery).
- Archive completed runs regularly to keep the active directory lean.
- Use `include_archived=True` sparingly in queries — filtering archived runs adds overhead.
- The WAL directory is append-only by design; include it in your backup strategy.

### Performance Considerations

- For batch creation of runs, use `_append_wal_batch()` instead of individual WAL writes.
- The snapshot (`runs_state.json`) is the fast read path; the WAL is the durability path.
- Each `update_state()` call does two disk writes: WAL append + snapshot rewrite. This is intentional for crash safety.
- In high-throughput deployments, consider placing `.hermes/` on an SSD or tmpfs-backed filesystem for the WAL.
