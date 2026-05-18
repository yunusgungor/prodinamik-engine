"""Prodinamik Engine v1.1 — Interactive Shell (REPL)

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
"""

import sys
import os
import atexit
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

# Readline — optional, graceful fallback
try:
    import readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

from .cli import get_engine, get_config
from .debug_cli import DebugCLI
from .log import get_logger

log = get_logger()

# ──────────────────────────────────────────────
# Colors (ANSI)
# ──────────────────────────────────────────────

class Color:
    """Minimal ANSI color helpers — auto-disable if not a tty"""
    _enabled = sys.stdout.isatty()

    @classmethod
    def disable(cls):
        cls._enabled = False

    @classmethod
    def _c(cls, code: int, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if cls._enabled else text

    @classmethod
    def green(cls, text: str) -> str:
        return cls._c(32, text)

    @classmethod
    def yellow(cls, text: str) -> str:
        return cls._c(33, text)

    @classmethod
    def red(cls, text: str) -> str:
        return cls._c(31, text)

    @classmethod
    def blue(cls, text: str) -> str:
        return cls._c(34, text)

    @classmethod
    def cyan(cls, text: str) -> str:
        return cls._c(36, text)

    @classmethod
    def bold(cls, text: str) -> str:
        return cls._c(1, text)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls._c(2, text)

    @classmethod
    def icon(cls, emoji: str, text: str) -> str:
        return f"{emoji} {text}"


# ──────────────────────────────────────────────
# Tab Completion
# ──────────────────────────────────────────────

class Completer:
    """Readline tab completer for shell commands"""

    COMMANDS = [
        "help", "run", "list", "transition", "debug",
        "config", "timeline", "event", "state", "why",
        "cost", "health", "summary", "benchmark", "status",
        "exit", "quit",
    ]

    def __init__(self, engine):
        self.engine = engine
        self._slug_cache: List[str] = []
        self._state_cache: Dict[str, List[str]] = {}
        self._profile_cache: List[str] = []
        self._refresh_caches()

    def _refresh_caches(self):
        """Refresh slug/state/profile caches"""
        try:
            runs = self.engine.list_runs(include_archived=False)
            self._slug_cache = [r.slug for r in runs]

            profiles = self.engine.registry.list() if hasattr(self.engine, 'registry') else []
            self._profile_cache = [p.name for p in profiles]
            if not self._profile_cache:
                self._profile_cache = ["content", "software", "research", "design"]

            for slug in self._slug_cache:
                run = self.engine.get_run(slug)
                if run and self.engine._get_profile(run.meta.profile):
                    try:
                        profile = self.engine._get_profile(run.meta.profile)
                        if profile.state_machine:
                            self._state_cache[slug] = list(profile.state_machine.config.states.keys())
                    except Exception:
                        self._state_cache[slug] = []
        except Exception:
            pass

    def complete(self, text: str, state: int) -> Optional[str]:
        """Readline completer: returns next match"""
        try:
            return self._matches[state]
        except (IndexError, AttributeError):
            return None

    def update_matches(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Build completion candidates"""
        self._refresh_caches()
        parts = line[:begidx].strip().split()
        cmd = parts[0] if parts else ""

        # First word: complete commands
        if not parts or (len(parts) == 1 and not line.endswith(" ")):
            candidates = [c for c in self.COMMANDS if c.startswith(text)]
            # Help can target any command
            if cmd == "help" and parts:
                candidates = [c for c in self.COMMANDS if c.startswith(text)]
            self._matches = candidates
            return candidates

        # Subsequent words: context-dependent
        arg_idx = len(parts)

        if cmd in ("run",):
            if arg_idx == 2 and not line.endswith(" "):
                # Complete profile name
                candidates = [p for p in self._profile_cache if p.startswith(text)]
            else:
                candidates = []
            self._matches = candidates
            return candidates

        if cmd in ("transition",):
            if arg_idx == 2 and not line.endswith(" "):
                candidates = [s for s in self._slug_cache if s.startswith(text)]
            elif arg_idx == 3 and not line.endswith(" "):
                # Complete state for slug
                slug = parts[1] if len(parts) > 1 else ""
                states = self._state_cache.get(slug, [])
                candidates = [s for s in states if s.startswith(text)]
            else:
                candidates = []
            self._matches = candidates
            return candidates

        if cmd in ("debug", "timeline", "event", "state", "why", "cost", "summary"):
            if arg_idx == 2 and not line.endswith(" "):
                candidates = [s for s in self._slug_cache if s.startswith(text)]
            else:
                candidates = []
            self._matches = candidates
            return candidates

        self._matches = []
        return []


# ──────────────────────────────────────────────
# Shell
# ──────────────────────────────────────────────

class ProdinamikShell:
    """Interactive REPL for Prodinamik Engine"""

    BANNER = f"""
{Color.bold(Color.cyan('╔══════════════════════════════════════╗'))}
{Color.bold(Color.cyan('║'))}   {Color.green('Prodinamik Engine v1.1')}          {Color.bold(Color.cyan('║'))}
{Color.bold(Color.cyan('║'))}   {Color.dim('Interactive Development Shell')}     {Color.bold(Color.cyan('║'))}
{Color.bold(Color.cyan('╚══════════════════════════════════════╝'))}
{Color.dim('Type help for commands · Tab to autocomplete · Ctrl+D/C to exit')}
"""

    def __init__(self, engine=None, config_path=None):
        self.config_path = config_path
        self.engine = engine or get_engine()
        self.config = get_config()
        self.history_file = Path.home() / ".prodinamik_history"
        self.completer = Completer(self.engine)
        self._started_at = datetime.now()

        # DebugCLI bridge
        self._debug_cli = None

        # Setup readline
        if HAS_READLINE:
            self._setup_readline()

    def _setup_readline(self):
        """Configure readline with history and completion"""
        histfile = str(self.history_file)

        # Load history
        try:
            readline.read_history_file(histfile)
        except (FileNotFoundError, OSError):
            pass

        # Set history file for auto-save
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, histfile)

        # Tab completion
        readline.set_completer(self.completer.complete)
        readline.set_completer_delims(" \t\n")
        readline.parse_and_bind("tab: complete")

        # Ctrl+arrows for word navigation
        try:
            readline.parse_and_bind("\\e[1;5C: forward-word")   # Ctrl+Right
            readline.parse_and_bind("\\e[1;5D: backward-word")  # Ctrl+Left
        except Exception:
            pass

    def _get_debug_cli(self):
        """Lazy-init DebugCLI with engine components"""
        if self._debug_cli is None:
            try:
                from .debug_cli import DebugCLI
                self._debug_cli = DebugCLI(
                    run_manager=self.engine.run_manager,
                    event_store=None,  # per-run from engine
                    cost_tracker=self.engine.cost_tracker if hasattr(self.engine, 'cost_tracker') else None,
                    efficiency_tracker=None,
                    degradation_manager=self.engine.degradation if hasattr(self.engine, 'degradation') else None,
                    budget_enforcer=self.engine.budget if hasattr(self.engine, 'budget') else None,
                    runtime_safety=None,
                    profile_registry=self.engine.registry if hasattr(self.engine, 'registry') else None,
                )
            except Exception:
                self._debug_cli = None
        return self._debug_cli

    def run(self):
        """Main REPL loop"""
        print(self.BANNER)

        while True:
            try:
                line = input(Color.cyan("prodinamik> "))
            except EOFError:  # Ctrl+D
                print()
                self._exit()
                return
            except KeyboardInterrupt:  # Ctrl+C
                print()
                continue

            line = line.strip()
            if not line:
                continue

            try:
                self._dispatch(line)
            except SystemExit:
                raise
            except Exception as e:
                print(f"{Color.red('⚠ Error:')} {e}")
                log.debug(f"Shell command failed: {line}", exc_info=True)

    def _dispatch(self, line: str):
        """Parse and route a command line"""
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        # Aliases
        if cmd in ("exit", "quit", "q"):
            self._exit()
            return
        if cmd == "?":
            cmd = "help"

        handlers = {
            "help": self._cmd_help,
            "run": self._cmd_run,
            "list": self._cmd_list,
            "transition": self._cmd_transition,
            "debug": self._cmd_debug,
            "config": self._cmd_config,
            "timeline": self._cmd_timeline,
            "event": self._cmd_event,
            "state": self._cmd_state,
            "why": self._cmd_why,
            "cost": self._cmd_cost,
            "health": self._cmd_health,
            "summary": self._cmd_summary,
            "benchmark": self._cmd_benchmark,
            "status": self._cmd_status,
        }

        handler = handlers.get(cmd)
        if handler:
            handler(args)
        else:
            print(f"{Color.yellow('Unknown command:')} {cmd}")
            print(f"  Try {Color.cyan('help')} for available commands")

    # ──────────────────────────────────────
    # Command Handlers
    # ──────────────────────────────────────

    def _cmd_help(self, args: List[str]):
        """Show help for commands"""
        if args:
            topic = args[0].lower()
            detail = {
                "run": "  run <profile> <title> [--slug NAME]\n    Create a new run under the given profile.\n    Profiles: content, software, research, design",
                "list": "  list [--archived]\n    List all active (or archived) runs.",
                "transition": "  transition <slug> <state>\n    Transition a run to a new state.\n    Tab-completes slugs and available states.",
                "debug": "  debug <slug>\n    Show detailed run information including elapsed time, timeout, and cost.",
                "config": "  config\n    Show current configuration (data_dir, logging, etc.)",
                "timeline": "  timeline <slug>\n    Show the last 20 events for a run.",
                "event": "  event <slug> <id>\n    Show detailed information about a specific event.",
                "state": "  state <slug> [event_id]\n    Show current run state or time-travel to an event.",
                "why": "  why <slug> <event_id>\n    5-Why root cause analysis for an event.",
                "cost": "  cost <slug>\n    Show cost timeline for a run.",
                "health": "  health [slug]\n    Show engine health report or per-run health.",
                "summary": "  summary <slug>\n    Show comprehensive run summary with metrics.",
                "benchmark": "  benchmark [runs=5]\n    Run performance benchmarks.",
                "status": "  status\n    Show engine status summary.",
            }
            info = detail.get(topic)
            if info:
                print(f"{Color.bold(Color.cyan(topic.upper()))}\n{info}")
            else:
                print(f"No help for '{topic}'. Try: {Color.cyan('help')} alone.")
            return

        print(f"""
{Color.bold('Commands')}:

  {Color.green('Run Management')}
    {Color.cyan('run')} <profile> <title>       Create a new run
    {Color.cyan('list')}                        List active runs
    {Color.cyan('transition')} <slug> <state>   Transition to a state
    {Color.cyan('status')}                      Engine status

  {Color.green('Debug & Inspection')}
    {Color.cyan('debug')} <slug>                Run details
    {Color.cyan('timeline')} <slug>             Event timeline
    {Color.cyan('event')} <slug> <id>           Event details
    {Color.cyan('state')} <slug>               Current state
    {Color.cyan('why')} <slug> <id>            5-Why analysis
    {Color.cyan('cost')} <slug>                Cost breakdown
    {Color.cyan('health')} [slug]              Health report
    {Color.cyan('summary')} <slug>             Full summary

  {Color.green('System')}
    {Color.cyan('config')}                      Show configuration
    {Color.cyan('benchmark')} [runs]            Performance benchmarks
    {Color.cyan('help')} [cmd]                  This help
    {Color.cyan('exit')} / {Color.cyan('quit')}               Exit shell

uptime_str = self._started_at.strftime("%H:%M:%S")
        print(f"{Color.dim(f'Active {len(self.completer._slug_cache)} runs · '
                           f'{len(self.completer._profile_cache)} profiles · '
                           f'Up since {uptime_str}')}")
""")

    def _cmd_run(self, args: List[str]):
        """Create a new run"""
        if len(args) < 2:
            print(f"{Color.red('Usage:')} run <profile> <title> [--slug NAME]")
            return

        profile = args[0]
        title = args[1]
        slug = None

        if "--slug" in args:
            idx = args.index("--slug")
            if idx + 1 < len(args):
                slug = args[idx + 1]

        try:
            run_obj = self.engine.create_run(profile, title, slug)
            print(f"{Color.green('✓')} Run created: {Color.bold(run_obj.meta.slug)}")
            print(f"  Profile: {run_obj.meta.profile}")
            print(f"  State:   {run_obj.meta.state}")
            self.completer._refresh_caches()
        except ValueError as e:
            print(f"{Color.red('✗')} {e}")

    def _cmd_list(self, args: List[str]):
        """List runs"""
        archived = "--archived" in args
        runs = self.engine.list_runs(include_archived=archived)

        if not runs:
            print(f"{Color.dim('No runs found. Create one with:')} {Color.cyan('run <profile> <title>')}")
            return

        print(f"{Color.bold(f'Runs ({len(runs)})')}:")
        for r in runs:
            status_icon = "📦" if r.status == "archived" else "🔄"
            elapsed = ""
            try:
                secs = self.engine.run_manager.get_state_elapsed(r.slug)
                if secs is not None:
                    elapsed = f" [{secs:.0f}s]"
            except Exception:
                pass
            print(f"  {status_icon} {Color.cyan(r.slug)} {Color.dim(r.title or '')}")
            print(f"       {Color.dim('→')} {r.state} ({r.profile}){Color.dim(elapsed)}")

    def _cmd_transition(self, args: List[str]):
        """Transition a run"""
        if len(args) < 2:
            print(f"{Color.red('Usage:')} transition <slug> <state>")
            return

        slug, to_state = args[0], args[1]
        try:
            run_obj = self.engine._do_transition(slug, to_state)
            print(f"{Color.green('✓')} {slug}: {Color.dim('→')} {Color.bold(run_obj.meta.state)}")
        except ValueError as e:
            print(f"{Color.red('✗')} {e}")

    def _cmd_debug(self, args: List[str]):
        """Show run details"""
        if not args:
            # Show engine status
            self._cmd_status([])
            return

        slug = args[0]
        run_obj = self.engine.get_run(slug)
        if not run_obj:
            print(f"{Color.red('Run not found:')} {slug}")
            return

        elapsed = None
        try:
            elapsed = self.engine.run_manager.get_state_elapsed(slug)
        except Exception:
            pass

        meta = run_obj.meta
        print(f"{Color.bold(f'📊 {meta.slug}')}")
        print(f"  {Color.dim('Profile:')}   {meta.profile}")
        print(f"  {Color.dim('State:')}     {Color.cyan(meta.state)}")
        print(f"  {Color.dim('Title:')}    {meta.title or '-'}")
        print(f"  {Color.dim('Status:')}   {meta.status}")
        print(f"  {Color.dim('Created:')}  {meta.created_at}")
        print(f"  {Color.dim('Updated:')}  {meta.updated_at}")

        if elapsed is not None:
            print(f"  {Color.dim('Elapsed:')}  {elapsed:.0f}s in current state")

        # Check timeout
        try:
            profile = self.engine._get_profile(meta.profile)
            if profile and profile.state_machine:
                state_def = profile.state_machine.config.states.get(meta.state)
                if state_def and state_def.timeout_seconds and elapsed is not None:
                    remaining = max(0, state_def.timeout_seconds - elapsed)
                    color = Color.green if remaining > 300 else (Color.yellow if remaining > 60 else Color.red)
                    print(f"  {Color.dim('Timeout:')}  {color(f'{remaining:.0f}s')} remaining "
                          f"({Color.dim(f'limit: {state_def.timeout_seconds}s')})")
        except Exception:
            pass

    def _cmd_config(self, args: List[str]):
        """Show config"""
        import yaml
        cfg = self.config
        print(f"{Color.bold('Configuration:')}")
        print(yaml.dump(cfg.to_dict(), default_flow_style=False).strip())

    def _cmd_timeline(self, args: List[str]):
        """Show event timeline (via DebugCLI)"""
        if not args:
            print(f"{Color.red('Usage:')} timeline <slug>")
            return

        slug = args[0]
        # Get event store for this run
        event_store = self._get_event_store(slug)
        if not event_store:
            print(f"{Color.yellow('No event store for:')} {slug}")
            return

        cli = self._get_debug_cli()
        if cli:
            # Temporarily attach the run's event store
            old = cli.event_store
            cli.event_store = event_store
            print(cli.handle("timeline", slug))
            cli.event_store = old
        else:
            print(f"{Color.red('DebugCLI not available')}")

    def _cmd_event(self, args: List[str]):
        """Show event details"""
        if len(args) < 2:
            print(f"{Color.red('Usage:')} event <slug> <event_id>")
            return
        slug, eid = args[0], args[1]
        event_store = self._get_event_store(slug)
        if not event_store:
            return
        cli = self._get_debug_cli()
        if cli:
            old = cli.event_store
            cli.event_store = event_store
            print(cli.handle("event", slug, eid))
            cli.event_store = old

    def _cmd_state(self, args: List[str]):
        """Show run state"""
        if not args:
            print(f"{Color.red('Usage:')} state <slug> [event_id]")
            return
        slug = args[0]
        eid = args[1] if len(args) > 1 else None

        cli = self._get_debug_cli()
        if cli:
            if eid:
                event_store = self._get_event_store(slug)
                if event_store:
                    old = cli.event_store
                    cli.event_store = event_store
                    print(cli.handle("state", slug, eid))
                    cli.event_store = old
            else:
                print(cli.handle("state", slug))

    def _cmd_why(self, args: List[str]):
        """5-Why analysis"""
        if len(args) < 2:
            print(f"{Color.red('Usage:')} why <slug> <event_id>")
            return
        slug, eid = args[0], args[1]
        event_store = self._get_event_store(slug)
        if not event_store:
            return
        cli = self._get_debug_cli()
        if cli:
            old = cli.event_store
            cli.event_store = event_store
            print(cli.handle("why", slug, eid))
            cli.event_store = old

    def _cmd_cost(self, args: List[str]):
        """Cost timeline"""
        if not args:
            print(f"{Color.red('Usage:')} cost <slug>")
            return
        slug = args[0]
        event_store = self._get_event_store(slug)
        if not event_store:
            return
        cli = self._get_debug_cli()
        if cli:
            old = cli.event_store
            cli.event_store = event_store
            result = cli.handle("cost", slug)
            print(result if result else f"{Color.yellow('No cost data for:')} {slug}")
            cli.event_store = old

    def _cmd_health(self, args: List[str]):
        """Health report"""
        cli = self._get_debug_cli()
        slug = args[0] if args else None

        if cli:
            print(cli.handle("health", slug))
        else:
            # Fallback: basic health
            health = self.engine.health_snapshot
            print(f"{Color.bold('Engine Health')}:")
            print(f"  Degradation:  {health['degradation']}")
            print(f"  Health Score: {health['health_score']:.2f}")
            print(f"  Active Runs:  {health['active_runs']}")
            print(f"  Total Cost:   ${health['total_cost']:.4f}")
            if health['profiles']:
                print(f"  Profiles:     {', '.join(health['profiles'])}")

    def _cmd_summary(self, args: List[str]):
        """Run summary"""
        if not args:
            print(f"{Color.red('Usage:')} summary <slug>")
            return
        slug = args[0]

        # Direct run info
        run_obj = self.engine.get_run(slug)
        if not run_obj:
            print(f"{Color.red('Run not found:')} {slug}")
            return

        meta = run_obj.meta
        print(f"{Color.bold(f'📋 {meta.slug}')}")
        print(f"  {Color.dim('Profile:')}   {meta.profile}")
        print(f"  {Color.dim('State:')}     {Color.cyan(meta.state)}")
        print(f"  {Color.dim('Title:')}    {meta.title or '-'}")
        print(f"  {Color.dim('Status:')}   {meta.status}")

        # Event metrics
        event_store = self._get_event_store(slug)
        if event_store:
            events = event_store.get_all()
            passed = sum(1 for e in events if e.data.get("passed", True))
            failed = sum(1 for e in events if not e.data.get("passed", True))
            total_cost = sum(e.cost_usd for e in events)

            print(f"\n  {Color.bold('Metrics:')}")
            print(f"  {Color.dim('Events:')}     {len(events)} ({passed} ✅, {failed} ❌)")
            print(f"  {Color.dim('Cost:')}      ${total_cost:.4f}")
            if events:
                top = max(events, key=lambda e: e.cost_usd)
                print(f"  {Color.dim('Top Event:')} #{top.sequence} {top.event_type} (${top.cost_usd:.4f})")

        # Degradation
        try:
            if hasattr(self.engine, 'degradation') and self.engine.degradation:
                print(f"\n  {self.engine.degradation.status_report()}")
        except Exception:
            pass

    def _cmd_benchmark(self, args: List[str]):
        """Run benchmarks"""
        try:
            from .bench import run_benchmark
            runs = int(args[0]) if args else 5
            result = run_benchmark(self.engine, runs=runs)
            self._print_benchmark(result)
        except ImportError:
            print(f"{Color.yellow('Benchmark module not installed. Try:')} pip install -e .[dev]")
        except Exception as e:
            print(f"{Color.red('Benchmark failed:')} {e}")

    def _cmd_status(self, args: List[str]):
        """Engine status overview"""
        health = self.engine.health_snapshot
        uptime = datetime.now() - self._started_at
        mins, secs = divmod(int(uptime.total_seconds()), 60)

        print(f"{Color.bold('Prodinamik Engine Status')}")
        print(f"  {Color.dim('Uptime:')}     {mins}m {secs}s")
        print(f"  {Color.dim('Degradation:')}  {self._degradation_badge(health['degradation'])}")
        print(f"  {Color.dim('Health:')}     {health['health_score']:.1f}/100")
        print(f"  {Color.dim('Active Runs:')} {health['active_runs']}")
        print(f"  {Color.dim('Total Cost:')} ${health['total_cost']:.4f}")
        if health['profiles']:
            print(f"  {Color.dim('Profiles:')}   {', '.join(health['profiles'])}")
        print(f"  {Color.dim('Shell:')}     {Color.cyan(f'prodinamik shell')} — {len(self.completer._slug_cache)} cached runs")

    def _degradation_badge(self, level: str) -> str:
        badges = {
            "FULL": Color.green("FULL"),
            "DEGRADED": Color.yellow("DEGRADED"),
            "SURVIVAL": Color.red("SURVIVAL"),
        }
        return badges.get(level, level)

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────

    def _get_event_store(self, slug: str):
        """Get event store for a slug"""
        try:
            return self.engine._get_event_store(slug)
        except Exception:
            return None

    def _print_benchmark(self, result: Dict[str, Any]):
        """Print benchmark results nicely"""
        print(f"\n{Color.bold('Benchmark Results')}:")
        for name, metrics in result.items():
            if isinstance(metrics, dict):
                avg = metrics.get("avg", "?")
                print(f"  {Color.cyan(name)}: {avg}")
            else:
                print(f"  {Color.cyan(name)}: {metrics}")
        print()

    def _exit(self):
        """Clean shutdown"""
        print(f"\n{Color.dim('👋 Goodbye!')}")
        sys.exit(0)


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

def run_shell(engine=None, config_path=None):
    """Start the interactive shell"""
    shell = ProdinamikShell(engine=engine, config_path=config_path)
    try:
        shell.run()
    except KeyboardInterrupt:
        print()
        shell._exit()
