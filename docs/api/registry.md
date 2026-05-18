# Profile Registry

Prodinamik Engine v0.5 — Profile Registry

3-Tier profile discovery (Review #11):
- Builtin: engine ile gelen, immutable
- User: kullanıcının yazdığı, editlenebilir
- Remote: community registry, imzalı

Resolution: En yüksek priority kazansın.
Dependency graph: diamond dependency check.

**Module:** `engine.registry.py`

## Classes

### `ProfileMetadata`

Profil metadata (profile.yaml içinden)

### `ProfileSource`

Profil kaynağı

### `ProfileRegistry`

3-Tier profile registry.

Sources (ascending priority):
- builtin: /opt/hermes/profiles/ (priority=0, immutable)
- remote: https://registry.prodinamik.dev/profiles/ (priority=50)
- user: ~/.hermes/profiles/ (priority=100)
- project: .hermes/profiles/ (priority=200)

**Methods:**

- `__init__(sources)`
- `resolve(name, version)`
  — Profil adını çözümle.
- `_find_in_source(source, name, version)`
  — Tek bir kaynakta profil ara
- `_load_profile(profile_dir, source)`
  — profile.yaml dosyasından metadata yükle
- `list_profiles()`
  — Tüm kaynaklardan profil listele
- `register(name, version, metadata)`
  — Profil kaydet (user source)
- `dependency_graph(name)`
  — Profil dependency graph'ini çözümle.
- `install_remote(name, version)`
  — Remote profil indir ve user'a yükle (güvenlik kontrollü)
- `stats()`

## Functions

### `demo()`
