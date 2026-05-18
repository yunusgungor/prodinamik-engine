"""
Prodinamik Engine v1.1 — Raft TCP Transport Layer

Real TCP-based peer communication for Raft consensus.
Replaces the mock/simulated peer communication.

Usage:
    # Server side (each node)
    transport = RaftTransport(node, host="0.0.0.0", port=9001)
    transport.start()

    # Client side (sending messages)
    transport = RaftTransport(node)
    transport.request_vote("192.168.1.2:9001", term=1, candidate_id="node-1")
"""

import json
import socket
import threading
import time
from typing import Optional, Dict, Any, Tuple, List, Callable
from datetime import datetime
from dataclasses import dataclass, asdict


# ──────────────────────────────────────────────
# Raft Protocol Message Types
# ──────────────────────────────────────────────

RAFT_MSG_REQUEST_VOTE = "RequestVote"
RAFT_MSG_REQUEST_VOTE_RESPONSE = "RequestVoteResponse"
RAFT_MSG_APPEND_ENTRIES = "AppendEntries"
RAFT_MSG_APPEND_ENTRIES_RESPONSE = "AppendEntriesResponse"
RAFT_MSG_HEARTBEAT = "Heartbeat"
RAFT_MSG_HEARTBEAT_RESPONSE = "HeartbeatResponse"
RAFT_MSG_INSTALL_SNAPSHOT = "InstallSnapshot"
RAFT_MSG_CLUSTER_JOIN = "ClusterJoin"
RAFT_MSG_CLUSTER_LEAVE = "ClusterLeave"
RAFT_MSG_HEALTH = "HealthRequest"


@dataclass
class RaftMessage:
    """Wire format for Raft protocol messages"""
    type: str
    sender_id: str
    term: int = 0
    data: dict = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "RaftMessage":
        data = json.loads(raw)
        return cls(**data)


# ──────────────────────────────────────────────
# TCP Server (per-node)
# ──────────────────────────────────────────────

class RaftTCPServer:
    """
    TCP server for receiving Raft messages from peers.
    Each Raft node runs one server on a configurable port.

    Messages are JSON-delimited by newline.
    """

    def __init__(self, node_id: str, host: str = "0.0.0.0",
                 port: int = 9001, handler: Callable = None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.handler = handler  # Callable[[RaftMessage], Optional[RaftMessage]]
        self._server: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.connections: int = 0

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def start(self):
        """Start TCP server in background thread"""
        if self._running:
            return

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.settimeout(1.0)  # 1s timeout for clean shutdown

        try:
            self._server.bind((self.host, self.port))
            self._server.listen(10)
            self._running = True
            self._thread = threading.Thread(target=self._serve, daemon=True,
                                            name=f"raft-server-{self.node_id}")
            self._thread.start()
            return True
        except OSError as e:
            print(f"⚠️ Raft server bind failed on {self.address}: {e}")
            return False

    def stop(self):
        """Stop TCP server"""
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _serve(self):
        """Main accept loop"""
        while self._running:
            try:
                client, addr = self._server.accept()
                self.connections += 1
                t = threading.Thread(target=self._handle_client,
                                     args=(client, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_client(self, client: socket.socket, addr):
        """Handle incoming connection: read JSON, call handler, respond"""
        try:
            client.settimeout(10.0)
            data = client.recv(65536)  # 64KB max message
            if not data:
                return

            msg = RaftMessage.from_json(data.decode("utf-8").strip())
            if self.handler:
                response = self.handler(msg)
                if response:
                    client.sendall(response.to_json().encode("utf-8") + b"\n")
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
        finally:
            client.close()


# ──────────────────────────────────────────────
# TCP Client (per-peer-request)
# ──────────────────────────────────────────────

class RaftTCPClient:
    """
    TCP client for sending Raft messages to peers.
    Each call opens a short-lived connection.
    """

    CONNECT_TIMEOUT = 3.0
    RESPONSE_TIMEOUT = 5.0

    @classmethod
    def send_message(cls, peer_address: str, msg: RaftMessage) -> Optional[RaftMessage]:
        """
        Send a Raft message to a peer and wait for response.
        Returns None if the peer is unreachable.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(cls.CONNECT_TIMEOUT)

            host, port_str = peer_address.split(":")
            port = int(port_str)

            sock.connect((host, port))
            sock.sendall(msg.to_json().encode("utf-8") + b"\n")

            # Read response
            sock.settimeout(cls.RESPONSE_TIMEOUT)
            data = sock.recv(65536)
            sock.close()

            if data:
                return RaftMessage.from_json(data.decode("utf-8").strip())
            return None

        except (socket.timeout, ConnectionRefusedError, OSError,
                ValueError, json.JSONDecodeError) as e:
            return None

    @classmethod
    def health_check(cls, peer_address: str) -> Optional[dict]:
        """Quick health check of a peer"""
        msg = RaftMessage(
            type=RAFT_MSG_HEALTH,
            sender_id="health-checker",
            data={"action": "ping"},
        )
        resp = cls.send_message(peer_address, msg)
        if resp and resp.data:
            return resp.data
        return None


# ──────────────────────────────────────────────
# Message Builder Helpers
# ──────────────────────────────────────────────

def build_vote_request(sender_id: str, term: int,
                       last_log_index: int, last_log_term: int) -> RaftMessage:
    return RaftMessage(
        type=RAFT_MSG_REQUEST_VOTE,
        sender_id=sender_id,
        term=term,
        data={"last_log_index": last_log_index, "last_log_term": last_log_term},
    )


def build_vote_response(sender_id: str, term: int, vote_granted: bool) -> RaftMessage:
    return RaftMessage(
        type=RAFT_MSG_REQUEST_VOTE_RESPONSE,
        sender_id=sender_id,
        term=term,
        data={"vote_granted": vote_granted},
    )


def build_append_entries(sender_id: str, term: int, entries: List[dict],
                         prev_log_index: int, prev_log_term: int,
                         leader_commit: int) -> RaftMessage:
    return RaftMessage(
        type=RAFT_MSG_APPEND_ENTRIES,
        sender_id=sender_id,
        term=term,
        data={
            "entries": entries,
            "prev_log_index": prev_log_index,
            "prev_log_term": prev_log_term,
            "leader_commit": leader_commit,
        },
    )


def build_append_response(sender_id: str, term: int, success: bool,
                           conflict_index: int = 0, conflict_term: int = 0) -> RaftMessage:
    return RaftMessage(
        type=RAFT_MSG_APPEND_ENTRIES_RESPONSE,
        sender_id=sender_id,
        term=term,
        data={"success": success, "conflict_index": conflict_index, "conflict_term": conflict_term},
    )


def build_heartbeat(sender_id: str, term: int, leader_commit: int) -> RaftMessage:
    return RaftMessage(
        type=RAFT_MSG_HEARTBEAT,
        sender_id=sender_id,
        term=term,
        data={"leader_commit": leader_commit},
    )
