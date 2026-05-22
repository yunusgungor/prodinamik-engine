"""StateGuard Decision Log → Prodinamik Event Store Bridge.

Wraps StateGuard's :class:`DecisionLogger` so that every
:meth:`DecisionEntry` is also persisted as a Prodinamik
:class:`Event` (``EventType.VALIDATION``) through the
:class:`EventStore`.

This makes validation decisions:
- Durable (JSONL files, not just in-memory)
- Searchable via Prodinamik's audit/query API
- Replayable (event sourcing)
- Retention-managed (90-day default for validation events)

Usage::

    from engine.decision_bridge import ProdinamikDecisionBridge

    bridge = ProdinamikDecisionBridge(event_store=my_store)
    bridge.log(decision_entry)  # → also writes to EventStore
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stateguard.models.log import DecisionEntry, DecisionLogger
from stateguard.models.enums import ValidationDimension

from engine.event_store import EventStore, Event, EventType


# ──────────────────────────────────────────────
# ProdinamikDecisionBridge
# ──────────────────────────────────────────────


class ProdinamikDecisionBridge:
    """Bridge that duplicates StateGuard decisions to Prodinamik EventStore.

    Delegates the original :class:`DecisionLogger` interface
    (:meth:`log`, :meth:`query`) but also persists every entry
    as a Prodinamik :class:`Event` with ``event_type=VALIDATION``.

    The in-memory log is kept for fast querying (same as the original
    ``DecisionLogger``).  The EventStore provides durable persistence
    and auditability.
    """

    def __init__(
        self,
        event_store: EventStore,
        decision_logger: DecisionLogger | None = None,
        run_slug: str = "stateguard",
    ) -> None:
        """Initialise the bridge.

        Args:
            event_store: A Prodinamik :class:`EventStore` instance.
            decision_logger: Optional existing :class:`DecisionLogger`.
                             If omitted, a new one is created.
            run_slug: The ``run_slug`` tag for EventStore entries.
        """
        self._logger = decision_logger or DecisionLogger()
        self._event_store = event_store
        self._run_slug = run_slug

    # ── Properties ─────────────────────────────

    @property
    def event_store(self) -> EventStore:
        return self._event_store

    @property
    def logger(self) -> DecisionLogger:
        return self._logger

    @property
    def run_slug(self) -> str:
        return self._run_slug

    @run_slug.setter
    def run_slug(self, value: str) -> None:
        self._run_slug = value

    # ── Decision Logger interface ──────────────

    def log(self, entry: DecisionEntry) -> None:
        """Record a decision entry — both in-memory and to EventStore.

        Args:
            entry: The :class:`DecisionEntry` to persist.
        """
        # 1. Write to original in-memory logger (fast query)
        self._logger.log(entry)

        # 2. Duplicate to EventStore (durable persistence)
        event = self._entry_to_event(entry)
        self._event_store.append(event)

    def query(
        self,
        agent_id: str | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        result: str | None = None,
    ) -> list[DecisionEntry]:
        """Query decision entries (delegates to in-memory logger).

        For persistent queries use :meth:`EventStore.query` instead.

        Args:
            agent_id:   Filter by agent identifier.
            time_range: ``(start, end)`` inclusive range on ``timestamp``.
            result:     Filter by decision string (case-insensitive).

        Returns:
            A new list of matching :class:`DecisionEntry` objects.
        """
        return self._logger.query(
            agent_id=agent_id,
            time_range=time_range,
            result=result,
        )

    def count(self) -> int:
        """Return the total number of entries in the in-memory log."""
        return len(self._logger._entries)

    # ── EventStore helpers ─────────────────────

    def flush(self) -> list[int]:
        """Flush all pending entries to EventStore.

        Returns:
            List of event sequence IDs.
        """
        # Already flushed synchronously in log(), but exposed for
        # batch scenarios where you might want to defer.
        return []

    # ── Mapping ────────────────────────────────

    def _entry_to_event(self, entry: DecisionEntry) -> Event:
        """Map a :class:`DecisionEntry` → Prodinamik :class:`Event`.

        Args:
            entry: StateGuard decision entry.

        Returns:
            A Prodinamik :class:`Event` with ``event_type=VALIDATION``.
        """
        return Event(
            sequence=0,  # Assigned by EventStore on append
            run_slug=self._run_slug,
            timestamp=entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp),
            event_type=EventType.VALIDATION.value,
            data={
                "agent_id": entry.agent_id,
                "step_id": entry.step_id,
                "dimension": entry.dimension.value if isinstance(entry.dimension, ValidationDimension) else str(entry.dimension),
                "score": entry.score,
                "decision": entry.decision,
                "details": entry.details,
            },
            parent_id=None,
            trace_id=f"sg-{entry.step_id}",
            hop_count=0,
            cost_usd=0.0,
            validator_tier=1,  # StateGuard tier (mapped as 1)
        )

    # ── Class method: create with defaults ─────

    @classmethod
    def create_default(
        cls,
        base_path: str = ".hermes/runs/stateguard",
        run_slug: str = "stateguard",
    ) -> "ProdinamikDecisionBridge":
        """Create a bridge with a default on-disk EventStore.

        Args:
            base_path: Base directory for the EventStore.
            run_slug:  Run slug for events.

        Returns:
            A ready-to-use :class:`ProdinamikDecisionBridge`.
        """
        from engine.event_store import EventStore
        store = EventStore(base_path=base_path, slug=run_slug)
        return cls(event_store=store, run_slug=run_slug)
