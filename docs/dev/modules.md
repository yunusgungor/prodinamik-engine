# Module Reference

Prodinamik Engine v1.3 consists of **49 Python modules** organized by functional layer.

## Core Engine

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/state_machine.py` | ~450 | YAML-defined state machine with LTL temporal validation |
| `engine/sm_parser.py` | ~200 | State machine YAML parser and validator |
| `engine/sm_types.py` | ~150 | StateType, TransitionType, RuntimeState enums |
| `engine/validators.py` | ~400 | 3-tier ValidatorPipeline + ContentAddressableCache |
| `engine/profile.py` | ~350 | ProductProfile ABC with pluggable validators/adapters |
| `engine/run_manager.py` | ~300 | Run lifecycle manager with WAL + snapshot |
| `engine/event_store.py` | ~250 | Event sourcing, batch append, retention |
| `engine/engine.py` | ~200 | Core engine loop |
| `engine/config.py` | ~200 | YAML configuration loader |
| `engine/registry.py` | ~100 | ProfileRegistry — profile discovery |
| `engine/log.py` | ~150 | Structured JSON logging |

## Runtime & DevEx

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/runtime.py` | ~350 | AsyncEngine — asyncio main loop, timeout watcher |
| `engine/hooks.py` | ~130 | HookRegistry — on_enter/on_exit/on_timeout |
| `engine/cli.py` | ~1,200 | Click CLI entry point (46 commands) |
| `engine/shell.py` | ~250 | Interactive REPL |
| `engine/scaffold.py` | ~150 | Project/profile scaffolding |
| `engine/bench.py` | ~200 | Performance benchmarks |
| `engine/debug_cli.py` | ~100 | Debug helpers |
| `engine/migration.py` | ~200 | Formal state migration plans |

## Observability

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/metrics.py` | ~300 | Counter, Gauge, Histogram, Prometheus export |
| `engine/dashboard.py` | ~350 | Terminal (ANSI) + HTML dashboard |
| `engine/audit.py` | ~350 | JSONL audit log, replay, compaction |
| `engine/alert.py` | ~300 | Slack/Telegram alert manager |

## Security & Distribution

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/auth.py` | ~250 | API key auth, RBAC (admin/user/readonly) |
| `engine/ratelimit.py` | ~150 | Token bucket rate limiter |
| `engine/server.py` | ~300 | HTTP server (metrics, healthz, API) |
| `engine/raft_consensus.py` | ~400 | Raft consensus implementation |
| `engine/raft_transport.py` | ~250 | TCP transport for Raft |
| `engine/raft_types.py` | ~100 | Raft message types |
| `engine/raft_cluster.py` | ~150 | Cluster management |
| `engine/raft.py` | ~200 | Raft core (legacy facade) |
| `engine/distributed.py` | ~200 | DistributedRunCoordinator |
| `engine/elector.py` | ~150 | etcd/Consul leader election |

## Quality

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/chaos.py` | ~500 | 10 fault scenarios |
| `engine/safety.py` | ~200 | EventBus, RuntimeSafetyMonitor |
| `engine/degradation.py` | ~200 | Graceful degradation levels |
| `engine/budget.py` | ~150 | Budget enforcement |
| `engine/cost.py` | ~200 | Cost tracking + efficiency |

## Plugin Ecosystem

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/plugin.py` | ~400 | PluginBase ABC, PluginManifest, PluginTool, PluginHook |
| `engine/plugin_registry.py` | ~550 | PluginRegistry singleton, discovery, enable/disable |
| `engine/hermes_bridge.py` | ~450 | PluginTool → Hermes tool defs, SKILL.md export |
| `engine/plugin_repo.py` | ~550 | PluginRepository, remote install, checksum |

## AI-Native Features

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/aidetect.py` | ~650 | DriftPatternCollector, TrendAnalyzer, EmergenceDetector |
| `engine/predict.py` | ~600 | MetricCollector, ForecastEngine, DegradationPredictor |
| `engine/skillforge.py` | ~380 | AutoSkillForge, SKILL.md + test generation |
| `engine/recommend.py` | ~500 | TransitionHistory, RunRecommender |
| `engine/autofix.py` | ~550 | FailureMatcher, AutoRemediator |

## Profiles

| Module | Lines | Description |
|--------|-------|-------------|
| `profiles/software.py` | ~200 | Software development profile (dev-cycle) |
| `profiles/content.py` | ~200 | Content production profile (Content-OS) |
| `profiles/research.py` | ~150 | Research pipeline profile |
| `profiles/design.py` | ~150 | Design pipeline profile |

## Utilities

| Module | Lines | Description |
|--------|-------|-------------|
| `engine/__init__.py` | ~190 | Package exports (all public API) |
| `adapters/__init__.py` | ~50 | Adapter implementations |
| `validators/__init__.py` | ~50 | Shared validators |

## Export Quick Reference

```python
from engine import (
    # Core
    ProdinamikEngine, ProdinamikConfig, StateMachine, RunManager,
    # Validation
    ValidatorPipeline, ContentAddressableCache, CachePolicy,
    # Observability
    MetricsRegistry, Dashboard, AuditLog,
    # Security
    AuthManager, RateLimiter, ProdinamikServer,
    # Distribution
    HybridConsensusNode, DistributedRunCoordinator,
    # Plugin
    PluginBase, PluginManifest, PluginRegistry, HermesPluginBridge,
    # AI
    AIDriftDetector, AIDegradationForecaster,
    AIRecommender, AutoRemediator, AutoSkillForge,
    # Runtime
    AsyncEngine, HookRegistry, ProdinamikShell,
    # Quality
    ChaosEngine, DegradationManager, BudgetEnforcer,
)
```
