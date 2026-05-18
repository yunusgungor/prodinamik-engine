"""
Prodinamik Engine v0.5 — Event Store

Append-only event log with:
- Type-based retention policy (TTL per event type)
- Compaction (N events → 1 summary)
- Query/filter API
- Cost tracking integration (CostAwareEvent)
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
import hashlib
import re


# ──────────────────────────────────────────────
# Event Types
# ──────────────────────────────────────────────

class EventType(Enum):
    STATE_TRANSITION = "state_transition"
    VALIDATION = "validation"
    VALIDATION_DETAIL = "validation_detail"
    ADAPTER_CALL = "adapter_call"
    ADAPTER_RESPONSE = "adapter_response"
    ERROR = "error"
    USER_ACTION = "user_action"
    WEEKLY_SUMMARY = "weekly_summary"
    DEGRADATION_CHANGE = "degradation_change"
    INVARIANT_VIOLATION = "invariant_violation"


# ──────────────────────────────────────────────
# Event
# ──────────────────────────────────────────────

@dataclass
class Event:
    """Tek bir olay (immutable)"""
    sequence: int
    run_slug: str
    timestamp: str                # ISO datetime
    event_type: str               # EventType value
    data: dict = field(default_factory=dict)
    parent_id: Optional[int] = None   # Causal chain
    trace_id: Optional[str] = None    # Cycle tracking
    hop_count: int = 0
    cost_usd: float = 0.0
    validator_tier: int = 1          # 1|2|3

    def dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────
# Cost-Aware Event (Review #7)
# ──────────────────────────────────────────────

class CostAwareEvent(Event):
    """Cost bilgisi taşıyan event — event store ile cost model'i birleştirir"""

    @classmethod
    def from_validation(cls, sequence: int, run_slug: str,
                        validator_name: str, tier: int,
                        passed: bool, cost_usd: float,
                        details: dict = None) -> "CostAwareEvent":
        return cls(
            sequence=sequence,
            run_slug=run_slug,
            timestamp=datetime.now().isoformat(),
            event_type=EventType.VALIDATION.value,
            data={
                "validator": validator_name,
                "passed": passed,
                "details": details or {},
            },
            cost_usd=cost_usd,
            validator_tier=tier,
        )

    @classmethod
    def from_transition(cls, sequence: int, run_slug: str,
                        from_state: str, to_state: str) -> "CostAwareEvent":
        return cls(
            sequence=sequence,
            run_slug=run_slug,
            timestamp=datetime.now().isoformat(),
            event_type=EventType.STATE_TRANSITION.value,
            data={
                "from": from_state,
                "to": to_state,
            },
            cost_usd=0.0,  # State transitions are free
        )

    @classmethod
    def from_error(cls, sequence: int, run_slug: str,
                   source: str, message: str,
                   cost_usd: float = 0.0) -> "CostAwareEvent":
        return cls(
            sequence=sequence,
            run_slug=run_slug,
            timestamp=datetime.now().isoformat(),
            event_type=EventType.ERROR.value,
            data={
                "source": source,
                "message": message,
            },
            cost_usd=cost_usd,
        )


# ──────────────────────────────────────────────
# Retention Policy (Review #3)
# ──────────────────────────────────────────────

class EventRetentionPolicy:
    """
    Type-based retention + compaction.

    Retention süreleri:
    - STATE_TRANSITION:  ∞ (silme, kritik, küçük)
    - VALIDATION_SUMMARY: ∞ (özet bilgi)
    - VALIDATION_DETAIL:  30 gün (büyük, LLM çıktısı)
    - ADAPTER_CALL:       30 gün
    - ADAPTER_RESPONSE:   7 gün (çok büyük)
    - ERROR:              365 gün
    - USER_ACTION:        365 gün
    - DEGRADATION_CHANGE: 180 gün
    """

    RETENTION: Dict[EventType, timedelta] = {
        EventType.STATE_TRANSITION: timedelta.max,
        EventType.VALIDATION: timedelta(days=90),
        EventType.VALIDATION_DETAIL: timedelta(days=30),
        EventType.ADAPTER_CALL: timedelta(days=30),
        EventType.ADAPTER_RESPONSE: timedelta(days=7),
        EventType.ERROR: timedelta(days=365),
        EventType.USER_ACTION: timedelta(days=365),
        EventType.WEEKLY_SUMMARY: timedelta.max,
        EventType.DEGRADATION_CHANGE: timedelta(days=180),
        EventType.INVARIANT_VIOLATION: timedelta(days=365),
    }

    COMPACTION_AGE = timedelta(days=30)  # 30 günden eski event'ler compact edilebilir
    COMPACTION_BATCH = 10                 # 10 event → 1 summary

    def __init__(self, overrides: Dict[EventType, timedelta] = None):
        if overrides:
            self.RETENTION = {**self.RETENTION, **overrides}

    def get_retention(self, event_type: EventType) -> timedelta:
        return self.RETENTION.get(event_type, timedelta(days=30))

    def should_purge(self, event: Event, now: datetime) -> bool:
        ttl = self.get_retention(EventType(event.event_type))
        if ttl == timedelta.max:
            return False
        event_time = datetime.fromisoformat(event.timestamp)
        return (now - event_time) > ttl


# ──────────────────────────────────────────────
# Event Store
# ──────────────────────────────────────────────

class EventStore:
    """
    Append-only event store.

    Dizin yapısı:
    .hermes/runs/{slug}/events/
    ├── index.json           # Event index (sequence → filename)
    ├── 0000000001.json      # Event #1
    ├── 0000000002.json      # Event #2
    ├── ...
    └── summary_20260501.json # Compaction summary
    """

    def __init__(self, base_path: str, slug: str, retention: EventRetentionPolicy = None):
        self.events_dir = Path(base_path) / "runs" / "active" / slug / "events"
        self.archive_dir = Path(base_path) / "runs" / "archive" / slug / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.retention = retention or EventRetentionPolicy()
        self._last_sequence = self._load_last_sequence()
        self._index: Dict[int, str] = {}
        self._index = self._load_index()

    # ──────────────────────────────────────
    # Write
    # ──────────────────────────────────────

    def append(self, event: Event) -> int:
        """Event'i log'a ekle (append-only). Event ID'sini döndür."""
        seq = self._next_sequence()
        event.sequence = seq

        filename = f"{seq:010d}.json"
        path = self.events_dir / filename

        path.write_text(
            json.dumps(event.dict(), ensure_ascii=False, default=str),
            encoding="utf-8"
        )

        self._index[seq] = filename
        self._last_sequence = seq
        self._save_index()

        return seq

    def append_many(self, events: List[Event]) -> List[int]:
        """Toplu event ekle"""
        return [self.append(e) for e in events]

    # ──────────────────────────────────────
    # Read
    # ──────────────────────────────────────

    def get(self, sequence: int) -> Optional[Event]:
        """Belirli bir event'i oku"""
        filename = self._index.get(sequence)
        if not filename:
            return None

        path = self.events_dir / filename
        if not path.exists():
            return None

        return self._parse_event(path)

    def get_range(self, start: int, limit: int = 100) -> List[Event]:
        """Event'leri sıralı oku (pagination)"""
        events = []
        for seq in range(start, self._last_sequence + 1):
            if len(events) >= limit:
                break
            event = self.get(seq)
            if event:
                events.append(event)
        return events

    def get_all(self) -> List[Event]:
        """Tüm event'leri oku (dikkat: büyük olabilir)"""
        return self.get_range(1, self._last_sequence + 1)

    def query(self, event_type: str = None, 
              validator: str = None,
              passed: bool = None,
              min_cost: float = None,
              since: str = None,
              limit: int = 100) -> List[Event]:
        """
        Event'lerde sorgu.
        
        Örnek:
            store.query(event_type="validation", validator="SlopScanT1")
            store.query(event_type="error", since="2026-05-01")
            store.query(min_cost=0.1)  # Pahalı event'leri bul
        """
        results = []

        for seq in range(self._last_sequence, 0, -1):
            if len(results) >= limit:
                break

            event = self.get(seq)
            if not event:
                continue

            if event_type and event.event_type != event_type:
                continue
            if validator and event.data.get("validator") != validator:
                continue
            if passed is not None and event.data.get("passed") != passed:
                continue
            if min_cost and event.cost_usd < min_cost:
                continue
            if since:
                try:
                    if event.timestamp < since:
                        continue
                except (ValueError, TypeError):
                    pass

            results.append(event)

        return results

    def cost_summary(self, since: str = None) -> Dict[str, float]:
        """Validator bazında toplam maliyet"""
        costs = {}
        for event in self.get_all():
            if event.event_type in (EventType.VALIDATION.value, EventType.VALIDATION_DETAIL.value):
                vname = event.data.get("validator", "unknown")
                if since and event.timestamp < since:
                    continue
                costs[vname] = costs.get(vname, 0.0) + event.cost_usd
        return dict(sorted(costs.items(), key=lambda x: x[1], reverse=True))

    # ──────────────────────────────────────
    # Retention & Compaction (Review #3)
    # ──────────────────────────────────────

    def purge(self):
        """Retention süresi geçen event'leri sil"""
        now = datetime.now()
        purged = 0
        to_delete = []

        for seq, filename in list(self._index.items()):
            path = self.events_dir / filename
            if not path.exists():
                to_delete.append(seq)
                continue

            try:
                event = self._parse_event(path)
                if self.retention.should_purge(event, now):
                    path.unlink()
                    to_delete.append(seq)
                    purged += 1
            except (json.JSONDecodeError, OSError):
                to_delete.append(seq)
                continue

        for seq in to_delete:
            del self._index[seq]

        if purged > 0 or to_delete:
            self._save_index()

        return purged

    def compact(self, slug: str) -> Optional[Event]:
        """
        30 günden eski event'leri özetleyerek sıkıştır.

        10 VALIDATION_DETAIL event'i → 1 VALIDATION_SUMMARY event'i
        %90 boyut azalması hedefi.
        """
        cutoff = datetime.now() - self.retention.COMPACTION_AGE
        old_events = []

        for seq, filename in list(self._index.items()):
            path = self.events_dir / filename
            if not path.exists():
                continue

            try:
                event = self._parse_event(path)
                event_time = datetime.fromisoformat(event.timestamp)
                if event_time < cutoff:
                    old_events.append(event)
            except (json.JSONDecodeError, OSError, ValueError):
                continue

        if len(old_events) < self.retention.COMPACTION_BATCH:
            return None  # Yeterli event yok

        # Detaylı event'leri sil
        detail_events = [e for e in old_events 
                        if e.event_type == EventType.VALIDATION_DETAIL.value]
        for e in detail_events:
            path = self.events_dir / f"{e.sequence:010d}.json"
            if path.exists():
                path.unlink()
            del self._index[e.sequence]

        # Özet event oluştur
        summary = self._summarize(old_events, slug)
        summary_seq = self.append(summary)

        self._save_index()
        return summary

    def _summarize(self, events: List[Event], slug: str) -> Event:
        """Event listesini özetle"""
        total_cost = sum(e.cost_usd for e in events)
        passed = sum(1 for e in events if e.data.get("passed", True))
        failed = sum(1 for e in events if not e.data.get("passed", True))

        return Event(
            sequence=0,  # append() atayacak
            run_slug=slug,
            timestamp=datetime.now().isoformat(),
            event_type=EventType.WEEKLY_SUMMARY.value,
            data={
                "compacted_events": len(events),
                "period_start": min(e.timestamp for e in events),
                "period_end": max(e.timestamp for e in events),
                "total_cost": total_cost,
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / max(passed + failed, 1),
                "top_validators": self.cost_summary(
                    since=min(e.timestamp for e in events)
                ),
            },
            cost_usd=0.0,
        )

    # ──────────────────────────────────────
    # Index Management
    # ──────────────────────────────────────

    def _load_last_sequence(self) -> int:
        """Mevcut event dosyalarından son sequence'ı bul"""
        seq = 0
        for f in self.events_dir.glob("[0-9]" * 10 + ".json"):
            try:
                s = int(f.stem)
                seq = max(seq, s)
            except ValueError:
                continue
        # Archive'de de ara
        if self.archive_dir.exists():
            for f in self.archive_dir.glob("[0-9]" * 10 + ".json"):
                try:
                    s = int(f.stem)
                    seq = max(seq, s)
                except ValueError:
                    continue
        return seq

    def _load_index(self) -> Dict[int, str]:
        """Index dosyasını yükle veya yeniden oluştur"""
        index_path = self.events_dir / "index.json"
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                return {int(k): v for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                pass

        # Index yoksa, event dosyalarını tara
        index = {}
        for f in sorted(self.events_dir.glob("[0-9]" * 10 + ".json")):
            try:
                seq = int(f.stem)
                index[seq] = f.name
            except ValueError:
                continue

        self._save_index(index)
        return index

    def _save_index(self, index: dict = None):
        index = index or self._index
        index_path = self.events_dir / "index.json"
        index_path.write_text(
            json.dumps({str(k): v for k, v in index.items()},
                      indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _next_sequence(self) -> int:
        return self._last_sequence + 1

    def _parse_event(self, path: Path) -> Optional[Event]:
        """JSON dosyasından Event oluştur"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Event(**data)
        except (json.JSONDecodeError, OSError, TypeError) as e:
            return None

    @property
    def event_count(self) -> int:
        return len(self._index)

    @property
    def storage_bytes(self) -> int:
        return sum(
            f.stat().st_size
            for f in self.events_dir.glob("*.json")
            if f.is_file()
        )

    def stats(self) -> dict:
        return {
            "slug": self.events_dir.parent.name,
            "event_count": self.event_count,
            "last_sequence": self._last_sequence,
            "storage_bytes": self.storage_bytes,
            "storage_kb": round(self.storage_bytes / 1024, 1),
            "event_types": self._type_counts(),
        }

    def _type_counts(self) -> Dict[str, int]:
        counts = {}
        for seq in self._index:
            event = self.get(seq)
            if event:
                et = event.event_type
                counts[et] = counts.get(et, 0) + 1
        return counts


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import tempfile
    import os

    tmpdir = tempfile.mkdtemp()
    slug = "demo-run"

    store = EventStore(base_path=tmpdir, slug=slug)
    print(f"📦 Event Store created: {store.events_dir}")

    # Add events
    for i in range(5):
        event = CostAwareEvent.from_validation(
            sequence=0, run_slug=slug,
            validator_name="SlopScanT1", tier=1,
            passed=(i % 2 == 0),
            cost_usd=0.01 * (i + 1),
        )
        seq = store.append(event)
        print(f"   ✅ Event #{seq}: validation cost=${event.cost_usd:.2f}")

    # Add state transition
    event = CostAwareEvent.from_transition(0, slug, "spec", "prototyping")
    store.append(event)
    print(f"   ✅ Event: state_transition spec→prototyping")

    # Add error
    event = CostAwareEvent.from_error(0, slug, "test", "Simulated error")
    store.append(event)
    print(f"   ✅ Event: error")

    # Query
    print(f"\n📊 Store stats: {store.stats()}")

    print(f"\n🔍 Query: validations only")
    for e in store.query(event_type="validation"):
        print(f"   #{e.sequence}: {e.data.get('validator')} "
              f"passed={e.data.get('passed')} cost=${e.cost_usd:.2f}")

    print(f"\n💰 Cost summary:")
    for vname, cost in store.cost_summary().items():
        print(f"   {vname}: ${cost:.2f}")

    # Retention
    purged = store.purge()
    print(f"\n🧹 Purge: {purged} event(s) removed")

    # Try compact (should be no-op for recent events)
    summary = store.compact(slug)
    if summary:
        print(f"   ✅ Compacted: {summary.data['compacted_events']} events → 1 summary")
    else:
        print(f"   ℹ️  Compact skipped (events too recent)")

    print(f"\n{'='*50}")
    print(f"Event Store demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
