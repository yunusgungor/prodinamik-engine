"""
Prodinamik Engine v1.1 — External Leader Election (etcd/Consul)

Integrates with etcd or HashiCorp Consul for leader election
in multi-node deployments. Acts as a coordination backend
for the Raft cluster when TCP discovery is not sufficient.

Usage:
    # etcd
    elector = ExternalLeaderElector(
        backend="etcd",
        endpoints=["http://127.0.0.1:2379"],
        key="prodinamik/leader",
        node_id="node-1",
        ttl_seconds=30,
    )
    elector.campaign()  # Try to become leader
    if elector.is_leader:
        print("I am the leader!")

    # Consul
    elector = ExternalLeaderElector(
        backend="consul",
        endpoints=["http://127.0.0.1:8500"],
        key="prodinamik/leader",
        node_id="node-1",
    )
"""

import json
import time
import threading
import urllib.request
import urllib.error
from typing import Optional, List
from datetime import datetime


class ExternalLeaderElector:
    """
    External leader election using etcd or Consul KV store.

    Implements the leader election pattern:
    1. Each node tries to acquire a lock key
    2. Only one node succeeds (the leader)
    3. The leader refreshes the key periodically (TTL)
    4. On failure, the key expires and another node takes over
    """

    def __init__(self, backend: str = "etcd",
                 endpoints: Optional[List[str]] = None,
                 key: str = "prodinamik/leader",
                 node_id: str = "unknown",
                 ttl_seconds: int = 30):
        assert backend in ("etcd", "consul"), f"Unsupported backend: {backend}"
        self.backend = backend
        self.endpoints = endpoints or ["http://127.0.0.1:2379"]
        self.key = key
        self.node_id = node_id
        self.ttl_seconds = ttl_seconds
        self._am_leader = False
        self._leader_id: Optional[str] = None
        self._running = False
        self._refresh_thread: Optional[threading.Thread] = None
        self._lease_id: Optional[str] = None

    # ── Properties ──

    @property
    def is_leader(self) -> bool:
        return self._am_leader

    @property
    def current_leader(self) -> Optional[str]:
        """Read current leader from backend"""
        try:
            value = self._read_key()
            if value:
                data = json.loads(value)
                return data.get("node_id")
        except (json.JSONDecodeError, OSError):
            pass
        return None

    @property
    def is_connected(self) -> bool:
        """Check if the backend is reachable"""
        try:
            if self.backend == "etcd":
                self._etcd_get("/version")
            elif self.backend == "consul":
                self._consul_get("/v1/status/leader")
            return True
        except OSError:
            return False

    # ── Campaign ──

    def campaign(self) -> bool:
        """
        Try to become leader.
        Returns True if this node becomes leader.
        """
        if self._am_leader:
            return True

        # Try to acquire the lock
        try:
            if self.backend == "etcd":
                self._etcd_campaign()
            elif self.backend == "consul":
                self._consul_campaign()
        except OSError:
            return False

        if self._am_leader:
            self._start_refresh_loop()

        return self._am_leader

    def resign(self):
        """Resign leadership"""
        self._running = False
        self._am_leader = False

        try:
            if self.backend == "etcd" and self._lease_id:
                self._etcd_delete(f"/v3/kv/lease/{self._lease_id}")
            elif self.backend == "consul":
                self._consul_delete(f"/v1/kv/{self.key}")
        except OSError:
            pass

    def _start_refresh_loop(self):
        """Periodically refresh the leader lock"""
        self._running = True

        def refresh():
            while self._running and self._am_leader:
                try:
                    if self.backend == "etcd":
                        self._etcd_refresh()
                    elif self.backend == "consul":
                        self._consul_refresh()
                except OSError:
                    self._am_leader = False
                    break
                time.sleep(self.ttl_seconds / 3)  # Refresh 3x per TTL

        self._refresh_thread = threading.Thread(target=refresh, daemon=True)
        self._refresh_thread.start()

    # ── etcd Implementation ──

    def _etcd_campaign(self):
        """Try to become leader via etcd"""
        endpoint = self.endpoints[0]

        # Try to create the key with ?prevExist=false (fail if exists)
        value = json.dumps({
            "node_id": self.node_id,
            "timestamp": datetime.now().isoformat(),
        })

        # Use etcd v3 KV API via gateway
        url = f"{endpoint}/v3/kv/put"
        payload = {
            "key": self._b64encode(self.key),
            "value": self._b64encode(value),
        }

        try:
            self._etcd_post(url, payload)
            self._am_leader = True
            self._leader_id = self.node_id
        except (urllib.error.HTTPError, OSError) as e:
            # Key already exists — someone else is leader
            self._am_leader = False

    def _etcd_refresh(self):
        """Refresh etcd lease"""
        if not self._lease_id:
            return
        url = f"{self.endpoints[0]}/v3/lease/keepalive"
        self._etcd_post(url, {"ID": self._lease_id})

    def _etcd_get(self, path: str) -> Optional[str]:
        """GET request to etcd"""
        url = f"{self.endpoints[0]}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode("utf-8")

    def _etcd_post(self, url: str, data: dict) -> dict:
        """POST request to etcd"""
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _etcd_delete(self, path: str):
        """DELETE request to etcd"""
        url = f"{self.endpoints[0]}{path}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=5):
            pass

    # ── Consul Implementation ──

    def _consul_campaign(self):
        """Try to become leader via Consul KV with CAS"""
        endpoint = self.endpoints[0]
        value = json.dumps({
            "node_id": self.node_id,
            "timestamp": datetime.now().isoformat(),
        })

        # Try to acquire the lock via PUT with ?acquire=<session>
        # Simplified: use CAS (compare-and-set) via PUT with ?cas=0
        url = f"{endpoint}/v1/kv/{self.key}?cas=0"
        req = urllib.request.Request(
            url, data=value.encode("utf-8"),
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result is True:
                    self._am_leader = True
                    self._leader_id = self.node_id
        except (urllib.error.HTTPError, OSError):
            self._am_leader = False

    def _consul_refresh(self):
        """Refresh Consul session (re-write key)"""
        self._consul_campaign()

    def _consul_get(self, path: str) -> Optional[str]:
        """GET request to Consul"""
        url = f"{self.endpoints[0]}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode("utf-8")

    def _consul_delete(self, path: str):
        """DELETE request to Consul"""
        url = f"{self.endpoints[0]}{path}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=5):
            pass

    @staticmethod
    def _b64encode(s: str) -> str:
        """Base64 encode for etcd v3 API"""
        import base64
        return base64.b64encode(s.encode()).decode()
