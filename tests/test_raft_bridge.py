"""Tests for Prodinamik AI Grid — Raft-Coodinator Bridge"""

import os
import sys
import json
import time
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.raft import HybridConsensusNode
from engine.raft_types import NodeRole
from engine.agent_runtime import (
    CoordinatorNode, CoordinatorConfig,
    CoordinatorRaftBridge, BridgeState,
)


# ════════════════════════════════════════════════
# Raft Callback Tests
# ════════════════════════════════════════════════

class TestRaftCallbacks:
    def test_become_leader_fires_callback(self):
        raft = HybridConsensusNode(node_id="test-leader", enable_transport=False)
        triggered = []
        
        raft.raft.on_leader_elected = lambda nid: triggered.append(nid)
        raft.raft.become_leader()
        
        assert len(triggered) == 1
        assert triggered[0] == "test-leader"
        assert raft.raft.role == NodeRole.LEADER

    def test_become_follower_from_leader_fires_stepdown(self):
        raft = HybridConsensusNode(node_id="test-stepdown", enable_transport=False)
        triggered = []
        
        raft.raft.on_leader_elected = lambda nid: None
        raft.raft.on_step_down = lambda: triggered.append("stepdown")
        
        # Become leader first
        raft.raft.become_leader()
        assert len(triggered) == 0  # stepdown not yet fired
        
        # Then step down
        raft.raft.become_follower(term=2)
        assert len(triggered) == 1

    def test_follower_to_follower_does_not_fire_stepdown(self):
        raft = HybridConsensusNode(node_id="test-noop", enable_transport=False)
        triggered = []
        
        raft.raft.on_step_down = lambda: triggered.append("stepdown")
        
        # Already follower, become follower again
        raft.raft.become_follower(term=1)
        assert len(triggered) == 0  # Should NOT fire

    def test_callbacks_can_be_none(self):
        raft = HybridConsensusNode(node_id="test-none", enable_transport=False)
        # No callbacks set — should not crash
        raft.raft.become_leader()
        raft.raft.become_follower(term=1)
        assert True  # No exception


# ════════════════════════════════════════════════
# Bridge Tests
# ════════════════════════════════════════════════

class TestCoordinatorRaftBridge:
    def test_attach_detach(self):
        raft = HybridConsensusNode(node_id="bridge-test", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig(node_id="coord-test"))
        bridge = CoordinatorRaftBridge(raft, coord)
        
        assert bridge.state == BridgeState.DETACHED
        bridge.attach()
        assert bridge.state == BridgeState.STANDBY
        assert raft.raft.on_leader_elected is not None
        assert raft.raft.on_step_down is not None
        
        bridge.detach()
        assert bridge.state == BridgeState.DETACHED

    def test_double_attach(self):
        raft = HybridConsensusNode(node_id="test", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig())
        bridge = CoordinatorRaftBridge(raft, coord)
        
        bridge.attach()
        bridge.attach()  # Should log warning but not error
        assert bridge.state == BridgeState.STANDBY

    def test_detach_when_not_attached(self):
        raft = HybridConsensusNode(node_id="test", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig())
        bridge = CoordinatorRaftBridge(raft, coord)
        
        bridge.detach()  # Should be no-op
        assert bridge.state == BridgeState.DETACHED

    def test_bridge_stats(self):
        raft = HybridConsensusNode(node_id="test", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig())
        bridge = CoordinatorRaftBridge(raft, coord)
        bridge.attach()
        
        stats = bridge.stats
        assert "state" in stats
        assert "promotions" in stats
        assert "stepdowns" in stats
        assert stats["state"] == "standby"

    @pytest.mark.asyncio
    async def test_leader_election_triggers_promotion(self):
        raft = HybridConsensusNode(node_id="test-promote", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig(node_id="coord-promote"))
        bridge = CoordinatorRaftBridge(raft, coord)
        bridge.attach()
        
        # Simulate leader election
        raft.raft.become_leader()
        
        # Give async promotion a moment to start
        await asyncio.sleep(0.1)
        
        # Bridge should be in transitioning or active state
        assert bridge.state in (BridgeState.TRANSITIONING, BridgeState.ACTIVE)

    @pytest.mark.asyncio
    async def test_force_promotion_and_demotion(self):
        raft = HybridConsensusNode(node_id="test-force", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig(node_id="coord-force"))
        bridge = CoordinatorRaftBridge(raft, coord)
        bridge.attach()
        
        ok = await bridge.force_promotion()
        assert ok
        assert bridge.is_active
        assert bridge.stats["promotions"] > 0
        
        ok = await bridge.force_demotion()
        assert ok
        assert bridge.is_standby
        assert bridge.stats["stepdowns"] > 0

    @pytest.mark.asyncio
    async def test_force_promotion_when_already_active(self):
        raft = HybridConsensusNode(node_id="test-already", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig())
        bridge = CoordinatorRaftBridge(raft, coord)
        bridge.attach()
        
        await bridge.force_promotion()
        assert bridge.is_active
        
        # Second promotion should be safe
        ok = await bridge.force_promotion()
        assert ok
        assert bridge.is_active

    def test_bridge_standby_property(self):
        raft = HybridConsensusNode(node_id="test", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig())
        bridge = CoordinatorRaftBridge(raft, coord)
        
        # DETACHED is not standny
        assert not bridge.is_standby
        assert not bridge.is_active
        
        # After attach but not promoted, it should be standby
        bridge.attach()
        assert bridge.is_standby


# ════════════════════════════════════════════════
# Integration: Raft → Bridge → Coordinator
# ════════════════════════════════════════════════

class TestRaftBridgeCoordinatorIntegration:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Raft leader election → bridge promotion → coordinator active"""
        raft = HybridConsensusNode(node_id="integration-node", enable_transport=False)
        coord = CoordinatorNode(CoordinatorConfig(node_id="integration-coord"))
        bridge = CoordinatorRaftBridge(raft, coord)
        
        # 1. Attach bridge
        bridge.attach()
        assert bridge.state == BridgeState.STANDBY
        
        # 2. Raft becomes leader → bridge promotes coordinator
        raft.raft.become_leader()
        
        # Give async promotion time
        await asyncio.sleep(0.2)
        
        # 3. Bridge should be promoted
        assert bridge.is_active or bridge.state == BridgeState.TRANSITIONING
        
        # 4. Raft steps down → bridge demotes coordinator
        raft.raft.become_follower(term=2)
        await asyncio.sleep(0.2)
        
        # 5. Bridge back to standby
        assert bridge.is_standby or bridge.state == BridgeState.TRANSITIONING
        
        # 6. Detach cleanly
        bridge.detach()
        assert bridge.state == BridgeState.DETACHED
