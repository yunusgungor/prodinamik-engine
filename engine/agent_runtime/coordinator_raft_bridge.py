"""Prodinamik AI Grid — Raft-Coodinator Bridge

Observer pattern: watches Raft leader election events and
promotes/demotes the Coordinator accordingly.

Architecture:
    Raft (DistributedStateMachine)
        ↓ on_leader_elected / on_step_down callbacks
    CoordinatorRaftBridge (Observer)
        ↓ coordinator.start() / coordinator.stop()
    CoordinatorNode
        ↓ WAL replay + CRDT sync on promotion
        
Usage:
    bridge = CoordinatorRaftBridge(raft_node, coordinator)
    bridge.attach()  # Registers callbacks
    # Raft handles the rest automatically
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..log import get_logger


class BridgeState(Enum):
    DETACHED = "detached"
    STANDBY = "standby"
    ACTIVE = "active"
    TRANSITIONING = "transitioning"


class CoordinatorRaftBridge:
    """
    Observer bridge between Raft consensus and the Coordinator.
    
    When the Raft node becomes leader, the bridge promotes the
    Coordinator (start, WAL replay, CRDT sync).
    When the Raft node steps down, the bridge demotes the Coordinator.
    
    Usage:
        raft = HybridConsensusNode(...)
        coordinator = CoordinatorNode(...)
        bridge = CoordinatorRaftBridge(raft, coordinator)
        bridge.attach()
        
        # Later:
        bridge.detach()
    """
    
    def __init__(
        self,
        raft_node: Any,  # HybridConsensusNode
        coordinator: Any,  # CoordinatorNode
        wal_replay_timeout: float = 10.0,
        crdt_sync_timeout: float = 5.0,
    ):
        self.raft = raft_node
        self.coordinator = coordinator
        self.wal_replay_timeout = wal_replay_timeout
        self.crdt_sync_timeout = crdt_sync_timeout
        self.log = get_logger()
        self.state = BridgeState.DETACHED
        self._promotion_count = 0
        self._stepdown_count = 0
        self._last_transition_at: Optional[float] = None
        self._original_leader_cb = None
        self._original_stepdown_cb = None
        
    def attach(self) -> None:
        """Register callbacks with the Raft node"""
        if self.state != BridgeState.DETACHED:
            self.log.warning("Bridge already attached")
            return
        
        # Store originals in case we need to chain
        sm = self.raft.raft  # DistributedStateMachine
        self._original_leader_cb = sm.on_leader_elected
        self._original_stepdown_cb = sm.on_step_down
        
        # Register our callbacks
        sm.on_leader_elected = self._on_leader_elected
        sm.on_step_down = self._on_step_down
        
        self.state = BridgeState.STANDBY
        self.log.info(f"Bridge attached to Raft node {self.raft.raft.node_id}")
    
    def detach(self) -> None:
        """Remove callbacks from the Raft node"""
        if self.state == BridgeState.DETACHED:
            return
        
        sm = self.raft.raft  # DistributedStateMachine
        sm.on_leader_elected = self._original_leader_cb
        sm.on_step_down = self._original_stepdown_cb
        
        # Also stop coordinator if running
        if self.state == BridgeState.ACTIVE:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.coordinator.stop())
            except RuntimeError:
                pass
        
        self.state = BridgeState.DETACHED
        self.log.info("Bridge detached")
    
    def _on_leader_elected(self, node_id: str) -> None:
        """Called when the Raft node becomes leader"""
        if self._original_leader_cb:
            try:
                self._original_leader_cb(node_id)
            except Exception as e:
                self.log.debug(f"Original leader callback: {e}")
        
        self.state = BridgeState.TRANSITIONING
        self._last_transition_at = time.time()
        
        self.log.info(f"Leader elected: {node_id} (this node)")
        
        # Fire-and-forget the coordinator promotion
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._promote_coordinator())
            else:
                # Sync fallback — start coordinator directly
                self._promote_sync()
        except RuntimeError:
            self._promote_sync()
    
    def _on_step_down(self) -> None:
        """Called when the Raft node loses leadership"""
        if self._original_stepdown_cb:
            try:
                self._original_stepdown_cb()
            except Exception as e:
                self.log.debug(f"Original stepdown callback: {e}")
        
        self.state = BridgeState.TRANSITIONING
        self._last_transition_at = time.time()
        
        self.log.info(f"Leader stepdown on node {self.raft.raft.node_id}")
        
        # Demote coordinator
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._demote_coordinator())
            else:
                self._demote_sync()
        except RuntimeError:
            self._demote_sync()
    
    async def _promote_coordinator(self) -> None:
        """Full async coordinator promotion with state transfer"""
        self.log.info("Promoting coordinator...")
        
        try:
            # 1. Start coordinator
            await self.coordinator.start()
            
            # 2. WAL replay is automatic (TaskQueue._init_wal)
            # 3. Wait for heartbeats from workers
            if self.coordinator.agent_registry:
                self.log.info("Waiting for worker heartbeats...")
                await asyncio.sleep(3)  # Give workers time to re-register
            
            # 4. Rebuild scheduler state
            if self.coordinator.scheduler:
                await self.coordinator.try_assign()
            
            # 5. CRDT sync (if global memory available)
            if hasattr(self.coordinator, 'task_queue') and self.coordinator.task_queue:
                queue_stats = self.coordinator.task_queue.stats
                self.log.info(f"Task queue recovered: {queue_stats.get('queue_depth', 0)} queued, "
                             f"{queue_stats.get('active', 0)} active")
            
            self.state = BridgeState.ACTIVE
            self._promotion_count += 1
            self.log.info(f"Coordinator promoted on node {self.raft.raft.node_id}")
            
        except Exception as e:
            self.log.error(f"Coordinator promotion failed: {e}")
            self.state = BridgeState.STANDBY
    
    def _promote_sync(self) -> None:
        """Sync fallback for coordinator promotion"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._promote_coordinator())
        except Exception:
            self.log.warning("Cannot promote coordinator (no event loop)")
            self.state = BridgeState.STANDBY
    
    async def _demote_coordinator(self) -> None:
        """Demote coordinator on leader stepdown"""
        self.log.info("Demoting coordinator...")
        self._stepdown_count += 1
        
        try:
            await self.coordinator.stop()
            self.state = BridgeState.STANDBY
            self.log.info("Coordinator demoted")
        except Exception as e:
            self.log.error(f"Coordinator demotion failed: {e}")
            self.state = BridgeState.STANDBY
    
    def _demote_sync(self) -> None:
        """Sync fallback for coordinator demotion"""
        self.state = BridgeState.STANDBY
        self.log.info("Coordinator demoted (sync)")
    
    @property
    def is_active(self) -> bool:
        return self.state == BridgeState.ACTIVE
    
    @property
    def is_standby(self) -> bool:
        return self.state == BridgeState.STANDBY
    
    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "promotions": self._promotion_count,
            "stepdowns": self._stepdown_count,
            "raft_node_id": self.raft.raft.node_id if hasattr(self.raft, 'raft') else "unknown",
            "coordinator_active": self.coordinator.is_active if hasattr(self.coordinator, 'is_active') else False,
            "last_transition_at": self._last_transition_at,
        }
    
    async def force_promotion(self) -> bool:
        """Manually force coordinator promotion (for testing/demo)"""
        if self.state == BridgeState.ACTIVE:
            self.log.warning("Coordinator already active")
            return True
        
        await self._promote_coordinator()
        return self.state == BridgeState.ACTIVE
    
    async def force_demotion(self) -> bool:
        """Manually force coordinator demotion"""
        if self.state != BridgeState.ACTIVE:
            return True
        
        await self._demote_coordinator()
        return self.state == BridgeState.STANDBY
