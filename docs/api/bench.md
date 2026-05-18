# Benchmarks

Prodinamik Engine v1.1 — Performance Benchmark Suite

Run via `prodinamik benchmark [runs]` or `python -m engine.bench`

Measures:
- State machine parsing throughput
- Run creation latency
- Transition latency
- Validator pipeline throughput
- WAL write throughput
- Event store append throughput

**Module:** `engine.bench.py`

## Classes

### `BenchmarkResult`

Single benchmark metric

**Methods:**

- `avg()`
- `median()`
- `min()`
- `max()`
- `p95()`
- `stddev()`
- `summary()`
- `__str__()`

### `Benchmark`

Compact benchmark runner

**Methods:**

- `__init__(name, iterations)`
- `measure(name, fn)`
  — Time a function call over N iterations
- `report()`
  — Return structured report
- `print()`
  — Pretty-print results

### `BenchProfile`(ProductProfile)

**Methods:**

- `validators()`
- `adapters()`
- `budget()`

## Functions

### `bench_state_machine_parsing(iterations)`

Time state machine YAML parsing

### `bench_run_creation(engine, iterations)`

Time run creation

### `bench_state_transition(engine, slug, iterations)`

Time state transitions

### `bench_event_store_append(iterations)`

Time event store appends

### `bench_wal_write(iterations)`

Time WAL write throughput

### `bench_profile_discovery(iterations)`

Time profile registry discovery

### `bench_async_engine_start_stop(iterations)`

Time async engine start/stop cycle

### `run_all_benchmarks(engine, iterations)`

Run all benchmark suites

### `run_benchmark(engine, runs)`

Entry point for CLI benchmark command
