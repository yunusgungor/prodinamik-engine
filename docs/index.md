# Prodinamik Engine v1.3

> **Product-Agnostic Pipeline Engine** — Formal state machine, 3-tier validator pipeline, event sourcing, Raft consensus, plugin ecosystem, and AI-native drift detection/prediction/remediation.

[![Tests](https://github.com/yunusgungor/prodinamik-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/yunusgungor/prodinamik-engine/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.3.0-blueviolet)](https://github.com/yunusgungor/prodinamik-engine)
[![Tests](https://img.shields.io/badge/tests-333%20passed-brightgreen)]()
[![Modules](https://img.shields.io/badge/modules-49-orange)]()

---

**Prodinamik Engine** is the **shared core** behind Content-OS, Haber-Kurator, and dev-cycle — managing all production pipelines through a unified state machine, validator pipeline, and distributed runtime.

## Features

### 🔧 Core Engine
- **Formal State Machine** — YAML-defined states with LTL temporal logic, compile-time validation
- **3-Tier Validator Pipeline** — T1 deterministic → T2 parallel (LLM) → T3 sequential (cross-ref)
- **Event Sourcing** — Append-only event store with WAL, retention, replay
- **4 Built-in Profiles** — `content`, `software`, `research`, `design`
- **Async Runtime** — asyncio main loop, lifecycle hooks, timeout watcher, graceful shutdown

### 📊 Observability & Security
- **Metrics** — Counter, Gauge, Histogram, Prometheus export
- **Dashboard** — Terminal (ANSI) + HTML dashboard with thermal bar
- **Audit** — JSONL audit log, segment rotation, query, replay, compaction
- **Auth** — API key auth (`pdmk_` prefix), RBAC (admin/user/readonly)
- **Rate Limiter** — Token bucket, configurable rates
- **HTTP Server** — Metrics, healthz, API endpoints
- **Alerting** — Slack/Telegram webhook, multi-channel

### 🌐 Distribution
- **Raft Consensus** — Leader election, TCP transport, log replication
- **Distributed Runs** — Multi-node run coordination
- **External Leader Election** — etcd/Consul integration

### 🧪 Quality
- **Chaos Engineering** — 10 fault scenarios with self-healing verification
- **Graceful Degradation** — FULL → DEGRADED → SURVIVAL → EMERGENCY
- **Cost Tracking** — Multi-dimensional (LLM, compute, storage, network)
- **Budget Enforcement** — WARN → SLOW → STOP

### 🔌 Plugin Ecosystem (v1.2)
- **PluginBase ABC** — Manifest, lifecycle, tools, hooks, validators
- **PluginRegistry** — Auto-discovery, dependency resolution, enable/disable
- **HermesPluginBridge** — Plugin tools → Hermes AIAgent tool definitions
- **PluginRepository** — Local/remote install, checksum verification

### 🤖 AI-Native Features (v1.3)
- **Drift Detection** — Trend analysis (linear regression), anomaly detection (z-score), emergence (3+ rule)
- **Predictive Degradation** — MA/LR/Holt-Winters forecasting, threshold breach prediction
- **Run Recommender** — Transition success scoring, bottleneck detection
- **Skill Emergence** — Auto SKILL.md + test generation, T3→T2 promotion
- **Auto-Remediation** — FailureMatcher (10 patterns), exponential backoff, cooldown

## Quick Start

```bash
# Install
pip install prodinamik-engine

# Core usage
prodinamik run content "My blog post"
prodinamik list
prodinamik transition my-blog-post reviewing

# Plugin ecosystem
prodinamik plugin discover
prodinamik plugin enable prodinamik.logging

# AI features
prodinamik ai status
prodinamik ai detect
prodinamik ai recommend drafting

# Observability
prodinamik dashboard
prodinamik serve --port 8080

# Chaos engineering
prodinamik chaos run cpu-spike --duration 2
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI (46 commands)                         │
├─────────────────────────────────────────────────────────────┤
│  ProfileRegistry → ProductProfile → RunManager → EventStore  │
│  PluginRegistry → PluginBase → HermesBridge                  │
│  Validators (T1/T2/T3) · Adapters (Circuit Breaker)         │
│  Hooks (on_enter/on_exit/on_timeout)                         │
├─────────────────────────────────────────────────────────────┤
│  Safety Monitor · Cost Tracker · Budget Enforcer             │
│  Degradation Manager · Metrics Pipeline · Audit Log          │
├─────────────────────────────────────────────────────────────┤
│  Distributed Consensus (Raft TCP Transport)                  │
│  HTTP Server · Auth · Rate Limiter                           │
│  Chaos Engine (10 fault scenarios)                           │
├─────────────────────────────────────────────────────────────┤
│  AI-Native: Drift Detection · Predictive Degradation ·      │
│             Run Recommender · Skill Emergence · Auto-Fix     │
├─────────────────────────────────────────────────────────────┤
│  Docker · CI/CD · Makefile · Prometheus · Grafana            │
└─────────────────────────────────────────────────────────────┘
```

## Project Status

| Metric | Value |
|--------|-------|
| **Version** | 1.3.0 |
| **Modules** | 49 Python modules |
| **Tests** | 333 (100% passing) |
| **CLI Commands** | 46 |
| **Profiles** | 4 (content, software, research, design) |
| **Plugin Types** | 9 |
| **Chaos Scenarios** | 10 |
| **Forecast Methods** | 3 (MA, LR, Holt-Winters) |
| **Roadmap** | ✅ 100% complete |

## Next Steps

- [Getting Started](getting-started/installation.md)
- [CLI Commands](guide/cli.md)
- [Plugin Ecosystem](guide/plugin-ecosystem.md)
- [AI-Native Features](guide/ai-native.md)
- [API Reference](api/engine.md)

## License

MIT License — see [LICENSE](license.md) for details.
