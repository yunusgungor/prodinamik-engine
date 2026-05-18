# Run Manager

Prodinamik Engine v0.5 — Run Manager

Run CRUD operations and state persistence engine. Every "run" represents a single execution
of a product profile through its state machine lifecycle.

**Core responsibilities:**
- Run lifecycle management (create, read, update state, archive, delete)
- State persistence via Write-Ahead Log (WAL) + atomic snapshots
- Crash recovery with WAL replay
- Run metadata storage in content-object.md (YAML frontmatter)
- State machine transition validation
- Run search and listing

**Module:** `engine.run_manager.py`

---

## Enums

### `RunStatus`

Run durumunu belirten enum.

| Member | Value | Description |
|---|---|---|
| `ACTIVE` | `"active"` | Çalışan/aktif run |
| `ARCHIVED` | `"archived"` | Arşivlenmiş run |
| `ERROR` | `"error"` | Hata durumundaki run |

---

## Data Classes

### `RunMeta`

Run metadata — `content-object.md`'ye YAML frontmatter olarak yazılır. Her run'ın
kimlik bilgilerini, profil adını ve mevcut state'ini taşır.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `slug` | `str` | — | Benzersiz run tanımlayıcısı (URL-safe) |
| `profile` | `str` | — | Kullanılan profil adı |
| `title` | `str` | — | Run başlığı |
| `created_at` | `str` | `""` | ISO format oluşturulma zamanı |
| `updated_at` | `str` | `""` | ISO format son güncelleme zamanı |
| `status` | `str` | `"active"` | RunStatus değeri |
| `state` | `str` | `""` | Mevcut state machine state'i |
| `version` | `int` | `0` | Optimistic locking versiyonu |

**Methods:**

**`to_dict() -> dict`**
RunMeta'yı sözlüğe dönüştürür (`dataclasses.asdict` kullanır).

**`from_dict(cls, d: dict) -> RunMeta`**
Sözlükten `RunMeta` oluşturur. Sadece `__dataclass_fields__` içindeki anahtarları alır,
fazladan alanları yok sayar.

---

### `Run`

Tek bir run'ın tam temsili. Meta, runtime state ve profili bir arada tutar.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `meta` | `RunMeta` | Run metadata (slug, title, state, version vb.) |
| `runtime` | `RuntimeState` | Runtime state machine state'i (current_state, version) |
| `profile` | `ProductProfile` | Run'ın bağlı olduğu profil |

---

## Class: `RunManager`

Run CRUD + state persistence. Tüm run operasyonlarının merkezi sınıfı.

**Directory structure:**

```
.hermes/
├── runs/
│   ├── active/{slug}/
│   │   ├── content-object.md     # Run metadata (YAML frontmatter)
│   │   ├── events/               # Event store
│   │   │   ├── 0000000001.json
│   │   │   └── ...
│   │   └── artifacts/            # Run içinde üretilen dosyalar
│   └── archive/{slug}/           # Archived run (taşınmış)
├── state/
│   ├── runs_state.json           # Snapshot (atomic write)
│   └── runs_state.json.tmp       # Geçici yazma (atomic rename için)
└── wal/
    └── wal_*.log                 # Write-ahead log entry'leri
    └── wal_batch_*.batch         # Toplu WAL yazma (batch)
```

---

### Constructor

**`__init__(base_path: str = ".hermes")`**

RunManager'ı başlatır ve gerekli dizin yapısını oluşturur.

- **base_path**: Kök dizin. Varsayılan: `".hermes"`. Testlerde geçici bir dizin verilebilir.

---

### Directory Utilities

**`_ensure_dirs()`**

Gerekli dizin yapısını oluşturur:
- `.hermes/runs/active/`
- `.hermes/runs/archive/`
- `.hermes/state/`
- `.hermes/wal/`

---

**`_run_path(slug: str) -> Path`**

Active run dizin yolunu döndürür: `{base}/runs/active/{slug}/`

---

**`_archive_path(slug: str) -> Path`**

Archive run dizin yolunu döndürür: `{base}/runs/archive/{slug}/`

---

**`_state_path() -> Path`** ve **`_state_tmp_path() -> Path`**

State snapshot yolları:
- `_state_path()` → `{base}/state/runs_state.json`
- `_state_tmp_path()` → `{base}/state/runs_state.json.tmp`

---

### Slug Generation

**`slugify(text: str) -> str`**

Temiz URL-safe slug oluşturur.

- **text**: Kaynak metin (ör: run başlığı)
- **Returns**: Küçük harf, tire ile ayrılmış, max 80 karakter
- **Fallback**: Boş sonuç durumunda `run-{timestamp}` formatında unique slug

**Algorithm:**
1. lowercase + strip
2. Alfanumerik olmayan karakterleri temizle
3. Whitespace/underscore → tire
4. Multiple tire → tek tire
5. Baştaki/sondaki tireleri kes
6. 80 karakterle sınırla

---

### CRUD: Create

**`create_run(title: str, profile: ProductProfile, slug: str = None) -> Run`**

Yeni bir run oluşturur.

- **title**: Run başlığı
- **profile**: Kullanılacak profil (`ProductProfile` instance). State machine içermelidir.
- **slug**: İsteğe bağlı özel slug. Verilmezse title'dan otomatik oluşturulur.
- **Returns**: Yeni oluşturulan `Run` objesi
- **Raises**: `ValueError` eğer:
  - Profile'in state machine'i yoksa (`"Profile '{name}' has no state machine"`)
  - Run zaten varsa (`"Run '{slug}' already exists"`)

**Process:**
1. Profile'in state machine'ini kontrol et
2. Slug oluştur (verilmediyse title'dan)
3. Initial state'i profile'in state machine'inden al
4. `RunMeta` oluştur (created_at, updated_at = now)
5. Dizin yapısını oluştur (`run_path`, `events/`, `artifacts/`)
6. `content-object.md`'ye meta yaz
7. WAL'a `create` action'ı ekle
8. Snapshot'ı güncelle (initial state ile)
9. `Run` objesini döndür

**Example:**
```python
from engine.run_manager import RunManager
from engine.profile import ProductProfile

# profile already has a state machine
mgr = RunManager(base_path="./.hermes")
run = mgr.create_run("My First Run", profile)
print(f"Created: {run.meta.slug} at {run.meta.state}")
```

---

### CRUD: Read

**`get_run(slug: str, profile: ProductProfile = None) -> Optional[Run]`**

Run bilgisini okur.

- **slug**: Run slug'ı
- **profile**: İsteğe bağlı profil (runtime state oluşturmak için)
- **Returns**: `Run` objesi veya `None`
- **Fallback**: Active'de bulunamazsa archive'de arar

**Process:**
1. Active run path'ini kontrol et
2. Yoksa archive path'ini kontrol et
3. `content-object.md`'den meta oku
4. `Run` objesi oluştur (meta + runtimeState + profile)

---

**`list_runs(include_archived: bool = False) -> List[RunMeta]`**

Tüm run'ları listeler.

- **include_archived**: True ise arşivlenmiş run'ları da dahil et
- **Returns**: `updated_at` alanına göre azalan sıralı `RunMeta` listesi
- **Iteration**: Aktif run dizini altındaki her dizin taranır

---

### CRUD: State Update

**`update_state(slug: str, to_state: str, profile: ProductProfile = None) -> Run`**

Run'ın state'ini günceller. State machine validasyonu, WAL ve snapshot atomic olarak güncellenir.

- **slug**: Run slug'ı
- **to_state**: Hedef state adı
- **profile**: İsteğe bağlı profil (state machine validasyonu için)
- **Returns**: Güncellenmiş `Run` objesi
- **Raises**: `ValueError` eğer:
  - Run bulunamazsa
  - Metadata okunamazsa
  - Transition geçersizse (`"Transition X → Y rejected: {reason}"`)

**Transition validation (profile varsa):**
1. `profile.state_machine.can_transition(from_state, to_state, runtime_state)` çağrılır
2. İzin verilmiyorsa `ValueError` fırlatılır

**Persistence process:**
1. Optimistic locking: `meta.version += 1`
2. WAL'a `transition` action'ı yaz (`from`, `to`, `version`, `timestamp`)
3. Snapshot atomically güncelle (`.tmp` → `rename` → `fsync`)
4. `content-object.md`'yi güncelle (yeni state, updated_at, version)

---

### CRUD: Archive

**`archive_run(slug: str) -> bool`**

Run'ı active'den archive'e taşır.

- **slug**: Run slug'ı
- **Returns**: `True` (başarılı)
- **Raises**: `ValueError` eğer run bulunamazsa

**Process:**
1. `active/{slug}/` → `archive/{slug}/` taşı (shutil.move)
2. Archive'de aynı slug varsa önce sil (shutil.rmtree)
3. Snapshot'ı güncelle: `status: "archived"`
4. WAL'a `archive` action'ı ekle

---

### State Persistence: Snapshot

**`_load_snapshot() -> Dict[str, dict]`**

State snapshot'ını `runs_state.json`'dan yükler.

- **Returns**: Tüm run'ların state bilgilerini içeren sözlük
- **Error handling**: JSON decode hatası veya okuma hatasında boş `{}` döner

**JSON format:**
```json
{
  "my-run": {
    "state": "process",
    "profile": "software-workflow",
    "status": "active",
    "updated_at": "2026-05-18T14:51:00",
    "version": 3
  },
  "another-run": {
    "state": "done",
    "profile": "content-pipeline",
    "status": "archived",
    "updated_at": "2026-05-17T10:30:00"
  }
}
```

---

**`_update_snapshot(slug: str, data: dict)`**

Snapshot'ı atomic olarak günceller.

- **slug**: Güncellenecek run slug'ı
- **data**: Eklenecek/güncellenecek alanlar (örn: `{"state": "process", "version": 3}`)
- **Atomic guarantee**: `.tmp` dosyasına yaz → `replace()` (POSIX atomic rename) → final

**Process:**
1. Mevcut snapshot'ı yükle
2. `data` ile merge et (varsa update, yoksa ekle)
3. Geçici dosyaya yaz (`runs_state.json.tmp`)
4. Atomic rename ile final dosyaya taşı

---

### State Persistence: Write-Ahead Log (WAL)

**`_append_wal(entry: dict)`**

WAL'a tek bir entry ekler.

- **entry**: `{"action": str, "slug": str, ...}` formatında log entry'si
- **Checksum**: Entry'in SHA-256 hash'i (ilk 16 hex karakter) otomatik eklenir
- **Filename**: `wal_{YYYYMMDD_HHMMSS_ffffff}.log` (mikrosaniye hassasiyetinde)

**Entry format:**
```json
{
    "action": "create",
    "slug": "my-first-run",
    "profile": "software-workflow",
    "state": "start",
    "timestamp": "2026-05-18T14:51:00.123456",
    "checksum": "a1b2c3d4e5f67890"
}
```

---

**`_append_wal_batch(entries: List[dict])`**

Toplu WAL yazma (batch). Tüm entry'leri tek bir `.batch` dosyasına yazar.
Per-entry file write yerine tek write ile ~5x hızlıdır (10+ entry için önerilir).

- **entries**: WAL entry listesi (her entry'e otomatik checksum eklenir)
- **Filename**: `wal_batch_{YYYYMMDD_HHMMSS_ffffff}.batch`
- **Atomic**: Tüm batch tek `write_text` çağrısı ile yazılır

---

### Crash Recovery

**`recover() -> Dict[str, dict]`**

Crash sonrası kurtarma mekanizması. Snapshot + WAL replay ile tutarlı durumu geri yükler.

- **Returns**: Recovery sonrası güncellenmiş snapshot sözlüğü

**Recovery process:**
1. Snapshot'ı yükle (`_load_snapshot`)
2. Tüm WAL `.log` dosyalarını kronolojik sırada oku
3. Her entry için checksum doğrulaması yap
4. Geçerli entry'leri snapshot'a replay et:
   - `create`: state, profile, status, updated_at ekle
   - `transition`: state → `to`, updated_at güncelle
   - `archive`: status → `"archived"`, updated_at güncelle
5. WAL compact işlemini çalıştır
6. Güncellenmiş snapshot'ı döndür

**Checksum validation:**
```python
entry_str = json.dumps(
    {k: v for k, v in entry.items() if k != "checksum"},
    sort_keys=True
)
expected = sha256(entry_str.encode()).hexdigest()[:16]
if entry.get("checksum") != expected:
    print(f"⚠️ WAL checksum mismatch: {wf.name}")
    continue  # skip corrupted entry
```

---

**`_compact_wal(snapshot: Dict[str, dict])`**

Recovery sonrası WAL'ı compact eder. Snapshot'tan eski WAL dosyalarını temizler.

- **snapshot**: Recovery sonrası güncel snapshot
- **Process**: Snapshot'taki en son `updated_at`'ten eski timestamp'e sahip WAL dosyalarını sil
- **Safety**: Sadece snapshot'ın kapsadığı entry'ler silinir

---

### Utility Methods

**`get_state_elapsed(slug: str) -> Optional[float]`**

Bir run'ın mevcut state'inde ne kadar süredir olduğunu döndürür.

- **slug**: Run slug'ı
- **Returns**: Saniye cinsinden süre (float) veya `None` (bulunamazsa / geçersiz timestamp)
- **Calculation**: `datetime.now() - updated_at` → `total_seconds()`

---

### Meta Read/Write

**`_write_meta(meta: RunMeta, run_path: Path)`**

`content-object.md` dosyasına YAML frontmatter formatında meta yazar.

- **meta**: `RunMeta` objesi
- **run_path**: Run dizini

**content-object.md format:**
```markdown
---
slug: my-first-run
profile: software-workflow
title: My First Run
created_at: 2026-05-18T14:51:00.123456
updated_at: 2026-05-18T14:51:00.123456
status: active
state: start
version: 0
---
```

---

**`_read_meta(run_path: Path) -> Optional[RunMeta]`**

`content-object.md`'den meta okur.

- **run_path**: Run dizini
- **Returns**: `RunMeta` objesi veya `None` (dosya yoksa)
- **Parsing**: Basit satır bazlı YAML frontmatter parser (two-pass parser gerektirmez)
- **Fallback**: `slug` alanı yoksa dizin adı kullanılır, `title` yoksa slug kullanılır

---

### Search

**`search_runs(query: str) -> List[RunMeta]`**

Run'larda basit metin araması yapar.

- **query**: Aranacak metin (case-insensitive)
- **Returns**: Eşleşen `RunMeta` listesi
- **Search fields**: `title`, `slug`, `profile`
- **Algorithm**: `query.lower() in field.lower()` (substring match)

**Example:**
```python
results = mgr.search_runs("test")
# Returns runs where title/slug/profile contains "test" (case-insensitive)
```

---

## Functions

### `demo()`

Tüm `RunManager` işlemlerini test eden demo fonksiyonu.

**Test flow:**
1. State machine YAML'ı parse et (3-state: start → process → done)
2. Test profili oluştur
3. Run oluştur (`create_run`)
4. Run oku (`get_run`)
5. State güncelle (`update_state`: start → process)
6. Run'ları listele (`list_runs`)
7. Run'larda ara (`search_runs`)
8. Run arşivle (`archive_run`)
9. Arşiv dahil listele (`list_runs(include_archived=True)`)
10. Kurtarma testi (`recover`)

**Usage:**
```python
from engine.run_manager import demo
demo()
```

---

## Usage Examples

### Full Run Lifecycle

```python
from engine.run_manager import RunManager
from engine.profile import ProductProfile

mgr = RunManager(base_path="./.hermes")

# Create
run = mgr.create_run("Deploy v2.1", profile)
print(f"Created: {run.meta.slug} → state={run.meta.state}")

# Read
run = mgr.get_run(run.meta.slug)
print(f"Read: {run.meta.title} @ {run.meta.state}")

# Update state (with transition validation)
run = mgr.update_state(run.meta.slug, "process", profile)
print(f"Transitioned to: {run.meta.state} (v{run.meta.version})")

# Search
results = mgr.search_runs("deploy")
print(f"Found {len(results)} matching runs")

# Archive
mgr.archive_run(run.meta.slug)
print("Run archived")

# List all (including archived)
all_runs = mgr.list_runs(include_archived=True)
print(f"Total runs: {len(all_runs)}")
```

### Crash Recovery

```python
from engine.run_manager import RunManager

# After a crash, create a new manager instance
mgr = RunManager(base_path="./.hermes")

# WAL replay restores the latest consistent state
snapshot = mgr.recover()
for slug, state in snapshot.items():
    print(f"  {slug}: state={state.get('state')}, status={state.get('status')}")
```

### Batch WAL Writing

```python
# _append_wal_batch is used internally for bulk operations
# For 10+ entries, it's ~5x faster than individual _append_wal calls
entries = [
    {"action": "create", "slug": "run-1", "state": "start", "timestamp": "..."},
    {"action": "create", "slug": "run-2", "state": "start", "timestamp": "..."},
    {"action": "transition", "slug": "run-1", "from": "start", "to": "process", ...},
]
mgr._append_wal_batch(entries)
```

---

## Error Handling

- **Profile without state machine**: `create_run` raises `ValueError`
- **Duplicate run**: `create_run` raises `ValueError` (`"already exists"`)
- **Run not found**: `get_run` returns `None`; `update_state` / `archive_run` raises `ValueError`
- **Invalid transition**: `update_state` raises `ValueError` with state machine rejection reason
- **Corrupt metadata**: `_read_meta` returns `None` silently
- **Corrupt snapshot**: `_load_snapshot` returns `{}` silently
- **Corrupt WAL entry**: `recover` skips entry if checksum mismatch, prints warning

---

## Architecture Notes

- **WAL-first**: State machine'e her müdahale önce WAL'a yazılır, sonra snapshot güncellenir. Bu sayede crash durumunda WAL replay ile tutarlılık sağlanır.
- **Atomic snapshot**: POSIX `rename()` atomic guarantee'si kullanılır. `.tmp` → final.
- **Optimistic locking**: `RunMeta.version` her state güncellemesinde artar. Future: concurrent update detection.
- **Separation of concerns**: Metadata (`content-object.md`) ile state snapshot (`runs_state.json`) ayrı tutulur. Snapshot hızlı query için, metadata ise kalıcı storage için.
- **Event sourcing pattern**: `events/` dizini event sourcing için hazırlanmıştır (şu anda boş, future use).
- **Artifact isolation**: Her run'ın `artifacts/` dizini kendine özgüdür, diğer run'larla karışmaz.
- **Archive separation**: Archive dizini active run'lardan ayrıdır. `list_runs` default olarak sadece active'leri gösterir.
