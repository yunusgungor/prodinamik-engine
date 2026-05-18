# Prodinamik Engine

> **Product-Agnostic Pipeline Engine** — Formal state machine, 3-tier validator pipeline, event sourcing, cost tracking, Raft consensus, and chaos engineering for multi-profile production pipelines.

[![Tests](https://github.com/yunusgungor/prodinamik-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/yunusgungor/prodinamik-engine/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Features

- **Formal State Machine** — YAML-defined states with LTL temporal logic, compile-time validation (dead cycles, unreachable states, reentry bounds)
- **3-Tier Validator Pipeline** — T1 deterministic (fail-fast) → T2 parallel (LLM) → T3 sequential (cross-ref)
- **Event Sourcing** — Append-only event store with type-based retention and replay
- **Cost Tracking** — Multi-dimensional (LLM, compute, storage, network) + budget enforcement (WARN→SLOW→STOP)
- **Graceful Degradation** — FULL → DEGRADED → SURVIVAL with auto-recovery
- **Async Runtime** — asyncio main loop, lifecycle hooks, timeout watcher, graceful shutdown
- **Raft Consensus** — Hybrid Raft+Offline+CRDT for distributed state management
- **Chaos Engineering** — 10 fault scenarios with self-healing verification
- **HTTP API** — RESTful API with API key auth, rate limiting, Prometheus metrics
- **4 Built-in Profiles** — content, software, research, design
- **Docker + CI/CD** — Multi-stage Dockerfile, GitHub Actions, Makefile

## Quick Start

```bash
# Install
pip install prodinamik-engine

# Create and manage runs
prodinamik run content "My blog post"
prodinamik list
prodinamik transition my-blog-post reviewing

# Interactive shell
prodinamik shell

# Health dashboard
prodinamik dashboard

# Start HTTP server
prodinamik serve --port 8080

# Chaos engineering
prodinamik chaos run cpu-spike --duration 2
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI (prodinamik) + Shell                 │
│  run · list · transition · debug · shell · new · bench     │
│  dashboard · metrics · audit · auth · serve · raft · chaos  │
├─────────────────────────────────────────────────────────────┤
│  Registry → Profiles → AsyncEngine → Run Manager             │
│  Validators (T1/T2/T3) · Adapters (Circuit Breaker)        │
│  Hooks (on_enter/on_exit/on_timeout)                        │
├─────────────────────────────────────────────────────────────┤
│  Event Store · Safety Monitor · Cost Tracker · Budget Enf.  │
│  Degradation Manager · Metrics Pipeline · Audit Log         │
├─────────────────────────────────────────────────────────────┤
│  Distributed Consensus (Raft + CRDT)                        │
│  HTTP Server · Auth · Rate Limiter                          │
│  Chaos Engine (10 fault scenarios)                          │
├─────────────────────────────────────────────────────────────┤
│  Docker · CI/CD · Makefile · Prometheus · Grafana            │
└─────────────────────────────────────────────────────────────┘
```

## License

MIT License — see [LICENSE](license.md) for details.
