# Cost Tracking

Prodinamik Engine v0.5 — Cost Tracker

Multi-dimensional cost tracking:
1. TOKENS — LLM çağrıları (validator, generation)
2. COMPUTE — CPU/GPU süresi (build, test)
3. STORAGE — Disk kullanımı (run data, cache, log)
4. NETWORK — API çağrıları (adapter, remote validator)

Deferred Efficiency (Review #6):
- T0: Run bitince benzer run'ların ortalamasına göre tahmin
- T1: N gün sonra API'den gerçek metrikler

Cost-Aware Events (Review #7):
- Event'ler cost_usd taşır
- TemporalCostDebugger ile cost timeline + anomaly detection

**Module:** `engine.cost.py`

## Classes

### `LLMCall`

Tek bir LLM API çağrısı

**Methods:**

- `__post_init__()`

### `ComputeOp`

CPU/GPU işlemi

**Methods:**

- `__post_init__()`

### `NetworkCall`

API/network çağrısı

**Methods:**

- `__post_init__()`

### `CostTracker`

Multi-dimensional cost tracker.

Cost per model ($/1M tokens):
  deepseek-v4-flash: $0.15 input / $0.60 output
  gpt-4o:           $2.50 / $10.00
  claude-sonnet-4:  $3.00 / $15.00

Compute: $0.05/core/hour, $2.50/GPU/hour
Storage: $0.10/GB/month

**Methods:**

- `__init__()`
- `record_llm(model, input_tokens, output_tokens, purpose, validator, wasted)`
  — LLM çağrısı kaydet. Cost'u döndür.
- `record_compute(phase, duration_s, cores, gpu)`
  — Compute işlemi kaydet. Cost'u döndür.
- `record_network(adapter, endpoint, duration_ms, cost_usd, status_code)`
  — Network çağrısı kaydet.
- `record_storage(bytes_count)`
  — Storage kullanımı güncelle.
- `total_llm_cost()`
- `total_compute_cost()`
- `total_network_cost()`
- `total_storage_cost()`
- `total_usd()`
- `total_llm_tokens()`
- `total_llm_calls()`
- `breakdown_by_validator()`
  — Hangi validator ne kadar token harcadı?
- `breakdown_by_purpose()`
  — Ne amaçla harcandı?
- `breakdown_by_model()`
  — Hangi model ne kadar harcadı?
- `waste_estimate()`
  — Boşa giden token maliyeti
- `top_spenders(n)`
  — En pahalı N validator/phase
- `savings_tips()`
  — Maliyet düşürme önerileri
- `summary()`
- `efficiency_score()`
  — output_value / total_cost (şimdilik output_value=1.0 varsayılan)
- `to_dict()`

### `RunEfficiency`

Bir run'ın efficiency verisi

**Methods:**

- `__post_init__()`
- `display_value()`
- `variance_pct()`

### `EfficiencyTracker`

Efficiency iki aşamada hesaplanır:
T0 (run bitince):  Tahmini — benzer run'ların ortalaması
T1 (N gün sonra):  Gerçek — API'den veri çekilince

**Methods:**

- `__init__()`
- `add_completed(run)`
  — Tamamlanmış run ekle
- `estimate(slug, profile, format, total_cost)`
  — Run bitince: benzer profile+format'taki run'ların
- `record_actual(slug, actual_value, source)`
  — N gün sonra: gerçek efficiency değerini gir.
- `display(slug)`

### `CostAnomaly`

İstatistiksel cost anomalisi

### `TemporalCostDebugger`

Cost-Aware event'ler üzerinden çalışır.
Event store'dan cost verisini okur, anomaly detection yapar.

**Methods:**

- `analyze_events(events)`
  — Event listesinden cost analizi çıkar.
- `cost_timeline(events)`
  — Event timeline'ı cost ile göster

## Functions

### `demo()`
