# Raft Types

Prodinamik Engine v1.1 — Raft Data Types

Review #5: Raft + Offline + CRDT çelişkisi çözümü.
All data types extracted from raft.py for modularity.

**Module:** `engine.raft_types.py`

## Classes

### `NodeRole`(Enum)

### `LogEntry`

Raft log entry

**Methods:**

- `__post_init__()`
- `checksum()`

### `NodeState`

Bir node'un state bilgisi

### `Snapshot`

Raft snapshot (state machine'in anlık görüntüsü)

**Methods:**

- `__post_init__()`

### `PendingOperation`

Offline'ta biriken işlem

**Methods:**

- `__post_init__()`

### `ClusterNode`

Discovered cluster node
