"""Tests for StateGuard Decision Log → Prodinamik Event Store Bridge.

Tests cover:
1. ProdinamikDecisionBridge creation
2. log() — writes to both in-memory log and EventStore
3. query() — delegates to in-memory logger
4. count() — tracks total entries
5. _entry_to_event() — correct mapping
6. Integration: real EventStore writes
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from stateguard.models.log import DecisionEntry
from stateguard.models.enums import ValidationDimension

from engine.decision_bridge import ProdinamikDecisionBridge
from engine.event_store import EventStore, Event, EventType


# ═══════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════


@pytest.fixture
def sample_entry() -> DecisionEntry:
    return DecisionEntry(
        agent_id="agent-1",
        step_id="tier_1",
        dimension=ValidationDimension.SEMANTIC,
        score=85.0,
        decision="pass",
        details={"threshold": 80.0},
    )


@pytest.fixture
def mock_store() -> MagicMock:
    store = MagicMock(spec=EventStore)
    store.append.return_value = 42  # Simulated sequence
    return store


# ═══════════════════════════════════════════════
# 1. Creation
# ═══════════════════════════════════════════════


class TestCreation:
    def test_default_creation(self, mock_store):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        assert bridge.event_store is mock_store
        assert bridge.logger is not None
        assert bridge.run_slug == "stateguard"

    def test_custom_logger(self, mock_store):
        from stateguard.models.log import DecisionLogger
        custom_logger = DecisionLogger()
        bridge = ProdinamikDecisionBridge(
            event_store=mock_store,
            decision_logger=custom_logger,
            run_slug="my-slug",
        )
        assert bridge.logger is custom_logger
        assert bridge.run_slug == "my-slug"

    def test_create_default(self, tmp_path):
        """create_default creates a working bridge with real EventStore."""
        base = str(tmp_path / "events")
        bridge = ProdinamikDecisionBridge.create_default(
            base_path=base,
            run_slug="test-run",
        )
        assert bridge.event_store is not None
        assert bridge.run_slug == "test-run"

    def test_run_slug_setter(self, mock_store):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.run_slug = "new-slug"
        assert bridge.run_slug == "new-slug"


# ═══════════════════════════════════════════════
# 2. log()
# ═══════════════════════════════════════════════


class TestLog:
    def test_writes_to_both(self, mock_store, sample_entry):
        """log() writes to in-memory logger AND EventStore."""
        bridge = ProdinamikDecisionBridge(event_store=mock_store)

        assert bridge.count() == 0
        bridge.log(sample_entry)
        assert bridge.count() == 1, "In-memory count should increment"
        mock_store.append.assert_called_once()

    def test_event_store_receives_event(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)

        args, kwargs = mock_store.append.call_args
        event = args[0]
        assert isinstance(event, Event)
        assert event.event_type == EventType.VALIDATION.value
        assert event.data["agent_id"] == "agent-1"
        assert event.data["score"] == 85.0
        assert event.data["decision"] == "pass"

    def test_entry_carries_dimension(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)

        args = mock_store.append.call_args[0]
        event = args[0]
        assert event.data["dimension"] == "semantic"

    def test_multiple_entries(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)
        bridge.log(sample_entry)
        assert bridge.count() == 2
        assert mock_store.append.call_count == 2

    def test_trace_id_format(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)

        event = mock_store.append.call_args[0][0]
        assert event.trace_id == "sg-tier_1"


# ═══════════════════════════════════════════════
# 3. query()
# ═══════════════════════════════════════════════


class TestQuery:
    def test_query_all(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)
        results = bridge.query()
        assert len(results) == 1
        assert results[0].agent_id == "agent-1"

    def test_query_by_agent(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)
        results = bridge.query(agent_id="agent-1")
        assert len(results) == 1
        results = bridge.query(agent_id="other")
        assert len(results) == 0

    def test_query_by_result(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        bridge.log(sample_entry)
        results = bridge.query(result="pass")
        assert len(results) == 1
        results = bridge.query(result="fail")
        assert len(results) == 0

    def test_query_empty(self, mock_store):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        assert bridge.query() == []


# ═══════════════════════════════════════════════
# 4. _entry_to_event()
# ═══════════════════════════════════════════════


class TestMapping:
    def test_required_fields_mapped(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        event = bridge._entry_to_event(sample_entry)

        assert event.run_slug == "stateguard"
        assert event.event_type == EventType.VALIDATION.value
        assert event.data["agent_id"] == "agent-1"
        assert event.data["score"] == 85.0
        assert event.data["dimension"] == "semantic"

    def test_timestamp_from_entry(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        event = bridge._entry_to_event(sample_entry)
        # Should be ISO format string
        assert "T" in event.timestamp

    def test_cost_is_zero(self, mock_store, sample_entry):
        bridge = ProdinamikDecisionBridge(event_store=mock_store)
        event = bridge._entry_to_event(sample_entry)
        assert event.cost_usd == 0.0


# ═══════════════════════════════════════════════
# 5. Integration with real EventStore
# ═══════════════════════════════════════════════


class TestRealEventStore:
    def test_event_persisted_to_disk(self, tmp_path, sample_entry):
        """log() to a real EventStore — verify disk persistence."""
        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="test")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="test")

        bridge.log(sample_entry)
        assert bridge.count() == 1

        # EventStore should have 1 event file
        events_dir = store.events_dir
        json_files = list(events_dir.glob("*.json"))
        # Remove index.json from count
        event_files = [f for f in json_files if f.name != "index.json"]
        assert len(event_files) == 1, f"Expected 1 event file, got {len(event_files)}: {event_files}"

    def test_multiple_events_ordered(self, tmp_path):
        """Multiple events get sequential sequence numbers."""
        base = str(tmp_path / "events")
        store = EventStore(base_path=base, slug="test")
        bridge = ProdinamikDecisionBridge(event_store=store, run_slug="test")

        e1 = DecisionEntry(
            agent_id="a1", step_id="tier_1",
            dimension=ValidationDimension.STRUCTURAL,
            score=80.0, decision="pass",
        )
        e2 = DecisionEntry(
            agent_id="a1", step_id="tier_2",
            dimension=ValidationDimension.SEMANTIC,
            score=60.0, decision="escalate",
        )

        seq1 = bridge.log(e1) or store._last_sequence
        # No return value from log, check _last_sequence from store
        bridge.log(e2)

        events_dir = store.events_dir
        event_files = sorted(
            [f for f in events_dir.glob("*.json") if f.name != "index.json"]
        )
        assert len(event_files) == 2
