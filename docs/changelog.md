# Changelog

## v1.3.0 (2026-05-18)

### Added
- **AI Drift Detection** — Trend analysis (linear regression), anomaly detection (z-score), emergence detection (3+ threshold)
- **Predictive Degradation** — MA/LR/Holt-Winters forecasting, threshold breach prediction, health scoring
- **Run Recommender** — Transition success scoring (rate × frequency × recency), bottleneck detection
- **Skill Emergence** — Auto SKILL.md + regression test generation, T3→T2 promotion at 10 successful fixes
- **Auto-Remediation** — FailureMatcher (10 built-in patterns), exponential backoff, cooldown, auto-escalation
- **Plugin Ecosystem** — PluginBase ABC, PluginRegistry (auto-discovery, dep resolution), HermesPluginBridge, PluginRepository
- **10 plugin CLI commands** — `list`, `discover`, `enable`, `disable`, `install`, `uninstall`, `info`, `reload`, `health`
- **4 AI CLI commands** — `ai detect`, `ai predict`, `ai recommend`, `ai status`
- **5 new modules** — `aidetect.py`, `predict.py`, `skillforge.py`, `recommend.py`, `autofix.py`
- **4 new modules** — `plugin.py`, `plugin_registry.py`, `hermes_bridge.py`, `plugin_repo.py`

### Changed
- Engine version: 1.2.0 → 1.3.0
- CLI commands: 42 → 46
- Tests: 266 → 333 (+67 new tests)
- Python modules: 44 → 49 (+5 AI, +4 plugin)
- `__version__` updated across all modules

### Fixed
- PluginRegistry singleton naming collision (classmethod vs instance method)
- Repository `shutil.ignored_patterns` compatibility (Python 3.10+)
- Engine version compatibility test drift
- CLI docstring sync with actual command count

## v1.2.0 (2026-05-18)

### Added
- Plugin Ecosystem: PluginBase ABC, PluginRegistry, HermesPluginBridge, PluginRepository
- 10 plugin CLI commands (list, discover, enable, disable, install, uninstall, info, reload, health)
- 4 plugin modules: plugin.py, plugin_registry.py, hermes_bridge.py, plugin_repo.py

### Changed
- Engine version: 1.1.0 → 1.2.0
- CLI commands: 32 → 42
- Tests: 200 → 266 (+66 plugin tests)
- Python modules: 40 → 44 (+4 plugin)

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
