# Safety Monitor

Prodinamik Engine v0.5 — Event Bus + Runtime Safety Invariants

Event Bus (Review #4):
- Trace ID + max hop count (5 hops)
- Duplicate detection
- Cross-profile cycle safety

Runtime Safety Invariants (Review #8):
- 10 runtime invariant
- Her invariant ihlalinde otomatik aksiyon
- Health report

**Module:** `engine.safety.py`

## Classes

### `BusEvent`

Event bus event'i — trace ID + hop count ile

**Methods:**

- `__post_init__()`

### `EventBus`

Cross-profile event bus with cycle safety.

- Trace ID: Her event zinciri benzersiz UUID
- Hop count: Max 5 profil hops, aşılınca durdurulur
- Duplicate detection: Aynı trace_id + type ikincisi atılır
- Async subscribers

**Methods:**

- `__init__()`
- `subscribe(event_type, handler)`
  — Bir event tipine abone ol
- `unsubscribe(event_type, handler)`
  — Aboneliği iptal et
- `emit(event)`
  — Event yayınla.
- `async _safe_call(handler, event)`
  — Subscriber'ı hata toleranslı çağır
- `unsubscribe(event_type, handler)`
  — Aboneliği iptal et
- `clear_traces()`
  — Periyodik temizlik (trace set'i çok büyümesin)
- `has_cycles()`
  — Hiç cycle tespit edilmiş mi?
- `stats()`

### `InvariantViolation`

### `RuntimeSafetyMonitor`

Runtime'da sürekli kontrol edilen invariant'lar.
Her transition, validasyon, event sonrası çalıştırılabilir.
Invariant ihlali → otomatik aksiyon (action matrix).

**Methods:**

- `__init__(event_bus)`
- `check_all(state_machine, run, store, cache, bus, degradation)`
  — Tüm invariant'ları kontrol et.
- `_call_with_context(check_fn, context, name)`
  — Invariant check fonksiyonuna uygun parametreleri geçir.
- `_take_action(action, invariant_name, context)`
  — Invariant ihlalinde aksiyon al
- `async _async_compact(store)`
  — Async compaction
- `resolve_violation(name)`
  — Violation'ı çözülmüş olarak işaretle
- `active_violations()`
- `health_score()`
  — 0.0 (critical) → 1.0 (perfect)
- `health_report()`
  — Kullanıcıya invariant durumunu göster

## Functions

### `async async_demo()`

### `demo()`
