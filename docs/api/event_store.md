# Event Store

Prodinamik Engine v0.5 — Event Store

Append-only event log with:
- Type-based retention policy (TTL per event type)
- Compaction (N events → 1 summary)
- Query/filter API
- Cost tracking integration (CostAwareEvent)

**Module:** `engine.event_store.py`

## Classes

### `EventType`(Enum)

### `Event`

Tek bir olay (immutable)

**Methods:**

- `dict()`

### `CostAwareEvent`(Event)

Cost bilgisi taşıyan event — event store ile cost model'i birleştirir

**Methods:**

- `from_validation(cls, sequence, run_slug, validator_name, tier, passed, cost_usd, details)`
- `from_transition(cls, sequence, run_slug, from_state, to_state)`
- `from_error(cls, sequence, run_slug, source, message, cost_usd)`

### `EventRetentionPolicy`

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

**Methods:**

- `__init__(overrides)`
- `get_retention(event_type)`
- `should_purge(event, now)`

### `EventStore`

Append-only event store.

Dizin yapısı:
.hermes/runs/{slug}/events/
├── index.json           # Event index (sequence → filename)
├── 0000000001.json      # Event #1
├── 0000000002.json      # Event #2
├── ...
└── summary_20260501.json # Compaction summary

**Methods:**

- `__init__(base_path, slug, retention)`
- `append(event)`
  — Event'i log'a ekle (append-only). Event ID'sini döndür.
- `append_many(events)`
  — Toplu event ekle (optimized batch).
- `get(sequence)`
  — Belirli bir event'i oku
- `get_range(start, limit)`
  — Event'leri sıralı oku (pagination)
- `get_all()`
  — Tüm event'leri oku (dikkat: büyük olabilir)
- `query(event_type, validator, passed, min_cost, since, limit)`
  — Event'lerde sorgu.
- `cost_summary(since)`
  — Validator bazında toplam maliyet
- `purge()`
  — Retention süresi geçen event'leri sil
- `compact(slug)`
  — 30 günden eski event'leri özetleyerek sıkıştır.
- `_summarize(events, slug)`
  — Event listesini özetle
- `_load_last_sequence()`
  — Mevcut event dosyalarından son sequence'ı bul
- `_load_index()`
  — Index dosyasını yükle veya yeniden oluştur
- `_save_index(index)`
- `_next_sequence()`
- `_parse_event(path)`
  — JSON dosyasından Event oluştur
- `event_count()`
- `storage_bytes()`
- `stats()`
- `_type_counts()`

## Functions

### `demo()`
