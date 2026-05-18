# Prodinamik Engine v1.3

**Product-Agnostic Pipeline Engine** — Formal state machine, multi-tier validation, event sourcing, Raft consensus, plugin ecosystem, and AI-native drift detection/prediction/remediation.

> 🚀 **49 Python modules · 333 tests · 46 CLI commands · 4 production profiles**

[![Tests](https://img.shields.io/badge/tests-333%20passed-brightgreen)](https://github.com/yunusgungor/prodinamik-engine)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.3.0-blueviolet)](https://github.com/yunusgungor/prodinamik-engine)

```bash
pip install prodinamik-engine
prodinamik run software "AI module refactoring"
prodinamik ai status
prodinamik plugin list
```

---

## ✨ Overview

Prodinamik Engine is the **shared core** behind Content-OS, Haber-Kurator, and dev-cycle. It manages any production pipeline — content, software, research, design — through a unified state machine, validator pipeline, and distributed runtime.

### Who Is It For?

| Role | Profile | What They Get |
|------|---------|---------------|
| **Content creator** | `content` | Auto content pipeline (brief → draft → verify → publish) |
| **Software dev** | `software` | Prototype → production framework (dev-cycle) |
| **Researcher** | `research` | Literature → structured report pipeline |
| **Designer** | `design` | Brief → asset generation pipeline |
| **DevOps** | any | Observability, alerting, chaos engineering |
| **Hermes user** | plugin | Extend engine via PluginBase → Hermes skills/tools |

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI (46 commands)                        │
├─────────────────────────────────────────────────────────────┤
│  ProfileRegistry ──► ProductProfile ──► RunManager ──► EventStore │
│       │                   │                                      │
│  ┌────┴────┐         ┌───┴────┐                              │
│  │ Plugin  │    ValidatorPipeline  Adapters                    │
│  │Registry │    3-Tier (Slop/     Circuit Breaker              │
│  │         │    Rubric/Hall.)     Retry · Fallback             │
│  └─────────┘    Content Cache     Timeout                      │
├─────────────────────────────────────────────────────────────┤
│  Safety (EventBus · Invariants · Health Score)                 │
│  Degradation (FULL → DEGRADED → SURVIVAL)                     │
│  Cost + Budget (4-dim · T0/T1 · 3σ Anomaly)                   │
│  Observability (Metrics · Dashboard · Audit Log)              │
│  Security (Auth · Rate Limiter · API Keys)                     │
├─────────────────────────────────────────────────────────────┤
│  Distribution (Raft Consensus · TCP Transport · Leader Election) │
├─────────────────────────────────────────────────────────────┤
│  AI-Native (Drift Detection · Predictive Degradation ·         │
│              Run Recommender · Skill Emergence · Auto-Fix)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Capabilities

### 🔧 Core Engine

| Feature | Implementation |
|---------|---------------|
| **State Machine** | YAML-defined, LTL temporal logic, 7-state lifecycle, 10 transitions |
| **Validation** | 3-tier pipeline: Slop scan (107 patterns) → Rubric (12 criteria) → Hallucination cross-ref |
| **Event Sourcing** | JSONL audit log, WAL, segment-based compaction, replay |
| **Product Profiles** | `software`, `content`, `research`, `design` — pluggable validators/adapters |
| **Async Runtime** | asyncio main loop, lifecycle hooks, timeout watcher, graceful shutdown |

### 📊 Observability

| Feature | Implementation |
|---------|---------------|
| **Metrics** | Counter, Gauge, Histogram, Prometheus export, EngineMetrics |
| **Dashboard** | Terminal (ANSI) + HTML dashboard with thermal bar, run matrix, alert log |
| **Audit** | JSONL audit log, segment rotation, query/filter, replay, compaction |
| **Alerting** | Slack/Telegram webhook, multi-channel, configurable thresholds |

### 🔒 Security & Distribution

| Feature | Implementation |
|---------|---------------|
| **Auth** | API key auth (`pdmk_` prefix), RBAC (admin/user/readonly) |
| **Rate Limiter** | Token bucket, configurable rates |
| **HTTP Server** | Metrics, healthz, API endpoints |
| **Raft Consensus** | Leader election, log replication, TCP transport, cluster management |
| **Distributed Runs** | Multi-node run coordination via Raft |
| **Leader Election** | etcd/Consul external leader election |

### 🧪 Quality

| Feature | Implementation |
|---------|---------------|
| **Chaos Engineering** | 10 fault scenarios (network partition, disk crash, OOM, CPU spike, degraded mode, WAL corruption, event flood) |
| **Graceful Degradation** | FULL → DEGRADED → SURVIVAL → EMERGENCY levels |
| **Budget Enforcement** | Iteration/cost budget with configurable thresholds |
| **Cost Tracking** | 4-dim cost model, T0/T1 pricing, 3σ anomaly detection |

### 🔌 Plugin Ecosystem (v1.2)

| Feature | Implementation |
|---------|---------------|
| **Plugin Base** | `PluginBase` ABC with manifest, lifecycle, tools, hooks |
| **Registry** | Auto-discovery from built-in + search paths, dependency resolution |
| **Hermes Bridge** | Plugin tools → Hermes AIAgent tool defs, SKILL.md export |
| **Repository** | Local/remote install, checksum verification, search |
| **CLI** | 10 plugin commands: `list`, `discover`, `enable`, `disable`, `install`, `uninstall`, `info`, `reload`, `health` |
| **Plugin Types** | 9 types: VALIDATOR, ADAPTER, HOOK, TOOL, PROFILE, STORE, UI, INTEGRATION, OTHER |

### 🤖 AI-Native Features (v1.3)

| Feature | Implementation |
|---------|---------------|
| **Drift Detection** | Trend analysis (linear regression), anomaly detection (z-score), emergence detection (3+ threshold) |
| **Predictive Degradation** | MA/LR/Holt-Winters forecasting, threshold breach prediction, health scoring |
| **Run Recommender** | Transition success scoring (rate × frequency × recency), bottleneck detection |
| **Skill Emergence** | Auto SKILL.md + regression test generation, T3→T2 promotion |
| **Auto-Remediation** | FailureMatcher (10 built-in patterns), exponential backoff, cooldown, auto-escalation |
| **CLI** | `prodinamik ai detect|predict|recommend|status` |

---

## 📦 49 Modules

```
engine/
├── aidetect.py         # AI Drift Detection (trend, anomaly, emergence)
├── alert.py            # Alert Manager (Slack/Telegram)
├── audit.py            # JSONL Audit Log
├── auth.py             # API Key Authentication
├── autofix.py          # Auto-Remediation (10 patterns)
├── bench.py            # Performance Benchmarking
├── budget.py           # Budget Enforcement
├── chaos.py            # Chaos Engineering (10 scenarios)
├── cli.py              # CLI Entry Point (46 commands)
├── config.py           # YAML Configuration
├── cost.py             # Cost Tracking
├── dashboard.py        # Terminal + HTML Dashboard
├── debug_cli.py        # Debug CLI Helpers
├── degradation.py      # Graceful Degradation
├── distributed.py      # Distributed Run Coordinator
├── elector.py          # External Leader Election
├── engine.py           # Core Engine Loop
├── event_store.py      # Event Sourcing
├── hermes_bridge.py    # Hermes Agent Integration
├── hooks.py            # Lifecycle Hooks
├── log.py              # Structured Logging
├── metrics.py          # Prometheus-compatible Metrics
├── migration.py        # Formal State Migration
├── plugin.py           # Plugin Base System
├── plugin_registry.py  # Plugin Registry
├── plugin_repo.py      # Plugin Repository
├── predict.py          # Predictive Degradation
├── profile.py          # ProductProfile ABC
├── raft_cluster.py     # Raft Cluster Management
├── raft_consensus.py   # Raft Consensus
├── raft.py             # Raft Core (legacy)
├── raft_transport.py   # Raft TCP Transport
├── raft_types.py       # Raft Message Types
├── ratelimit.py        # Token Bucket Rate Limiter
├── recommend.py        # Run Recommender
├── registry.py         # ProfileRegistry
├── run_manager.py      # Run Lifecycle
├── runtime.py          # Async Runtime
├── safety.py           # Runtime Safety Monitor
├── scaffold.py         # Project Scaffolding
├── server.py           # HTTP Server
├── shell.py            # Interactive REPL
├── skillforge.py       # Skill Emergence Automation
├── sm_parser.py        # State Machine Parser
├── sm_types.py         # State Machine Types
├── state_machine.py    # State Machine Engine
├── validators.py       # Validator Pipeline
├── __init__.py         # Package Init + Exports

profiles/
├── content.py          # Content Production Profile
├── design.py           # Design Profile
├── research.py         # Research Profile
├── software.py         # Software Development Profile
```

---

## 🖥️ 46 CLI Commands

```
prodinamik run <profile> <title>        # Start a new run
prodinamik list                          # List all runs
prodinamik transition <slug> <state>     # State transition
prodinamik debug <slug>                  # Show run details
prodinamik config                        # Show config
prodinamik validate <profile_path>       # Validate profile
prodinamik daemon                        # Start async runtime daemon
prodinamik shell                         # Interactive REPL
prodinamik new profile <name>            # Generate new profile
prodinamik new project <name>            # Generate new project
prodinamik benchmark [runs]              # Performance benchmarks
prodinamik completion bash|zsh           # Shell completion
prodinamik dashboard [--compact|--html]  # Health dashboard
prodinamik metrics [--prometheus]        # Metrics export
prodinamik audit query [type]            # Audit log query
prodinamik audit stats                   # Audit statistics
prodinamik audit compact                 # Compact old entries
prodinamik auth create <name>            # Create API key
prodinamik auth list                     # List API keys
prodinamik auth revoke <id>              # Revoke API key
prodinamik auth info <id>                # Show key details
prodinamik serve [--port PORT]           # HTTP server
prodinamik raft status                   # Raft cluster health
prodinamik raft peers <ids>              # Register peers
prodinamik raft elect                    # Force leader election
prodinamik chaos run <scenario>          # Run chaos scenario
prodinamik chaos list                    # List chaos scenarios
prodinamik chaos report                  # Show chaos report
prodinamik alert send <level> <title>    # Send alert
prodinamik alert test [--channel]        # Test alert channel
prodinamik alert recent [--limit]        # Recent alerts
prodinamik alert status                  # Alert manager status
prodinamik plugin list                   # List plugins
prodinamik plugin discover               # Scan for plugins
prodinamik plugin enable <id>            # Enable plugin
prodinamik plugin disable <id>           # Disable plugin
prodinamik plugin install <id> [--source] # Install plugin
prodinamik plugin uninstall <id>         # Uninstall plugin
prodinamik plugin info <id>              # Show plugin details
prodinamik plugin reload                 # Reload plugin(s)
prodinamik plugin health                 # Plugin health checks
prodinamik ai detect                     # AI drift detection
prodinamik ai predict [--metric]         # Degradation forecast
prodinamik ai recommend <state>          # Next state recommendation
prodinamik ai status                     # AI features status
prodinamik version                       # Show version
```

---

## 🔌 Quick Start Plugin Usage

```python
from engine.plugin import PluginBase, PluginManifest, PluginType, PluginTool

class SlackPlugin(PluginBase):
    """Notify Slack on state transitions"""

    @property
    def manifest(self):
        return PluginManifest(
            id="prodinamik.slack",
            name="Slack Integration",
            version="1.0.0",
            plugin_type=PluginType.INTEGRATION,
            hooks=["on_error", "on_degrade"],
            provides_tools=["slack_send"],
        )

    def get_tools(self):
        return [
            PluginTool(
                name="slack_send",
                description="Send message to Slack",
                handler=self._send_message,
                parameters={
                    "channel": {"type": "string"},
                    "message": {"type": "string"},
                },
            )
        ]

    async def _send_message(self, channel, message):
        # ... send to Slack
        return {"ok": True}
```

```bash
prodinamik plugin discover
prodinamik plugin enable prodinamik.slack
prodinamik plugin info prodinamik.slack
```

---

## 🤖 Quick Start AI Features

```python
from engine.aidetect import AIDriftDetector, DriftType, DriftSeverity

detector = AIDriftDetector()

# Record drifts
detector.record_drift("D01", DriftType.FORMAT, DriftSeverity.MEDIUM,
                      "run-1", "drafting", "Invalid YAML frontmatter")

# Analyze
report = detector.generate_report()
print(f"Health Score: {report['health_score']}/100")
print(f"Emergence Candidates: {len(report['emergence_candidates'])}")
```

```bash
prodinamik ai detect
prodinamik ai predict --metric latency_ms
prodinamik ai recommend drafting
```

---

## 📊 Test Status

```
333 passed in 67s
```

| Category | Tests |
|----------|-------|
| Core Engine | ~45 |
| Profiles | ~30 |
| Runtime & DevEx | ~25 |
| Observability | ~40 |
| Security & Distribution | ~35 |
| Chaos Engineering | ~20 |
| Distribution & Scaling | ~25 |
| Plugin Ecosystem | ~66 |
| AI-Native Features | ~67 |
| **Total** | **333** |

---

## 🚀 Project Timeline

```
Short-Term  (9/9):   ✅ Core, Resilience, Runtime, DevEx, Observability, Security, Chaos
Medium-Term (3/3):   ✅ Monitoring, Documentation, Performance
Long-Term   (3/3):   ✅ Distribution & Scaling, Plugin Ecosystem, AI-Native Features
────────────────────────────────────────────────────────
ROADMAP COMPLETE
```

---

## 📚 Documentation

Full documentation at [yunusgungor.github.io/prodinamik-engine](https://yunusgungor.github.io/prodinamik-engine)

```bash
# Build locally
mkdocs build
mkdocs serve
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

*Built with Hermes Agent · dev-cycle v5.0 framework · 2026*
