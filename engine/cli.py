"""Prodinamik Engine v1.1 — CLI Entry Point (32 commands)

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


@click.group()
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
        sys.exit(1)


@cli.command()
def version():
    """Show version"""
    click.echo("Prodinamik Engine v1.1.0")


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
def raft_peers(peer_ids: tuple):
    """Register peer nodes (space-separated IDs)"""
    from .raft import HybridConsensusNode, RaftCluster

    cfg = get_config()
    node = HybridConsensusNode(
        node_id="cli-node",
        peers=list(peer_ids),
        state_dir=str(Path(cfg.data_dir) / "raft"),
    )
    cluster = RaftCluster(node)
    cluster.discover_peers(list(peer_ids))
    click.echo(f"✅ Registered {len(peer_ids)} peer(s)")
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


if __name__ == "__main__":
    cli()
