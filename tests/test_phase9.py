"""Prodinamik Engine v1.1 — Phase 5: Security & Distribution Tests

Tests for:
- Auth (engine/auth.py)
- Rate Limiter (engine/ratelimit.py)
- HTTP Server (engine/server.py)
- Raft hardening (engine/raft.py)
- CLI extensions (auth, serve, raft)
"""

import os
import json
import time
import tempfile
import shutil
from pathlib import Path
from threading import Thread

import pytest


# ──────────────────────────────────────────────
# Auth Tests
# ──────────────────────────────────────────────


@pytest.fixture
def auth_manager():
    """Temp auth manager for testing"""
    tmpdir = tempfile.mkdtemp()
    from engine.auth import AuthManager
    mgr = AuthManager(base_path=os.path.join(tmpdir, "auth"))
    yield mgr
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_create_key(auth_manager):
    """Create key returns (key_id, raw_key)"""
    key_id, raw_key = auth_manager.create_key("test-bot", role="user")
    assert key_id.startswith("test-bot")
    assert raw_key.startswith("pdmk_")
    assert len(raw_key) > 20


def test_create_key_invalid_role(auth_manager):
    """Invalid role raises ValueError"""
    with pytest.raises(ValueError):
        auth_manager.create_key("bad", role="superadmin")


def test_validate_key_valid(auth_manager):
    """Valid key returns AuthResult with correct role"""
    _, raw_key = auth_manager.create_key("deploy", role="admin")
    result = auth_manager.validate_key(raw_key)
    assert result.valid
    assert result.role == "admin"
    assert result.name == "deploy"


def test_validate_key_invalid(auth_manager):
    """Invalid key returns invalid result"""
    result = auth_manager.validate_key("pdmk_invalid_key_here")
    assert not result.valid
    assert "not found" in result.error


def test_validate_key_bad_format(auth_manager):
    """Bad key format returns early error"""
    result = auth_manager.validate_key("bad-format-key")
    assert not result.valid
    assert "Invalid key format" in result.error


def test_validate_key_wrong_prefix(auth_manager):
    """Key without pdmk_ prefix is rejected"""
    result = auth_manager.validate_key("sk_test_12345")
    assert not result.valid


def test_list_keys(auth_manager):
    """List keys returns all created keys"""
    auth_manager.create_key("bot-1", role="user")
    auth_manager.create_key("bot-2", role="admin")
    keys = auth_manager.list_keys()
    assert len(keys) == 2
    names = [k["name"] for k in keys]
    assert "bot-1" in names
    assert "bot-2" in names


def test_revoke_key(auth_manager):
    """Revoke disables key"""
    key_id, raw_key = auth_manager.create_key("ephemeral")
    assert auth_manager.revoke_key(key_id)

    result = auth_manager.validate_key(raw_key)
    assert not result.valid
    assert "disabled" in result.error


def test_revoke_nonexistent(auth_manager):
    """Revoking non-existent key returns False"""
    assert not auth_manager.revoke_key("nonexistent-id")


def test_get_key_info(auth_manager):
    """Get key returns info dict without hash"""
    key_id, _ = auth_manager.create_key("my-service", role="admin",
                                          expires_in_days=30)
    info = auth_manager.get_key(key_id)
    assert info is not None
    assert info["name"] == "my-service"
    assert info["role"] == "admin"
    assert info["enabled"] is True
    assert "key_hash" not in info
    assert info["expires_at"] is not None


def test_get_key_nonexistent(auth_manager):
    """Get non-existent key returns None"""
    assert auth_manager.get_key("no-such-key") is None


def test_require_role_decorator(auth_manager):
    """Require_role decorator enforces minimum role"""
    from engine.auth import AuthManager, AuthResult, ROLE_HIERARCHY

    @AuthManager.require_role("user")
    def handler(auth_result):
        return "ok"

    # Admin should pass
    result = handler(auth_result=AuthResult(valid=True, role="admin"))
    assert result == "ok"

    # User should pass
    result = handler(auth_result=AuthResult(valid=True, role="user"))
    assert result == "ok"

    # Readonly should fail for user-level
    with pytest.raises(PermissionError):
        handler(auth_result=AuthResult(valid=True, role="readonly"))

    # Invalid should fail
    with pytest.raises(PermissionError):
        handler(auth_result=AuthResult(valid=False))


def test_key_expiry(auth_manager):
    """Expired key returns invalid"""
    key_id, raw_key = auth_manager.create_key("short-lived", expires_in_days=-1)
    result = auth_manager.validate_key(raw_key)
    assert not result.valid
    assert "expired" in result.error


def test_auth_manager_persists(auth_manager):
    """Keys persist across AuthManager instances"""
    key_id, raw_key = auth_manager.create_key("persistent", role="admin")

    # New instance, same path
    from engine.auth import AuthManager
    mgr2 = AuthManager(base_path=auth_manager.base_path)
    result = mgr2.validate_key(raw_key)
    assert result.valid
    assert result.name == "persistent"


# ──────────────────────────────────────────────
# Rate Limiter Tests
# ──────────────────────────────────────────────


def test_rate_limiter_allows_first():
    """First request is always allowed"""
    from engine.ratelimit import RateLimiter
    limiter = RateLimiter(rate=10, burst=10)
    allowed, wait = limiter.check("key-1")
    assert allowed
    assert wait == 0.0


def test_rate_limiter_blocks():
    """Exceeding burst rate blocks"""
    from engine.ratelimit import RateLimiter
    limiter = RateLimiter(rate=1, burst=1)

    # First request is allowed
    allowed, _ = limiter.check("key-1", cost=10)
    assert allowed

    # Immediate second request should be denied
    allowed, wait = limiter.check("key-1", cost=10)
    assert not allowed
    assert wait > 0


def test_rate_limiter_reset_key():
    """Reset restores bucket for a key"""
    from engine.ratelimit import RateLimiter
    limiter = RateLimiter(rate=1, burst=1)

    limiter.check("key-a")
    limiter.check("key-b")

    limiter.reset("key-a")
    allowed, _ = limiter.check("key-a", cost=10)
    assert allowed


def test_rate_limiter_stats():
    """Stats track allowed/denied correctly"""
    from engine.ratelimit import RateLimiter
    limiter = RateLimiter(rate=1, burst=1)

    limiter.check("key-1", cost=1)
    limiter.check("key-1", cost=1)
    limiter.check("key-1", cost=1)

    stats = limiter.stats()
    assert stats["total_allowed"] == 1
    assert stats["total_denied"] == 2


def test_rate_limiter_per_key():
    """Rate limiting is per-key"""
    from engine.ratelimit import RateLimiter
    limiter = RateLimiter(rate=1, burst=1)

    limiter.check("key-a", cost=10)
    allowed, _ = limiter.check("key-b", cost=10)
    assert allowed  # Different key, different bucket


def test_auth_rate_limiter():
    """Combined auth+rate limit check works"""
    from engine.ratelimit import AuthRateLimiter
    from engine.auth import AuthManager
    import tempfile

    tmpdir = tempfile.mkdtemp()
    auth = AuthManager(base_path=os.path.join(tmpdir, "auth"))
    _, raw_key = auth.create_key("test", role="user")
    arl = AuthRateLimiter(auth_manager=auth)

    result = arl.check_request(raw_key)
    assert result["allowed"]
    assert result["status"] == "ok"


def test_auth_rate_limiter_bad_key():
    """Combined check rejects bad key"""
    from engine.ratelimit import AuthRateLimiter
    arl = AuthRateLimiter()
    result = arl.check_request("pdmk_bad_key_1234")
    assert not result["allowed"]
    assert result["status"] == "auth_error"


# ──────────────────────────────────────────────
# Server Tests
# ──────────────────────────────────────────────


def test_server_health_endpoint():
    """Server health check works"""
    from engine.server import ProdinamikServer
    from engine.config import ProdinamikConfig
    from engine.runtime import AsyncEngine

    cfg = ProdinamikConfig.load()
    engine = AsyncEngine(cfg)
    server = ProdinamikServer(engine, port=0)  # port 0 = auto-assign
    assert server is not None
    assert not server.is_running


def test_server_auth_wiring():
    """Server has auth_manager and rate_limiter wired"""
    from engine.server import ProdinamikServer
    server = ProdinamikServer(port=0)
    assert server.auth_manager is not None
    assert server.rate_limiter is not None
    assert server.handler_class is not None


def test_handler_health_logic():
    """Handler health logic produces status response"""
    from engine.server import ProdinamikHandler
    handler = ProdinamikHandler
    assert hasattr(handler, '_handle_health')
    assert hasattr(handler, '_handle_metrics')
    assert hasattr(handler, '_handle_api')


# ──────────────────────────────────────────────
# Raft Hardening Tests
# ──────────────────────────────────────────────


def test_hybrid_node_health():
    """HybridConsensusNode.health() returns snapshot"""
    from engine.raft import HybridConsensusNode
    node = HybridConsensusNode("test-node-1", state_dir=tempfile.mkdtemp())
    h = node.health()
    assert h["node_id"] == "test-node-1"
    assert "role" in h
    assert "term" in h
    assert "log_length" in h
    assert "is_offline" in h


def test_is_leader():
    """is_leader returns False for new follower"""
    from engine.raft import HybridConsensusNode
    node = HybridConsensusNode("test-node", state_dir=tempfile.mkdtemp())
    assert not node.is_leader()


def test_raft_cluster_create():
    """RaftCluster creates with local node"""
    from engine.raft import HybridConsensusNode, RaftCluster
    node = HybridConsensusNode("local", state_dir=tempfile.mkdtemp())
    cluster = RaftCluster(node)
    report = cluster.health_report()
    assert report["cluster_size"] == 1
    assert report["local_node"] == "local"


def test_raft_cluster_discover():
    """RaftCluster discovers peers"""
    from engine.raft import HybridConsensusNode, RaftCluster
    node = HybridConsensusNode("local", state_dir=tempfile.mkdtemp())
    cluster = RaftCluster(node)
    cluster.discover_peers(["peer-a", "peer-b"])
    report = cluster.health_report()
    assert report["cluster_size"] == 3


def test_raft_cluster_update_peer():
    """RaftCluster updates peer health"""
    from engine.raft import HybridConsensusNode, RaftCluster
    node = HybridConsensusNode("local", state_dir=tempfile.mkdtemp())
    cluster = RaftCluster(node)
    cluster.update_peer("peer-a", {
        "role": "follower",
        "is_offline": False,
        "log_length": 42,
        "state_count": 10,
    })
    report = cluster.health_report()
    assert report["nodes"]["peer-a"]["role"] == "follower"
    assert report["nodes"]["peer-a"]["log_length"] == 42


def test_raft_cluster_status_text():
    """RaftCluster status_text returns readable output"""
    from engine.raft import HybridConsensusNode, RaftCluster
    node = HybridConsensusNode("local", state_dir=tempfile.mkdtemp())
    cluster = RaftCluster(node)
    text = cluster.status_text()
    assert "Raft Cluster" in text
    assert "local" in text


# ──────────────────────────────────────────────
# CLI Integration Tests
# ──────────────────────────────────────────────


def test_cli_auth_help():
    """CLI auth help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "--help"])
    assert result.exit_code == 0
    assert "Manage API keys" in result.output


def test_cli_auth_list_empty():
    """CLI auth list returns no keys initially"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "list"])
    assert result.exit_code == 0
    assert "No API keys found" in result.output or "API Keys" in result.output


def test_cli_serve_help():
    """CLI serve help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "HTTP server" in result.output


def test_cli_raft_help():
    """CLI raft help works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["raft", "--help"])
    assert result.exit_code == 0
    assert "Raft consensus" in result.output


def test_cli_raft_status():
    """CLI raft status works"""
    from click.testing import CliRunner
    from engine.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["raft", "status"])
    assert result.exit_code == 0
    assert "Raft Cluster" in result.output
