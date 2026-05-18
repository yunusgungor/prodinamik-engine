# Terminology Glossary

---

## A

**API Key** — A bearer token in the format `pdmk_<48-hex-characters>` used to authenticate requests to the engine's HTTP API. Keys are hashed (SHA-256) before storage; the raw key is shown only once at creation.

**AuthManager** — The core authentication module responsible for API key creation, validation, listing, and revocation. Integrates with RBAC and rate limiting.

**Auto-Remediation** — An AI-native feature that automatically detects and corrects common run failures by analyzing error patterns and applying predefined or learned fix strategies.

---

## B

**Budget** — A cost-tracking mechanism that monitors resource consumption per run, profile, or namespace. Budgets can trigger alerts or degrade engine tiers when thresholds are exceeded.

---

## C

**Chaos Engineering** — A built-in framework for injecting controlled faults (network partitions, disk pressure, CPU spikes, WAL corruption) into the engine to test resilience and self-healing capabilities.

**Cluster Mode** — An operating mode where multiple engine nodes form a Raft-based consensus cluster for high availability and state replication. Disabled by default for single-machine deployments.

**Context** — A JSON object attached to a run that carries input parameters, intermediate results, and metadata across state transitions. Validators and hooks can read and modify the context.

---

## D

**Degradation** — A tiered self-preservation mechanism (FULL → DEGRADED → SURVIVAL) that reduces engine capabilities under resource pressure (CPU, memory, disk). Recovery is automatic when metrics normalize.

**Drift Detection** — An AI-native feature that monitors state machine execution patterns and detects anomalies or behavioral shifts, such as increasing transition failure rates or unusual timing distributions.

---

## E

**Event Store** — A persistent append-only log of all state machine events (transitions, validation results, errors, context changes). Used for auditing, debugging, and replay analytics.

**Engine** — The core runtime that loads profiles, manages state machines, processes transitions, coordinates plugins, and exposes CLI/HTTP interfaces. The central orchestrator of the entire system.

---

## F

**Fault Domain** — A logical grouping of components that share failure risk. In chaos engineering, scenarios target specific fault domains (network, disk, memory, CPU) to isolate blast radius.

---

## G

**Guard Condition** — A boolean expression attached to a state transition that must evaluate to true for the transition to be permitted. Guards are checked before validators run.

---

## H

**Hermes Bridge** — A plugin that connects Prodinamik Engine to Hermes Agent, enabling natural-language workflow management, AI-assisted diagnostics, and conversational run inspection.

**Hook** — A user-defined callback function (before_transition, after_transition, on_run_start, on_run_complete) that executes at specific lifecycle points. Hooks can modify context, log events, or call external systems.

**HTTP API** — A RESTful interface exposing engine operations (run management, state machine inspection, plugin administration, cluster management) over HTTP. Protected by API key authentication and rate limiting.

---

## I

**Idempotency** — A property of state transitions ensuring that applying the same transition multiple times produces the same result. Critical for safe WAL replay after crashes.

**Initial State** — The first state a run enters when created. Defined in the state machine YAML under `initial_state`.

---

## L

**Leader** — In a Raft cluster, the single node responsible for managing log replication and coordinating committed entries. Elected by consensus among cluster members.

**Log Compaction** — The process of truncating old WAL and Raft log entries after they have been superseded by a snapshot. Reduces storage footprint and speeds up recovery.

---

## M

**Migration** — A utility for upgrading state machine definitions or profiles across engine versions, handling schema changes and data transformations automatically.

---

## N

**Namespace** — A logical grouping of runs and profiles for multi-tenant deployments. Each namespace has isolated data directories and can have independent RBAC policies.

**Node** — A single instance of the Prodinamik Engine process. In cluster mode, multiple nodes form a Raft consensus group.

---

## P

**Plugin** — A self-contained Python package that extends engine functionality via a defined hook interface. Plugins can add custom validators, notification channels, storage backends, or AI capabilities.

**Plugin Manifest** — A JSON file (`manifest.json`) inside a plugin directory declaring metadata (name, version, author, engine version compatibility, dependencies, exposed hooks).

**Predictive Degradation** — An AI-native feature that forecasts resource pressure and proactively triggers degradation before thresholds are breached, using historical metrics and trend analysis.

**Profile** — A TOML configuration file defining engine behavior: data paths, Raft settings, rate limits, plugin allowlists, timeout defaults, and chaos safety thresholds. Multiple profiles can coexist and be switched at runtime.

---

## R

**Raft** — A consensus algorithm for managing a replicated log across a cluster of nodes. Prodinamik Engine uses Raft to replicate state machine transitions across multiple nodes for fault tolerance.

**Raft Quorum** — The minimum number of nodes that must agree on a log entry for it to be committed. In a cluster of N nodes, quorum is `(N/2) + 1`.

**RBAC (Role-Based Access Control)** — A permission model with three roles: `admin` (full access), `user` (standard operations), and `readonly` (inspection only). Assigned per API key.

**Run** — A single execution instance of a state machine. A run starts in an initial state, progresses through transitions, and terminates in a final state (completed, failed, or cancelled).

**Run Manager** — The module responsible for creating, listing, inspecting, cancelling, and rerunning state machine runs. Exposed via both CLI (`prodinamik run ...`) and HTTP API.

---

## S

**Safety Threshold** — A configurable limit on chaos engineering scenarios to prevent actual damage. For example, memory pressure cannot exceed 80% of total RAM.

**Skill Emergence** — An AI-native feature that analyzes historical run patterns and automatically generates reusable state machine templates ("skills") for common workflow patterns.

**Snapshot** — A point-in-time capture of the entire state machine state, used for Raft log compaction and fast node recovery. Snapshots are periodically created and persisted.

**State Machine** — A formal model defining a set of states, transitions between them, and validators/hooks attached to each transition. Defined in YAML and parsed by the engine at load time.

**SURVIVAL** — The most restrictive degradation tier. Only critical state transitions are accepted; plugin hooks, chaos experiments, AI features, and non-essential operations are suspended.

---

## T

**Terminal State** — A state from which no further transitions are possible (e.g., `completed`, `failed`, `cancelled`). Once a run reaches a terminal state, it is immutable.

**Tier 1 Validation** — Schema-level validation: checks that transition inputs conform to the state machine's field definitions, types, and constraints. Always runs first.

**Tier 2 Validation** — Business-level validation: custom Python validator functions attached to transitions that enforce domain-specific rules and invariants.

**Tier 3 Validation** — Consensus-level validation: in cluster mode, requires a Raft quorum to approve a transition before it is applied.

**Transition** — A directed edge between two states in the state machine, optionally guarded by validators and hooks. Transitions are the fundamental unit of work in the engine.

---

## V

**Validator** — A callable that checks preconditions before a transition is applied. Validators can be built-in (schema checks, type checks) or custom (user-provided Python functions). A failing validator blocks the transition.

---

## W

**WAL (Write-Ahead Log)** — A durable, append-only log that records every transition attempt before it is executed. On crash recovery, the WAL ensures that incomplete transitions are replayed or rolled back, providing at-least-once semantics.
