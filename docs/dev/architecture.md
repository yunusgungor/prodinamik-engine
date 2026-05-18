# Architecture

## High-Level Design

The Prodinamik Engine uses a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                             │
│  run · list · transition · debug · shell · new · bench      │
│  dashboard · metrics · audit · auth · serve · raft · chaos  │
├─────────────────────────────────────────────────────────────┤
│                      Application Layer                        │
│  Registry → Profiles → AsyncEngine → Run Manager             │
│  Validators (3-tier) · Adapters (circuit breaker)            │
│  Hooks (on_enter/on_exit/on_timeout)                        │
├─────────────────────────────────────────────────────────────┤
│                       Core Layer                              │
│  State Machine · Event Store · Safety Monitor                │
│  Cost Tracker · Budget Enforcer · Degradation Manager        │
├─────────────────────────────────────────────────────────────┤
│                     Infrastructure Layer                      │
│  Metrics Pipeline · Dashboard · Audit Log                    │
│  HTTP Server · Auth · Rate Limiter · Raft Cluster            │
│  Chaos Engine · Alert Manager                                │
├─────────────────────────────────────────────────────────────┤
│                       DevOps Layer                            │
│  Docker · CI/CD · Prometheus · Grafana · Makefile            │
└─────────────────────────────────────────────────────────────┘
```

## Core Concepts

### State Machine

Formal YAML-defined state machine with:
- 4 state types: `initial`, `intermediate`, `terminal`, `error`
- 3 transition types: `REVERSIBLE`, `COMPENSABLE`, `IRREVERSIBLE`
- Compile-time validation: dead cycles, unreachable states, reentry bounds
- LTL temporal logic constraints
- Per-state hooks: `on_enter`, `on_exit`, `on_timeout`

### 3-Tier Validator Pipeline

| Tier | Execution | Speed | Deterministic | Example |
|------|-----------|-------|---------------|---------|
| T1 | Sequential, fail-fast | <50ms | Yes | Schema validation, regex patterns |
| T2 | Parallel, independent | <5s | No | Rubric scoring, hallucination check |
| T3 | Sequential, dependent | <10s | No | Coverage threshold, final grade |

### Event Sourcing

Append-only event log with:
- Type-based TTL and compaction
- Replay capability
- Cost-aware events

### Graceful Degradation

| Level | Validators | Adapters | State Tracking |
|-------|------------|----------|----------------|
| FULL | All active | All active | ✅ |
| DEGRADED | T1 only | Cached only | ✅ |
| SURVIVAL | None | None | ✅ |

### Raft Consensus

Hybrid model combining:
- **Online**: Standard Raft consensus (Leader writes, Follower replicates)
- **Offline**: Optimistic local writes (pending log)
- **Reconnect**: 5-step sync (Raft sync → pending propose → CRDT merge → merge write → final state)

## Module Map

Engine modules (35 files) organized by phase:

| Phase | Module(s) | Lines |
|-------|-----------|-------|
| Core Foundation | state_machine, sm_types, sm_parser, profile, run_manager, validators, event_store | ~2,800 |
| Resilience | degradation, safety, cost, budget, migration | ~1,600 |
| Async Runtime | runtime, hooks | ~600 |
| Developer Exp. | shell, scaffold, bench, debug_cli, registry | ~1,200 |
| Observability | metrics, dashboard, audit | ~1,500 |
| Security | auth, ratelimit, server, raft (types/consensus/cluster) | ~2,100 |
| Chaos Eng. | chaos | ~800 |
| Monitoring | alert | ~400 |
| **Total** | **35 files** | **~11,000** |
