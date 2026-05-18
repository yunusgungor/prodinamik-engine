# CLI Entry Point

Prodinamik Engine v1.1 — CLI Entry Point (32 commands)

Usage:
    prodinamik run <profile> <title>        # Start new run
    prodinamik list                          # List all runs
    prodinamik transition <slug> <state>     # State transition
    prodinamik debug <slug>                  # Show run details
    prodinamik config                        # Show config
    prodinamik validate <profile_path>       # Validate profile
    prodinamik daemon                        # Start daemon (async runtime)
    prodinamik shell                         # Interactive REPL
    prodinamik new profile <name>            # Generate a new profile
    prodinamik new project <name>            # Generate a new project
    prodinamik benchmark [runs]              # Run performance benchmarks
    prodinamik completion bash|zsh           # Generate shell completion script
    prodinamik dashboard [--compact|--html]  # Show health dashboard
    prodinamik metrics [--prometheus]        # Show/export engine metrics
    prodinamik audit query [type]            # Query audit log
    prodinamik audit stats                   # Audit log statistics
    prodinamik audit compact                 # Compact old audit entries
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
    prodinamik chaos report                  # Show chaos test report
    prodinamik version                       # Show version

**Module:** `engine.cli.py`

## Functions

### `get_config()`

### `get_engine()`

### `cli(verbose, config)`

Prodinamik Engine — Product-Agnostic Pipeline Engine

### `run(profile, title, slug)`

Start a new run with the given PROFILE and TITLE

### `list(include_archived)`

List all runs

### `transition(slug, to_state)`

Transition a run to a new state

### `debug(slug)`

Show run details or engine status

### `config()`

Show current configuration

### `validate(profile_path)`

Validate a profile file

### `daemon()`

Start the async runtime daemon (blocking)

### `version()`

Show version

### `shell(no_color)`

Start interactive REPL shell

### `new()`

Scaffold new profiles and projects

### `profile(name, output)`

Generate a new profile module

### `project(name, output)`

Generate a new project scaffold

### `benchmark(runs)`

Run performance benchmarks

### `completion(shell_type)`

Generate shell completion script

### `dashboard(compact, no_color, html, output)`

Show engine health dashboard

### `metrics(prometheus, output)`

Show or export engine metrics

### `audit()`

Query and manage audit log

### `query(event_type, since, until, limit, as_json)`

Query audit log entries

### `stats()`

Show audit log statistics

### `compact(older_than)`

Compact old audit entries

### `auth()`

Manage API keys and authentication

### `create_key(name, role, expires)`

Create a new API key

### `list_keys()`

List all API keys

### `revoke(key_id)`

Revoke an API key

### `key_info(key_id)`

Show API key details

### `serve(host, port, blocking)`

Start HTTP server with /metrics, /healthz, /api/v1

### `raft()`

Manage Raft consensus cluster

### `raft_status()`

Show Raft cluster status

### `raft_peers(peer_ids)`

Register peer nodes (space-separated IDs)

### `raft_elect()`

Force leader election

### `chaos()`

Chaos engineering: fault injection and resilience testing

### `chaos_run(scenario, duration, dangerous)`

Run a chaos scenario

Scenarios: network-partition, network-latency, disk-full, disk-corruption,
memory-pressure, cpu-spike, random-crash, degraded-mode, wal-corruption, event-flood

### `chaos_list()`

List all available chaos scenarios

### `chaos_report(scenario)`

Show chaos test report

### `alert()`

Send and manage alerts to Slack/Telegram

### `send(level, title, message, metric)`

Send an alert to configured channels

### `test(channel)`

Send a test alert to verify channel configuration

### `recent(limit, min_level)`

Show recent alerts

### `status()`

Show alert manager configuration and stats
