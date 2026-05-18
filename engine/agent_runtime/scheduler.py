"""Prodinamik AI Grid — Scheduler

Assigns queued tasks to worker nodes based on capability affinity
and load balancing (least-loaded first).

Architecture:
    Scheduler
    ├── Capability-based assignment
    ├── Load-aware balancing (least-loaded first)
    ├── Affinity matching (task → node capability)
    └── Round-robin fallback

Usage:
    scheduler = Scheduler(agent_registry, task_queue)
    node_id = await scheduler.schedule(task)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from ..log import get_logger


class Scheduler:
    """
    Scheduler assigns queued tasks to worker nodes.
    
    Strategy:
    1. Match task affinity to node capabilities
    2. Among matching nodes, pick the least-loaded
    3. If no match, pick any alive, healthy node
    4. If no nodes available, task remains queued
    
    Usage:
        scheduler = Scheduler(agent_registry, task_queue)
        node_id = await scheduler.schedule(task)
        await scheduler.try_assign()  # Batch assign multiple tasks
    """
    
    def __init__(
        self,
        agent_registry: Any,  # AgentRegistry
        task_queue: Any,      # TaskQueue
    ):
        self.registry = agent_registry
        self.queue = task_queue
        self.log = get_logger()
        self._assignments: Dict[str, str] = {}  # task_id → node_id
        self._total_scheduled: int = 0
        self._total_failed_assign: int = 0
    
    async def schedule(self, task: Any) -> Optional[str]:
        """Schedule a single task to the best available node"""
        if not task or task.status.value != "queued":
            return None
        
        # Strategy 1: Match affinity
        if task.affinity:
            node_id = self.registry.find_best_node(affinity=task.affinity)
            if node_id:
                await self._assign(task, node_id)
                return node_id
        
        # Strategy 2: Try capability match from tools
        if task.tools:
            for tool in task.tools[:3]:  # First 3 tools as hints
                node_id = self.registry.find_best_node(capability=tool)
                if node_id:
                    await self._assign(task, node_id)
                    return node_id
        
        # Strategy 3: Any available node
        node_id = self.registry.find_best_node()
        if node_id:
            await self._assign(task, node_id)
            return node_id
        
        self._total_failed_assign += 1
        return None
    
    async def try_assign(self) -> int:
        """Try to assign all queued tasks to available nodes. Returns count assigned."""
        if not self.queue or not self.registry:
            return 0
        
        assigned = 0
        max_iterations = min(50, self.queue.queue_depth)
        
        for _ in range(max_iterations):
            # Get a queued task
            task = self.queue.dequeue()
            if not task:
                break
            
            node_id = await self.schedule(task)
            if node_id:
                assigned += 1
            else:
                # Put back in queue if no node available
                await self.queue.enqueue(task)
                break
        
        if assigned:
            self.log.debug(f"Scheduler: assigned {assigned} task(s)")
        
        return assigned
    
    async def _assign(self, task: Any, node_id: str) -> None:
        """Assign a task to a node"""
        await self.queue.acknowledge(task.task_id, node_id)
        self._assignments[task.task_id] = node_id
        self._total_scheduled += 1
        self.log.debug(f"Assigned task {task.task_id} → node {node_id}")
    
    def get_node_for_task(self, task_id: str) -> Optional[str]:
        """Get which node a task was assigned to"""
        return self._assignments.get(task_id)
    
    def get_tasks_for_node(self, node_id: str) -> List[str]:
        """Get all task IDs assigned to a node"""
        return [tid for tid, nid in self._assignments.items() if nid == node_id]
    
    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_scheduled": self._total_scheduled,
            "failed_assignments": self._total_failed_assign,
            "active_assignments": len(self._assignments),
        }
