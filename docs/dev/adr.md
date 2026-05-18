# Architecture Decision Records

This document records significant architectural decisions made during the development of the Prodinamik Engine. Each ADR describes the context, decision, alternatives considered, and consequences to preserve institutional knowledge and explain why the system is built the way it is.

---

### ADR-001: YAML-based State Machine Definitions

- **Date:** 2025-11-10
- **Context:** The engine needed a way to define state machines — states, transitions, guards, hooks — that is both human-readable and machine-verifiable. Early prototypes used a Python DSL with class-based state definitions (`class MyMachine(StateMachine)` with decorators and method-based triggers). While expressive, this approach made state machine definitions non-portable across teams, hard to version-control review, and difficult to validate at load time without executing the code.
- **Decision:** State machines are defined in YAML files with a formal schema. The schema supports 4 state types (`initial`, `intermediate`, `terminal`, `error`), 3 transition types (`REVERSIBLE`, `COMPENSABLE`, `IRREVERSIBLE`), per-state hooks (`on_enter`, `on_exit`, `on_timeout`), LTL temporal logic constraints, and compile-time validation (dead cycle detection, unreachable state detection, reentry bound checking).
- **Alternatives considered:**
  - **Python DSL with dataclass decorators:** Verbose, hard to validate statically, definitions coupled to Python runtime.
  - **JSON schema:** Less readable than YAML, no support for comments, visually noisy for deeply nested transitions.
  - **TOML:** Limited nesting expressiveness, no standard for multi-line block structures that state machines require.
  - **XML:** Too heavyweight, verbose namespace declarations, poor developer ergonomics.
- **Consequences:** YAML definitions are portable, can be checked into version control, and validated at load time without importing engine code. Users must learn the YAML schema vocabulary (~15 keywords). Compile-time validation catches dead cycles and unreachable states early — before any run starts. The YAML parser adds ~200 LoC and a dependency on `PyYAML`. Cross-team reviews of state machine logic are now feasible since YAML is more accessible than Python DSL.

---

### ADR-002: 3-Tier Validator Pipeline

- **Date:** 2025-11-15
- **Context:** State transitions needed validation, but different validation types have fundamentally different performance and determinism requirements. Schema checks (e.g., "is the required field present?") must be fast, deterministic, and fail-fast. Semantic checks (e.g., "does this output meet rubric criteria?") are slower, can be non-deterministic (LLM-based), and benefit from parallel execution. A single-validator approach forces all checks into the same execution model, penalizing fast checks with the latency of slow ones.
- **Decision:** A 3-tier validator pipeline:
  - **T1 (Tier 1):** Sequential, fail-fast. Execution time <50ms. Deterministic. Handles schema validation, regex pattern matching, field existence checks.
  - **T2 (Tier 2):** Parallel, independent. Execution time <5s. Non-deterministic. Handles rubric scoring, hallucination checks, similarity comparisons.
  - **T3 (Tier 3):** Sequential, dependent. Execution time <10s. Non-deterministic. Handles coverage thresholds, final grade computation, cross-validation of T2 results.
  Each tier reports a `ValidationResult` with `passed`, `score`, and `details` fields. Pipeline execution stops at T1 failure (fail-fast) but continues through all T2 validators even on partial failures.
- **Alternatives considered:**
  - **Single monolithic validator:** Inflexible, hard to parallelize, couples fast and slow checks.
  - **2-tier (fast/slow):** No distinction between independent and dependent slow checks, misses parallel optimization opportunity for T2.
  - **Pluggable chain-of-responsibility:** Too complex for the common case, harder to reason about execution order, no clear tier grouping.
- **Consequences:** Validators are independently testable and composable. Degradation levels can disable tiers surgically (DEGRADED keeps only T1). Parallel T2 execution improves throughput 3-5x for AI-heavy workloads. The pipeline adds ~150 LoC of orchestration logic. Each tier has its own timeout and retry policy. T3 validators can access T2 results via the shared context object.

---

### ADR-003: Event Sourcing with WAL

- **Date:** 2025-11-18
- **Context:** State transitions and engine events needed to be recorded durably for audit, replay, and debugging. A simple database-only approach would couple storage to the runtime and lose events on crash if writes are buffered. The system needed crash-safe, append-only semantics with the ability to replay events for analysis or recovery.
- **Decision:** Use an append-only Write-Ahead Log (WAL) backed by SQLite for event sourcing. Events are written to the WAL before any state mutation occurs (write-ahead pattern). Each event carries a type, timestamp, payload, and optional cost/budget metadata. The event store supports type-based TTL (e.g., debug events expire after 24h, audit events persist for 90 days), online compaction, and full replay via `EventStore.replay()`.
- **Alternatives considered:**
  - **Database-only persistence (direct writes to SQLite):** Loses uncommitted events on crash, no separation between domain state and event log.
  - **Kafka/RabbitMQ event bus:** Overkill for single-node operation, adds operational complexity (ZooKeeper, broker management).
  - **In-memory only:** No durability, events lost on process restart.
  - **Flat JSON files on disk:** No indexing — replay requires full scan, no TTL-based compaction, prone to corruption on concurrent writes.
- **Consequences:** Crash-safe writes with at-most-1µs overhead per event (SQLite WAL mode). Replay enables debugging, audit trails, and state reconstruction. Compaction keeps WAL size bounded (~500 MB max). The SQLite dependency is already present for other engine metadata (profiles, run state). Query performance for recent events is excellent (>10,000 events/sec read). Historical event query requires compaction-aware indexing.

---

### ADR-004: Degradation Levels (FULL/DEGRADED/SURVIVAL/EMERGENCY)

- **Date:** 2025-11-22
- **Context:** The engine runs in unpredictable environments — network partitions, upstream API failures, resource exhaustion, external service degradation. It needed a graceful degradation mechanism that preserves core state tracking while shedding non-essential work under stress. A binary on/off approach was too coarse; continuous weighted scoring was too complex for operators to reason about.
- **Decision:** Four discrete degradation levels:
  - **FULL:** All validators active (T1+T2+T3), all adapters active, all integrations enabled, state tracking on.
  - **DEGRADED:** T1 validators only, cached adapters only (no new external calls), state tracking on. Typically triggered by upstream API latency spikes.
  - **SURVIVAL:** No validators, no adapters (uses default values), state tracking on. Triggered by resource pressure (memory >85%, CPU >90%).
  - **EMERGENCY:** No validators, no adapters, no state tracking — pure pass-through with minimal logging. Last resort before process termination.
  Levels are auto-escalated by the Safety Monitor based on configurable thresholds, and can be manually set via CLI (`prodinamik degradation set --level DEGRADED`). A "cool-down" period prevents oscillation between levels.
- **Alternatives considered:**
  - **Binary on/off degradation:** Too coarse — no middle ground between "fully operational" and "fully degraded".
  - **Continuous weighted degradation (0.0-1.0):** Too complex for operators to understand and act upon, hard to test exhaustively.
  - **Circuit-breaker per component:** No coordination between components — one component might degrade while another operates at full capacity, causing inconsistent behavior.
- **Consequences:** Operators have clear, testable semantics for each level (~80 lines of orchestration logic). Auto-escalation prevents cascading failures by preemptively reducing load. EMERGENCY mode is the last resort before process termination — it logs a critical alert and returns a minimal response. Each level maps to a specific operational playbook ("Degraded — check upstream APIs", "Survival — scale up cluster"). The Safety Monitor evaluates thresholds every 10 seconds.

---

### ADR-005: Plugin System with Hermes Bridge

- **Date:** 2026-01-08
- **Context:** The engine needed to support third-party extensions — custom validators, adapters (Slack, email, custom APIs), notification targets — without modifying core code. A simple hook-callback system was too limited (no lifecycle management, no dependency resolution). A full plugin framework risked being too invasive and creating coupling between core and extensions.
- **Decision:** Plugin system based on an abstract base class `PluginBase` with required metadata (`name`, `version`, `dependencies`) and lifecycle hooks (`on_load`, `on_unload`, `on_event`). Discovery uses filesystem scanning (default: `~/.prodinamik/plugins/` and `./plugins/`) with automatic dependency resolution (topological sort). The `HermesPluginBridge` provides a controlled API surface (~15 methods) for plugins to call back into engine internals — reading state, emitting events, accessing the event store — without exposing the full engine API.
- **Alternatives considered:**
  - **Pure hook callbacks (function references):** No lifecycle management, no dependency resolution, no versioning.
  - **Python entry-points convention:** Pip-coupled, harder to version-manage and install without `pip`, requires package build step.
  - **Subprocess plugins (IPC):** Serialization/deserialization overhead for every event, complex marshalling for Python objects, harder to debug.
  - **Shared-library plugins (C extensions):** Platform-specific, unsafe memory access, steep learning curve for plugin authors.
- **Consequences:** Plugins are discoverable, versioned, and dependency-aware. Plugin install via `prodinamik plugin install` pulls from a configured repository or local path. The HermesBridge provides a stable API surface isolated from core internals — plugins that use it are less likely to break across engine versions. Plugin isolation is convention-based (no true sandboxing — users should audit third-party plugins before installation). The system spans 4 modules totaling ~600 LoC. Plugin health checks via `prodinamik plugin health` verify every loaded plugin responds correctly.

---

### ADR-006: Raft Consensus for Distribution

- **Date:** 2026-01-15
- **Context:** The engine needed multi-node coordination for high-availability deployments. Key requirements: strong consistency for state machine transitions (no split-brain), tolerance for node failures (up to 2 of 5 nodes), and graceful offline operation (nodes should continue working during network partitions). The system must support both always-online clusters and occasionally-disconnected edge nodes.
- **Decision:** Use the Raft consensus algorithm for leader election and log replication. Implemented as a hybrid model:
  - **Online mode:** Standard Raft consensus — Leader handles all writes, Followers replicate the log, reads served by any node (with index check).
  - **Offline mode (partition or single-node):** Optimistic local writes with a pending log, local state machine progression allowed.
  - **Reconnection:** 5-step sync protocol — (1) Raft log sync from leader, (2) pending log proposal, (3) CRDT merge for conflicting entries, (4) merge write to primary log, (5) final state reconciliation.
  Cluster membership is managed via explicit configuration (node addresses). Leader election uses randomized timeouts (150-300ms). Raft spans 3 modules: `raft_types.py` (message types, log entries), `raft_consensus.py` (algorithm core), `raft_cluster.py` (cluster management, health).
- **Alternatives considered:**
  - **CRDT-only (Conflict-free Replicated Data Types):** No strong consistency guarantee for state machine transitions — eventual consistency only.
  - **2-Phase Commit (2PC):** Blocking protocol — coordinator failure blocks all participants, poor partition tolerance.
  - **Gossip protocol:** Eventual consistency only, not suitable for coordinating state machine transitions where order matters.
  - **Paxos:** Theoretically correct but notoriously complex to implement correctly — Raft's "understandability" goal was a deliberate design win.
- **Consequences:** Strong consistency for critical transitions during online mode. Offline writes are possible but enter a conflict resolution phase on reconnect (CRDT merge). The Raft implementation spans 3 modules (~900 LoC total, ~250 LoC consensus core, ~300 LoC cluster management, ~350 LoC types). Cluster setup requires explicit node addresses — no auto-discovery yet (ADR-021 planned). Leader election completes in ~200ms average. Write throughput is ~1,000 ops/sec on 5-node cluster with default settings.

---

### ADR-007: Async Runtime with asyncio

- **Date:** 2025-12-05
- **Context:** The engine needed to handle concurrent operations — parallel T2 validators, adapter I/O (HTTP calls, LLM inference, database queries), HTTP server, event processing — without the overhead of thread-based concurrency. The original v1.0 synchronous engine blocked on every I/O operation, limiting throughput to ~10 concurrent runs. A modern async approach was needed to scale to hundreds of concurrent runs while keeping resource usage low.
- **Decision:** Use Python's built-in `asyncio` for the async runtime. The `AsyncEngine` wraps the synchronous core with lifecycle hooks:
  - `on_start`: Initialize connections, load plugins, warm caches
  - `on_stop`: Graceful shutdown with configurable drain timeout
  - `on_timeout`: Configurable per-run timeout with automatic rollback
  A timeout watcher coroutine runs alongside the main loop, tracking run deadlines and canceling overdue executions. Long-running CPU-bound tasks (T3 validators, large data transforms) are offloaded to a `ThreadPoolExecutor` (max_workers=4 by default). The async runtime is ~250 LoC of orchestration, including health check endpoints and metrics collection.
- **Alternatives considered:**
  - **Threading (`threading.Thread`):** GIL contention for CPU-bound work, higher memory overhead per task (~8KB per thread stack vs ~2KB per coroutine), harder to reason about shared state.
  - **Multiprocessing (`multiprocessing.Process`):** IPC complexity (pickle serialization), high startup cost (~100ms per process),不适合 for I/O-heavy workloads where most time is spent waiting on network.
  - **Trio/Anyio:** Excellent API design (structured concurrency) but adds an external dependency that the project wanted to avoid.
  - **Gevent/eventlet:** Monkey-patching approach, implicit concurrency makes debugging difficult, less transparent control flow.
- **Consequences:** Efficient I/O-bound concurrency with zero external dependencies (asyncio is part of the Python standard library since 3.4). The engine scales to ~500 concurrent runs on modest hardware. Users must write async-compatible adapters for full benefit — synchronous adapters are wrapped with `run_in_executor` but incur thread pool overhead. The ThreadPoolExecutor handles CPU-bound validation tasks transparently, with configurable worker count. The timeout watcher prevents runaway runs from consuming resources indefinitely.

---

### ADR-008: Cache Policies with Content-Addressing

- **Date:** 2026-01-20
- **Context:** Adapters (HTTP calls, LLM inference, database queries) produce results that can be cached to reduce latency, cost, and upstream load. A simple TTL-based cache (e.g., "expire after 5 minutes") leads to staleness for dynamic resources. A write-through cache adds latency on every write even when reads are rare. The cache needed to handle diverse policies and carry cost metadata for budget enforcement.
- **Decision:** Content-addressed cache where cache keys are deterministic SHA-256 hashes of canonicalized adapter inputs (sorted JSON keys, whitespace-normalized). Supports configurable policies:
  - **TTL-based expiry:** Entries expire after a configurable duration (per-adapter default: 300s).
  - **LRU eviction:** Bounded memory usage (default: 256MB, configurable via `PRODINAMIK_CACHE_SIZE` env var).
  - **Pinned entries:** Never evicted — used for reference data (schemas, templates).
  - **Conditional refresh:** `refresh_if_older_than` setting re-fetches in background while serving stale cache (stale-while-revalidate pattern).
  Each cache entry carries cost metadata (API call cost, compute time) for budget enforcement. Cache hit/miss statistics are exposed via Prometheus metrics (`prodinamik_cache_hits_total`, `prodinamik_cache_misses_total`).
- **Alternatives considered:**
  - **Pure TTL cache:** Stale data window (TTL must be conservative), no content-awareness (different inputs with same output hash mismatch).
  - **Redis-backed cache:** Excellent features but adds an operational dependency (Redis server), overkill for single-node development.
  - **No cache at all:** Poor performance for repeated inputs (e.g., same LLM prompt evaluated across multiple runs).
  - **Write-through cache:** Adds latency to every write operation, even for data that is rarely read back.
- **Consequences:** Cache hit avoids redundant expensive operations — measured ~90% hit rate for T2 validators with repeated inputs. Content-addressing means identical inputs always produce cache hits regardless of arrival order. Memory usage is bounded by LRU policy (256 MB default, ~100K entries). Cache invalidation requires explicit "bust" operations for mutable resources — an `Adapter.bust_cache(input)` method is provided. Cost metadata enables budget-aware cache decisions (cache expiry can be extended for expensive entries).

---

### ADR-009: AI-Native Features as Optional Modules

- **Date:** 2026-02-10
- **Context:** The engine needed AI capabilities — drift detection, predictive degradation, run recommendation, skill emergence, auto-remediation — without making AI a hard dependency. These features are valuable for LLM-heavy workloads but not everyone needs them. Making AI a core dependency would bloat the installation, add unused imports, and create a maintenance burden for non-AI users.
- **Decision:** AI features are implemented as 5 optional modules that import from core only:
  - `aidetect.py` — Drift detection (linear regression trend analysis, z-score anomaly detection, emergence detection with configurable threshold)
  - `predict.py` — Predictive degradation (moving average, linear regression, Holt-Winters forecasting)
  - `skillforge.py` — Skill emergence (auto SKILL.md generation, regression test generation, T3→T2 promotion)
  - `recommend.py` — Run recommender (transition success scoring: rate × frequency × recency, bottleneck detection)
  - `autofix.py` — Auto-remediation (FailureMatcher with 10 built-in patterns, exponential backoff, cooldown, auto-escalation)
  They are shipped with the package but require explicit opt-in via engine config (`ai.enabled: true`) or profile. A non-AI engine is fully functional — AI modules simply aren't loaded or instantiated.
- **Alternatives considered:**
  - **AI features as a separate package (`prodinamik-ai`):** Versioning complexity — must keep in sync with core API changes. Slower iteration velocity.
  - **AI features as mandatory core dependency:** Bloats the engine for non-AI users (~1,200 LoC of AI code), unnecessary imports and module loading.
  - **AI features as external microservices:** Operational overhead (deploy and monitor separate services), network latency on every AI call, harder to orchestrate as a cohesive system.
- **Consequences:** Core engine footprint remains small (~35 modules). AI modules can evolve independently within the same release cycle. The 5 AI modules total ~1,200 LoC with dedicated test suites. Users that enable AI features get drift detection, self-healing, and predictive scaling out of the box. The opt-in pattern serves as a natural feature gate — AI-heavy deployments enable all features; lightweight deployments keep only drift detection.

---

### ADR-010: Click CLI Framework

- **Date:** 2025-10-25
- **Context:** The engine needed a CLI with ~40+ commands organized into hierarchical groups (run, config, plugin, ai, etc.) with help text, tab completion, configuration file loading, and colored output. The choice of CLI framework directly affects developer productivity (how easy is it to add a new command?) and user experience (how discoverable and self-documenting is the interface?).
- **Decision:** Use Click for the CLI layer. Commands are organized under CLI groups:
  - `run`, `list`, `transition`, `debug` — core engine commands
  - `config`, `profile` — configuration management
  - `plugin` — 10 subcommands (list, discover, enable, disable, install, uninstall, info, reload, health, validate)
  - `ai` — 4 subcommands (detect, predict, recommend, status)
  - `serve`, `dashboard`, `metrics`, `audit` — operations
  - `raft`, `chaos` — advanced features
  Click's decorator-based API (`@click.command`, `@click.option`, `@click.group`) makes adding a new command ~10-15 LoC. Configuration is loaded via `@click.pass_context` with auto-detection of `config.yaml` in the current directory.
- **Alternatives considered:**
  - **`argparse` (stdlib):** Verbose for 40+ commands — manual subcommand nesting requires dozens of `set_defaults(func=...)` lines. No auto-help text formatting, no automatic type coercion, no tab completion support.
  - **`typer`:** Modern, type-hint driven, automatic help generation. However, it adds an external dependency (Click is already transitive via MkDocs), and its plugin ecosystem is less mature than Click's.
  - **`google-fire`:** Too magical — exposes any Python function as a CLI without explicit help control, making it hard to produce professional help output and validate inputs.
- **Consequences:** Clean command hierarchy with automatic help generation, tab completion, and colored output. Adding a new command is 10-15 LoC — one decorator, one function. Click is already a transitive dependency via MkDocs (used for the documentation site). The CLI grows from ~18 to ~46 commands across versions (v0.5 → v1.3) without structural changes. Command nesting is limited to 2 levels for discoverability.

---

### ADR-011: Content-Addressed Validator Cache

- **Date:** 2026-02-05
- **Context:** Validators, especially T2 and T3 (LLM-based rubric scoring, hallucination checks, coverage analysis), are expensive to run — each AI validation call costs ~$0.01-0.05 and takes 1-5 seconds. Identical inputs across different runs, transitions, or parallel executions should hit a cache rather than recompute. The cache needed to be shared across the parallel T2 pool and handle version invalidation.
- **Decision:** The validator cache uses content-addressed keys — SHA-256 hash of normalized validator inputs (sorted JSON keys, whitespace-normalized, type-stable). Each validator declares its cacheability via a class attribute `cacheable = True`. The cache is a shared `LRUCache` instance passed to all validators in the T2 parallel pool. Cache entries are invalidated on:
  - Schema version change (detected via `engine.config.schema_version`)
  - Explicit bust via `Validator.bust_cache(inputs)`
  - TTL expiry (default: 600s for T2, 300s for T3)
  - Memory pressure (cache shrinks to 50% when heap usage >80%)
- **Alternatives considered:**
  - **Per-validator instance cache:** No sharing between runs or parallel validators, 3x higher memory usage for identical inputs.
  - **No cache:** Repeated AI calls for identical inputs across parallel T2 validations — expensive ($0.05/call × 10 parallel = $0.50 per transition) and slow (10-50s per transition).
  - **Database-backed cache:** Disk-bound lookup (SQLite B-tree traversal ~5ms) is slower than in-memory dict lookup (~0.1µs) for sub-5s validations where speed matters.
- **Consequences:** T2 validators with identical inputs across parallel executions see ~90% cache hit rate. Cache is in-memory with ~64 MB default capacity (~25,000 entries). Version invalidation ensures correctness after schema/upstream changes. Cost savings are significant — a transition that previously cost $0.50 in AI calls now costs $0.05 after cache warmup. The cache is invisibly shared — validators don't need to know about each other's caching.

---

### ADR-012: Project Structure — Single `engine/` Package

- **Date:** 2025-10-20
- **Context:** As the project grew from a single file (`engine.py`, ~800 LoC) to 35+ Python modules across versions, the project structure needed to scale. Two fundamental approaches: keep everything under a single `engine/` package with flat module layout, or introduce namespace/subdirectory packages. The wrong choice could lead to import friction, circular dependencies, and difficulty navigating the codebase.
- **Decision:** All Python modules live under a single `engine/` package with a flat module layout. Sub-directories (e.g., `engine/core/`, `engine/ai/`, `engine/plugins/`) are not used. Instead, modules are flat within `engine/`:
  ```
  engine/
    __init__.py        # ~50 LoC, re-exports key classes
    state_machine.py
    sm_types.py
    sm_parser.py
    profile.py
    run_manager.py
    validators.py
    event_store.py
    degradation.py
    raft_consensus.py
    raft_types.py
    raft_cluster.py
    plugin.py
    plugin_registry.py
    hermes_bridge.py
    plugin_repo.py
    aidetect.py
    predict.py
    skillforge.py
    ...
  ```
- **Alternatives considered:**
  - **Namespace packages (`prodinamik.engine.*`, `prodinamik.plugins.*`):** Requires `pkgutil.extend_path` or `importlib.metadata`, import complexity for users (`from prodinamik.engine import state_machine` vs `from engine import state_machine`), harder to document with MkDocs since each package needs its own nav section.
  - **Deep nested structure (`engine/core/`, `engine/ai/`, `engine/plugins/`):** Adds import friction (`from engine.core.state_machine import ...`), circular import risk between sub-packages (e.g., `plugins` importing from `core` and vice versa), requires `__init__.py` files in every sub-directory.
- **Consequences:** Import paths are short and predictable (`from engine import state_machine`). No `__init__.py` sub-packaging overhead — the single package init is clean and minimal (~50 LoC). The flat structure works reliably up to ~50 modules; beyond that, sub-packages would be needed for maintainability (ADR-018 tracks this threshold). Module naming follows a consistent `snake_case` convention. The MkDocs API reference is easy to generate — each module maps directly to a page in the nav without sub-package prefixes.
