# Quickstart

Welcome to **Prodinamik Engine** — a product-agnostic pipeline engine with
formal state machines, validators, event sourcing, cost tracking, and
graceful degradation.

This guide gets you from zero to a running pipeline in under 5 minutes.

---

## What is a State Machine?

A state machine is a mathematical model of computation that can be in exactly
one of a finite number of *states* at any given time. Transitions between
states are governed by deterministic rules: a transition fires when its
preconditions are met, moving the system from one state to the next. This
makes state machines ideal for modelling workflows, pipelines, and
lifecycles because the possible paths are explicit and verifiable.

In Prodinamik, each **profile** (e.g., "software", "content", "research")
defines its own state machine. States can be *initial* (entry point),
*intermediate* (work in progress), *terminal* (done), or *error* (blocked).
Transitions carry metadata such as type (reversible, compensable, irreversible),
conditions, and actions. The engine validates the state machine at compile
time — checking for reachability, dead-end cycles, missing transitions, and
proper termination — so you catch bugs before runtime.

---

## Core Concepts: Profile, Run, Transition

### Profile

A **Profile** is a named, versioned collection of:

- A **state machine** (YAML) that defines states and transitions
- **Validators** (T1/T2/T3) that check work at each stage
- **Adapters** that connect to external systems (GitHub, file, etc.)
- **Store schemas** that define run artifacts
- **Budget** constraints (cost, concurrency, storage)

Built-in profiles: `software`, `content`, `research`, `design`.

```python
from profiles.software import SoftwareProfile

profile = SoftwareProfile()
profile.initialize()
print(profile.name)        # "software"
print(profile.state_machine)  # StateMachine(...)
```

### Run

A **Run** is a single execution of a profile. Each run has:

- A **slug** (unique, URL-safe identifier)
- A **title** (human-readable)
- A **current state** (tracks position in the state machine)
- **Events** (ordered log of state transitions and actions)
- **Artifacts** (files produced during the run)

Runs are persisted to `.hermes/runs/active/{slug}/` with WAL (write-ahead
log) and atomic snapshots for crash safety.

### Transition

A **Transition** moves a run from one state to another. The engine validates:

1. The transition is defined in the profile's state machine
2. The source state is not terminal
3. No human approval is required (or it has been given)
4. Re-entry limits have not been exceeded
5. Any custom condition evaluates to `true`

Transitions are logged with timing and can be reversed for debugging.

---

## Step-by-Step: Create, List, Transition, Debug, Dashboard

### 1. Create a run

```bash
prodinamik run software "Implement FFT algorithm"
```

Expected output:

```
✅ Run created: implement-fft-algorithm (software profile)
   State: spec
   Next: prototyping → iteration → review → release
```

> 💡 The slug `implement-fft-algorithm` is auto-generated from the title.
> You can pass a custom slug with `--slug my-custom-slug`.

### 2. List runs

```bash
prodinamik list
```

Expected output:

```
Active runs:
  • implement-fft-algorithm [software] → spec (active)
```

Add `--archived` to include archived runs.

### 3. Transition state

```bash
prodinamik transition implement-fft-algorithm prototyping
```

Expected output:

```
✅ Transition: spec → prototyping
   Timing: 0.002s
```

Continue through the happy path:

```bash
prodinamik transition implement-fft-algorithm iteration
prodinamik transition implement-fft-algorithm review
prodinamik transition implement-fft-algorithm release
```

The software profile defines this lifecycle:

```
spec → prototyping → iteration → review → release
       ↕                ↕            ↕
     blocked ←──── iteration ←─── cancelled
```

### 4. Debug a run

```bash
prodinamik debug implement-fft-algorithm
```

Expected output:

```
📋 Run: implement-fft-algorithm
   Profile:  software
   State:    release (terminal)
   Status:   active
   Created:  2026-05-18T15:30:00
   Updated:  2026-05-18T15:30:12
   Events:
     • spec → prototyping  (0.001s)
     • prototyping → iteration  (0.002s)
     • iteration → review  (0.001s)
     • review → release  (0.002s)
   Artifacts: 2 files
```

### 5. View the dashboard

```bash
prodinamik dashboard
```

Renders a terminal ASCII dashboard with:

- **Thermal map** of health score, degradation, and budget
- **Run matrix** — all active runs grouped by profile
- **Degradation state** — FULL / DEGRADED / SURVIVAL indicator
- **Cost summary** — total, active, estimated daily
- **Recent alerts** — rolling log of warnings and errors

You can also render an HTML dashboard:

```python
from engine.dashboard import render_html_dashboard

html = render_html_dashboard(engine, metrics_snapshot={})
with open("dashboard.html", "w") as f:
    f.write(html)
```

### 6. Use the interactive shell

```bash
prodinamik shell
```

Inside the shell:

```
Prodinamik> list
Prodinamik> transition implement-fft-algorithm review
Prodinamik> debug implement-fft-algorithm
Prodinamik> dashboard
Prodinamik> help
Prodinamik> exit
```

### 7. Run the automated demo

```bash
pip install -e ".[dev]"
python scripts/demo.py
```

This walks through the entire lifecycle programmatically and prints
timing, metrics, and dashboard output.

---

## HTTP API Quickstart

Prodinamik ships with a REST HTTP server for remote control.

### Start the server

```bash
# Create an API key first
prodinamik auth create admin-bot --role admin
# Output: Key created: admin-bot-a1b2c3d4
# Key: pdmk_<48 hex chars>

# Start server on port 8080
prodinamik serve --port 8080
```

### Endpoints

```bash
# Health check
curl http://localhost:8080/healthz

# List all runs
curl -H "X-API-Key: pdmk_<key>" http://localhost:8080/api/v1/runs

# Create a run
curl -X POST -H "X-API-Key: pdmk_<key>" \
  -H "Content-Type: application/json" \
  -d '{"profile": "software", "title": "API Demo Run"}' \
  http://localhost:8080/api/v1/runs

# Transition a run
curl -X POST -H "X-API-Key: pdmk_<key>" \
  -H "Content-Type: application/json" \
  -d '{"to_state": "prototyping"}' \
  http://localhost:8080/api/v1/runs/<slug>/transition

# Get run details
curl -H "X-API-Key: pdmk_<key>" \
  http://localhost:8080/api/v1/runs/<slug>

# Metrics (Prometheus format)
curl http://localhost:8080/metrics
```

### Python client

```python
from engine.server import ProdinamikServer
from engine.auth import AuthManager

server = ProdinamikServer(engine, auth=AuthManager(), port=8080)
server.start()  # Blocks

# In another thread/process:
# curl http://localhost:8080/api/v1/runs
```

---

## Where to Go Next

| Topic | Resource |
|-------|----------|
| **Profiles** | `profiles/software.py`, `engine/profile.py` |
| **State machines** | `engine/state_machine.py`, `engine/sm_types.py` |
| **Run Manager** | `engine/run_manager.py` — CRUD + WAL + snapshots |
| **Dashboard** | `engine/dashboard.py` — terminal + HTML |
| **Metrics** | `engine/metrics.py` — Prometheus export |
| **Chaos engineering** | `prodinamik chaos list` |
| **CLI reference** | `prodinamik --help` |
| **Configuration** | `prodinamik.yaml` in project root |
| **Full API docs** | `python scripts/gen_api_docs.py` |

For questions, issues, or contributions, visit the repository at
[github.com/yunusgungor/prodinamik-engine](https://github.com/yunusgungor/prodinamik-engine).
