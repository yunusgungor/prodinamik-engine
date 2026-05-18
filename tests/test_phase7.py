"""Prodinamik Engine v1.1 — Phase 3: Developer Experience Tests

Tests for:
- Interactive Shell (engine/shell.py)
- Scaffolding (engine/scaffold.py)
- Benchmark (engine/bench.py)
- CLI extensions (engine/cli.py: shell, new, benchmark, completion)
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def tmp_engine():
    """Create a minimal engine in temp dir"""
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    tmpdir = tempfile.mkdtemp()
    cfg = ProdinamikConfig.load()
    cfg.data_dir = os.path.join(tmpdir, "data")
    engine = AsyncEngine(cfg)
    return engine, tmpdir


@pytest.fixture
def tmp_profile_dir():
    """Temp directory for profile scaffolding"""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


# ──────────────────────────────────────────────
# Shell Tests
# ──────────────────────────────────────────────


def test_shell_import():
    """Shell module imports cleanly"""
    from engine.shell import ProdinamikShell, Color, Completer
    assert ProdinamikShell
    assert Color
    assert Completer


def test_color_class():
    """Color helper works with and without tty"""
    from engine.shell import Color

    # Force enabled
    Color._enabled = True
    green = Color.green("hello")
    assert "\033[32m" in green
    assert "hello" in green

    # Disabled
    Color._enabled = False
    plain = Color.green("hello")
    assert plain == "hello"


def test_completer_commands():
    """Completer knows builtin commands"""
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine
    from engine.shell import Completer

    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)
    completer = Completer(engine)

    assert "help" in completer.COMMANDS
    assert "run" in completer.COMMANDS
    assert "exit" in completer.COMMANDS
    assert "quit" in completer.COMMANDS
    assert "timeline" in completer.COMMANDS
    assert "benchmark" in completer.COMMANDS


def test_shell_banner():
    """Shell has a banner"""
    from engine.shell import ProdinamikShell
    assert "Prodinamik Engine" in ProdinamikShell.BANNER
    assert "help" in ProdinamikShell.BANNER.lower()


# ──────────────────────────────────────────────
# Scaffold Tests
# ──────────────────────────────────────────────


def test_generate_profile(tmp_profile_dir):
    """Profile scaffolding generates valid Python"""
    from engine.scaffold import generate_profile

    filepath = generate_profile("test-workflow", tmp_profile_dir)
    assert filepath.exists()
    assert filepath.suffix == ".py"
    assert filepath.name == "test-workflow.py"

    # Verify it's valid Python
    content = filepath.read_text()
    compile(content, filepath.name, "exec")

    # Check key parts
    assert "class TestWorkflowProfile(ProductProfile)" in content
    assert 'name = "test-workflow"' in content


def test_generate_profile_with_dashes(tmp_profile_dir):
    """Profile scaffolding handles multi-word slugs"""
    from engine.scaffold import generate_profile

    filepath = generate_profile("my-custom-flow", tmp_profile_dir)
    content = filepath.read_text()

    assert "class MyCustomFlowProfile(ProductProfile)" in content
    assert 'name = "my-custom-flow"' in content


def test_generate_profile_idempotent(tmp_profile_dir):
    """Generating same profile twice raises FileExistsError"""
    from engine.scaffold import generate_profile

    generate_profile("test", tmp_profile_dir)
    with pytest.raises(FileExistsError):
        generate_profile("test", tmp_profile_dir)


def test_generate_project(tmpdir):
    """Project scaffolding generates complete structure"""
    from engine.scaffold import generate_project

    project_dir = generate_project("my-app", Path(tmpdir))
    assert project_dir.exists()

    # Expected files
    assert (project_dir / "profile.py").exists()
    assert (project_dir / "prodinamik.yaml").exists()
    assert (project_dir / "README.md").exists()
    assert (project_dir / "runs" / ".gitkeep").exists()

    # Verify profile.py is valid Python
    content = (project_dir / "profile.py").read_text()
    compile(content, "profile.py", "exec")


def test_generate_project_idempotent(tmpdir):
    """Generating same project twice raises FileExistsError"""
    from engine.scaffold import generate_project

    generate_project("my-app", Path(tmpdir))
    with pytest.raises(FileExistsError):
        generate_project("my-app", Path(tmpdir))


def test_list_profiles(tmp_profile_dir):
    """List profiles returns generated profiles"""
    from engine.scaffold import generate_profile, list_profiles

    generate_profile("alpha", tmp_profile_dir)
    generate_profile("beta", tmp_profile_dir)

    profiles = list_profiles(tmp_profile_dir)
    assert "alpha" in profiles
    assert "beta" in profiles


# ──────────────────────────────────────────────
# Benchmark Tests
# ──────────────────────────────────────────────


def test_benchmark_result():
    """BenchmarkResult properly calculates stats"""
    from engine.bench import BenchmarkResult

    r = BenchmarkResult(name="test")
    r.samples = [10.0, 20.0, 30.0]

    s = r.summary()
    assert s["avg"] == 20.0
    assert s["min"] == 10.0
    assert s["max"] == 30.0
    assert s["median"] == 20.0
    assert s["samples"] == 3


def test_benchmark_result_single():
    """BenchmarkResult handles single sample"""
    from engine.bench import BenchmarkResult

    r = BenchmarkResult(name="single")
    r.samples = [42.0]

    s = r.summary()
    assert s["avg"] == 42.0
    assert s["min"] == 42.0
    assert s["max"] == 42.0
    assert s["stddev"] == 0.0


def test_benchmark_result_empty():
    """BenchmarkResult handles no samples"""
    from engine.bench import BenchmarkResult

    r = BenchmarkResult(name="empty")
    s = r.summary()
    assert s["avg"] == 0.0
    assert s["samples"] == 0


def test_bench_event_store():
    """Event store benchmark completes without error"""
    from engine.bench import bench_event_store_append

    result = bench_event_store_append(iterations=2)
    assert result is not None
    assert len(result.samples) > 0


def test_bench_state_machine():
    """State machine benchmark completes"""
    from engine.bench import bench_state_machine_parsing

    result = bench_state_machine_parsing(iterations=2)
    assert result is not None
    assert len(result.samples) == 2


def test_bench_profile_discovery():
    """Profile discovery benchmark completes"""
    from engine.bench import bench_profile_discovery

    result = bench_profile_discovery(iterations=2)
    assert result is not None


def test_bench_wal_write():
    """WAL write benchmark completes"""
    from engine.bench import bench_wal_write

    result = bench_wal_write(iterations=2)
    assert result is not None
    assert len(result.samples) > 0


# ──────────────────────────────────────────────
# CLI Integration Tests
# ──────────────────────────────────────────────


def test_cli_version():
    """CLI version command works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "Prodinamik Engine" in result.output


def test_cli_completion_bash():
    """CLI completion bash works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "bash"])
    assert result.exit_code == 0
    assert "_prodinamik_completion" in result.output


def test_cli_completion_zsh():
    """CLI completion zsh works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "zsh"])
    assert result.exit_code == 0
    assert "#compdef prodinamik" in result.output


def test_cli_new_profile_help():
    """CLI new profile help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["new", "profile", "--help"])
    assert result.exit_code == 0
    assert "Generate a new profile module" in result.output


def test_cli_new_project_help():
    """CLI new project help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["new", "project", "--help"])
    assert result.exit_code == 0
    assert "Generate a new project scaffold" in result.output


def test_cli_shell_help():
    """CLI shell help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["shell", "--help"])
    assert result.exit_code == 0
    assert "Start interactive REPL shell" in result.output


def test_cli_benchmark_help():
    """CLI benchmark help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["benchmark", "--help"])
    assert result.exit_code == 0
    assert "Run performance benchmarks" in result.output


# ──────────────────────────────────────────────
# DebugCLI Integration Tests
# ──────────────────────────────────────────────


def test_debug_cli_help():
    """DebugCLI remains functional"""
    from engine.debug_cli import DebugCLI

    cli = DebugCLI()
    result = cli.handle("help")
    assert "timeline" in result
    assert "event" in result
    assert "summary" in result


def test_debug_cli_unknown():
    """DebugCLI handles unknown commands"""
    from engine.debug_cli import DebugCLI

    cli = DebugCLI()
    result = cli.handle("nonexistent")
    assert "timeline" in result  # Falls back to help


# ──────────────────────────────────────────────
# Async Engine Compatibility
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_with_shell_completer():
    """Engine works with shell completer"""
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine
    from engine.shell import Completer

    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)

    # Completer initializes without error
    completer = Completer(engine)
    assert completer._profile_cache
    assert len(completer._profile_cache) >= 1
