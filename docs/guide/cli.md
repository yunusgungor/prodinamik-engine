# CLI Commands

The `prodinamik` CLI provides **36 commands** organized into logical groups.

## Global Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable debug logging |
| `-c, --config PATH` | Config file path |
| `--help` | Show help message |

## Run Management

```bash
prodinamik run <profile> <title>          # Create a new run
prodinamik list                           # List all runs
prodinamik transition <slug> <state>     # Transition to new state
prodinamik debug <slug>                  # Show run details
prodinamik archive <slug>                # Archive a completed run
```

## Developer Experience

```bash
prodinamik shell                          # Interactive REPL
prodinamik new profile <name>             # Generate a profile scaffold
prodinamik new project <name>             # Generate a project scaffold
prodinamik benchmark [runs]              # Run performance benchmarks
prodinamik completion bash|zsh           # Generate shell completion
```

## Observability

```bash
prodinamik dashboard                      # Health dashboard
prodinamik dashboard --compact            # Compact view
prodinamik dashboard --html --output f.html  # HTML export
prodinamik metrics --prometheus           # Prometheus metrics
prodinamik audit query [type]             # Query audit log
prodinamik audit stats                    # Audit statistics
prodinamik audit compact                  # Compact old entries
```

## Security

```bash
prodinamik auth create <name> [--role]    # Create API key
prodinamik auth list                      # List API keys
prodinamik auth revoke <id>              # Revoke API key
prodinamik auth info <id>                # Show key details
```

## HTTP Server

```bash
prodinamik serve [--port PORT]            # Start HTTP server
prodinamik serve --port 8080 --bind 0.0.0.0  # Public server
```

## Raft Cluster

```bash
prodinamik raft status                    # Cluster health
prodinamik raft peers <ids>              # Register peers
prodinamik raft elect                     # Force leader election
```

## Chaos Engineering

```bash
prodinamik chaos list                     # List scenarios
prodinamik chaos run <scenario> [--dangerous]  # Run fault scenario
prodinamik chaos report [--scenario]      # View results
```

## Monitoring & Alerts

```bash
prodinamik alert send <level> <title>     # Send alert
prodinamik alert test [--channel]         # Test channel
prodinamik alert recent [--limit]         # Recent alerts
prodinamik alert status                   # Alert manager status
```

## Configuration

```bash
prodinamik config                         # Show current config
prodinamik validate <profile_path>       # Validate profile YAML
prodinamik version                        # Show version
```
