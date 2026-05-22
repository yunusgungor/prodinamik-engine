"""Tests for StateGuard HITL → Prodinamik Human Loop Bridge.

Tests cover:
1. ProdinamikHITLHandler creation — type/validity guards
2. request_approval — creates escalation in HumanLoopManager
3. check_approval — reads back pending/decided status + auto-timeout
4. resolve_approval — approve / reject delegation
5. get_pending_requests — lists active requests
6. on_timeout — fail-close default
7. Callbacks — on_escalate / on_review
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from engine.hitl_bridge import ProdinamikHITLHandler
from engine.agent_runtime.human_loop import (
    HumanLoopManager,
    ReviewStatus,
    EscalationReason,
)


# ═══════════════════════════════════════════════
# 1. Creation
# ═══════════════════════════════════════════════


class TestCreation:
    def test_default_creation(self):
        """Create with default timeout."""
        h = ProdinamikHITLHandler()
        assert h.timeout_minutes == 5
        assert h.loop is not None

    def test_custom_timeout(self):
        h = ProdinamikHITLHandler(timeout_minutes=10)
        assert h.timeout_minutes == 10

    def test_custom_loop(self):
        loop = HumanLoopManager()
        h = ProdinamikHITLHandler(human_loop=loop)
        assert h.loop is loop

    def test_timeout_bool_raises(self):
        with pytest.raises(TypeError, match="must be an int"):
            ProdinamikHITLHandler(timeout_minutes=True)

    def test_timeout_negative_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            ProdinamikHITLHandler(timeout_minutes=-1)

    def test_pending_count_starts_zero(self):
        h = ProdinamikHITLHandler()
        assert h.pending_count == 0


# ═══════════════════════════════════════════════
# 2. request_approval
# ═══════════════════════════════════════════════


class TestRequestApproval:
    def test_returns_expected_keys(self):
        h = ProdinamikHITLHandler(timeout_minutes=5)
        result = h.request_approval({"step": "test", "error": "failed"})
        assert "request_id" in result
        assert result["status"] == "pending"
        assert "timeout_at" in result
        assert result["timeout_minutes"] == 5

    def test_request_id_format(self):
        h = ProdinamikHITLHandler()
        result = h.request_approval({"step": "tier_1"})
        assert result["request_id"].startswith("hitl_")

    def test_pending_count_increments(self):
        h = ProdinamikHITLHandler()
        assert h.pending_count == 0
        h.request_approval({"step": "tier_1"})
        # Allow async escalation to propagate
        import time
        time.sleep(0.1)
        assert h.pending_count == 1

    def test_invalid_step_info_raises(self):
        h = ProdinamikHITLHandler()
        with pytest.raises(TypeError, match="step_info must be a dict"):
            h.request_approval("not a dict")

    def test_multiple_requests_unique_ids(self):
        h = ProdinamikHITLHandler()
        r1 = h.request_approval({"step": "a"})
        r2 = h.request_approval({"step": "b"})
        assert r1["request_id"] != r2["request_id"]


# ═══════════════════════════════════════════════
# 3. check_approval
# ═══════════════════════════════════════════════


class TestCheckApproval:
    def test_pending_status(self):
        h = ProdinamikHITLHandler(timeout_minutes=60)
        req = h.request_approval({"step": "tier_1"})
        time.sleep(0.05)
        status = h.check_approval(req["request_id"])
        assert status["status"] == "pending"
        assert status["approved"] is None

    def test_approved_status(self):
        h = ProdinamikHITLHandler()
        req = h.request_approval({"step": "tier_1"})
        time.sleep(0.05)

        # Resolve via bridge
        h.resolve_approval(req["request_id"], approved=True, reason="looks good")

        status = h.check_approval(req["request_id"])
        assert status["status"] == "decided"
        assert status["approved"] is True
        assert status["reason"] == "looks good"

    def test_rejected_status(self):
        h = ProdinamikHITLHandler()
        req = h.request_approval({"step": "tier_1"})
        time.sleep(0.05)

        h.resolve_approval(req["request_id"], approved=False, reason="bad output")

        status = h.check_approval(req["request_id"])
        assert status["status"] == "decided"
        assert status["approved"] is False
        assert "bad output" in status["reason"]

    def test_unknown_request_id_raises(self):
        h = ProdinamikHITLHandler()
        with pytest.raises(KeyError, match="not found"):
            h.check_approval("nonexistent")


# ═══════════════════════════════════════════════
# 4. resolve_approval
# ═══════════════════════════════════════════════


class TestResolveApproval:
    def test_approve(self):
        h = ProdinamikHITLHandler()
        req = h.request_approval({"step": "tier_1"})
        time.sleep(0.05)

        result = h.resolve_approval(req["request_id"], approved=True)
        assert result["status"] == "decided"
        assert result["approved"] is True

    def test_reject(self):
        h = ProdinamikHITLHandler()
        req = h.request_approval({"step": "tier_1"})
        time.sleep(0.05)

        result = h.resolve_approval(req["request_id"], approved=False)
        assert result["status"] == "decided"
        assert result["approved"] is False

    def test_unknown_request_raises(self):
        h = ProdinamikHITLHandler()
        with pytest.raises(KeyError, match="not found"):
            h.resolve_approval("nonexistent", True)

    def test_non_bool_approved_raises(self):
        h = ProdinamikHITLHandler()
        req = h.request_approval({"step": "test"})
        time.sleep(0.05)
        with pytest.raises(TypeError, match="approved must be a bool"):
            h.resolve_approval(req["request_id"], approved="yes")  # type: ignore


# ═══════════════════════════════════════════════
# 5. get_pending_requests
# ═══════════════════════════════════════════════


class TestGetPendingRequests:
    def test_empty_when_no_requests(self):
        h = ProdinamikHITLHandler()
        result = h.get_pending_requests()
        assert result["count"] == 0
        assert result["pending"] == []

    def test_returns_pending_items(self):
        h = ProdinamikHITLHandler(timeout_minutes=60)
        h.request_approval({"step": "tier_1", "error": "low score"})
        time.sleep(0.05)

        result = h.get_pending_requests()
        assert result["count"] >= 1
        assert result["pending"][0]["request_id"].startswith("hitl_")

    def test_resolved_not_in_pending(self):
        h = ProdinamikHITLHandler(timeout_minutes=60)
        req = h.request_approval({"step": "tier_1"})
        time.sleep(0.05)

        h.resolve_approval(req["request_id"], approved=True)
        result = h.get_pending_requests()
        assert result["count"] == 0


# ═══════════════════════════════════════════════
# 6. on_timeout
# ═══════════════════════════════════════════════


class TestOnTimeout:
    def test_fail_close_default(self):
        h = ProdinamikHITLHandler()
        result = h.on_timeout()
        assert result["approved"] is False
        assert result["reason"] == "timeout"


# ═══════════════════════════════════════════════
# 7. Callbacks
# ═══════════════════════════════════════════════


class TestCallbacks:
    def test_on_escalate_registers(self):
        h = ProdinamikHITLHandler()
        cb = MagicMock()
        h.on_escalate(cb)
        assert cb in h.loop._callbacks_on_escalate

    def test_on_review_registers(self):
        h = ProdinamikHITLHandler()
        cb = MagicMock()
        h.on_review(cb)
        assert cb in h.loop._callbacks_on_review

    def test_stats(self):
        h = ProdinamikHITLHandler()
        stats = h.stats()
        assert "pending" in stats
        assert "total_escalated" in stats
