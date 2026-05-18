# Frequently Asked Questions

---

## General

### Q: What is Prodinamik Engine?

**A:** Prodinamik Engine is a product-agnostic pipeline engine built around a formal state machine core. It manages complex workflows through defined states and transitions, with features including 3-tier validation, Raft-based consensus for fault tolerance, plugin extensibility, AI-native capabilities (drift detection, skill emergence, predictive degradation), and built-in chaos engineering. It is designed to run anywhere — single machine, Docker, or multi-node cluster — and exposes both a CLI and HTTP API.

---

### Q: Who created Prodinamik Engine?

**A:** The project was created and is maintained by Yunus Güngör. It is open-source under a permissive license, hosted at [github.com/yunusgungor/prodinamik-engine](https://github.com/yunusgungor/prodinamik-engine).

---

### Q: What does "product-agnostic" mean in practice?

**A:** It means the engine does not assume any specific domain or application. The same engine can orchestrate CI/CD pipelines, data processing workflows, approval chains, deployment rollouts, or any other stateful process. You define the states and transitions via YAML — the engine handles execution, validation, persistence, and recovery regardless of the domain.

---

## Architecture

### Q: How is Prodinamik Engine different from Airflow or Prefect?

**A:** Airflow and Prefect are DAG-based orchestrators focused on directed acyclic graphs of tasks. Prodinamik Engine is state machine-based, which means:

- **Cycles are supported** — states can loop (e.g., review → revise → review) natively
- **Formal validation** — each transition can have preconditions, validators, and guard conditions
- **Consensus layer** — Raft integration provides fault-tolerant state replication, not available in Airflow/Prefect
- **Degradation model** — automatic tier-based degradation (FULL → DEGRADED → SURVIVAL) under resource pressure
- **AI-native features** — drift detection, skill emergence, and predictive degradation are built in, not add-ons

For simple linear DAGs, Airflow or Prefect may be simpler. For complex stateful workflows with validation, consensus, and self-healing, Prodinamik Engine is more appropriate.

---

### Q: Do I need Raft for single-machine use?

**A:** No. Raft is optional and only needed when you run a multi-node cluster for high availability. On a single machine, the engine uses a local WAL (Write-Ahead Log) for persistence. Raft is automatically disabled when `cluster_mode` is not set in the profile. You can safely ignore all Raft configuration for single-node deployments.

---

### Q: What is the state machine lifecycle?

**A:** A run starts in an initial state (e.g., `pending`), transitions through intermediate states (`running`, `validating`, `approving`), and eventually reaches a terminal state (`completed`, `failed`, `cancelled`). Each transition can execute hooks, run validators, and update the run context. The full lifecycle is persisted in the event store and WAL for durability and auditability.

---

### Q: How does the 3-tier validation work?

**A:** The three tiers are:

1. **Tier 1 — Schema validation:** Checks that transition inputs match the YAML-defined schema (required fields, types, constraints).
2. **Tier 2 — Business validators:** Custom Python validator functions attached to transitions, checking domain-specific logic.
3. **Tier 3 — Consensus validation:** In cluster mode, a transition may require a quorum of Raft nodes to agree before proceeding.

Tier 1 always runs first. Tier 2 and Tier 3 are optional per transition. If any tier fails, the transition is rejected and the run remains in its current state.

---

## Usage

### Q: How do I create a custom profile?

**A:** Profiles are TOML files that define engine behavior. To create one:

1. Generate a starter profile: `prodinamik profile init my-profile`
2. Edit `~/.prodinamik/profiles/my-profile.toml`
3. Activate it: `prodinamik profile use my-profile`

Key settings include: data directory paths, Raft configuration, rate limits, timeout defaults, plugin allowlists, and chaos safety thresholds. See the [Profiles documentation](getting-started/profiles.md) for the full schema.

---

### Q: Can I use Prodinamik Engine without Hermes Agent?

**A:** Yes, absolutely. Hermes Agent is an optional integration that enables natural-language interaction and AI-assisted workflow management. The core engine — state machine execution, CLI, HTTP API, plugins, Raft — works independently. The Hermes Bridge plugin provides the integration layer when you choose to use Hermes Agent alongside the engine.

---

### Q: How do I inspect a running workflow?

**A:** Use the CLI:

```bash
prodinamik run list                           # List all runs with status
prodinamik run inspect <run-id>               # Full run details
prodinamik run logs <run-id>                  # Run-specific logs
prodinamik run list --status running          # Filter by status
```

Or via the HTTP API: `GET /api/v1/runs/{run_id}`

---

### Q: How do I cancel or retry a run?

**A:**

- Cancel a running run: `prodinamik run cancel <run-id>`
- Retry a failed run from scratch: `prodinamik run rerun <run-id>`
- Retry from a specific state: `prodinamik run rerun <run-id> --from-state validate`

Retries respect the original profile settings but allow overriding context values with `--context`.

---

### Q: What happens if the engine crashes during a transition?

**A:** The WAL records every transition attempt before execution. On restart, the engine replays incomplete transitions from the WAL. If a transition was partially applied, the engine can either roll back to the previous consistent state or complete the transition, depending on the transition's idempotency settings. This guarantees at-least-once semantics for state changes.

---

## Performance

### Q: How many runs can the engine handle concurrently?

**A:** This depends on hardware and configuration. A single node can handle hundreds of concurrent runs with the default thread pool. Key limits:

- **Default max concurrent runs:** 50 (configurable via `max_concurrent_runs` in profile)
- **Event store throughput:** ~5,000 events/second on SSD-backed storage
- **Raft throughput:** ~1,000 committed log entries/second per leader (3-node cluster)

For higher throughput, tune the async runtime pool size and consider sharding by profile or namespace.

---

### Q: How does the degradation system work under load?

**A:** The engine monitors CPU, memory, and I/O metrics. When thresholds are breached, it degrades through three tiers:

1. **Tier 1 (FULL):** All features active.
2. **Tier 2 (DEGRADED):** Non-critical plugins disabled, rate limits tightened, AI features throttled.
3. **Tier 3 (SURVIVAL):** Only critical state transitions accepted, plugin hooks bypassed, chaos engine paused, Raft heartbeats reduced.

Recovery is automatic when resource metrics return to normal for a configurable cooldown period.

---

### Q: What is the storage footprint of the WAL and event store?

**A:** Approximately 1–5 KB per event, depending on context size. A run with 20 transitions generates roughly 20–100 KB of WAL and event store data. The engine supports log compaction and retention policies:

```bash
prodinamik config show | grep -E "retention|compaction|wal_"
```

Typical retention defaults: WAL segments retained for 7 days, event store pruned after 30 days. Both are configurable per profile.

---

## Deployment

### Q: What are the minimum system requirements?

**A:**

- **CPU:** 1 core (2+ recommended for production)
- **RAM:** 256 MB minimum, 1 GB+ recommended (memory scales with concurrent runs)
- **Disk:** 100 MB for binaries + data directory (SSD recommended for WAL)
- **OS:** Linux (kernel 4.15+), macOS, or WSL2

Additional resources are needed per plugin and for AI features (drift detection requires ~500 MB for model loading).

---

### Q: Can I run Prodinamik Engine in Docker?

**A:** Yes. An official Docker image is available. Quick start:

```bash
docker pull ghcr.io/yunusgungor/prodinamik-engine:latest
docker run -d \
  --name prodinamik \
  -v /data/prodinamik:/var/lib/prodinamik \
  -p 8080:8080 \
  ghcr.io/yunusgungor/prodinamik-engine:latest
```

For multi-node Raft deployments, use Docker Compose or Kubernetes with headless services. See the [Docker & CI/CD guide](dev/docker-ci-cd.md) for production patterns.

---

### Q: How do I set up a multi-node Raft cluster?

**A:** A minimal 3-node setup:

1. On each node, create a profile with `cluster_mode = true` and a unique `node_id`.
2. On node 1, bootstrap: `prodinamik raft init --bootstrap`
3. On nodes 2 and 3, join: `prodinamik raft join <node1-address>:<raft-port>`
4. Verify: `prodinamik raft list` should show all three members

Each node needs bidirectional TCP access to the others on the Raft port (default: 7000). For production, place nodes in different availability zones.

---

### Q: How do I upgrade the engine without downtime?

**A:** In a Raft cluster, perform a rolling upgrade:

1. Stop the engine on node 3: `prodinamik stop`
2. Upgrade the binary: `pip install --upgrade prodinamik-engine`
3. Start the engine: `prodinamik start`
4. Wait for the node to rejoin the cluster: `prodinamik raft status`
5. Repeat for nodes 2 and 1

During upgrades, the cluster maintains quorum (2 of 3 nodes active) so run execution continues uninterrupted. Always consult the [changelog](changelog.md) for breaking changes before upgrading.

---

### Q: How do I back up the engine data?

**A:** The critical data paths are:

- **WAL directory:** Contains the write-ahead log for recovery
- **Event store:** Persisted run events
- **Auth directory:** API key hashes
- **Raft data:** Raft log and snapshots (cluster mode only)

Backup command:

```bash
prodinamik backup --output /backups/prodinamik-$(date +%Y%m%d).tar.gz
```

Restore:

```bash
prodinamik restore --input /backups/prodinamik-20260518.tar.gz
```

For Raft clusters, take backups from a follower node to avoid impacting the leader. Always stop the engine or use filesystem snapshots for consistent backups.
