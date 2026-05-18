"""
Prodinamik Engine v0.5 — Profile Registry

3-Tier profile discovery (Review #11):
- Builtin: engine ile gelen, immutable
- User: kullanıcının yazdığı, editlenebilir
- Remote: community registry, imzalı

Resolution: En yüksek priority kazansın.
Dependency graph: diamond dependency check.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import json
import yaml


@dataclass
class ProfileMetadata:
    """Profil metadata (profile.yaml içinden)"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    extends: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    maturity: str = "alpha"  # alpha | beta | stable | deprecated
    total_runs: int = 0
    success_rate: float = 0.0
    known_issues: List[str] = field(default_factory=list)


@dataclass
class ProfileSource:
    """Profil kaynağı"""
    name: str
    priority: int
    path: Optional[str] = None
    url: Optional[str] = None
    trust: str = "full"       # full | verified | untrusted
    immutable: bool = False
    cache_ttl: int = 86400


class ProfileRegistry:
    """
    3-Tier profile registry.

    Sources (ascending priority):
    - builtin: /opt/hermes/profiles/ (priority=0, immutable)
    - remote: https://registry.prodinamik.dev/profiles/ (priority=50)
    - user: ~/.hermes/profiles/ (priority=100)
    - project: .hermes/profiles/ (priority=200)
    """

    DEFAULT_SOURCES = {
        "builtin": ProfileSource(
            name="builtin", priority=0, path="/opt/hermes/profiles/",
            trust="full", immutable=True,
        ),
        "user": ProfileSource(
            name="user", priority=100, path="~/.hermes/profiles/",
            trust="full", immutable=False,
        ),
        "project": ProfileSource(
            name="project", priority=200, path=".hermes/profiles/",
            trust="full", immutable=False,
        ),
        "remote": ProfileSource(
            name="remote", priority=50, url="https://registry.prodinamik.dev/profiles/",
            trust="verified", immutable=True, cache_ttl=86400,
        ),
    }

    def __init__(self, sources: Dict[str, ProfileSource] = None):
        self.sources = sources or dict(self.DEFAULT_SOURCES)
        self._cache: Dict[str, ProfileMetadata] = {}
        self._profiles: Dict[str, ProfileMetadata] = {}

    def resolve(self, name: str, version: str = None) -> Optional[ProfileMetadata]:
        """
        Profil adını çözümle.
        En yüksek priority kaynak kazansın.
        version belirtilmişse sadece o versiyonu ara.
        """
        # Cache
        cache_key = f"{name}@{version}" if version else name
        if cache_key in self._cache:
            return self._cache[cache_key]

        candidates = []

        for source_name, source in sorted(
            self.sources.items(),
            key=lambda x: x[1].priority,
            reverse=True
        ):
            profile = self._find_in_source(source, name, version)
            if profile:
                candidates.append((source.priority, profile))

        if not candidates:
            available = self.list_profiles()
            similar = [p for p in available if name.lower() in p.name.lower()]
            hint = f" Did you mean one of: {similar[:3]}?" if similar else ""
            print(f"⚠️ Profile '{name}' not found in any source.{hint}")
            return None

        # En yüksek priority
        candidates.sort(key=lambda x: x[0], reverse=True)
        result = candidates[0][1]

        self._cache[cache_key] = result
        return result

    def _find_in_source(self, source: ProfileSource, name: str,
                         version: str = None) -> Optional[ProfileMetadata]:
        """Tek bir kaynakta profil ara"""
        if source.path:
            base = Path(source.path).expanduser()
            if not base.exists():
                return None

            # Versiyon belirtilmişse
            if version:
                profile_dir = base / name / version
                if profile_dir.exists():
                    return self._load_profile(profile_dir, source)
                return None

            # Versiyon belirtilmemişse → en yeni stable bul
            versions = sorted([
                d.name for d in (base / name).iterdir()
                if d.is_dir() and (d / "profile.yaml").exists()
            ]) if (base / name).exists() else []

            # Sort by version (simple semantic)
            versions.sort(key=lambda v: [int(x) for x in v.split(".")])
            if versions:
                return self._load_profile(base / name / versions[-1], source)

        return None

    def _load_profile(self, profile_dir: Path, source: ProfileSource
                      ) -> Optional[ProfileMetadata]:
        """profile.yaml dosyasından metadata yükle"""
        yaml_path = profile_dir / "profile.yaml"
        if not yaml_path.exists():
            return None

        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            return ProfileMetadata(
                name=data.get("name", "unknown"),
                version=data.get("version", "0.0.0"),
                description=data.get("description", ""),
                author=data.get("author", {}).get("name", ""),
                extends=data.get("extends"),
                dependencies=data.get("dependencies", {}).get("profiles", []),
                maturity=data.get("maturity", {}).get("level", "alpha"),
                total_runs=data.get("maturity", {}).get("total_runs", 0),
                success_rate=data.get("maturity", {}).get("success_rate", 0),
                known_issues=data.get("maturity", {}).get("known_issues", []),
            )
        except Exception as e:
            print(f"⚠️ Failed to load profile from {yaml_path}: {e}")
            return None

    def list_profiles(self) -> List[ProfileMetadata]:
        """Tüm kaynaklardan profil listele"""
        if self._profiles:
            return list(self._profiles.values())

        all_profiles = []
        seen = set()

        for source_name, source in sorted(
            self.sources.items(),
            key=lambda x: x[1].priority,
            reverse=True
        ):
            if source.path:
                base = Path(source.path).expanduser()
                if not base.exists():
                    continue

                for profile_dir in base.iterdir():
                    if not profile_dir.is_dir():
                        continue

                    # Versiyon alt dizinlerini tara
                    versions = sorted([
                        vdir for vdir in profile_dir.iterdir()
                        if vdir.is_dir() and (vdir / "profile.yaml").exists()
                    ], key=lambda p: p.name)

                    if not versions:
                        continue

                    # En son versiyonu al
                    latest = versions[-1]
                    meta = self._load_profile(latest, source)
                    if meta and meta.name not in seen:
                        seen.add(meta.name)
                        all_profiles.append(meta)

        self._profiles = {p.name: p for p in all_profiles}
        return all_profiles

    def register(self, name: str, version: str, metadata: ProfileMetadata):
        """Profil kaydet (user source)"""
        user_source = self.sources.get("user")
        if not user_source or not user_source.path:
            return False, "User source not configured"

        base = Path(user_source.path).expanduser()
        profile_dir = base / name / version
        profile_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = profile_dir / "profile.yaml"
        data = {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "author": {"name": metadata.author},
            "extends": metadata.extends,
            "dependencies": {"profiles": metadata.dependencies},
            "maturity": {
                "level": metadata.maturity,
                "total_runs": metadata.total_runs,
                "success_rate": metadata.success_rate,
                "known_issues": metadata.known_issues,
            },
        }

        yaml_path.write_text(yaml.dump(data, allow_unicode=True, indent=2),
                            encoding="utf-8")

        # Cache'i temizle
        self._cache.pop(f"{name}@{version}", None)
        self._profiles.pop(name, None)

        return True, f"Registered {name}@{version} in {profile_dir}"

    def dependency_graph(self, name: str) -> Dict[str, Any]:
        """
        Profil dependency graph'ini çözümle.
        Diamond dependency conflict detection.
        """
        graph = {"root": name, "nodes": {}, "edges": [], "conflicts": []}

        def resolve_deps(profile_name: str, visited: set):
            if profile_name in visited:
                return
            visited.add(profile_name)

            meta = self.resolve(profile_name)
            if not meta:
                return

            graph["nodes"][profile_name] = meta.version

            for dep_name in meta.dependencies:
                dep = self.resolve(dep_name)
                if dep:
                    graph["edges"].append({"from": profile_name, "to": dep_name})

                    # Diamond conflict check
                    if dep_name in graph["nodes"]:
                        existing_ver = graph["nodes"][dep_name]
                        if existing_ver != dep.version:
                            graph["conflicts"].append({
                                "dependency": dep_name,
                                "version_1": existing_ver,
                                "version_2": dep.version,
                                "between": [profile_name, dep_name],
                            })

                    resolve_deps(dep_name, visited)

        resolve_deps(name, set())
        return graph

    def install_remote(self, name: str, version: str = None) -> Tuple[bool, str]:
        """Remote profil indir ve user'a yükle (güvenlik kontrollü)"""
        remote = self.sources.get("remote")
        if not remote:
            return False, "Remote source not configured"

        # TODO: Gerçek HTTP download
        url = f"{remote.url}{name}/{version or 'latest'}/profile.yaml"
        return False, f"Remote install from {url} — not yet implemented"

    def stats(self) -> dict:
        return {
            "sources": {k: {"priority": v.priority, "trust": v.trust}
                       for k, v in self.sources.items()},
            "profiles_cached": len(self._profiles),
            "resolution_cache": len(self._cache),
        }


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import tempfile
    import os

    reg = ProfileRegistry()

    print("📦 Profile Registry")
    print(f"   Sources: {len(reg.sources)}")
    for name, source in sorted(reg.sources.items(), key=lambda x: x[1].priority):
        print(f"   • {name}: priority={source.priority}, trust={source.trust}")

    # Register a profile (user source)
    import tempfile
    tmpdir = tempfile.mkdtemp()
    user_path = os.path.join(tmpdir, "user-profiles")
    os.makedirs(user_path)
    reg.sources["user"].path = user_path

    meta = ProfileMetadata(
        name="software-workflow",
        version="1.0.0",
        description="Software development lifecycle",
        author="Yunus Güngör",
        extends="base-validation@2.0",
        dependencies=["base-validation", "code-quality"],
        maturity="beta",
        total_runs=15,
        success_rate=0.87,
    )

    success, msg = reg.register("software-workflow", "1.0.0", meta)
    print(f"\n   ✅ Register: {msg}")

    # Resolve
    resolved = reg.resolve("software-workflow")
    assert resolved is not None
    assert resolved.version == "1.0.0"
    assert resolved.author == "Yunus Güngör"
    print(f"   ✅ Resolve: {resolved.name}@{resolved.version} by {resolved.author}")

    # List profiles
    profiles = reg.list_profiles()
    print(f"   ✅ List: {len(profiles)} profile(s)")

    # Dependency graph
    graph = reg.dependency_graph("software-workflow")
    print(f"   ✅ Dependency graph: {len(graph['nodes'])} node(s), "
          f"{len(graph['edges'])} edge(s), "
          f"{len(graph['conflicts'])} conflict(s)")

    # Stats
    print(f"   ✅ Stats: {reg.stats()}")

    print(f"\n{'='*50}")
    print(f"Profile Registry demo passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
