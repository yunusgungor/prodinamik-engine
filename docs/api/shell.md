# Interactive Shell

Prodinamik Engine v1.1 — Interactive Shell (REPL)

A readline-based interactive command shell with tab completion, history,
and colored output. Run via `prodinamik shell` or directly.

Commands:
  help [cmd]          Show help
  run <profile> <title>      Create a new run
  list [--archived]          List all runs
  transition <slug> <state>  Transition a run
  debug <slug>               Show run details
  config                     Show config
  timeline <slug>            Show event timeline
  event <slug> <id>          Show event details
  state <slug> [id]          Show run state
  why <slug> <id>            5-Why analysis
  cost <slug>                Cost timeline
  health [slug]              Health report
  summary <slug>             Run summary
  benchmark [runs]           Run benchmarks
  status                     Engine status
  exit / quit / Ctrl+D       Exit shell

**Module:** `engine.shell.py`

## Classes

### `Color`

Minimal ANSI color helpers — auto-disable if not a tty

**Methods:**

- `disable(cls)`
- `_c(cls, code, text)`
- `green(cls, text)`
- `yellow(cls, text)`
- `red(cls, text)`
- `blue(cls, text)`
- `cyan(cls, text)`
- `bold(cls, text)`
- `dim(cls, text)`
- `icon(cls, emoji, text)`

### `Completer`

Readline tab completer for shell commands

**Methods:**

- `__init__(engine)`
- `_refresh_caches()`
  — Refresh slug/state/profile caches
- `complete(text, state)`
  — Readline completer: returns next match
- `update_matches(text, line, begidx, endidx)`
  — Build completion candidates

### `ProdinamikShell`

Interactive REPL for Prodinamik Engine

**Methods:**

- `__init__(engine, config_path)`
- `_setup_readline()`
  — Configure readline with history and completion
- `_get_debug_cli()`
  — Lazy-init DebugCLI with engine components
- `run()`
  — Main REPL loop
- `_dispatch(line)`
  — Parse and route a command line
- `_cmd_help(args)`
  — Show help for commands
- `_cmd_run(args)`
  — Create a new run
- `_cmd_list(args)`
  — List runs
- `_cmd_transition(args)`
  — Transition a run
- `_cmd_debug(args)`
  — Show run details
- `_cmd_config(args)`
  — Show config
- `_cmd_timeline(args)`
  — Show event timeline (via DebugCLI)
- `_cmd_event(args)`
  — Show event details
- `_cmd_state(args)`
  — Show run state
- `_cmd_why(args)`
  — 5-Why analysis
- `_cmd_cost(args)`
  — Cost timeline
- `_cmd_health(args)`
  — Health report
- `_cmd_summary(args)`
  — Run summary
- `_cmd_benchmark(args)`
  — Run benchmarks
- `_cmd_status(args)`
  — Engine status overview
- `_degradation_badge(level)`
- `_get_event_store(slug)`
  — Get event store for a slug
- `_print_benchmark(result)`
  — Print benchmark results nicely
- `_exit()`
  — Clean shutdown

## Functions

### `run_shell(engine, config_path)`

Start the interactive shell
