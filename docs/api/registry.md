# Profile Registry

Prodinamik Engine v0.5 — Profile Registry

3-Tier profile discovery (Review #11):

- **Builtin**: Engine ile gelen, immutable (priority=0)
- **Remote**: Community registry, imzalı (priority=50)
- **User**: Kullanıcının yazdığı, editlenebilir (priority=100)
- **Project**: Proje bazlı override (priority=200)

Resolution: En yüksek priority kazansın. Alt seviye kaynaklar override edilir.
Dependency graph: Diamond dependency conflict detection.

**Module:** `engine.registry.py`

---

## Classes

### `ProfileMetadata`

Profil metadata (profile.yaml içinden). Her profil versiyonu için bir metadata objesi oluşturulur.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | — | Profil adı |
| `version` | `str` | — | Semantik versiyon (ör: `"1.0.0"`) |
| `description` | `str` | `""` | Kısa açıklama |
| `author` | `str` | `""` | Yazar adı (`author.name` alanından) |
| `extends` | `Optional[str]` | `None` | Üst profil referansı (ör: `"base-validation@2.0"`) |
| `dependencies` | `List[str]` | `[]` | Bağımlı profil listesi (`dependencies.profiles` alanından) |
| `maturity` | `str` | `"alpha"` | Olgunluk seviyesi: `alpha | beta | stable | deprecated` |
| `total_runs` | `int` | `0` | Toplam çalıştırma sayısı |
| `success_rate` | `float` | `0.0` | Başarı oranı (0.0 — 1.0) |
| `known_issues` | `List[str]` | `[]` | Bilinen sorunlar listesi |

---

### `ProfileSource`

Profil kaynağı. Her kaynağın priority, path/url, trust seviyesi ve cache politikası vardır.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | — | Kaynak adı (örn: `"builtin"`, `"user"`, `"remote"`) |
| `priority` | `int` | — | Çözümleme önceliği (yüksek = öncelikli) |
| `path` | `Optional[str]` | `None` | Yerel dosya sistemi yolu |
| `url` | `Optional[str]` | `None` | Uzak registry URL'si |
| `trust` | `str` | `"full"` | Güven seviyesi: `full | verified | untrusted` |
| `immutable` | `bool` | `False` | Değiştirilemez kaynak mı? |
| `cache_ttl` | `int` | `86400` | Cache süresi (saniye) |

---

### `ProfileRegistry`

3-Tier profile registry. Profil yönetiminin merkezi sınıfı.

**Default Sources (ascending priority):**

| Source | Priority | Path/URL | Immutable | Trust |
|---|---|---|---|---|
| `builtin` | 0 | `/opt/hermes/profiles/` | Yes | `full` |
| `remote` | 50 | `https://registry.prodinamik.dev/profiles/` | Yes | `verified` |
| `user` | 100 | `~/.hermes/profiles/` | No | `full` |
| `project` | 200 | `.hermes/profiles/` | No | `full` |

**Method: `__init__(sources: Dict[str, ProfileSource] = None)`**

ProfileRegistry'yi başlatır. `sources` parametresi verilmezse `DEFAULT_SOURCES` kullanılır.

- **sources**: Özel kaynak tanımları. None ise varsayılan 4 kaynak kullanılır.
- **Internal state**: `_cache` (çözümleme cache'i) ve `_profiles` (listelenmiş profiller) initialize edilir.

---

**Method: `resolve(name: str, version: str = None) -> Optional[ProfileMetadata]`**

Profil adını çözümle. En yüksek priority kaynak kazansın.

- **name**: Profil adı (ör: `"software-workflow"`)
- **version**: Versiyon filtresi (ör: `"1.0.0"`). None ise en son versiyon.
- **Returns**: `ProfileMetadata` veya `None` (bulunamazsa)
- **Cache**: Sonuç `_cache`'e yazılır, aynı sorgu tekrarlandığında cache'den döner.
- **Similar suggestion**: Bulunamazsa, benzer isimde profiller önerir (`Did you mean ...?`).

**Algorithm:**
1. Cache kontrolü (`{name}@{version}`)
2. Tüm kaynakları priority'ye göre azalan sırala
3. Her kaynakta `_find_in_source` ile ara
4. Adayları priority'ye göre sırala, en yükseği döndür
5. Bulunamazsa benzer isim önerisi yap

---

**Method: `_find_in_source(source: ProfileSource, name: str, version: str = None) -> Optional[ProfileMetadata]`**

Tek bir kaynakta profil ara (internal).

- **source**: Taranacak kaynak
- **name**: Profil adı
- **version**: Belirtilmişse sadece o versiyonu ara. Yoksa en yeni stable versiyonu bul.
- **Returns**: `ProfileMetadata` veya `None`

**Algorithm:**
1. Kaynak path'i kontrol et (path yoksa None döner)
2. Versiyon belirtilmişse `{base}/{name}/{version}/profile.yaml` ara
3. Versiyon belirtilmemişse `{base}/{name}/` altındaki versiyon dizinlerini tara
4. Versiyonları semantik olarak sırala, en sonuncuyu yükle

---

**Method: `_load_profile(profile_dir: Path, source: ProfileSource) -> Optional[ProfileMetadata]`**

`profile.yaml` dosyasından metadata yükle (internal).

- **profile_dir**: Profil dizini (`profile.yaml` içermeli)
- **source**: Kaynak bilgisi
- **Returns**: `ProfileMetadata` veya yükleme hatasında `None`

**profile.yaml format:**
```yaml
name: software-workflow
version: "1.0.0"
description: Software development lifecycle
author:
  name: Yunus Güngör
extends: base-validation@2.0
dependencies:
  profiles:
    - base-validation
    - code-quality
maturity:
  level: beta           # alpha | beta | stable | deprecated
  total_runs: 15
  success_rate: 0.87
  known_issues:
    - "Memory leak in long runs"
```

---

**Method: `list_profiles() -> List[ProfileMetadata]`**

Tüm kaynaklardan profil listele.

- **Returns**: Benzersiz profil listesi (en yüksek priority versiyonlar)
- **Deduplication**: Aynı isimde profil birden fazla kaynakta varsa, en yüksek priority olan alınır
- **Cache**: İlk çağrıda tüm kaynaklar taranır, sonuç `_profiles`'a cache'lenir

**Algorithm:**
1. `_profiles` cache'i doluysa direkt döndür
2. Kaynakları priority'ye göre azalan sırala
3. Her kaynağın path'ini tara
4. Her profil için en son versiyonu bul
5. `seen` seti ile deduplicate et
6. Sonuçları `_profiles`'a cache'le

---

**Method: `register(name: str, version: str, metadata: ProfileMetadata) -> Tuple[bool, str]`**

Profil kaydet (user source).

- **name**: Profil adı
- **version**: Versiyon
- **metadata**: Kaydedilecek `ProfileMetadata` objesi
- **Returns**: `(success: bool, message: str)`

**Process:**
1. User source'un path'ini kontrol et (yoksa hata döner)
2. `{user_path}/{name}/{version}/` dizinini oluştur
3. `profile.yaml`'e metadata'yı YAML formatında yaz
4. Cache'i temizle (sonraki resolve/listeleme güncel görsün)

---

**Method: `dependency_graph(name: str) -> Dict[str, Any]`**

Profil dependency graph'ini çözümle. Diamond dependency conflict detection.

- **name**: Kök profil adı
- **Returns**: `{ "root": str, "nodes": {}, "edges": [], "conflicts": [] }`

**Return structure:**
```python
{
    "root": "software-workflow",
    "nodes": {
        "software-workflow": "1.0.0",
        "base-validation": "2.0.0",
        "code-quality": "1.5.0"
    },
    "edges": [
        {"from": "software-workflow", "to": "base-validation"},
        {"from": "software-workflow", "to": "code-quality"}
    ],
    "conflicts": [
        {
            "dependency": "base-validation",
            "version_1": "2.0.0",
            "version_2": "1.8.0",
            "between": ["profile-a", "base-validation"]
        }
    ]
}
```

**Diamond conflict detection:**
- Aynı bağımlılık farklı versiyonlarda çözümlenirse conflict olarak işaretlenir
- Her conflict için: bağımlılık adı, iki versiyon ve aralarındaki profil listelenir

---

**Method: `install_remote(name: str, version: str = None) -> Tuple[bool, str]`**

Remote profil indir ve user'a yükle (güvenlik kontrollü).

- **name**: Remote profil adı
- **version**: Versiyon (None = latest)
- **Returns**: `(success: bool, message: str)`
- **Status**: Henüz implementasyon aşamasında (TODO). Remote source'un URL'si kullanılarak download planlanmıştır.

---

**Method: `stats() -> dict`**

Registry istatistikleri döndürür.

- **Returns**:
```python
{
    "sources": {
        "builtin": {"priority": 0, "trust": "full"},
        "user": {"priority": 100, "trust": "full"},
        ...
    },
    "profiles_cached": 5,      # _profiles cache boyutu
    "resolution_cache": 3,     # _cache (resolve cache) boyutu
}
```

---

## Functions

### `demo()`

ProfileRegistry'nin tüm temel işlemlerini test eden demo fonksiyonu.

**Test flow:**
1. Registry oluştur ve kaynakları listele
2. User source için geçici bir dizin oluştur
3. `software-workflow` profilini kaydet (`register`)
4. Profili çözümle (`resolve`) ve versiyon doğrula
5. Tüm profilleri listele (`list_profiles`)
6. Dependency graph çözümle (`dependency_graph`)
7. Registry istatistiklerini görüntüle (`stats`)

**Usage:**
```python
from engine.registry import demo
demo()
```

---

## Usage Examples

### Basic Profile Resolution

```python
from engine.registry import ProfileRegistry

reg = ProfileRegistry()

# Resolve a profile (latest version)
profile = reg.resolve("software-workflow")
if profile:
    print(f"Found: {profile.name}@{profile.version}")
    print(f"Author: {profile.author}")
    print(f"Maturity: {profile.maturity}")

# Resolve a specific version
profile_v1 = reg.resolve("base-validation", "2.0.0")
```

### Register a New Profile

```python
from engine.registry import ProfileRegistry, ProfileMetadata

reg = ProfileRegistry()
meta = ProfileMetadata(
    name="my-workflow",
    version="1.0.0",
    description="Custom workflow",
    author="Developer",
    maturity="alpha",
)
success, msg = reg.register("my-workflow", "1.0.0", meta)
```

### Dependency Analysis

```python
from engine.registry import ProfileRegistry

reg = ProfileRegistry()
graph = reg.dependency_graph("software-workflow")

if graph["conflicts"]:
    print("⚠️ Diamond conflicts detected:")
    for c in graph["conflicts"]:
        print(f"  {c['dependency']}: v{c['version_1']} vs v{c['version_2']}")
else:
    print("✅ No dependency conflicts")
```

---

## Error Handling

- **Profil bulunamazsa**: `resolve()` `None` döner, benzer isim önerisi loglanır
- **YAML yükleme hatası**: `_load_profile()` `None` döner, hata mesajı terminale yazılır
- **Kaynak dizini yoksa**: Sessizce atlanır (`list_profiles` / `_find_in_source`)
- **User source yoksa**: `register()` `(False, "User source not configured")` döner
- **Remote install**: Henüz implemente edilmedi — `(False, "not yet implemented")` döner

---

## Architecture Notes

- **3-Tier design**: Priority-based resolution sayesinde proje bazlı profiller her zaman built-in'lere baskın gelir.
- **No hard override**: Builtin kaynaklar immutable'dır, üzerine yazılamaz.
- **Cache invalidation**: `register()` ve `install_remote()` sonrası ilgili cache temizlenir.
- **Extension**: Yeni kaynak tipleri `ProfileSource` ile kolayca eklenebilir.
- **Version sorting**: Basit semantik versiyon sıralaması (split by `.`, int cast).
- **Multi-source merge**: Aynı profil adı birden çok kaynakta varsa, en yüksek priority'li versiyon kullanılır.
