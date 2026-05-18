# Prodinamik Engine

**Product-Agnostic Pipeline Engine** — Formal state machine, multi-tier validation, event sourcing, cost tracking, and graceful degradation for multi-profile production pipelines.

```bash
pip install prodinamik-engine
prodinamik run content "RISC-V timing closure rehberi"
prodinamik list
prodinamik debug flux-v1-release
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     CLI (prodinamik)                  │
├─────────────────────────────────────────────────────┤
│  Registry ──► Profiles ──► Run Manager ──► Event Store│
│                  │                                      │
│            ┌─────┴──────┐                          │
│        Validators   Adapters                       │
│            3-Tier    Circuit Breaker                │
│            Cache      Retry · Fallback              │
│            Timeout                                  │
├─────────────────────────────────────────────────────┤
│  Safety (EventBus · Invariants · Health Score)       │
│  Degradation (FULL → DEGRADED → SURVIVAL)           │
│  Cost + Budget (4-dim · T0/T1 · 3σ Anomaly)         │
│  Raft Consensus (Leader · CRDT · Offline Ops)        │
└─────────────────────────────────────────────────────┘
```

## Quickstart

```bash
# Install
pip install -e .

# Create a run
prodinamik run content "RISC-V timing closure"
# ✅ Run created: Slug=risc-v-timing-closure, State=captured

# List runs
prodinamik list
# 📋 Runs (1): 🔄 risc-v-timing-closure — RISC-V timing closure [captured]

# Transition state
prodinamik transition risc-v-timing-closure idea_review
# ✅ risc-v-timing-closure: → idea_review

# Debug a run
prodinamik debug risc-v-timing-closure

# Show config
prodinamik config

# Validate a custom profile
prodinamik validate my_profiles/hardware.py

# Version
prodinamik version
```

## Built-in Profiles

| Profile | States | Transitions | Validators | Use Case |
|---------|--------|-------------|------------|----------|
| **content** | 9 | 11 | SlopScan, Length, Schema | Blog/newsletter pipeline |
| **software** | 7 | 10 | Spec, Build, Test, Lint | dev-cycle, open-source |
| **research** | 10 | 15 | Scope, Citation, Method, Stats | Academic papers |
| **design** | 8 | 13 | Brief, Research, A11Y, DS, RWD, IX | UI/UX workflow |

## Configuration

`prodinamik.yaml` in project root or `~/.config/prodinamik/config.yaml`:

```yaml
data_dir: ".hermes"
log:
  level: "INFO"
  format: "text"
budget:
  soft_limit_usd: 1.0
  hard_limit_usd: 5.0
```

Environment overrides: `PRODINAMIK_LOG_LEVEL=DEBUG`, `PRODINAMIK_BUDGET_HARD=10.0`.

## Key Concepts

### State Machine
Each profile defines a formal state machine in YAML with compile-time validation. Supports:
- **State types:** initial, intermediate, terminal, error
- **Transition types:** reversible, compensable, irreversible
- **Cycle detection** (Johnson's algorithm)
- **Reachability analysis** (BFS)
- **LTL constraints** (temporal logic)
- **Reentry limits, timeouts, reminders**

### 3-Tier Validator Pipeline
```
T1 (fail-fast) → T2 (parallel) → T3 (sequential)
```
Content-addressable cache + degradation-aware policy + per-validator timeout.

### Degradation
```
FULL ──(LLM error)──► DEGRADED ──(disk >95%)──► SURVIVAL
  ▲                      │                          │
  └────(recover)─────────┘──────(manual)────────────┘
```

### Event Sourcing
Append-only event log with type-based TTL (7d–∞), compaction (10→1 summary), and cost query.

## Development

```bash
# Install dev deps
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Validate profiles
prodinamik validate profiles/content.py

# Debug CLI (interactive mode coming in v1.1)
python -c "from engine.debug_cli import DebugCLI; ..."
```

## License

MIT — Yunus Güngör
