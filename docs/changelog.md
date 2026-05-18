# Changelog

## v1.1.0 (2026-05-18)

### Added
- Async runtime engine with lifecycle hooks, timeout watcher, graceful shutdown
- Interactive REPL shell with tab completion and history
- Profile/project scaffolding generator
- Performance benchmark suite (6 suites)
- Prometheus metrics pipeline (Counter, Gauge, Histogram)
- Terminal health dashboard with HTML export
- Append-only audit log with replay and compaction
- API key authentication with RBAC (admin/user/readonly)
- Token bucket rate limiter per-key
- HTTP server with Prometheus `/metrics` and REST API
- Raft cluster management (health, discovery, failover)
- Chaos engineering (10 fault scenarios, self-healing verification)
- Alert manager (Slack/Telegram webhook, dedup, rate limiting)
- 4 production profiles: content, software, research, design
- Multi-stage Dockerfile (production 231MB)
- GitHub Actions CI/CD (test → lint → docker → GHCR)
- Makefile (18 targets)
- Prometheus alert rules (19 rules)
- Grafana dashboard template (21 panels)
- Stress test script (`scripts/stress_test.py`)
- Memory profiler (`scripts/memory_profile.py`)
- OpenAPI/Swagger spec for HTTP API
- MkDocs documentation site
- Auto-generated API reference (33 modules)

### Changed
- `raft.py` split into 4 files (types, consensus, cluster, facade)
- `state_machine.py` split into 3 files (types, parser, runtime)
- All Drift corrections (D01-D10) applied
- Coverage config added to `pyproject.toml`

### Fixed
- Dashboard "Run Matrix" assertion in empty engine state
- Chaos random crash thread warning (expected behavior documented)
- Test count: 165 → 177 (+12 monitoring tests)

## v1.0.0 (2026-05-17)

### Added
- Formal YAML state machine with LTL temporal constraints
- 3-tier validator pipeline with content-addressable cache
- Event sourcing with retention policies
- Cost tracking (LLM, compute, storage, network)
- Budget enforcement (WARN → SLOW → STOP)
- Graceful degradation (FULL → DEGRADED → SURVIVAL)
- Hybrid Raft+Offline+CRDT consensus
- WAL with atomic snapshots
- EventBus with trace_id and cycle detection
- 4-source profile registry
- Migration plans with cross-profile orchestration
- Click CLI with 25+ commands
- Async+sync dual-mode validation
