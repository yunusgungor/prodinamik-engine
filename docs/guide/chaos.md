# Chaos Engineering Guide

Prodinamik Engine v1.1 — Chaos Engineering Framework

Chaos engineering is the discipline of experimenting on a system to build confidence in its capability to withstand turbulent conditions. The Prodinamik Engine includes a built-in chaos engineering framework that injects controlled faults, monitors system health, and verifies self-healing behavior.

**Source modules:** `engine/chaos.py` (688 lines), `engine/degradation.py` (358 lines)

---

## Overview

The chaos framework tests the engine's resilience across three dimensions:

1. **Infrastructure faults** — network partitions, disk failures, memory pressure, CPU spikes
2. **Data corruption** — WAL corruption, file corruption, event flooding
3. **Degradation transitions** — FULL → DEGRADED → SURVIVAL lifecycle

Each scenario captures health snapshots **before**, **during**, and **after** fault injection, measures recovery time, and validates self-healing.

---

## Available Scenarios

| Scenario | Fault Type | Dangerous | Default Duration | Description |
|----------|-----------|-----------|------------------|-------------|
| `network-partition` | NETWORK_PARTITION | No | 5s | Block outbound TCP ports 80/443 via iptables |
| `network-latency` | NETWORK_LATENCY | No | 5s | Add 100ms artificial latency via tc |
| `disk-full` | DISK_FULL | Yes | 5s | Write 50MB temporary file to data directory |
| `disk-corruption` | DISK_CORRUPTION | Yes | 3s | Corrupt 2 random JSON/log files by byte mutation |
| `memory-pressure` | MEMORY_PRESSURE | Yes | 3s | Allocate 200MB list to trigger OOM pressure |
| `cpu-spike` | CPU_SPIKE | No | 5s | Spawn 4 threads burning SHA-256 hashes |
| `random-crash` | RANDOM_CRASH | Yes | 2s | Raise RuntimeError in a daemon thread |
| `degraded-mode` | DEGRADED_MODE | No | 8s | Force FULL→DEGRADED→SURVIVAL→FULL transitions |
| `wal-corruption` | WAL_CORRUPTION | Yes | 5s | Corrupt WAL files and verify recovery |
| `event-flood` | EVENT_FLOOD | No | 3s | Create up to 20 runs rapidly (5/sec) |

> **Dangerous scenarios** (`dangerous=True`) may cause data loss, service disruption, or resource exhaustion. Run only in isolated test/staging environments.

---

## Getting Started

### Programmatic Usage

```python
from engine.chaos import ChaosEngine
from engine.engine import ProdinamikEngine

engine = ProdinamikEngine()  # or your engine instance
chaos = ChaosEngine(engine=engine, base_path="./data/chaos")

# Run a single scenario
result = chaos.run_scenario("network-partition")
print(result.report())
```

### CLI Usage

```bash
# List available scenarios
prodinamik chaos list

# Run a specific scenario
prodinamik chaos run network-partition

# Run a scenario with custom duration
prodinamik chaos run cpu-spike --duration 10

# Run all non-dangerous scenarios
prodinamik chaos run-all

# Run all scenarios (including dangerous)
prodinamik chaos run-all --dangerous

# View report
prodinamik chaos report
```

Example CLI output for `prodinamik chaos list`:

```
Available Chaos Scenarios:
  cpu-spike          Generate CPU load via subprocess
  degraded-mode      Force FULL→DEGRADED→SURVIVAL transitions
  disk-corruption    Corrupt random WAL/snapshot files ⚠️ DANGEROUS
  disk-full          Simulate disk full by filling data directory ⚠️ DANGEROUS
  event-flood        Rapid event injection to test throughput
  memory-pressure    Allocate memory to trigger pressure ⚠️ DANGEROUS
  network-latency    Add artificial network latency via tc
  network-partition  Simulate network failure by blocking ports
  random-crash       Simulate random process crash ⚠️ DANGEROUS
  wal-corruption     Corrupt WAL entries and verify recovery ⚠️ DANGEROUS
```

---

## Scenario Lifecycle

Every scenario follows a 6-phase execution:

```
Phase 1: Capture health BEFORE
    └─ health_before = engine.health_snapshot

Phase 2: Inject fault
    └─ handler(scenario_duration)
    └─ fault_type → handler mapping

Phase 3: Wait & capture health DURING
    └─ time.sleep(min(1, duration/3))
    └─ health_during = engine.health_snapshot

Phase 4: Wait for recovery window
    └─ time.sleep(scenario_duration)

Phase 5: Capture health AFTER
    └─ health_after = engine.health_snapshot

Phase 6: Evaluate
    └─ system_survived = _check_survival()
    └─ self_healed = _check_self_healing()
    └─ Save result to disk
```

---

## ScenarioResult

```python
@dataclass
class ScenarioResult:
    scenario_name: str
    fault_type: str
    started_at: str
    duration_seconds: float
    fault_injected: bool
    system_survived: bool
    self_healed: bool
    recovery_time_seconds: float
    health_before: dict
    health_during: dict
    health_after: dict
    events_logged: int
    errors: List[str]
```

### Pass/Fail Criteria

A scenario **passes** when:

```
passed() = system_survived and (self_healed or no errors)
```

- `system_survived` — engine health snapshot shows `available=True` and `health_score >= 0`
- `self_healed` — degradation level did not worsen permanently AND health score did not drop catastrophically

### Report Format

```python
result = chaos.run_scenario("disk-full")
print(result.report())
```

Output:

```
==================================================
  Chaos: disk-full (disk-full)
  Status: ✅ PASS
  Duration: 5.2s
  Fault injected: ✅
  System survived: ✅
  Self-healed: ✅
  Recovery time: 5.8s
  Events logged: 42
==================================================
```

---

## Fault Injection Details

### Network Partition (`_fault_network_partition`)

```python
# Blocks HTTP(S) outbound via iptables
subprocess.run(["iptables", "-A", "OUTPUT", "-p", "tcp",
                "--dport", "80,443", "-j", "DROP"])
# Auto-restores after duration via daemon thread
```

**Fallback:** If iptables is unavailable, simply sleeps for `duration` seconds.

### Network Latency (`_fault_network_latency`)

```python
# Adds 100ms latency on loopback via tc
subprocess.run(["tc", "qdisc", "add", "dev", "lo", "root",
                "netem", "delay", "100ms"])
```

### Disk Full (`_fault_disk_full`)

```python
# Writes 50MB file to base_path/fill/
with open(large_file, "wb") as f:
    f.write(os.urandom(50 * 1024 * 1024))
```

### Disk Corruption (`_fault_disk_corruption`)

```python
# Corrupts random JSON/log files by mutating 5 random bytes
for _ in range(5):
    pos = random.randint(0, min(size - 1, 1000))
    data[pos] = random.randint(0, 255)
```

### Memory Pressure (`_fault_memory_pressure`)

```python
# Allocates 200MB
big_list = [0] * (200 * 1024 * 1024 // 8)
```

### CPU Spike (`_fault_cpu_spike`)

```python
# Burns CPU with SHA-256 on 4 threads
def burn_cpu():
    while not stop_event.is_set():
        _ = hashlib.sha256(os.urandom(1024)).hexdigest()
```

### Random Crash (`_fault_random_crash`)

```python
# Raises RuntimeError in daemon thread
def crash():
    raise RuntimeError("Simulated chaos crash")
```

### Degraded Mode (`_fault_degraded_mode`)

```python
# Forces engine through FULL→DEGRADED→SURVIVAL→FULL
deg.health_state = "DEGRADED"
time.sleep(2)
deg.health_state = "SURVIVAL"
time.sleep(2)
deg.health_state = "FULL"
```

### WAL Corruption (`_fault_wal_corruption`)

```python
# Finds WAL files or creates a fake one, then corrupts
wal_files = list(data_dir.rglob("*.wal")) + list(data_dir.rglob("wal*"))
for target in wal_files[:2]:
    self._corrupt_file(target)
```

### Event Flood (`_fault_event_flood`)

```python
# Creates runs rapidly
for i in range(n_runs):
    engine.create_run("chaos", f"flood-run-{i}", slug=f"chaos-flood-{i}")
    time.sleep(0.1)
```

---

## Self-Healing Verification

After fault injection, the framework checks two conditions:

### `_check_survival`

```python
def _check_survival(self, result) -> bool:
    after = result.health_after
    if not after or not after.get("available", True):
        return False
    score = after.get("health_score", 0)
    return score >= 0  # Any valid score means alive
```

### `_check_self_healing`

```python
def _check_self_healing(self, result) -> bool:
    # Degradation must not worsen permanently
    deg_before = before.get("degradation", "FULL")
    deg_after = after.get("degradation", "FULL")
    if deg_rank[deg_after] > deg_rank[deg_before] + 1:
        return False
    # Health score must not drop catastrophically
    if score_before > 50 and score_after < 10:
        return False
    return True
```

---

## Running All Scenarios

```python
# Non-dangerous only (default)
results = chaos.run_all(dangerous=False)

# All scenarios
results = chaos.run_all(dangerous=True)

for name, result in results.items():
    status = "✅" if result.passed() else "❌"
    print(f"{status} {name}: survived={result.system_survived}, "
          f"healed={result.self_healed}, recovery={result.recovery_time_seconds:.1f}s")
```

---

## Comprehensive Report

```python
# Full summary
print(chaos.report())

# Single scenario
print(chaos.report(scenario_name="cpu-spike"))
```

Report output:

```
=======================================================
  Prodinamik Chaos Engineering Report
=======================================================
  ✅ network-partition: survived=True, healed=True, recovery=5.1s
  ✅ network-latency: survived=True, healed=True, recovery=5.0s
  ❌ disk-full: survived=False, healed=False, recovery=0.0s
  ✅ cpu-spike: survived=True, healed=True, recovery=5.2s
  ✅ degraded-mode: survived=True, healed=True, recovery=8.3s
  ✅ event-flood: survived=True, healed=True, recovery=3.0s
───────────────────────────────────────────────────────
  Total: 6 | ✅ 5 passed | ❌ 1 failed
=======================================================
```

---

## Production Usage Considerations

### When to Run Chaos Experiments

| Environment | Frequency | Scenarios |
|-------------|-----------|-----------|
| CI/CD pipeline | Every merge | network-latency, cpu-spike, event-flood |
| Staging | Daily | All non-dangerous |
| Pre-production | Weekly | All scenarios |
| Production | Scheduled maintenance | network-latency, degraded-mode only |

### Safety Guidelines

1. **Never run dangerous scenarios on production** — disk-full, disk-corruption, memory-pressure, random-crash, and wal-corruption can cause permanent data loss
2. **Always have a recovery plan** — the framework auto-recovers most faults, but disk corruption may require manual WAL replay
3. **Start with short durations** — use the default durations first, then increase gradually
4. **Monitor real user traffic** — do not run chaos experiments during peak load

### Integration with Degradation Manager

The chaos framework works closely with `DegradationManager` (`engine/degradation.py`). The `degraded-mode` scenario specifically tests the 3-level degradation lifecycle:

- **FULL** — all features enabled, all caches active
- **DEGRADED** — T2/T3 validators disabled, remote adapters offline, only T1 validation + state tracking active
- **SURVIVAL** — all validators disabled, state tracking only, minimal functionality

---

## Recovery Procedures

### Automatic Recovery

Most fault handlers include automatic cleanup via daemon threads:

| Fault | Auto-Cleanup | Recovery Mechanism |
|-------|-------------|-------------------|
| network-partition | After `duration` seconds | `iptables -F OUTPUT` |
| network-latency | After `duration` seconds | `tc qdisc del dev lo root` |
| disk-full | After `duration` seconds | Deletes temporary fill file |
| memory-pressure | After `duration` seconds | Releases reference to allocated list |
| cpu-spike | After `duration` seconds | Sets stop event on burn threads |

### Manual Recovery

For scenarios without auto-cleanup:

```python
# After disk corruption — replay WAL
from engine.migration import MigrationManager
mgr = MigrationManager(engine)
mgr.replay_wal()

# After degraded mode — force recovery
engine.degradation.manual_recover()

# After event flood — clean up runs
for run in engine.list_runs():
    if "chaos-flood" in run.slug:
        run.delete()
```

### Post-Mortem Analysis

Each scenario result is persisted as JSON:

```bash
ls ./data/chaos/results/
# network-partition_1712345678.json
# cpu-spike_1712345679.json
# ...
```

```python
# Load and analyze
import json
from pathlib import Path
result = json.loads(
    Path("./data/chaos/results/cpu-spike_1712345679.json").read_text()
)
print(f"Health before: {result['health_before']}")
print(f"Health after: {result['health_after']}")
```

---

## Extending Chaos Scenarios

To add a custom fault scenario:

1. Add a new `FaultType` enum value
2. Add a scenario definition to `ChaosEngine.SCENARIOS`
3. Implement `_fault_<name>` method with injection + cleanup logic
4. Register the handler in `_fault_handlers` dict

```python
class FaultType(Enum):
    MY_CUSTOM_FAULT = "my-custom-fault"

# In ChaosEngine.__init__:
self._fault_handlers[FaultType.MY_CUSTOM_FAULT] = self._fault_my_custom

# Implement
def _fault_my_custom(self, duration: int) -> bool:
    try:
        # Inject fault
        ...
        # Schedule cleanup
        threading.Thread(target=..., args=(duration,), daemon=True).start()
        return True
    except Exception as e:
        self._errors.append(f"my-custom: {e}")
        return False
```

---

## Reference: CLI Commands

```bash
prodinamik chaos list                          # List all scenarios
prodinamik chaos run <scenario>                # Run one scenario
prodinamik chaos run <scenario> --duration 10  # Custom duration
prodinamik chaos run-all                       # All non-dangerous
prodinamik chaos run-all --dangerous           # All scenarios
prodinamik chaos report                        # Summary report
prodinamik chaos report --scenario cpu-spike   # Single scenario
```

---

## Reference: Key Functions

| Function | File | Description |
|----------|------|-------------|
| `ChaosEngine.run_scenario()` | `chaos.py:207` | Execute one fault scenario |
| `ChaosEngine.run_all()` | `chaos.py:270` | Execute all scenarios |
| `ChaosEngine.list_scenarios()` | `chaos.py:194` | List available scenarios |
| `ChaosEngine.report()` | `chaos.py:286` | Generate report |
| `run_chaos_scenario()` | `chaos.py:673` | CLI entry point |
| `list_chaos_scenarios()` | `chaos.py:679` | CLI list entry point |
| `chaos_report()` | `chaos.py:685` | CLI report entry point |

Related modules: `engine.degradation.py` (degradation levels and health checks), `engine.audit.py` (event logging).
