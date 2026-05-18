# Degradation Manager

Prodinamik Engine v0.5 — Degradation Manager

3-seviyeli graceful degradation (Review #10 → refined):
- FULL:     Tüm özellikler aktif
- DEGRADED: T2/T3 validator'lar + remote adapter'lar kapalı, prediction aktif
- SURVIVAL: Tüm validator/adapter'lar kapalı, sadece state tracking

Health monitor:
- LLM API sağlığı
- Disk kullanımı
- Budget limitleri
- Invariant violations

**Module:** `engine.degradation.py`

## Classes

### `DegradationLevel`(Enum)

### `HealthCheckResult`

Tek bir health check sonucu

### `DegradationEvent`

Degradation değişikliği — event store'a yazılır

### `DegradationManager`

Health monitor + degradation controller.

Otomatik degradation:
- LLM API hatası + remote adapter hatası → DEGRADED
- Disk >%95 + Budget hard limit aşımı → SURVIVAL

Manuel override:
- Kullanıcı manuel degrade edebilir
- Kullanıcı manuel recover edebilir

**Methods:**

- `__init__(base_path)`
- `check_health(engine_state)`
  — Tüm health check'leri çalıştır
- `_check_disk_usage()`
  — Disk kullanımı kontrolü
- `_check_llm_api(state)`
  — LLM API sağlığı (engine_state'dan gelen veriye göre)
- `_check_remote_adapters(state)`
  — Remote adapter sağlığı
- `_check_budget(state)`
  — Budget limit kontrolü
- `_check_memory(state)`
  — Memory kullanımı (basit)
- `evaluate(engine_state)`
  — Health check sonuçlarına göre degradation seviyesini belirle.
- `_transition_to(new_level, failed_checks, engine_state)`
  — Degradation seviyesini değiştir
- `manual_degrade(level, reason)`
  — Kullanıcı manuel degrade eder
- `manual_recover()`
  — Kullanıcı manuel FULL moda döner
- `is_enabled(feature)`
  — Belirli bir feature'ın aktif olup olmadığını kontrol et
- `feature_matrix()`
  — Tüm feature'ların durumu
- `status_report()`
  — Kullanıcıya durum raporu

## Functions

### `demo()`
