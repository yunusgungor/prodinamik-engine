"""Prodinamik Engine v1.0 — CLI Entry Point (Async)

Usage:
    prodinamik run <profile> <title>        # Start new run
    prodinamik list                          # List all runs
    prodinamik transition <slug> <state>     # State transition
    prodinamik debug <slug>                  # Show run details
    prodinamik config                        # Show config
    prodinamik validate <profile_path>       # Validate profile
    prodinamik daemon                        # Start daemon (async runtime)
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
    click.echo("Prodinamik Engine v1.0.0")


if __name__ == "__main__":
    cli()
