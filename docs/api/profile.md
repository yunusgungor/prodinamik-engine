# Product Profile

Prodinamik Engine v0.5 — Product Profile Base Class

Her ürün tipi (Content, Software, Research, ...) bir ProductProfile olarak
tanımlanır. Profile, state machine, validator set'i, adapter listesi,
store şeması, template'ler ve budget tanımını içerir.

Kullanım:
    class SoftwareProfile(ProductProfile):
        name = "software"
        version = "1.0"
        ...

**Module:** `engine.profile.py`

## Classes

### `Budget`

Per-profile resource budget

### `ValidatorTier`(Enum)

### `ValidatorDef`

Validator tanımı (profile YAML'de kullanılır)

### `AdapterDef`

Adapter tanımı

### `StoreDef`

Store tipi tanımı

### `TemplateDef`

Template tanımı

### `Validator`(ABC)

Base validator sınıfı. Her ValidatorDef için bir instance.

**Methods:**

- `__init__(defn)`
- `async validate(artifact)`
- `async auto_fix(artifact)`
  — Opsiyonel: otomatik düzeltme
- `explain(result)`
  — Validasyon sonucunu açıkla

### `ValidationResult`

Validator çıktısı

### `Adapter`(ABC)

Base adapter sınıfı. Circuit breaker + fallback içerir.

**Methods:**

- `__init__(defn)`
- `async _send(artifact)`
  — Gerçek gönderme işlemi (alt sınıflar override eder)
- `async send(artifact)`
  — Circuit breaker + retry + fallback ile send
- `_record_failure()`
- `async _fallback(artifact)`
  — Varsayılan fallback: artifact'i dosyaya yaz

### `TransientError`(Exception)

Geçici hata (retry yapılabilir)

### `PermanentError`(Exception)

Kalıcı hata (retry yapılamaz)

### `AdapterResult`

Adapter çıktısı

### `ProductProfile`(ABC)

Bir ürün tipini tanımlar.

Alt sınıflar şunları TANIMLAMALIDIR:
- name: str
- version: str
- _state_machine_yaml: str (inline YAML veya path)

Alt sınıflar ŞUNLARI OVERRIDE EDEBİLİR:
- setup_validators()
- setup_adapters()
- setup_stores()
- setup_templates()
- setup_budget()

**Methods:**

- `__init__()`
- `initialize()`
  — Profile'i başlat. State machine'i yükle, validator'ları setup et.
- `state_machine()`
- `setup_validators()`
  — Validator'ları tanımla
- `setup_adapters()`
  — Adapter'ları tanımla
- `setup_stores()`
  — Store şemasını tanımla
- `setup_templates()`
  — Template'leri tanımla
- `setup_budget()`
  — Budget'ı yapılandır
- `validators()`
- `tier1_validators()`
- `tier2_validators()`
- `tier3_validators()`
- `adapters()`
- `stores()`
- `templates()`
- `budget()`
- `add_validator(defn)`
- `add_adapter(defn)`
- `add_store(defn)`
- `add_template(defn)`
- `summary()`
- `__repr__()`
