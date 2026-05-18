"""Prodinamik Engine v1.3 — CLI Entry Point (46 commands)

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
"""

import sys
import os
import asyncio
from pathlib import Path
from typing import Optional

import click

from .config import ProdinamikConfig
from .log import setup as setup_logging, get_logger
from .runtime import AsyncEngine, run_engine


# ──────────────────────────────────────────────
# Shared state
# ──────────────────────────────────────────────

_engine: Optional[AsyncEngine] = None
_config: Optional[ProdinamikConfig] = None


def get_config() -> ProdinamikConfig:
    global _config
    if _config is None:
        paths = [
            Path("prodinamik.yaml"),
            Path.home() / ".config" / "prodinamik" / "config.yaml",
        ]
        for p in paths:
            if p.exists():
                _config = ProdinamikConfig.load(str(p))
                break
        if _config is None:
            _config = ProdinamikConfig.load()
    return _config


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = get_config()
        _engine = AsyncEngine(cfg)
    return _engine


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


class CategorizedCLI(click.Group):
    """Click Group with categorized help output."""

    COMMAND_CATEGORIES = [
        ("🏗️  CORE", [
            "run", "list", "transition", "debug", "config",
            "validate", "daemon", "shell", "version",
        ]),
        ("🧰  DEVELOPER", ["new", "benchmark", "completion"]),
        ("📊  OBSERVABILITY", ["dashboard", "metrics", "audit", "alert"]),
        ("🔒  SECURITY", ["auth", "serve"]),
        ("🌐  DISTRIBUTION", ["raft"]),
        ("🧪  QUALITY", ["chaos"]),
        ("🔌  EXTENSIONS", ["plugin", "ai"]),
        ("🤖  AI PROVIDERS", ["llm"]),
        ("🤖  AGENT RUNTIME", ["agent"]),
    ]

    def format_commands(self, ctx, formatter):
        cmd_map = {c.name: c for c in self.commands.values()}
        for cat, names in self.COMMAND_CATEGORIES:
            items = []
            for name in names:
                cmd = cmd_map.get(name)
                if cmd:
                    items.append((name, cmd.get_short_help_str(45)))
            if items:
                with formatter.section(cat):
                    formatter.write_dl(items)


@click.group(cls=CategorizedCLI)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
def cli(verbose: bool, config: Optional[str]):
    """Prodinamik Engine — Product-Agnostic Pipeline Engine"""
    global _config
    _config = get_config() if not config else ProdinamikConfig.load(config)
    if verbose:
        _config.log.level = "DEBUG"
    setup_logging(_config.log)
    get_logger().debug(f"Config loaded: data_dir={_config.data_dir}")


@cli.command()
@click.argument("profile")
@click.argument("title")
@click.option("--slug", help="Custom slug (auto-generated from title if omitted)")
def run(profile: str, title: str, slug: Optional[str]):
    """Start a new run with the given PROFILE and TITLE"""
    engine = get_engine()
    try:
        run_obj = engine.create_run(profile, title, slug)
        click.echo(f"✅ Run created:")
        click.echo(f"   Slug:    {run_obj.meta.slug}")
        click.echo(f"   Profile: {run_obj.meta.profile}")
        click.echo(f"   State:   {run_obj.meta.state}")
    except ValueError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--include-archived", is_flag=True, help="Show archived runs too")
def list(include_archived: bool):
    """List all runs"""
    engine = get_engine()
    runs = engine.list_runs(include_archived=include_archived)
    if not runs:
        click.echo("No runs found.")
        return

    click.echo(f"📋 Runs ({len(runs)}):")
    for r in runs:
        status = "📦" if r.status == "archived" else "🔄"
        click.echo(f"   {status} `{r.slug}` — {r.title} [{r.state}] ({r.profile})")


@cli.command()
@click.argument("slug")
@click.argument("to_state")
def transition(slug: str, to_state: str):
    """Transition a run to a new state"""
    engine = get_engine()
    try:
        run_obj = engine._do_transition(slug, to_state)
        click.echo(f"✅ {slug}: → {run_obj.meta.state}")
    except ValueError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("slug", required=False)
def debug(slug: Optional[str]):
    """Show run details or engine status"""
    engine = get_engine()
    if slug:
        run_obj = engine.get_run(slug)
        if run_obj:
            elapsed = engine.run_manager.get_state_elapsed(slug)
            click.echo(f"📊 Run: `{run_obj.meta.slug}`")
            click.echo(f"   Profile: {run_obj.meta.profile}")
            click.echo(f"   State:   {run_obj.meta.state}")
            click.echo(f"   Status:  {run_obj.meta.status}")
            if elapsed is not None:
                click.echo(f"   Elapsed: {elapsed:.0f}s in state")
            # Check timeout
            profile = engine._get_profile(run_obj.meta.profile)
            if profile and profile.state_machine:
                state_def = profile.state_machine.config.states.get(run_obj.meta.state)
                if state_def and state_def.timeout_seconds:
                    remaining = max(0, state_def.timeout_seconds - elapsed)
                    click.echo(f"   Timeout: {remaining:.0f}s remaining "
                               f"(limit: {state_def.timeout_seconds}s)")
        else:
            click.echo(f"❌ Run '{slug}' not found")
    else:
        health = engine.health_snapshot
        click.echo(f"📊 Engine Status:")
        click.echo(f"   Profiles:     {', '.join(health['profiles'])}")
        click.echo(f"   Degradation:  {health['degradation']}")
        click.echo(f"   Health Score: {health['health_score']:.2f}")
        click.echo(f"   Active Runs:  {health['active_runs']}")
        click.echo(f"   Total Cost:   ${health['total_cost']:.4f}")


@cli.command()
def config():
    """Show current configuration"""
    cfg = get_config()
    import yaml
    click.echo("📋 Configuration:")
    click.echo(yaml.dump(cfg.to_dict(), default_flow_style=False).strip())


@cli.command()
@click.argument("profile_path", type=click.Path(exists=True))
def validate(profile_path: str):
    """Validate a profile file"""
    from .profile import ProductProfile

    sys.path.insert(0, str(Path(profile_path).parent))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("profile_mod", profile_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        profiles = []
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and issubclass(obj, ProductProfile) and obj is not ProductProfile:
                p = obj()
                p.initialize()
                profiles.append(p)

        if not profiles:
            click.echo("❌ No ProductProfile subclass found in file")
            sys.exit(1)

        for p in profiles:
            sm = p.state_machine
            click.echo(f"✅ {p.name} v{p.version}")
            click.echo(f"   States:      {len(sm.config.states)}")
            click.echo(f"   Transitions: {len(sm.config.transitions)}")
            click.echo(f"   Validators:  {len(p.validators)}")
            click.echo(f"   Adapters:    {len(p.adapters)}")
            click.echo(f"   Budget:      ${p.budget.hard_limit_usd} hard limit")

    except Exception as e:
        click.echo(f"❌ Validation failed: {e}", err=True)
        click.echo("   Try: Check the profile file format and ensure all required fields are present.", err=True)
        sys.exit(1)


@cli.command()
def daemon():
    """Start the async runtime daemon (blocking)"""
    click.echo("🚀 Prodinamik Engine daemon starting...")
    try:
        engine = run_engine()
    except KeyboardInterrupt:
        click.echo("\n👋 Daemon stopped.")
    except Exception as e:
        click.echo(f"❌ Daemon error: {e}", err=True)
        click.echo("   Try: Check 'prodinamik config' and logs for details.", err=True)
        sys.exit(1)


@cli.command()
def version():
    """Show version"""
    from . import __version__
    click.echo(f"Prodinamik Engine v{__version__}")


# ──────────────────────────────────────────────
# Phase 3: Developer Experience Commands
# ──────────────────────────────────────────────


@cli.command()
@click.option("--no-color", is_flag=True, help="Disable ANSI colors")
def shell(no_color: bool):
    """Start interactive REPL shell"""
    from .shell import run_shell, Color
    if no_color:
        Color.disable()
    engine = get_engine()
    click.echo("Starting interactive shell...")
    try:
        run_shell(engine=engine)
    except SystemExit:
        pass


@cli.group()
def new():
    """Scaffold new profiles and projects"""


@new.command()
@click.argument("name")
@click.option("--output", "-o", type=click.Path(), default="profiles",
              help="Output directory (default: profiles/)")
def profile(name: str, output: str):
    """Generate a new profile module"""
    from .scaffold import generate_profile

    output_path = Path(output)
    try:
        filepath = generate_profile(name, output_path)
        click.echo(f"✅ Profile generated: {filepath}")
        click.echo(f"   Register by importing {name}.{name.title()}Profile")
    except FileExistsError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)


@new.command()
@click.argument("name")
@click.option("--output", "-o", type=click.Path(), default=".",
              help="Parent directory (default: current dir)")
def project(name: str, output: str):
    """Generate a new project scaffold"""
    from .scaffold import generate_project

    output_path = Path(output)
    try:
        project_dir = generate_project(name, output_path)
        click.echo(f"✅ Project generated: {project_dir}")
        click.echo(f"   cd {project_dir}")
        click.echo(f"   pip install -e .")
        click.echo(f"   prodinamik run {name} \"first task\"")
    except FileExistsError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("runs", default=5, type=int)
def benchmark(runs: int):
    """Run performance benchmarks"""
    from .bench import run_benchmark
    engine = get_engine()
    click.echo(f"🚀 Running benchmarks ({runs} iterations each)...")
    try:
        results = run_benchmark(engine=engine, runs=runs)
        click.echo("\n📊 Summary:")
        for name, metrics in results.items():
            click.echo(f"   {name}: avg={metrics['avg']}ms  p95={metrics['p95']}ms  (n={metrics['samples']})")
    except Exception as e:
        click.echo(f"❌ Benchmark failed: {e}", err=True)
        click.echo("   Try: Ensure engine is initialized and at least one run exists.", err=True)
        sys.exit(1)


@cli.command()
@click.argument("shell_type", type=click.Choice(["bash", "zsh"]))
def completion(shell_type: str):
    """Generate shell completion script"""
    if shell_type == "bash":
        click.echo(_BASH_COMPLETION)
    else:
        click.echo(_ZSH_COMPLETION)


_BASH_COMPLETION = """# Prodinamik Engine Bash Completion
# Source with: source <(prodinamik completion bash)

_prodinamik_completion()
{
    local cur prev words cword
    _init_completion || return

    # Commands
    local commands="run list transition debug config validate daemon shell new benchmark completion version dashboard metrics audit help"

    # First word: command
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        return
    fi

    # Subcommands
    case "${words[1]}" in
        run)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=($(compgen -W "content software research design" -- "$cur"))
            fi
            ;;
        transition|debug)
            if [[ $cword -eq 2 ]]; then
                # List runs from engine
                local runs=$(prodinamik list 2>/dev/null | grep -oP "(?<=\`)[^`]+(?=\`)" | head -20)
                COMPREPLY=($(compgen -W "$runs" -- "$cur"))
            fi
            ;;
        new)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=($(compgen -W "profile project" -- "$cur"))
            fi
            ;;
        completion)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=($(compgen -W "bash zsh" -- "$cur"))
            fi
            ;;
    esac
}

complete -F _prodinamik_completion prodinamik
"""

_ZSH_COMPLETION = """#compdef prodinamik
# Prodinamik Engine Zsh Completion
# Source with: source <(prodinamik completion zsh)

_prodinamik() {
    local -a commands
    commands=(
        'run:Create a new run'
        'list:List all runs'
        'transition:Transition a run to a new state'
        'debug:Show run details'
        'config:Show configuration'
        'validate:Validate a profile file'
        'daemon:Start the async runtime daemon'
        'shell:Start interactive REPL shell'
        'new:Scaffold new profiles and projects'
        'benchmark:Run performance benchmarks'
        'completion:Generate shell completion script'
        'dashboard:Show health dashboard'
        'metrics:Export Prometheus metrics'
        'audit:Query audit log'
        'version:Show version'
    )

    _arguments \\
        '1: :->command' \\
        '*: :->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                run)
                    _arguments '2:profile:(content software research design)'
                    ;;
                new)
                    _arguments '2:type:(profile project)'
                    ;;
                completion)
                    _arguments '2:shell:(bash zsh)'
                    ;;
                transition|debug)
                    # Dynamic completion would need engine access
                    ;;
            esac
            ;;
    esac
}

compdef _prodinamik prodinamik
"""


# ──────────────────────────────────────────────
# Phase 4: Observability Commands
# ──────────────────────────────────────────────


@cli.command()
@click.option("--compact", is_flag=True, help="Show compact one-line status")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors")
@click.option("--html", is_flag=True, help="Export as HTML file")
@click.option("--output", "-o", type=click.Path(), help="Output file for HTML export")
def dashboard(compact: bool, no_color: bool, html: bool, output: str):
    """Show engine health dashboard"""
    from .dashboard import Dashboard, render_html_dashboard
    if no_color:
        Dashboard.GREEN = Dashboard.YELLOW = Dashboard.RED = ""
        Dashboard.CYAN = Dashboard.BLUE = Dashboard.DIM = ""
        Dashboard.BOLD = Dashboard.RESET = ""

    engine = get_engine()

    if html:
        html_content = render_html_dashboard(engine)
        out_path = output or "prodinamik_dashboard.html"
        Path(out_path).write_text(html_content, encoding="utf-8")
        click.echo(f"✅ Dashboard exported: {out_path}")
        return

    dash = Dashboard(engine)

    if compact:
        click.echo(dash.render_compact())
    else:
        click.echo(dash.render())


@cli.command()
@click.option("--prometheus", is_flag=True, help="Render in Prometheus format")
@click.option("--output", "-o", type=click.Path(), help="Write metrics to file")
def metrics(prometheus: bool, output: str):
    """Show or export engine metrics"""
    from .metrics import metrics, EngineMetrics

    engine = get_engine()
    em = EngineMetrics(engine)
    em.poll()

    if prometheus:
        result = metrics.render_prometheus()
    else:
        snap = em.snapshot()
        import json
        result = json.dumps(snap, indent=2, default=str)

    if output:
        Path(output).write_text(result, encoding="utf-8")
        click.echo(f"✅ Metrics written: {output}")
    else:
        click.echo(result)


@cli.group()
def audit():
    """Query and manage audit log"""


@audit.command()
@click.argument("event_type", required=False)
@click.option("--since", help="Start timestamp (ISO format)")
@click.option("--until", help="End timestamp (ISO format)")
@click.option("--limit", default=20, type=int, help="Max entries")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def query(event_type, since, until, limit, as_json):
    """Query audit log entries"""
    from .audit import AuditLog

    engine = get_engine()
    cfg = get_config()
    audit_dir = Path(cfg.data_dir) / "audit"
    log = AuditLog(base_path=str(audit_dir))

    results = log.query(
        since=since, until=until,
        event_type=event_type, limit=limit,
    )

    if as_json:
        import json as j
        click.echo(j.dumps([e.to_dict() for e in results], indent=2, ensure_ascii=False))
    else:
        if not results:
            click.echo("No audit entries found.")
            return
        for e in results:
            summary = e.data.get("slug", e.data.get("profile", e.event_type))
            click.echo(f"  [{e.timestamp[11:19]}] {e.event_type}: {summary}")


@audit.command()
def stats():
    """Show audit log statistics"""
    from .audit import AuditLog

    engine = get_engine()
    cfg = get_config()
    audit_dir = Path(cfg.data_dir) / "audit"
    log = AuditLog(base_path=str(audit_dir))

    s = log.stats()
    click.echo("📊 Audit Log Stats:")
    click.echo(f"   Active entries:     {s['active_entries']}")
    click.echo(f"   Archive segments:   {s['archive_segments']}")
    click.echo(f"   Base path:          {s['base_path']}")


@audit.command()
@click.option("--older-than", default=7, type=int, help="Compact entries older than N days")
def compact(older_than: int):
    """Compact old audit entries"""
    from .audit import AuditLog

    engine = get_engine()
    cfg = get_config()
    audit_dir = Path(cfg.data_dir) / "audit"
    log = AuditLog(base_path=str(audit_dir))

    count = log.compact(older_than_days=older_than)
    if count:
        click.echo(f"✅ Compacted {count} entries older than {older_than} days")
    else:
        click.echo("No entries to compact.")


# ──────────────────────────────────────────────
# Phase 5: Security & Distribution Commands
# ──────────────────────────────────────────────


@cli.group()
def auth():
    """Manage API keys and authentication"""


@auth.command()
@click.argument("name")
@click.option("--role", default="user", type=click.Choice(["admin", "user", "readonly"]),
              help="Access role")
@click.option("--expires", default=None, type=int,
              help="Days until expiration (optional)")
def create_key(name: str, role: str, expires: Optional[int]):
    """Create a new API key"""
    from .auth import AuthManager

    cfg = get_config()
    auth_dir = Path(cfg.data_dir) / "auth"
    mgr = AuthManager(base_path=str(auth_dir))

    key_id, raw_key = mgr.create_key(
        name=name, role=role,
        expires_in_days=expires,
    )

    click.echo(f"✅ API key created:")
    click.echo(f"   Name:    {name}")
    click.echo(f"   Role:    {role}")
    click.echo(f"   Key ID:  {key_id}")
    click.echo(f"   {'─' * 40}")
    click.echo(f"   {raw_key}")
    click.echo(f"   {'─' * 40}")
    click.echo(f"   ⚠️  This key will not be shown again. Store it securely.")


@auth.command(name="list")
def list_keys():
    """List all API keys"""
    from .auth import AuthManager

    cfg = get_config()
    auth_dir = Path(cfg.data_dir) / "auth"
    mgr = AuthManager(base_path=str(auth_dir))

    keys = mgr.list_keys()
    if not keys:
        click.echo("No API keys found.")
        return

    click.echo(f"📋 API Keys ({len(keys)}):")
    for k in keys:
        status = "✅" if k["enabled"] else "❌"
        expires = f" (expires: {k['expires_at'][:10]})" if k.get("expires_at") else ""
        click.echo(f"   {status} {k['key_id']} — {k['name']} [{k['role']}]{expires}")


@auth.command()
@click.argument("key_id")
def revoke(key_id: str):
    """Revoke an API key"""
    from .auth import AuthManager

    cfg = get_config()
    auth_dir = Path(cfg.data_dir) / "auth"
    mgr = AuthManager(base_path=str(auth_dir))

    if mgr.revoke_key(key_id):
        click.echo(f"✅ Key revoked: {key_id}")
    else:
        click.echo(f"❌ Key not found: {key_id}")
        sys.exit(1)


@auth.command()
@click.argument("key_id")
def key_info(key_id: str):
    """Show API key details"""
    from .auth import AuthManager

    cfg = get_config()
    auth_dir = Path(cfg.data_dir) / "auth"
    mgr = AuthManager(base_path=str(auth_dir))

    info = mgr.get_key(key_id)
    if not info:
        click.echo(f"❌ Key not found: {key_id}")
        sys.exit(1)

    click.echo(f"📌 Key: {info['key_id']}")
    click.echo(f"   Name:    {info['name']}")
    click.echo(f"   Role:    {info['role']}")
    click.echo(f"   Enabled: {'✅' if info['enabled'] else '❌'}")
    click.echo(f"   Created: {info['created_at'][:19]}")
    if info.get("expires_at"):
        click.echo(f"   Expires: {info['expires_at'][:10]}")
    if info.get("last_used_at"):
        click.echo(f"   Last Used: {info['last_used_at'][:19]}")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.option("--port", default=8080, type=int, help="Port number")
@click.option("--blocking", is_flag=True, help="Run in foreground (blocking)")
def serve(host: str, port: int, blocking: bool):
    """Start HTTP server with /metrics, /healthz, /api/v1"""
    from .server import ProdinamikServer

    engine = get_engine()
    server = ProdinamikServer(engine, host=host, port=port)

    if blocking:
        click.echo(f"🚀 HTTP server starting on http://{host}:{port} (blocking)")
        server.start_blocking()
    else:
        server.start()
        click.echo(f"🚀 HTTP server started on http://{host}:{port}")
        click.echo(f"   Endpoints:")
        click.echo(f"   • GET  /healthz   — Health check")
        click.echo(f"   • GET  /metrics   — Prometheus metrics")
        click.echo(f"   • GET  /api/v1/runs — Run management")
        click.echo(f"   • GET  /api/v1/health — Detailed health")
        click.echo(f"   • GET  /api/v1/profiles — Profile list")
        click.echo(f"   • GET  /api/v1/audit — Audit log query")
        click.echo(f"")
        click.echo(f"   Use --blocking for foreground mode.")


@cli.group()
def raft():
    """Manage Raft consensus cluster"""


@raft.command(name="status")
def raft_status():
    """Show Raft cluster status"""
    from .raft import HybridConsensusNode, RaftCluster

    cfg = get_config()
    node = HybridConsensusNode(
        node_id="cli-node",
        peers=[],
        state_dir=str(Path(cfg.data_dir) / "raft"),
    )
    cluster = RaftCluster(node)
    click.echo(cluster.status_text())


@raft.command(name="peers")
@click.argument("peer_ids", nargs=-1, required=True)
@click.option("--transport", "-t", default="",
              help="TCP addresses (format: node:host:port,...)")
@click.option("--port", "-p", default=9001,
              help="Local Raft TCP server port (default: 9001)")
def raft_peers(peer_ids: tuple, transport: str, port: int):
    """Register peer nodes (space-separated IDs)

    With --transport, enables real TCP-based Raft communication.
    Example:
      prodinamik raft peers node-b node-c --transport node-b:192.168.1.2:9001,node-c:192.168.1.3:9001
    """
    from .raft import HybridConsensusNode, RaftCluster

    cfg = get_config()
    node = HybridConsensusNode(
        node_id="cli-node",
        peers=list(peer_ids),
        state_dir=str(Path(cfg.data_dir) / "raft"),
        enable_transport=bool(transport),
        raft_port=port,
    )
    cluster = RaftCluster(node)
    cluster.discover_peers(list(peer_ids))

    # Parse and register TCP transport addresses
    if transport:
        for mapping in transport.split(","):
            parts = mapping.strip().split(":")
            if len(parts) >= 3:
                nid, host, p = parts[0], parts[1], parts[2]
                node.register_peer_transport(nid, f"{host}:{p}")
                click.echo(f"   🔗 {nid} → {host}:{p}")
        node.start_transport()
        click.echo(f"   🚀 Local Raft server: 0.0.0.0:{port}")

    click.echo(f"✅ Registered {len(peer_ids)} peer(s)")
    click.echo(f"   TCP transport: {'🌐 enabled' if transport else '💻 simulated (no TCP)'}")
    click.echo(cluster.status_text())


@raft.command(name="elect")
def raft_elect():
    """Force leader election"""
    from .raft import HybridConsensusNode, RaftCluster

    cfg = get_config()
    node = HybridConsensusNode(
        node_id="cli-node",
        state_dir=str(Path(cfg.data_dir) / "raft"),
    )
    cluster = RaftCluster(node)
    result = cluster.elect_leader()
    if result:
        click.echo(f"✅ Leader elected: {result}")
    else:
        click.echo(f"⚠️  Could not elect leader (may already be one)")
    click.echo(cluster.status_text())


# ──────────────────────────────────────────────
# Phase 6: Chaos Engineering Commands
# ──────────────────────────────────────────────


@cli.group()
def chaos():
    """Chaos engineering: fault injection and resilience testing"""


@chaos.command(name="run")
@click.argument("scenario")
@click.option("--duration", type=int, help="Override scenario duration (seconds)")
@click.option("--dangerous", is_flag=True, help="Allow dangerous scenarios")
def chaos_run(scenario: str, duration: Optional[int], dangerous: bool):
    """Run a chaos scenario
    
    Scenarios: network-partition, network-latency, disk-full, disk-corruption,
    memory-pressure, cpu-spike, random-crash, degraded-mode, wal-corruption, event-flood
    """
    from .chaos import ChaosEngine

    engine = get_engine()

    # Check if scenario exists and is dangerous
    all_scenarios = ChaosEngine.SCENARIOS
    if scenario not in all_scenarios:
        click.echo(f"❌ Unknown scenario: {scenario}")
        click.echo(f"   Available: {', '.join(sorted(all_scenarios.keys()))}")
        sys.exit(1)

    info = all_scenarios[scenario]
    if info["dangerous"] and not dangerous:
        click.echo(f"⚠️  '{scenario}' is a DANGEROUS scenario. Use --dangerous to run.")
        click.echo(f"   It may corrupt data or crash the engine.")
        sys.exit(1)

    chaos = ChaosEngine(engine)
    click.echo(f"🧪 Running chaos scenario: {scenario}")
    click.echo(f"   {info['description']}")
    click.echo(f"   Duration: {duration or info['duration']}s")
    click.echo(f"   Dangerous: {'⚠️' if info['dangerous'] else '✅'}")
    click.echo("")

    result = chaos.run_scenario(scenario, duration=duration)
    click.echo(result.report())


@chaos.command(name="list")
def chaos_list():
    """List all available chaos scenarios"""
    from .chaos import ChaosEngine

    scenarios = ChaosEngine.SCENARIOS
    click.echo(f"🧪 Chaos Scenarios ({len(scenarios)}):")
    for name, info in sorted(scenarios.items()):
        danger = " ⚠️ DANGEROUS" if info["dangerous"] else ""
        click.echo(f"   {name:25s}  {info['description']}{danger}")


@chaos.command(name="report")
@click.option("--scenario", help="Filter to one scenario")
def chaos_report(scenario: Optional[str]):
    """Show chaos test report"""
    from .chaos import ChaosEngine

    engine = get_engine()
    chaos = ChaosEngine(engine)

    if scenario:
        click.echo(chaos.report(scenario_name=scenario))
    else:
        click.echo(chaos.report())


# ──────────────────────────────────────────────
# Alert Commands
# ──────────────────────────────────────────────


@cli.group()
def alert():
    """Send and manage alerts to Slack/Telegram"""
    pass


@alert.command()
@click.argument("level", type=click.Choice(["info", "warning", "critical"]))
@click.argument("title")
@click.option("--message", "-m", default="", help="Alert message body")
@click.option("--metric", "-M", multiple=True, help="Key=value metrics (e.g. usage=0.85)")
def send(level, title, message, metric):
    """Send an alert to configured channels"""
    from engine.alert import alert_config_from_env

    mgr = alert_config_from_env()
    if not mgr.is_configured:
        click.echo("⚠️  No alert channels configured. Set PRODINAMIK_SLACK_WEBHOOK, "
                   "PRODINAMIK_TELEGRAM_TOKEN, or PRODINAMIK_TELEGRAM_CHAT_ID env vars.")
        return

    metrics = {}
    for m in metric:
        if "=" in m:
            k, v = m.split("=", 1)
            metrics[k] = v

    alert_obj = mgr.send_alert(level, title, message, metrics)
    click.echo(f"✅ Alert sent: {alert_obj.emoji} [{level.upper()}] {title}")
    click.echo(f"   Channels: {', '.join(mgr.enabled_channels)}")
    click.echo(f"   ID: {alert_obj.id}")


@alert.command()
@click.option("--channel", "-c", default="slack", help="Channel to test: slack, telegram, generic")
def test(channel):
    """Send a test alert to verify channel configuration"""
    from engine.alert import alert_config_from_env

    mgr = alert_config_from_env()
    if channel not in mgr.enabled_channels:
        click.echo(f"⚠️  Channel '{channel}' not configured. Available: {mgr.enabled_channels or 'none'}")
        return

    success = mgr.test(channel)
    if success:
        click.echo(f"✅ Test alert sent to {channel}")
    else:
        click.echo(f"⚠️  Test may have failed — check channel")


@alert.command()
@click.option("--limit", "-n", default=10, help="Number of recent alerts")
@click.option("--min-level", "-l", default="info", help="Minimum severity level")
def recent(limit, min_level):
    """Show recent alerts"""
    from engine.alert import alert_config_from_env

    mgr = alert_config_from_env()
    alerts = mgr.recent(limit=limit, min_level=min_level)
    if not alerts:
        click.echo("No alerts recorded.")
        return
    for a in alerts:
        click.echo(f"  {a.emoji} [{a.level.upper():8s}] {a.title} — {a.timestamp}")


@alert.command()
def status():
    """Show alert manager configuration and stats"""
    from engine.alert import alert_config_from_env

    mgr = alert_config_from_env()
    summary = mgr.summary()
    click.echo("📡 Alert Manager Status")
    click.echo(f"   Channels: {', '.join(summary['channels']) or 'none'}")
    click.echo(f"   Total alerts: {summary['total_alerts']}")
    click.echo(f"   Counts: {summary['counts']}")


# ──────────────────────────────────────────────
# Phase 10: AI-Native Features Commands
# ──────────────────────────────────────────────


@cli.group()
def ai():
    """AI-Native features — detect, predict, recommend, status"""


@ai.command("detect")
@click.option("--drift-type", default=None, help="Filter by drift type")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def ai_detect(drift_type, as_json):
    """Run AI drift detection and trend analysis"""
    from .aidetect import AIDriftDetector

    detector = AIDriftDetector()
    report = detector.generate_report()

    if as_json:
        import json as j
        click.echo(j.dumps(report, indent=2, ensure_ascii=False))
        return

    click.echo("🔍 AI Drift Detection Report")
    click.echo(f"   Health Score:     {report['health_score']}/100")
    click.echo(f"   Total Events:     {report['total_events']}")
    click.echo(f"   Degrading Trends: {report['degrading_trends']}")
    click.echo(f"   Stable Trends:    {report['stable_trends']}")

    if report["emergence_candidates"]:
        click.echo(f"\n🧬 Emergence Candidates:")
        for c in report["emergence_candidates"]:
            click.echo(f"   💡 {c['suggested_skill']} "
                       f"(confidence={c['confidence']})")
            click.echo(f"      {c['description'][:80]}...")

    if report.get("anomalies", {}).get("anomalous_runs"):
        click.echo(f"\n⚠️  Anomalous Runs:")
        for a in report["anomalies"]["anomalous_runs"]:
            click.echo(f"   {a['run_id']}: z={a['z_score']} "
                       f"(drifts={a['drift_count']})")


@ai.command("predict")
@click.option("--metric", "-m", default=None, help="Specific metric to forecast")
@click.option("--horizon", "-h", default=60, type=int, help="Forecast horizon in minutes")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def ai_predict(metric, horizon, as_json):
    """Predict future degradation from metric trends"""
    from .predict import AIDegradationForecaster

    forecaster = AIDegradationForecaster()

    if metric:
        prediction = forecaster.predict(metric, horizon)
        if prediction:
            if as_json:
                import json as j
                click.echo(j.dumps(prediction.to_dict(), indent=2, ensure_ascii=False))
            else:
                click.echo(f"📊 Degradation Prediction: {metric}")
                click.echo(f"   Current Level:     {prediction.current_level.value}")
                click.echo(f"   Predicted Level:   {prediction.predicted_level.value}")
                if prediction.time_to_degradation:
                    click.echo(f"   Time to Degradation: {prediction.time_to_degradation:.1f}m")
                click.echo(f"   Confidence:        {prediction.confidence:.0%}")
                click.echo(f"   Recommendation:    {prediction.recommendation}")
        else:
            click.echo("⚠️  Insufficient data for prediction. Record metrics first.")
    else:
        report = forecaster.generate_report(horizon)
        if as_json:
            import json as j
            click.echo(j.dumps(report, indent=2, ensure_ascii=False))
        else:
            click.echo("📊 Degradation Forecast Report")
            health = report["degradation_assessment"]
            click.echo(f"   Health Score: {health['health_score']}/100")
            click.echo(f"   🔴 Critical: {health['critical']}")
            click.echo(f"   🟡 Warning:  {health['warning']}")
            click.echo(f"   🟢 Normal:   {health['normal']}")
            click.echo(f"   Metrics Tracked: {report['metrics_tracked']}")


@ai.command("recommend")
@click.argument("current_state")
@click.option("--run-id", default="current", help="Run identifier")
@click.option("--profile", default="default", help="Profile name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def ai_recommend(current_state, run_id, profile, as_json):
    """Get recommended next state transitions"""
    from .recommend import AIRecommender

    recommender = AIRecommender()
    rec = recommender.get_recommendation(run_id, current_state, profile)

    if not rec:
        click.echo("⚠️  No recommendations available for this state.")
        return

    if as_json:
        import json as j
        click.echo(j.dumps(rec.to_dict(), indent=2, ensure_ascii=False))
        return

    click.echo(f"🎯 Next State Recommendations")
    click.echo(f"   Current: {current_state}")
    click.echo(f"   Best Next: {rec.best_next_state}")
    click.echo(f"   Confidence: {rec.confidence:.0%}")
    click.echo(f"   Reasoning: {rec.reasoning}")
    if rec.estimated_duration:
        click.echo(f"   Est. Duration: {rec.estimated_duration:.0f}s")

    if rec.warnings:
        click.echo(f"\n⚠️  Warnings:")
        for w in rec.warnings:
            click.echo(f"   • {w}")

    if len(rec.recommended_states) > 1:
        click.echo(f"\n📋 All Recommendations:")
        for state, score in rec.recommended_states:
            click.echo(f"   {state}: {score:.0%}")


@ai.command("status")
def ai_status():
    """Show AI-Native features status and metrics"""
    from .aidetect import AIDriftDetector
    from .predict import AIDegradationForecaster
    from .recommend import AIRecommender
    from .autofix import AutoRemediator
    from .skillforge import AutoSkillForge

    click.echo("🤖 AI-Native Features Status")
    click.echo(f"{'─'*50}")

    detector = AIDriftDetector()
    dm = detector.metrics
    click.echo(f"\n🔍 Drift Detection")
    click.echo(f"   Events: {dm['total_events']}")
    click.echo(f"   Types:  {dm['unique_types']}")

    forecaster = AIDegradationForecaster()
    fm = forecaster.metrics
    click.echo(f"\n📊 Degradation Forecasting")
    click.echo(f"   Metrics: {fm['tracked_metrics']}")
    click.echo(f"   Points:  {fm['total_points']}")

    recommender = AIRecommender()
    rm = recommender.metrics
    click.echo(f"\n🎯 Run Recommender")
    click.echo(f"   Transitions: {rm['total_transitions']}")
    click.echo(f"   Bottlenecks: {rm['bottlenecks']}")

    remediator = AutoRemediator()
    rs = remediator.get_stats()
    click.echo(f"\n🛠️  Auto-Remediation")
    click.echo(f"   Incidents:   {rs['total_incidents']}")
    click.echo(f"   Auto-fixed:  {rs['auto_remediated']}")
    click.echo(f"   Success:     {rs['success_rate']:.0%}")

    forge = AutoSkillForge(detector)
    ss = forge.stats_summary()
    click.echo(f"\n🧬 Skill Emergence")
    click.echo(f"   Generated:  {ss['total_generated']}")
    click.echo(f"   Promotable: {ss['promotable']}")
    click.echo(f"{'─'*50}")
    click.echo("   ⚡ Usage: prodinamik ai <detect|predict|recommend>")


# ── LLM Provider Commands ─────────────────────


@cli.group()
def llm():
    """Manage LLM providers"""
    pass


@llm.command("list")
def llm_list():
    """List registered LLM providers"""
    from .llm_registry import LLMProviderRegistry

    registry = LLMProviderRegistry.get_instance()
    providers = registry.list_providers()

    if not providers:
        click.echo("No LLM providers registered.")
        click.echo("")
        click.echo("   📋 Discovered LLM plugins:")
        click.echo("      prodinamik.llm.openai")
        click.echo("      prodinamik.llm.anthropic")
        click.echo("      prodinamik.llm.ollama")
        click.echo("")
        click.echo("   Enable one:")
        click.echo("      prodinamik plugin enable prodinamik.llm.openai")
        click.echo("      prodinamik llm list")
        return

    click.echo("🤖 Registered LLM Providers:")
    click.echo(f"   {'ID':25s} {'Models':40s} {'Default':10s}")
    click.echo(f"   {'─'*25} {'─'*40} {'─'*10}")
    for p in providers:
        default_mark = "✅" if p["default"] else ""
        models_str = ", ".join(p["models"][:3]) if p["models"] else "—"
        click.echo(f"   {p['id']:25s} {models_str:40s} {default_mark:10s}")


@llm.command("health")
def llm_health():
    """Check LLM provider health"""
    from .llm_registry import LLMProviderRegistry

    registry = LLMProviderRegistry.get_instance()
    health = registry.health()

    if not health:
        click.echo("No LLM providers registered.")
        return

    click.echo("🏥 LLM Provider Health:")
    click.echo(f"   {'Provider':25s} {'Status':10s} {'Default Model':20s}")
    click.echo(f"   {'─'*25} {'─'*10} {'─'*20}")
    for pid, info in health.items():
        status = info.get("status", "unknown")
        icon = "✅" if status == "ok" else "❌"
        model = info.get("default_model", "—")
        click.echo(f"   {icon} {pid:23s} {status:10s} {model:20s}")


@llm.command("stats")
def llm_stats():
    """Show LLM usage statistics"""
    from .llm_registry import LLMProviderRegistry

    registry = LLMProviderRegistry.get_instance()
    stats = registry.usage_stats()

    if not stats:
        click.echo("No LLM usage recorded yet.")
        return

    click.echo("📊 LLM Usage Statistics:")
    for pid, s in stats.items():
        click.echo(f"\n  🤖 {pid}:")
        click.echo(f"     Total calls:          {s['total_calls']}")
        click.echo(f"     Failed calls:         {s['failed_calls']}")
        click.echo(f"     Prompt tokens:        {s['total_prompt_tokens']}")
        click.echo(f"     Completion tokens:    {s['total_completion_tokens']}")
        click.echo(f"     Last call:            {s['last_call'] or 'never'}")
        if s.get("last_error"):
            click.echo(f"     ⚠️  Last error:  {s['last_error']}")


# ──────────────────────────────────────────────
# Phase 9: Plugin Ecosystem Commands
# ──────────────────────────────────────────────


@cli.group()
def plugin():
    """Manage plugins — list, install, enable, disable, info"""


@plugin.command("list")
@click.option("--type", "plugin_type", default=None,
              help="Filter by plugin type (validator|adapter|hook|tool|profile|integration)")
@click.option("--enabled", is_flag=True, help="Show only enabled plugins")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def plugin_list(plugin_type, enabled, as_json):
    """List all registered plugins"""
    from .plugin_registry import PluginRegistry
    from .plugin import PluginType, PluginStatus

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)
    registry.discover()

    plugins = registry.list_plugins()
    if enabled:
        plugins = [p for p in plugins if p.status == PluginStatus.ENABLED]
    if plugin_type:
        try:
            pt = PluginType(plugin_type)
            plugins = [p for p in plugins if p.manifest and p.manifest.plugin_type == pt]
        except ValueError:
            click.echo(f"⚠️  Unknown plugin type: {plugin_type}")
            click.echo(f"   Valid: {', '.join(t.value for t in PluginType)}")
            return

    if as_json:
        import json as j
        click.echo(j.dumps(registry.to_dict(), indent=2, ensure_ascii=False))
        return

    if not plugins:
        click.echo("No plugins found. Run 'prodinamik plugin discover' to scan.")
        return

    click.echo(f"📦 Plugins ({len(plugins)}):")
    click.echo(f"   {'ID':30s} {'Status':12s} {'Type':14s} {'Version':10s}")
    click.echo(f"   {'─'*30} {'─'*12} {'─'*14} {'─'*10}")
    for p in plugins:
        if p.manifest:
            status_icon = {"enabled": "🟢", "disabled": "⚪", "error": "🔴", "installed": "📥"}.get(p.status.value, "❓")
            click.echo(f"   {status_icon} {p.manifest.id:28s} {p.status.value:12s} "
                       f"{p.manifest.plugin_type.value:14s} {p.manifest.version:10s}")


@plugin.command()
def discover():
    """Scan for new plugins in search paths"""
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)
    count = registry.discover()

    if count:
        click.echo(f"✅ Discovered {count} new plugin(s). Total: {registry.count}")
    else:
        click.echo(f"ℹ️  No new plugins found. Total: {registry.count}")

    summary = registry.snapshot_metrics()
    click.echo(f"   🟢 Enabled: {summary['enabled']}")
    click.echo(f"   ⚪ Disabled: {summary['disabled']}")
    click.echo(f"   🔴 Error: {summary['error']}")


@plugin.command()
@click.argument("plugin_id")
async def enable(plugin_id):
    """Enable a plugin by ID"""
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)
    registry.discover()

    success = await registry.enable(plugin_id)
    if success:
        click.echo(f"✅ Plugin enabled: {plugin_id}")
    else:
        state = registry.get(plugin_id)
        if state and state.error:
            click.echo(f"❌ Failed to enable {plugin_id}: {state.error}")
        else:
            click.echo(f"❌ Plugin not found: {plugin_id}")


@plugin.command()
@click.argument("plugin_id")
async def disable(plugin_id):
    """Disable a plugin by ID"""
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)

    success = await registry.disable(plugin_id)
    if success:
        click.echo(f"✅ Plugin disabled: {plugin_id}")
    else:
        click.echo(f"❌ Plugin not found: {plugin_id}")


@plugin.command()
@click.argument("plugin_id")
@click.option("--source", "-s", default=None, help="Source file or directory path")
async def install(plugin_id, source):
    """Install a plugin from source or repository"""
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)

    success = await registry.install(plugin_id, source=source)
    if success:
        click.echo(f"✅ Plugin installed: {plugin_id}")
        click.echo("   Use 'prodinamik plugin enable <id>' to activate it.")
    else:
        click.echo(f"❌ Failed to install {plugin_id}")


@plugin.command()
@click.argument("plugin_id")
async def uninstall(plugin_id):
    """Uninstall a plugin"""
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)

    success = await registry.uninstall(plugin_id)
    if success:
        click.echo(f"✅ Plugin uninstalled: {plugin_id}")
    else:
        click.echo(f"❌ Plugin not found: {plugin_id}")


@plugin.command("info")
@click.argument("plugin_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def plugin_info(plugin_id, as_json):
    """Show detailed plugin information"""
    from .plugin_registry import PluginRegistry
    from .plugin import PluginStatus

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)
    registry.discover()

    state = registry.get(plugin_id)
    if not state:
        click.echo(f"❌ Plugin not found: {plugin_id}")
        return

    manifest = state.manifest
    instance = state.instance

    if as_json:
        import json as j
        info = {
            "id": manifest.id if manifest else plugin_id,
            "name": manifest.name if manifest else plugin_id,
            "version": manifest.version if manifest else "?",
            "status": state.status.value,
            "type": manifest.plugin_type.value if manifest else "unknown",
            "description": manifest.description if manifest else "",
            "author": manifest.author if manifest else "",
            "license": manifest.license if manifest else "",
            "hooks": manifest.hooks if manifest else [],
            "tools": len(instance.get_tools()) if instance else 0,
            "validators": len(instance.get_validators()) if instance else 0,
            "dependencies": manifest.dependencies if manifest else [],
            "error": state.error,
            "enabled_at": state.enabled_at.isoformat() if state.enabled_at else None,
            "error_count": state.error_count,
        }
        click.echo(j.dumps(info, indent=2, ensure_ascii=False))
        return

    status_icon = {"enabled": "🟢", "disabled": "⚪", "error": "🔴", "installed": "📥"}.get(state.status.value, "❓")

    click.echo(f"{status_icon} Plugin: {manifest.name if manifest else plugin_id}")
    click.echo(f"   ID:         {manifest.id if manifest else plugin_id}")
    click.echo(f"   Version:    {manifest.version if manifest else '?'}")
    click.echo(f"   Status:     {state.status.value}")
    click.echo(f"   Type:       {manifest.plugin_type.value if manifest else '?'}")
    click.echo(f"   Description: {manifest.description if manifest else 'No description'}")
    if manifest:
        click.echo(f"   Author:     {manifest.author or 'Unknown'}")
        click.echo(f"   License:    {manifest.license}")
        if manifest.dependencies:
            click.echo(f"   Deps:       {', '.join(manifest.dependencies)}")
        if manifest.hooks:
            click.echo(f"   Hooks:      {', '.join(manifest.hooks)}")
    if instance:
        tools = instance.get_tools()
        if tools:
            click.echo(f"   Tools:      {len(tools)} registered")
            for t in tools:
                click.echo(f"     - {t.name}: {t.description}")
        validators = instance.get_validators()
        if validators:
            click.echo(f"   Validators: {len(validators)} registered")
    if state.error:
        click.echo(f"   ⚠️  Last error: {state.error}")
        click.echo(f"   Error count: {state.error_count}")


@plugin.command()
@click.option("--plugin-id", default=None, help="Specific plugin to reload (default: all)")
async def reload(plugin_id):
    """Reload plugin(s) after changes"""
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)

    if plugin_id:
        success = await registry.reload(plugin_id)
        if success:
            click.echo(f"✅ Plugin reloaded: {plugin_id}")
        else:
            click.echo(f"❌ Failed to reload {plugin_id}")
    else:
        previously_enabled = [p.manifest.id for p in registry.list_plugins()
                              if p.status.value == "enabled" and p.manifest]
        count = registry.discover()
        for pid in previously_enabled:
            await registry.enable(pid)
        click.echo(f"✅ Reloaded {count} plugins, re-enabled {len(previously_enabled)}")


@plugin.command("health")
def plugin_health():
    """Run health checks on all plugins"""
    import asyncio
    from .plugin_registry import PluginRegistry

    engine = get_engine()
    registry = PluginRegistry.get_instance(engine)
    registry.discover()

    results = asyncio.run(registry.health_check_all())
    if not results:
        click.echo("No plugins to check.")
        return

    click.echo("🏥 Plugin Health:")
    click.echo(f"   {'Plugin':30s} {'Status':10s} {'Healthy':8s}")
    click.echo(f"   {'─'*30} {'─'*10} {'─'*8}")
    healthy_count = 0
    for pid, result in results.items():
        healthy = result.get("healthy", False)
        status = result.get("status", "unknown")
        icon = "✅" if healthy else "❌"
        if healthy:
            healthy_count += 1
        click.echo(f"   {icon} {pid:28s} {status:10s} {'✅' if healthy else '❌':8s}")

    click.echo(f"\n   Healthy: {healthy_count}/{len(results)}")


# ──────────────────────────────────────────────
# Agent Runtime CLI
# ──────────────────────────────────────────────


@cli.group()
def agent():
    """AI Agent runtime commands"""
    pass


@agent.group()
def supervisor():
    """Agent Supervisor management"""
    pass


@supervisor.command("start")
def supervisor_start():
    """Start the AgentSupervisor"""
    import asyncio
    from .agent_runtime import AgentSupervisor, SupervisorConfig
    from .log import get_logger

    log = get_logger()
    engine = get_engine()

    config = SupervisorConfig()
    supervisor = AgentSupervisor(config)

    async def _run():
        await supervisor.start()
        log.info(f"AgentSupervisor started: {supervisor.identity.node_id}")
        click.echo(f"✅ AgentSupervisor started: {supervisor.identity.node_id}")
        click.echo(f"   Hostname: {supervisor.identity.hostname}")
        click.echo(f"   Max workers: {config.max_workers}")

        # Keep running until keyboard interrupt
        try:
            while supervisor.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await supervisor.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


@supervisor.command("stop")
def supervisor_stop():
    """Stop the AgentSupervisor"""
    click.echo("⚠️  Supervisor stop via CLI not yet implemented (use Ctrl+C)")


@supervisor.command("status")
def supervisor_status():
    """Show AgentSupervisor status"""
    from .agent_runtime import AgentSupervisor

    # Try to get active supervisor from engine
    engine = get_engine()
    supervisor = getattr(engine, '_agent_supervisor', None)

    if not supervisor:
        click.echo("❌ AgentSupervisor not running. Start with: prodinamik agent supervisor start")
        return

    click.echo(f"\n📊 AgentSupervisor Status")
    click.echo(f"{'─' * 50}")
    click.echo(f"Node ID:     {supervisor.identity.node_id}")
    click.echo(f"Hostname:    {supervisor.identity.hostname}")
    click.echo(f"Running:     {'✅' if supervisor.is_running else '❌'}")
    click.echo(f"Workers:     {supervisor.active_worker_count}/{supervisor.config.max_workers}")
    click.echo(f"Uptime:      {supervisor.identity.uptime_seconds:.0f}s")
    click.echo(f"Heartbeats:  {supervisor._heartbeat_count}")


@agent.command()
@click.argument("goal", nargs=-1, required=True)
@click.option("--provider", "-p", help="LLM provider ID (e.g. prodinamik.llm.openai)")
@click.option("--max-steps", "-s", default=20, help="Maximum execution steps")
def run(goal, provider, max_steps):
    """Submit a task to the agent runtime"""
    import asyncio
    from .agent_runtime import AgentSupervisor, SupervisorConfig
    from .agent_base import AgentResult
    from .log import get_logger

    log = get_logger()
    goal_text = " ".join(goal)

    click.echo(f"🚀 Submitting task: {goal_text[:80]}...")

    # Create temporary supervisor + worker
    config = SupervisorConfig()
    supervisor = AgentSupervisor(config)

    async def _run_task():
        await supervisor.start()

        worker_id = await supervisor.spawn_worker(
            task_id=f"cli-{hash(goal_text) % 10000:04d}",
            goal=goal_text,
            context={"source": "cli"},
            tools=[],
            provider_id=provider,
            max_steps=max_steps,
        )

        click.echo(f"   Worker ID: {worker_id}")

        # Wait for worker to complete
        while True:
            worker = supervisor.get_worker(worker_id)
            if not worker:
                break
            if worker.status.value in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

        await supervisor.stop()

        if worker and worker.status.value == "completed":
            click.echo(f"\n✅ Task completed ({worker.duration_ms:.0f}ms)")
        elif worker and worker.status.value == "failed":
            click.echo(f"\n❌ Task failed: {worker.error}")
        else:
            click.echo(f"\n⚠️  Task {worker.status.value if worker else 'unknown'}")

    asyncio.run(_run_task())


@agent.command("list")
def list_workers():
    """List all workers"""
    click.echo("📋 Workers")
    click.echo(f"{'─' * 60}")

    engine = get_engine()
    supervisor = getattr(engine, '_agent_supervisor', None)

    if not supervisor:
        click.echo("No active supervisor. Use: prodinamik agent supervisor start")
        return

    workers = supervisor.list_workers()
    if not workers:
        click.echo("No workers.")
        return

    for w in workers:
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
            "crashed": "💥",
        }.get(w.status.value, "❓")
        click.echo(f"{status_icon} {w.worker_id}: {w.goal[:50]}... [{w.status.value}]")


@agent.command()
@click.argument("worker_id")
def status(worker_id):
    """Show worker details"""
    engine = get_engine()
    supervisor = getattr(engine, '_agent_supervisor', None)

    if not supervisor:
        click.echo("No active supervisor.")
        return

    worker = supervisor.get_worker(worker_id)
    if not worker:
        click.echo(f"❌ Worker not found: {worker_id}")
        return

    click.echo(f"\n📊 Worker: {worker.worker_id}")
    click.echo(f"{'─' * 50}")
    click.echo(f"Task ID:     {worker.task_id}")
    click.echo(f"Status:      {worker.status.value}")
    click.echo(f"Goal:        {worker.goal[:100]}")
    click.echo(f"Duration:    {worker.duration_ms:.0f}ms")
    click.echo(f"Progress:    {worker.progress:.0%}")
    if worker.error:
        click.echo(f"Error:       {worker.error}")


@agent.command()
@click.argument("worker_id")
def cancel(worker_id):
    """Cancel a running worker"""
    engine = get_engine()
    supervisor = getattr(engine, '_agent_supervisor', None)

    if not supervisor:
        click.echo("No active supervisor.")
        return

    if supervisor.cancel_worker(worker_id):
        click.echo(f"✅ Worker cancelled: {worker_id}")
    else:
        click.echo(f"❌ Worker not found: {worker_id}")


@agent.command()
def providers():
    """List available LLM providers"""
    click.echo("🔌 Available LLM Providers")
    click.echo(f"{'─' * 50}")

    try:
        from .llm_registry import LLMProviderRegistry
        registry = LLMProviderRegistry.get_instance()
        providers_list = registry.list_providers()

        if not providers_list:
            click.echo("No LLM providers registered.")
            click.echo("Enable one with: prodinamik plugin enable prodinamik.llm.openai")
            return

        for p in providers_list:
            click.echo(f"✅ {p.manifest.id} v{p.manifest.version}")
            if hasattr(p, 'models') and p.models and len(p.models) > 3:
                click.echo(f"   Models: {', '.join(p.models[:3])}...")
            if hasattr(p, 'default_model') and p.default_model:
                click.echo(f"   Default: {p.default_model}")
    except Exception as e:
        click.echo(f"❌ LLM registry not available: {e}")


# ──────────────────────────────────────────────
# Coordinator CLI
# ──────────────────────────────────────────────

@cli.group()
def coordinator():
    """AI Grid Coordinator management"""
    pass


@coordinator.command("start")
@click.option("--node-id", "-n", default="", help="Node ID for this coordinator")
def coordinator_start(node_id):
    """Start the Coordinator Node"""
    import asyncio
    from .agent_runtime import CoordinatorNode, CoordinatorConfig
    from .log import get_logger

    log = get_logger()

    config = CoordinatorConfig(
        node_id=node_id or f"coord-{os.uname().nodename}",
    )
    coord = CoordinatorNode(config)

    async def _run():
        await coord.start()
        click.echo(f"✅ Coordinator started: {config.node_id}")
        click.echo(f"   Status: {coord.status.value}")
        click.echo(f"   Task queue: WAL-backed")
        click.echo(f"   Human loop: {'enabled' if config.enable_human_loop else 'disabled'}")

        try:
            while coord.is_active:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await coord.stop()
            click.echo("\n✅ Coordinator stopped")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


@coordinator.command("status")
def coordinator_status():
    """Show Coordinator status"""
    from .agent_runtime import CoordinatorNode

    click.echo("\n📊 Coordinator Status")
    click.echo("─" * 50)
    click.echo("Status: not running (start with: prodinamik coordinator start)")


@coordinator.command("submit")
@click.argument("goal", nargs=-1, required=True)
@click.option("--priority", "-p", default=2, type=int, help="Priority (0=critical, 1=high, 2=normal, 3=low)")
@click.option("--affinity", "-a", default="", help="Node capability affinity")
@click.option("--max-steps", "-s", default=20, type=int, help="Max execution steps")
def coordinator_submit(goal, priority, affinity, max_steps):
    """Submit a goal to the coordinator task queue"""
    import asyncio
    from .agent_runtime import CoordinatorNode, CoordinatorConfig

    goal_text = " ".join(goal)
    config = CoordinatorConfig()
    coord = CoordinatorNode(config)

    async def _submit():
        await coord.start()
        task_id = await coord.submit_task(
            goal=goal_text,
            priority=priority,
            affinity=affinity,
            max_steps=max_steps,
        )
        click.echo(f"✅ Task submitted: {task_id}")
        click.echo(f"   Goal: {goal_text[:80]}...")
        click.echo(f"   Priority: {priority}")
        click.echo(f"   Affinity: '{affinity}'")
        await coord.stop()

    asyncio.run(_submit())


@coordinator.command("queue")
def coordinator_queue():
    """Show task queue status"""
    import asyncio
    from .agent_runtime import CoordinatorNode, CoordinatorConfig

    config = CoordinatorConfig()
    coord = CoordinatorNode(config)

    async def _show():
        await coord.start()
        stats = coord.stats
        click.echo("\n📋 Task Queue")
        click.echo("─" * 50)
        click.echo(f"Queue depth:  {stats['queue_depth']}")
        click.echo(f"Active:       {stats['active_tasks']}")
        click.echo(f"Total:        {stats['total_tasks']}")
        click.echo(f"Assigned:     {stats['tasks_assigned']}")
        click.echo(f"Completed:    {stats['tasks_completed']}")
        click.echo(f"Failed:       {stats['tasks_failed']}")
        click.echo(f"Nodes alive:  {stats['nodes_alive']}")
        click.echo(f"Total nodes:  {stats['total_nodes']}")
        await coord.stop()

    asyncio.run(_show())


@coordinator.command("nodes")
def coordinator_nodes():
    """List registered worker nodes"""
    import asyncio
    from .agent_runtime import CoordinatorNode, CoordinatorConfig

    config = CoordinatorConfig()
    coord = CoordinatorNode(config)

    async def _show():
        await coord.start()
        nodes = coord.agent_registry.list_nodes()
        alive = coord.agent_registry.get_alive_count()

        click.echo(f"\n🔌 Worker Nodes ({alive}/{len(nodes)} alive)")
        click.echo("─" * 60)

        if not nodes:
            click.echo("No nodes registered. Start workers with: prodinamik agent supervisor start")
        else:
            for n in nodes:
                alive_mark = "✅" if n.is_alive() else "❌"
                healthy_mark = "🟢" if n.is_healthy else "🔴"
                click.echo(f"{alive_mark} {healthy_mark} {n.node_id} ({n.hostname})")
                click.echo(f"   Workers: {n.active_workers}/{n.max_workers}")
                if n.capabilities:
                    click.echo(f"   Caps: {', '.join(n.capabilities)}")

        await coord.stop()

    asyncio.run(_show())


if __name__ == "__main__":
    cli()
