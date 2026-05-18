# Interactive Shell (REPL)

**Module:** `engine.shell.py`

The interactive shell provides a readline-based REPL (Read-Eval-Print Loop) for
Prodinamik Engine. It supports tab completion, command history persistence, ANSI
colored output, and a full suite of management commands for inspecting and
controlling engine runs.

## Overview

The shell architecture follows a layered design:

```
run_shell()
    └── ProdinamikShell.run()    ← main REPL loop (input → dispatch)
            ├── Completer        ← readline tab completion (command + arg context)
            ├── Color            ← ANSI color helpers (auto-disabled on non-TTY)
            ├── DebugCLI         ← optional bridge for advanced debug commands
            └── Engine           ← underlying engine via get_engine()
```

Key features:

- **Readline integration** (graceful fallback when `readline` is unavailable):
  command history saved to `~/.prodinamik_history` (1000 entries), Ctrl+arrow
  word navigation, and full tab completion for commands, run slugs, profile
  names, and valid state transitions.
- **Command dispatch** routes input through a handler dict — unknown commands
  get a friendly suggestion to type `help`.
- **DebugCLI bridge** lazily initializes a `DebugCLI` with the engine's run
  manager, cost tracker, degradation manager, budget enforcer, and profile
  registry, exposing rich inspection commands (timeline, event, state, why,
  cost, health).
- **Color is auto-disabled** when `stdout` is not a TTY (piped output), so
  shell output is safe for log files and pipelines.

## Available Commands

| Command | Arguments | Description |
|---|---|---|
| `help` | `[cmd]` | Show general help or help for a specific command |
| `run` | `<profile> <title> [--slug NAME]` | Create a new run under a profile |
| `list` | `[--archived]` | List active (or archived) runs |
| `transition` | `<slug> <state>` | Transition a run to a new state |
| `debug` | `<slug>` | Show detailed run information |
| `config` | — | Display current engine configuration (YAML) |
| `timeline` | `<slug>` | Show the event timeline for a run |
| `event` | `<slug> <id>` | Show details for a specific event |
| `state` | `<slug> [event_id]` | Show current run state or time-travel |
| `why` | `<slug> <event_id>` | 5-Why root cause analysis for an event |
| `cost` | `<slug>` | Show cost timeline breakdown |
| `health` | `[slug]` | Engine or per-run health report |
| `summary` | `<slug>` | Comprehensive run summary with metrics |
| `benchmark` | `[runs=5]` | Run performance benchmarks |
| `status` | — | Engine status overview |
| `exit` / `quit` / `q` | — | Exit the shell |

## Classes

### `Color`

Minimal ANSI color helpers. All methods are classmethods. Colors are
automatically disabled when `sys.stdout.isatty()` is `False`.

**`disable()`** — Force-disable all color output (useful for testing).

**`green(text: str) -> str`** — Wrap text in green (ANSI 32).

**`yellow(text: str) -> str`** — Wrap text in yellow (ANSI 33).

**`red(text: str) -> str`** — Wrap text in red (ANSI 31).

**`blue(text: str) -> str`** — Wrap text in blue (ANSI 34).

**`cyan(text: str) -> str`** — Wrap text in cyan (ANSI 36).

**`bold(text: str) -> str`** — Wrap text in bold (ANSI 1).

**`dim(text: str) -> str`** — Wrap text in dim (ANSI 2).

**`icon(emoji: str, text: str) -> str`** — Concatenate `{emoji} {text}` (no
color wrapping, useful for status icons).

---

### `Completer`

Readline tab completer that provides context-sensitive completion candidates.
Built against the engine for live run slugs, profile names, and per-run state
machine states.

**`__init__(engine)`** — Initialise the completer, populating slug, profile,
and state caches via `_refresh_caches()`.

**`_refresh_caches()`** — Refresh the internal caches from the engine:

- `_slug_cache` — list of all non-archived run slugs
- `_profile_cache` — profile names from `engine.registry.list()`, falling back
  to `["content", "software", "research", "design"]` when the registry is
  unavailable
- `_state_cache` — per-slug map of valid state names from each run's profile
  state machine

Caches are rebuilt on every tab press to reflect newly created runs.

**`complete(text: str, state: int) -> Optional[str]`** — Standard readline
completer interface. Returns the `state`-th matching candidate or `None`.

**`update_matches(text: str, line: str, begidx: int, endidx: int) -> List[str]`**
— Build the candidate list for the current input context:

| Position | Example Command | Candidates |
|---|---|---|
| First word (no previous command) | `ru` → | `run`, `...` (all commands starting with "ru") |
| Second arg of `run` | `run cont` → | Profile names starting with "cont" |
| Second arg of `transition` | `transition my-run-` → | Run slugs |
| Third arg of `transition` | `transition my-run draf` → | Valid state names for `my-run` |
| Second arg of `debug` / `timeline` / `event` / `state` / `why` / `cost` / `summary` | | Run slugs |

---

### `ProdinamikShell`

The main REPL class. Coordinates readline setup, the event loop, command
dispatch, and graceful shutdown.

**`__init__(engine=None, config_path=None)`**

- `engine` — Optional `ProdinamikEngine` instance. If `None`, one is obtained
  via `get_engine()`.
- `config_path` — Optional path to configuration file; passed through to engine.

Initialises:
- `history_file` = `~/.prodinamik_history`
- `completer` = `Completer(engine)`
- `_debug_cli` = `None` (lazy)
- `_started_at` = `datetime.now()`
- Calls `_setup_readline()` if `readline` is available.

**`_setup_readline()`** — Configure readline: load existing history file,
set history length to 1000, register `atexit` autosave, set completer, and
bind `Tab → complete`, `Ctrl+Right → forward-word`, `Ctrl+Left → backward-word`.

**`_get_debug_cli() -> DebugCLI`** — Lazy-initialises a `DebugCLI` instance
bridging the engine's `run_manager`, `cost_tracker`, `degradation` manager,
`budget` enforcer, and profile `registry`. If any component is missing, the
bridge simply omits it. Returns `None` if `DebugCLI` cannot be imported.

**`run()`** — Main REPL loop:

1. Prints the banner (version, prompt hint with tab-completion mention).
2. Enters an infinite loop:
   - Prompts with `prodinamik> ` (cyan).
   - `EOFError` (Ctrl+D) → calls `_exit()`.
   - `KeyboardInterrupt` (Ctrl+C) → prints newline and continues.
   - Empty lines → skipped.
   - Delegates to `_dispatch(line)`.
   - Re-raises `SystemExit`; all other exceptions are caught and printed in
     red with a debug-level log entry.

**`_dispatch(line: str)`** — Tokenise the input and route to the matching
handler. Aliases: `exit`, `quit`, `q` → `_exit()`; `?` → `help`. Unknown
commands print an error with a tip to type `help`.

#### Command Handlers

**`_cmd_help(args: List[str])`** — If `args` is non-empty, looks up the topic
in a detail dict and prints specific usage. Otherwise prints the full
command catalogue grouped into *Run Management*, *Debug & Inspection*, and
*System* categories, followed by session stats (active runs, profiles, uptime).

**`_cmd_run(args: List[str])`** — Creates a new run. Requires at least 2 args
(`profile`, `title`). Accepts optional `--slug NAME`. On success, refreshes
the completer's caches. Raises `ValueError` on invalid profile.

**`_cmd_list(args: List[str])`** — Lists runs with optional `--archived` flag.
Shows slug, title, state, profile, and (when available) elapsed time in
current state. Empty state prints a hint to create a run.

**`_cmd_transition(args: List[str])`** — Transitions a run to a new state.
Calls `engine._do_transition(slug, to_state)`. Raises `ValueError` on
invalid transitions.

**`_cmd_debug(args: List[str])`** — With a slug: prints full run metadata
(profile, state, title, status, timestamps, elapsed time in current state,
timeout remaining with color-coded urgency). Without args: delegates to
`_cmd_status`.

**`_cmd_config(args: List[str])`** — Dumps engine configuration as YAML via
`yaml.dump()`.

**`_cmd_timeline(args: List[str])`** — Delegates to `DebugCLI.handle("timeline",
slug)`. Bridges the run's specific event store temporarily.

**`_cmd_event(args: List[str])`** — Delegates to `DebugCLI.handle("event",
slug, event_id)`. Requires slug and event ID.

**`_cmd_state(args: List[str])`** — Shows current run state. With an optional
second arg (event ID), performs time-travel to reconstruct state at that event.

**`_cmd_why(args: List[str])`** — 5-Why root cause analysis. Bridges event
store and delegates to `DebugCLI`.

**`_cmd_cost(args: List[str])`** — Cost timeline. Delegates to
`DebugCLI.handle("cost", slug)`.

**`_cmd_health(args: List[str])`** — With a slug: delegates to DebugCLI.
Without slug: prints engine-level health snapshot (degradation level, health
score, active runs, total cost, active profiles).

**`_cmd_summary(args: List[str])`** — Prints slug, profile, state, title,
status, event metrics (total events, passed/failed counts, total cost,
most expensive event), and degradation report if available.

**`_cmd_benchmark(args: List[str])`** — Imports `bench.run_benchmark` and
runs it. Default iteration count is 5. Prints results per metric.

**`_cmd_status(args: List[str])`** — Prints engine status: uptime, degradation
badge (FULL=green, DEGRADED=yellow, SURVIVAL=red), health score, active runs,
total cost, profiles, and cached run count.

#### Internal Helpers

**`_degradation_badge(level: str) -> str`** — Maps degradation level strings
to colorised badges.

**`_get_event_store(slug: str)`** — Returns the event store for a run slug,
or `None` on failure.

**`_print_benchmark(result: Dict[str, Any])`** — Pretty-prints benchmark
results (metric name → average value).

**`_exit()`** — Prints a goodbye message and calls `sys.exit(0)`.

## Module-Level Functions

### `run_shell(engine=None, config_path=None)`

Entry point for starting the interactive shell. Creates a `ProdinamikShell`
instance and calls `.run()`. Catches `KeyboardInterrupt` for a clean exit.

```python
# Start with default engine
run_shell()

# Start with a pre-configured engine
from engine import get_engine
engine = get_engine(config_path="/etc/prodinamik/config.yaml")
run_shell(engine=engine)
```

This is the function invoked by the `prodinamik shell` CLI command.

## Usage Examples

```python
from engine.shell import ProdinamikShell, Color, run_shell

# Programmatic use — create shell and run one-off inspection
shell = ProdinamikShell()
shell._cmd_debug(["my-run-123"])    # prints debug info for that run
shell._cmd_status([])               # prints engine status
```

```python
# Using Color helpers for custom output
from engine.shell import Color

print(Color.green("All checks passed"))
print(Color.red(f"Errors: {count}"))
print(Color.bold(Color.cyan("Prodinamik Engine")))
print(Color.icon("🚀", "Launching..."))  # → "🚀 Launching..."
print(Color.dim("background info"))
```

```python
# Direct CLI invocation (via entry point)
# $ prodinamik shell
# prodinamik> run software "API Refactor"
# prodinamik> list
# prodinamik> transition my-run-001 review
# prodinamik> health
# prodinamik> exit
```

## Error Handling & Edge Cases

- **Readline not available** — `HAS_READLINE = False`; history and tab
  completion are silently disabled. The shell still works with basic `input()`.
- **Piped / non-TTY output** — `Color._enabled` is set to `False`; ANSI escape
  sequences are stripped, making output safe for logs.
- **Engine not found** — `get_engine()` raises; the caller (`run_shell()`)
  propagates the exception. Wrap with `try/except` if calling programmatically.
- **Invalid run slug** — Command handlers print `"Run not found: {slug}"` in
  red and return gracefully.
- **Invalid state transition** — `engine._do_transition()` raises `ValueError`
  with a descriptive message; the shell prints it in red.
- **DebugCLI bridge failure** — If any engine component is missing, the
  corresponding `DebugCLI` argument is `None`. The bridge degrades gracefully.
- **Ctrl+C during prompt** — Caught as `KeyboardInterrupt`; the loop continues
  without printing an error trace.
- **Ctrl+D (EOF)** — Clean exit with goodbye message.
- **History file permissions** — Read/write failures on
  `~/.prodinamik_history` are silently ignored (no crash on startup).

## Related Modules

| Module | Relationship |
|---|---|
| `engine.cli` | Provides `get_engine()` and `get_config()` used in `__init__` |
| `engine.debug_cli` | `DebugCLI` for rich inspection commands |
| `engine.log` | Logger for debug-level command tracing |
| `engine.bench` | Benchmark runner invoked by `_cmd_benchmark` |
| `engine.run_manager` | Underlying run management (state elapsed time) |
