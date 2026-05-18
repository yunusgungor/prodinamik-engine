# CLI Commands

The `prodinamik` CLI provides **46 commands** organized into logical groups.

## Global Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable debug logging |
| `-c, --config PATH` | Config file path |
| `--help` | Show help message |

## Run Management

```bash
prodinamik run <profile> <title>        # Start a new run
prodinamik list                          # List all runs (active/completed/archived)
prodinamik transition <slug> <state>     # Transition a run to a new state
prodinamik debug <slug>                  # Show detailed run information
```

**Output example:**
```
$ prodinamik list
📋 Active Runs:
  flux-v1-release    [software · approved]  4m ago
  blog-post          [content · drafting]   12m ago
```

## Configuration & Validation

```bash
prodinamik config                        # Show current configuration
prodinamik validate <profile_path>       # Validate a profile YAML
```

## Runtime & DevEx

```bash
prodinamik daemon                        # Start async runtime daemon
prodinamik shell                         # Interactive REPL
prodinamik new profile <name>            # Generate a new profile scaffold
prodinamik new project <name>            # Generate a new project scaffold
prodinamik benchmark [runs]              # Run performance benchmarks
prodinamik completion bash|zsh           # Generate shell completion script
```

## Dashboard & Observability

```bash
prodinamik dashboard                     # Show health dashboard
prodinamik dashboard --compact           # Compact mode
prodinamik dashboard --html              # Export as HTML
prodinamik metrics                       # Show current metrics
prodinamik metrics --prometheus          # Export Prometheus format
```

## Audit Log

```bash
prodinamik audit query [event_type]      # Query audit log entries
prodinamik audit query --since 2026-01-01 --limit 50
prodinamik audit stats                   # Show audit log statistics
prodinamik audit compact                 # Compact entries older than 7 days
```

## Authentication

```bash
prodinamik auth create <name>            # Create a new API key
prodinamik auth list                     # List all API keys
prodinamik auth revoke <id>              # Revoke an API key
prodinamik auth info <id>                # Show key details
```

## HTTP Server

```bash
prodinamik serve                         # Start HTTP server (port 8080)
prodinamik serve --port 9000             # Custom port
```

## Raft Cluster

```bash
prodinamik raft status                   # Show Raft cluster health
prodinamik raft peers <ids>              # Register peers (space-separated)
prodinamik raft elect                    # Force leader election
```

## Chaos Engineering

```bash
prodinamik chaos run <scenario>          # Run a chaos scenario
prodinamik chaos run network-partition --duration 5
prodinamik chaos list                    # List all available scenarios
prodinamik chaos report                  # Show chaos test report
```

**Available scenarios:** `network-partition`, `latency-injection`, `disk-crash`, `disk-full`, `memory-pressure`, `cpu-spike`, `random-crash`, `degraded-mode`, `wal-corruption`, `event-flood`

## Alerting

```bash
prodinamik alert send <level> <title>    # Send an alert
prodinamik alert send warning "Budget near limit" -m "usage=0.85"
prodinamik alert test [--channel]        # Test alert channel
prodinamik alert recent [--limit]        # Show recent alerts
prodinamik alert status                  # Show alert manager status
```

**Alert levels:** `info`, `warning`, `critical`

## Plugin Ecosystem

```bash
prodinamik plugin list                   # List all registered plugins
prodinamik plugin list --enabled         # Show only enabled plugins
prodinamik plugin list --type validator  # Filter by plugin type
prodinamik plugin list --json            # JSON output
prodinamik plugin discover               # Scan for new plugins
prodinamik plugin enable <id>            # Enable a plugin
prodinamik plugin disable <id>           # Disable a plugin
prodinamik plugin install <id> [--source] # Install a plugin
prodinamik plugin uninstall <id>         # Uninstall a plugin
prodinamik plugin info <id>              # Show plugin details
prodinamik plugin info <id> --json       # JSON output
prodinamik plugin reload                 # Reload all plugins
prodinamik plugin reload --plugin-id x   # Reload specific plugin
prodinamik plugin health                 # Run health checks on all plugins
```

**Plugin types:** `validator`, `adapter`, `hook`, `tool`, `profile`, `store`, `ui`, `integration`, `other`

## AI-Native Features

```bash
prodinamik ai detect                     # AI drift detection report
prodinamik ai predict                    # Degradation forecast (all metrics)
prodinamik ai predict --metric latency_ms # Specific metric forecast
prodinamik ai predict --horizon 120      # Custom forecast horizon
prodinamik ai recommend <current_state>  # Next state recommendation
prodinamik ai recommend drafting --profile software
prodinamik ai status                     # Show AI features status
```

## Version

```bash
prodinamik version                       # Show engine version
```

---

## Full Command Summary

| # | Command | Group | Description |
|---|---------|-------|-------------|
| 1 | `run` | Core | Start a new run |
| 2 | `list` | Core | List all runs |
| 3 | `transition` | Core | Transition run state |
| 4 | `debug` | Core | Show run details |
| 5 | `config` | Config | Show configuration |
| 6 | `validate` | Config | Validate profile |
| 7 | `daemon` | Runtime | Start async daemon |
| 8 | `shell` | Runtime | Interactive REPL |
| 9 | `new profile` | DevEx | Generate profile scaffold |
| 10 | `new project` | DevEx | Generate project scaffold |
| 11 | `benchmark` | DevEx | Performance benchmarks |
| 12 | `completion` | DevEx | Shell completion scripts |
| 13 | `dashboard` | Monitor | Health dashboard |
| 14 | `metrics` | Monitor | Metrics export |
| 15 | `audit query` | Audit | Query audit log |
| 16 | `audit stats` | Audit | Audit statistics |
| 17 | `audit compact` | Audit | Compact old entries |
| 18 | `auth create` | Auth | Create API key |
| 19 | `auth list` | Auth | List API keys |
| 20 | `auth revoke` | Auth | Revoke API key |
| 21 | `auth info` | Auth | Show key details |
| 22 | `serve` | Server | HTTP server |
| 23 | `raft status` | Raft | Cluster health |
| 24 | `raft peers` | Raft | Register peers |
| 25 | `raft elect` | Raft | Force election |
| 26 | `chaos run` | Chaos | Run chaos scenario |
| 27 | `chaos list` | Chaos | List scenarios |
| 28 | `chaos report` | Chaos | Chaos test report |
| 29 | `alert send` | Alert | Send alert |
| 30 | `alert test` | Alert | Test channel |
| 31 | `alert recent` | Alert | Recent alerts |
| 32 | `alert status` | Alert | Alert manager status |
| 33 | `plugin list` | Plugin | List plugins |
| 34 | `plugin discover` | Plugin | Scan for plugins |
| 35 | `plugin enable` | Plugin | Enable plugin |
| 36 | `plugin disable` | Plugin | Disable plugin |
| 37 | `plugin install` | Plugin | Install plugin |
| 38 | `plugin uninstall` | Plugin | Uninstall plugin |
| 39 | `plugin info` | Plugin | Plugin details |
| 40 | `plugin reload` | Plugin | Reload plugins |
| 41 | `plugin health` | Plugin | Health checks |
| 42 | `ai detect` | AI | Drift detection report |
| 43 | `ai predict` | AI | Degradation forecast |
| 44 | `ai recommend` | AI | State recommendation |
| 45 | `ai status` | AI | AI features status |
| 46 | `version` | System | Show version |
