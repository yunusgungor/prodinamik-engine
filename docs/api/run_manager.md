# Run Manager

Prodinamik Engine v0.5 — Run Manager

Run CRUD işlemleri:
- create_run: Yeni run oluştur
- get_run: Run bilgisi oku
- update_state: State güncelle (WAL + snapshot)
- archive_run: Run arşivle
- search_runs: Run'larda ara
- list_runs: Tüm run'ları listele

State persistence:
- WAL (Write-Ahead Log): Her değişiklik önce log'a
- Atomic snapshot: .tmp yaz → rename → fsync
- Recovery: Crash sonrası WAL replay

**Module:** `engine.run_manager.py`

## Classes

### `RunStatus`(Enum)

### `RunMeta`

Run metadata — content-object.md'ye yazılır

**Methods:**

- `to_dict()`
- `from_dict(cls, d)`

### `Run`

Tek bir run'ın tam temsili

### `RunManager`

Run CRUD + state persistence.

Dizin yapısı:
.hermes/runs/active/{slug}/
├── content-object.md     # Run metadata
├── events/               # Event store
│   ├── 0000000001.json
│   └── ...
└── artifacts/            # Run içinde üretilen dosyalar

.hermes/runs/archive/{slug}/  # Archived run
.hermes/state/
├── runs_state.json       # Snapshot (atomic write)
└── runs_state.json.tmp   # Geçici yazma
.hermes/wal/
└── wal_*.log             # Write-ahead log

**Methods:**

- `__init__(base_path)`
- `_ensure_dirs()`
  — Gerekli dizin yapısını oluştur
- `_run_path(slug)`
- `_archive_path(slug)`
- `_state_path()`
- `_state_tmp_path()`
- `slugify(text)`
  — Temiz URL-safe slug oluştur
- `create_run(title, profile, slug)`
  — Yeni run oluştur.
- `get_run(slug, profile)`
  — Run bilgisini oku. Yoksa None döner.
- `list_runs(include_archived)`
  — Tüm run'ları listele
- `update_state(slug, to_state, profile)`
  — Run'ın state'ini güncelle.
- `archive_run(slug)`
  — Run'ı archive'e taşı.
- `_load_snapshot()`
  — State snapshot'ını yükle
- `_update_snapshot(slug, data)`
  — Snapshot'ı atomic olarak güncelle.
- `_append_wal(entry)`
  — WAL'a entry ekle (single)
- `_append_wal_batch(entries)`
  — Toplu WAL yazma (batch).
- `recover()`
  — Crash sonrası kurtarma.
- `_compact_wal(snapshot)`
  — WAL'ı compact et: snapshot ile WAL arasındaki farkı kapat.
- `get_state_elapsed(slug)`
  — Bir run'ın mevcut state'inde ne kadar süredir olduğunu döndür (saniye).
- `_write_meta(meta, run_path)`
  — content-object.md dosyasına meta yaz
- `_read_meta(run_path)`
  — content-object.md'den meta oku
- `search_runs(query)`
  — Run'larda basit metin araması

### `TestProfile`(ProductProfile)

## Functions

### `demo()`
