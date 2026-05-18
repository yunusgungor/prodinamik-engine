"""
Prodinamik Engine v1.1 — Raft Cluster Management

Cluster health monitoring, node discovery, failover, and demo.
"""

import time
import threading
from typing import Dict, List, Optional

from .raft_types import ClusterNode
from .raft_consensus import HybridConsensusNode


class RaftCluster:
    """Cluster management: health monitoring, node discovery, failover.

    Usage:
        cluster = RaftCluster(local_node)
        cluster.discover_peers(["node-a", "node-b"])
        print(cluster.health_report())
        cluster.elect_leader()
    """

    def __init__(self, local_node: HybridConsensusNode):
        self.local = local_node
        self.nodes: Dict[str, ClusterNode] = {}
        self._lock = threading.Lock()
        self._update_local()

    def _update_local(self):
        h = self.local.health()
        self.nodes[self.local.raft.node_id] = ClusterNode(
            node_id=h["node_id"],
            role=h["role"],
            last_seen=time.time(),
            healthy=not h["is_offline"],
            log_length=h["log_length"],
            state_count=h["state_count"],
        )

    def discover_peers(self, peer_ids: List[str]):
        with self._lock:
            for pid in peer_ids:
                if pid not in self.nodes:
                    self.nodes[pid] = ClusterNode(
                        node_id=pid,
                        last_seen=time.time(),
                    )

    def update_peer(self, node_id: str, health: dict):
        with self._lock:
            node = self.nodes.setdefault(node_id, ClusterNode(node_id=node_id))
            node.role = health.get("role", node.role)
            node.last_seen = time.time()
            node.healthy = not health.get("is_offline", False)
            node.log_length = health.get("log_length", 0)
            node.state_count = health.get("state_count", 0)

    def elect_leader(self) -> Optional[str]:
        leader = self.get_leader()
        if leader and leader.healthy:
            return leader.node_id
        if self.local.force_election():
            self._update_local()
            return self.local.raft.node_id
        return None

    def get_leader(self) -> Optional[ClusterNode]:
        return next((n for n in self.nodes.values() if n.role == "leader"), None)

    def health_report(self) -> dict:
        self._update_local()
        with self._lock:
            leader = self.get_leader()
            return {
                "cluster_size": len(self.nodes),
                "local_node": self.local.raft.node_id,
                "local_role": self.local.raft.role.value,
                "leader": leader.node_id if leader else None,
                "healthy_nodes": sum(1 for n in self.nodes.values() if n.healthy),
                "nodes": {
                    nid: {
                        "role": n.role,
                        "healthy": n.healthy,
                        "last_seen_ago": int(time.time() - n.last_seen),
                        "log_length": n.log_length,
                        "state_count": n.state_count,
                    }
                    for nid, n in sorted(self.nodes.items())
                },
            }

    def status_text(self) -> str:
        report = self.health_report()
        lines = [f"📡 Raft Cluster ({report['cluster_size']} nodes)"]
        lines.append(f"   Local: {report['local_node']} ({report['local_role']})")
        if report['leader']:
            lines.append(f"   Leader: {report['leader']}")
        lines.append(f"   Healthy: {report['healthy_nodes']}/{report['cluster_size']}")
        for nid, info in report['nodes'].items():
            health_icon = "🟢" if info['healthy'] else "🔴"
            ago = info['last_seen_ago']
            lines.append(f"   {health_icon} {nid} — {info['role']} ({ago}s ago, "
                         f"log={info['log_length']}, state={info['state_count']})")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import tempfile
    import os
    tmpdir = tempfile.mkdtemp()

    leader = HybridConsensusNode("node-1", ["node-2", "node-3"],
                                  state_dir=os.path.join(tmpdir, "raft1"))
    follower = HybridConsensusNode("node-2", ["node-1", "node-3"],
                                    state_dir=os.path.join(tmpdir, "raft2"))

    leader.raft.become_leader()
    print("📡 Cluster: node-1 (leader), node-2 (follower)")
    print(f"\n{leader.status()}")

    success, err = leader.apply({
        "type": "create",
        "slug": "flux-release",
        "initial_state": "spec"
    })
    assert success
    success, err = leader.apply({
        "type": "transition",
        "slug": "flux-release",
        "to_state": "prototyping"
    })
    assert success
    state = leader.get_state("flux-release")
    assert state.current_state == "prototyping"
    print(f"\n✅ Leader: flux-release → {state.current_state} (v{state.version})")

    follower.raft.log = list(leader.raft.log)
    follower.raft.commit_index = len(leader.raft.log) - 1
    follower.raft._apply_committed()
    fstate = follower.get_state("flux-release")
    print(f"✅ Follower: flux-release → {fstate.current_state} (v{fstate.version})")

    print(f"\n📱 Offline test:")
    follower_offline = HybridConsensusNode("node-2", ["node-1"],
                                            state_dir=os.path.join(tmpdir, "raft3"))
    follower_offline.offline.go_offline()
    follower_offline.apply({
        "type": "transition",
        "slug": "flux-release",
        "to_state": "iteration"
    })
    offline_state = follower_offline.get_state("flux-release")
    print(f"   Offline: flux-release → {offline_state.current_state} "
          f"(v{offline_state.version}, pending={follower_offline.offline.pending_count})")

    follower_offline.offline.is_offline = False
    follower_offline.reconnect(leader)

    final_state = leader.get_state("flux-release")
    print(f"\n✅ After reconnect: flux-release → {final_state.current_state}")
    assert final_state.current_state == "iteration", \
        f"Expected iteration, got {final_state.current_state}"
    print(f"   Version: v{final_state.version}")

    print(f"\n🔄 CRDT merge test:")
    leader.apply({"type": "transition", "slug": "flux-release", "to_state": "review"})

    from .raft_types import NodeState
    leader.raft.state_machine["test-run"] = NodeState(current_state="drafting", version=1)
    remote = NodeState(current_state="verification", version=1)

    from .raft_consensus import StateCRDT
    merged = StateCRDT.merge(
        leader.raft.state_machine["test-run"],
        remote,
        {"drafting": ["verification"], "verification": ["review"]}
    )
    print(f"   Local: drafting v1 + Remote: verification v1")
    print(f"   Merged: {merged.current_state} (forward path → verification wins)")

    print(f"\n{'='*50}")
    print(f"Hybrid Raft demo passed!")
    print(f"{'='*50}")
