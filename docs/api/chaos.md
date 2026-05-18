# Chaos Engine

Prodinamik Engine v1.1 — Chaos Engineering Framework

Fault injection, scenario execution, and self-healing verification.
Built for testing degradation, recovery, and resilience.

Scenarios:
  - network-partition:    Simulate network failure
  - network-latency:      Add artificial latency
  - disk-full:            Simulate disk full condition
  - disk-corruption:      Corrupt WAL/snapshot files
  - memory-pressure:      Simulate memory exhaustion
  - cpu-spike:            Generate CPU load
  - random-crash:         SIGKILL simulation
  - degraded-mode:        Trigger FULL→DEGRADED→SURVIVAL transitions
  - wal-corruption:       Manually corrupt WAL entries
  - event-flood:          Rapid event injection

Usage:
    chaos = ChaosEngine(engine, base_path)
    result = chaos.run_scenario("disk-full")
    print(result.report())

**Module:** `engine.chaos.py`

## Classes

### `FaultType`(Enum)

### `ScenarioResult`

Result of a single chaos scenario run

**Methods:**

- `passed()`
  — Scenario passes if system survived and either healed or no critical damage
- `report()`

### `ChaosEngine`

Chaos engineering framework for Prodinamik Engine.

Injects faults, monitors system health, and verifies self-healing.

**Methods:**

- `__init__(engine, base_path)`
- `list_scenarios()`
  — List all available chaos scenarios
- `run_scenario(scenario_name, duration)`
  — Run a single chaos scenario.
- `run_all(dangerous)`
  — Run all scenarios. If dangerous=False, skip dangerous ones.
- `report(scenario_name)`
  — Generate report of all results or a single scenario
- `_fault_network_partition(duration)`
  — Simulate network partition by blocking outbound connections
- `_restore_network(delay)`
  — Restore network after delay
- `_fault_network_latency(duration)`
  — Add artificial network latency
- `_restore_latency(delay)`
- `_fault_disk_full(duration)`
  — Simulate disk full by writing a large file
- `_cleanup_disk_fill(delay)`
- `_fault_disk_corruption(duration)`
  — Corrupt random files in data directory
- `_corrupt_file(path)`
  — Corrupt a file by replacing random bytes
- `_fault_memory_pressure(duration)`
  — Allocate memory to simulate pressure
- `_release_memory(delay, data)`
- `_fault_cpu_spike(duration)`
  — Generate CPU load
- `_stop_cpu_burn(delay, event)`
- `_fault_random_crash(duration)`
  — Simulate crash by raising an exception in a thread
- `_fault_degraded_mode(duration)`
  — Force degradation transitions
- `_fault_wal_corruption(duration)`
  — Corrupt WAL entries and verify recovery
- `_fault_event_flood(duration)`
  — Rapid event injection
- `_capture_health()`
  — Capture current engine health snapshot
- `_check_survival(result)`
  — Check if engine survived the fault
- `_check_self_healing(result)`
  — Check if system recovered to acceptable state
- `_save_result(result)`
  — Save result to disk
- `_load_result(scenario_name)`
  — Load most recent result for a scenario

## Functions

### `run_chaos_scenario(engine, scenario_name, duration)`

Entry point for CLI

### `list_chaos_scenarios()`

Entry point for CLI list

### `chaos_report(engine)`

Entry point for CLI report
