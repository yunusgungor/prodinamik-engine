"""Prodinamik Engine v1.0 — Shared Test Fixtures"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.state_machine import StateMachineParser, StateMachine
from profiles.software import SoftwareProfile
from profiles.content import ContentProfile
from profiles.research import ResearchProfile
from profiles.design import DesignProfile


# ──────────────────────────────────────────────
# Shared State Machine Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def sm() -> StateMachine:
    """Software StateMachine fixture (from profiles/software.py)"""
    config = StateMachineParser.parse_string(SoftwareProfile.state_machine_yaml)
    return StateMachine(config)


@pytest.fixture(scope="module")
def content_sm() -> StateMachine:
    """Content StateMachine fixture (from profiles/content.py)"""
    config = StateMachineParser.parse_string(ContentProfile.state_machine_yaml)
    return StateMachine(config)


@pytest.fixture(scope="module")
def research_sm() -> StateMachine:
    """Research StateMachine fixture"""
    config = StateMachineParser.parse_string(ResearchProfile.state_machine_yaml)
    return StateMachine(config)


@pytest.fixture(scope="module")
def design_sm() -> StateMachine:
    """Design StateMachine fixture"""
    config = StateMachineParser.parse_string(DesignProfile.state_machine_yaml)
    return StateMachine(config)


# ──────────────────────────────────────────────
# Shared Profile Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def sw_profile() -> SoftwareProfile:
    """Initialized SoftwareProfile fixture"""
    profile = SoftwareProfile()
    profile.initialize()
    return profile


@pytest.fixture(scope="module")
def ct_profile() -> ContentProfile:
    """Initialized ContentProfile fixture"""
    profile = ContentProfile()
    profile.initialize()
    return profile


@pytest.fixture(scope="module")
def rs_profile() -> ResearchProfile:
    """Initialized ResearchProfile fixture"""
    profile = ResearchProfile()
    profile.initialize()
    return profile


@pytest.fixture(scope="module")
def ds_profile() -> DesignProfile:
    """Initialized DesignProfile fixture"""
    profile = DesignProfile()
    profile.initialize()
    return profile


# ──────────────────────────────────────────────
# Shared RunManager Fixture
# ──────────────────────────────────────────────

@pytest.fixture
def run_manager():
    """Fresh RunManager with temp directory"""
    from engine.run_manager import RunManager
    tmpdir = tempfile.mkdtemp()
    return tmpdir, RunManager(base_path=os.path.join(tmpdir, ".hermes"))


# ──────────────────────────────────────────────
# Chaos Engine Fixture
# ──────────────────────────────────────────────


@pytest.fixture
def chaos_engine():
    """ChaosEngine with temp directory (returns chaos, engine, tmpdir)"""
    from engine.chaos import ChaosEngine
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    tmpdir = tempfile.mkdtemp()
    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)
    chaos = ChaosEngine(engine, base_path=tmpdir)
    return chaos, engine, tmpdir
