# Validator Pipeline

Prodinamik Engine v0.5 — Validators

Base validator sınıfları + Tier1 regex/rule tabanlı validator'lar.
Tier 1 = Fail-fast, deterministik, <50ms, LLM gerektirmez.

Her validator:
- Content-addressable cache ile cache'lenebilir
- Per-validator timeout ile zaman aşımına uğratılabilir
- Degradation-aware cache policy ile çalışır

**Module:** `engine.validators.py`

## Classes

### `CachePolicy`(Enum)

### `ContentAddressableCache`

Validator sonuçlarını content hash'ine göre cache'ler.
Degradation-aware: Hangi seviyede hangi cache'lerin geçerli olduğunu bilir.

**Methods:**

- `__init__(cache_dir)`
- `get(content, validator_name, tier, cache_policy)`
  — Cache'ten sonuç al.
- `set(content, validator_name, result, tier, ttl)`
  — Cache'e sonuç yaz
- `_is_valid(entry, tier, policy)`
- `invalidate(validator_name)`
  — Cache'i temizle (belirli validator veya tümü)
- `hit_rate()`
- `stats()`

### `CacheEntry`

**Methods:**

- `is_expired()`

### `ValidatorTimeoutManager`

Her validator için ayrı timeout yönetimi.
Timeout olan validator'lar skipped olarak işaretlenir.

**Methods:**

- `get_timeout(cls, validator_name, default)`
- `async run_with_timeout(cls, validator, artifact)`
  — Validator'ı timeout ile çalıştır

### `RegexValidator`(Validator)

Regex pattern tabanlı validasyon.
T1: <50ms, deterministik, LLM gerektirmez.

**Methods:**

- `__init__(defn, patterns)`
  — patterns: [(pattern_name, regex, severity), ...]
- `async validate(artifact)`
  — Tüm regex pattern'lerini tara.
- `_get_content(artifact)`
  — Artifact'ten içerik string'ini çıkar
- `_format_message(errors, warnings)`

### `LengthValidator`(Validator)

İçerik uzunluğu validasyonu — T1

**Methods:**

- `__init__(defn, min_chars, max_chars)`
- `async validate(artifact)`
- `_get_content(artifact)`

### `SchemaValidator`(Validator)

YAML/JSON şema validasyonu — T1
Verilen artifact'in geçerli bir YAML/JSON olup olmadığını kontrol eder.

**Methods:**

- `__init__(defn, schema_type)`
- `async validate(artifact)`
- `_get_content(artifact)`

### `ValidatorPipeline`

3-Tier Validator Pipeline.

T1: Fail-fast (sıralı, deterministik, <50ms)
T2: Parallel (bağımsız, LLM çağrılı)
T3: Sequential (T2 sonuçlarına bağımlı)

Her validator content-addressable cache + per-validator timeout ile çalışır.

**Methods:**

- `__init__(cache, cache_policy)`
- `async run(artifact, tier1, tier2, tier3)`
  — Tüm pipeline'ı çalıştır.
- `async _run_tier1(artifact, validators, results)`
  — T1: Sıralı, fail-fast
- `async _run_tier2(artifact, validators, results)`
  — T2: Paralel (bağımsız)
- `async _run_tier3(artifact, validators, results)`
  — T3: Sequential (T2'ye bağımlı)

### `PipelineResult`

Pipeline çıktısı

**Methods:**

- `summary()`

## Functions

### `demo()`
