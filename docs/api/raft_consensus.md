# Raft Consensus

Prodinamik Engine v1.1 — Hybrid Raft Consensus Core

StateCRDT, DistributedStateMachine, OfflineManager, HybridConsensusNode.

**Module:** `engine.raft_consensus.py`

## Classes

### `StateCRDT`

CRDT for distributed state.
Uses version vectors for conflict detection.

**Methods:**

- `merge(local, remote, state_machine_transitions)`
- `_is_on_same_path(a, b, transitions)`
- `_find_path(start, end, transitions, visited)`

### `DistributedStateMachine`

Distributed state machine backed by Raft+CRDT.
State machine SADECE Leader'da çalışır.
Follower'lar Leader'ın log'unu replicate eder.

**Methods:**

- `__init__(node_id, peers, state_dir)`
- `configure_transitions(transitions)`
- `become_follower(term)`
- `become_candidate()`
- `become_leader()`
- `_start_election()`
  — Force an election cycle
- `append_entries(entries, prev_log_index, prev_log_term, leader_commit)`
- `request_vote(candidate_term, candidate_id, last_log_index, last_log_term)`
- `_apply_committed()`
- `_apply_command(command)`
- `get_state(slug)`
- `propose(command)`
- `_load_log()`
- `_save_log()`
- `_load_snapshot()`
- `save_snapshot()`
- `_last_log_term()`
- `_request_vote(peer)`
- `_broadcast_heartbeat()`
- `_replicate_to(peer)`
- `provide_merge(slug, merged_state)`
- `status()`

### `OfflineManager`

Offline mode: optimistic local writes.
Reconnect: pending log → Leader approval → CRDT merge.

**Methods:**

- `__init__(local_node)`
- `go_offline()`
- `go_online(leader)`
- `apply_pending(command)`
- `_sync_with_leader(leader)`
- `pending_count()`
- `status()`

### `HybridConsensusNode`

Raft + Offline + CRDT hybrid model.

Online:  Raft consensus (Leader writes, Follower replicates)
Offline: Optimistic local writes (pending log)
Reconnect: 5-adımlı sync prosedürü

**Methods:**

- `__init__(node_id, peers, state_dir, raft_host, raft_port, enable_transport)`
- `transport()`
  — Lazy-init TCP transport
- `register_peer_transport(peer_id, address)`
  — Register a peer's TCP address (e.g., 'node-2' → '192.168.1.2:9001')
- `_handle_raft_message(msg)`
  — Handle incoming Raft messages from TCP transport
- `start_transport()`
  — Enable and start TCP transport
- `stop_transport()`
  — Stop TCP transport
- `apply(command)`
- `raft_request_vote()`
  — Request votes from peers via TCP (if transport enabled).
- `raft_broadcast_heartbeat()`
  — Broadcast heartbeat to all peers via TCP (if available)
- `raft_replicate_to(peer_id)`
  — Replicate log to a specific peer via TCP (if available)
- `raft_peer_health(peer_id)`
  — Check peer health via TCP
- `reconnect(leader)`
- `get_state(slug)`
- `status()`
- `health()`
- `is_leader()`
- `force_election()`
