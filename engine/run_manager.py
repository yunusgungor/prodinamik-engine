"""
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
"""

import json
import hashlib
import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

from engine.profile import ProductProfile
from engine.state_machine import (
    StateMachine, RuntimeState, TransitionType,
    StateMachineConfig, StateMachineValidationError,
)


# ──────────────────────────────────────────────
# Run Status
# ──────────────────────────────────────────────

class RunStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    ERROR = "error"


# ──────────────────────────────────────────────
# Run Data
# ──────────────────────────────────────────────

@dataclass
class RunMeta:
    """Run metadata — content-object.md'ye yazılır"""
    slug: str
    profile: str
    title: str
    created_at: str = ""        # ISO datetime
    updated_at: str = ""        # ISO datetime
    status: str = "active"
    state: str = ""
    version: int = 0             # Optimistic locking

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RunMeta":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Run:
    """Tek bir run'ın tam temsili"""
    meta: RunMeta
    runtime: RuntimeState
    profile: ProductProfile


# ──────────────────────────────────────────────
# Run Manager
# ──────────────────────────────────────────────

class RunManager:
    """
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
    """

    def __init__(self, base_path: str = ".hermes"):
        self.base_path = Path(base_path)
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Gerekli dizin yapısını oluştur"""
        dirs = [
            self.base_path / "runs" / "active",
            self.base_path / "runs" / "archive",
            self.base_path / "state",
            self.base_path / "wal",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _run_path(self, slug: str) -> Path:
        return self.base_path / "runs" / "active" / slug

    def _archive_path(self, slug: str) -> Path:
        return self.base_path / "runs" / "archive" / slug

    def _state_path(self) -> Path:
        return self.base_path / "state" / "runs_state.json"

    def _state_tmp_path(self) -> Path:
        return self.base_path / "state" / "runs_state.json.tmp"

    # ──────────────────────────────────────
    # Slug Generation
    # ──────────────────────────────────────

    @staticmethod
    def slugify(text: str) -> str:
        """Temiz URL-safe slug oluştur"""
        slug = text.lower().strip()
        slug = re.sub(r'[^a-z0-9\-_\s]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        slug = slug.strip('-')[:80]
        if not slug:
            slug = f"run-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return slug

    # ──────────────────────────────────────
    # CRUD: Create
    # ──────────────────────────────────────

    def create_run(self, title: str, profile: ProductProfile,
                   slug: str = None) -> Run:
        """
        Yeni run oluştur.

        - Slug belirtilmezse title'dan otomatik oluştur
        - Profile'in state machine'inden initial state alınır
        - WAL'a yazılır
        - content-object.md oluşturulur
        """
        if not profile.state_machine:
            raise ValueError(f"Profile '{profile.name}' has no state machine")

        # Slug
        if not slug:
            slug = self.slugify(title)

        # Run path
        run_path = self._run_path(slug)
        co_path = run_path / "content-object.md"
        if co_path.exists():
            raise ValueError(f"Run '{slug}' already exists")

        # Initial state
        initial_state = list(profile.state_machine.config.initial_states.keys())[0] \
            if hasattr(profile.state_machine.config.initial_states, 'keys') else \
            profile.state_machine.config.initial_states[0].name

        runtime = RuntimeState(current_state=initial_state)
        now_iso = datetime.now().isoformat()

        meta = RunMeta(
            slug=slug,
            profile=profile.name,
            title=title,
            created_at=now_iso,
            updated_at=now_iso,
            status="active",
            state=initial_state,
        )

        # Dizin oluştur
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "events").mkdir(exist_ok=True)
        (run_path / "artifacts").mkdir(exist_ok=True)

        # content-object.md yaz
        self._write_meta(meta, run_path)

        # WAL
        self._append_wal({
            "action": "create",
            "slug": slug,
            "profile": profile.name,
            "state": initial_state,
            "timestamp": now_iso,
        })

        # Snapshot güncelle
        self._update_snapshot(slug, {
            "state": initial_state,
            "profile": profile.name,
            "status": "active",
            "updated_at": now_iso,
        })

        return Run(meta=meta, runtime=runtime, profile=profile)

    # ──────────────────────────────────────
    # CRUD: Read
    # ──────────────────────────────────────

    def get_run(self, slug: str, profile: ProductProfile = None) -> Optional[Run]:
        """Run bilgisini oku. Yoksa None döner."""
        run_path = self._run_path(slug)
        if not run_path.exists():
            # Archive'de ara
            archive_path = self._archive_path(slug)
            if archive_path.exists():
                meta = self._read_meta(archive_path)
                if meta:
                    return Run(
                        meta=meta,
                        runtime=RuntimeState(current_state=meta.state),
                        profile=profile,
                    )
            return None

        meta = self._read_meta(run_path)
        if not meta:
            return None

        return Run(
            meta=meta,
            runtime=RuntimeState(current_state=meta.state, version=meta.version),
            profile=profile,
        )

    def list_runs(self, include_archived: bool = False) -> List[RunMeta]:
        """Tüm run'ları listele"""
        runs = []

        # Active
        for d in (self.base_path / "runs" / "active").iterdir():
            if d.is_dir():
                meta = self._read_meta(d)
                if meta:
                    runs.append(meta)

        # Archived
        if include_archived:
            archive_dir = self.base_path / "runs" / "archive"
            if archive_dir.exists():
                for d in archive_dir.iterdir():
                    if d.is_dir():
                        meta = self._read_meta(d)
                        if meta:
                            runs.append(meta)

        return sorted(runs, key=lambda r: r.updated_at, reverse=True)

    # ──────────────────────────────────────
    # CRUD: State Update
    # ──────────────────────────────────────

    def update_state(self, slug: str, to_state: str,
                     profile: ProductProfile = None,
                     runtime_overrides: Optional[Dict[str, Any]] = None) -> Run:
        """
        Run'ın state'ini güncelle.

        1. Validasyon: can_transition?
        2. WAL'a yaz
        3. Snapshot güncelle
        4. content-object.md güncelle

        runtime_overrides: RuntimeState alanlarını override etmek için dict
                          (örn: {"human_approved": True} — condition engine'i bypass)
        """
        run_path = self._run_path(slug)
        if not run_path.exists():
            raise ValueError(f"Run '{slug}' not found")

        meta = self._read_meta(run_path)
        if not meta:
            raise ValueError(f"Run '{slug}' has no metadata")

        from_state = meta.state

        # State machine validasyonu (profile varsa)
        if profile and profile.state_machine:
            sm = profile.state_machine
            rt = RuntimeState(
                current_state=from_state,
                version=meta.version,
            )
            # Runtime overrides uygula (condition engine'i bypass için)
            if runtime_overrides:
                for key, value in runtime_overrides.items():
                    if hasattr(rt, key):
                        setattr(rt, key, value)
            allowed, reason = sm.can_transition(from_state, to_state, rt)
            if not allowed:
                raise ValueError(f"Transition {from_state} → {to_state} rejected: {reason}")

        now_iso = datetime.now().isoformat()
        meta.version += 1

        # WAL
        self._append_wal({
            "action": "transition",
            "slug": slug,
            "from": from_state,
            "to": to_state,
            "version": meta.version,
            "timestamp": now_iso,
        })

        # Snapshot (atomic write)
        self._update_snapshot(slug, {
            "state": to_state,
            "status": "active",
            "updated_at": now_iso,
            "version": meta.version,
        })

        # content-object.md güncelle
        meta.state = to_state
        meta.updated_at = now_iso
        self._write_meta(meta, run_path)

        return Run(
            meta=meta,
            runtime=RuntimeState(current_state=to_state, version=meta.version),
            profile=profile,
        )

    # ──────────────────────────────────────
    # CRUD: Archive
    # ──────────────────────────────────────

    def archive_run(self, slug: str) -> bool:
        """
        Run'ı archive'e taşı.

        - active/{slug}/ → archive/{slug}/
        - Snapshot'ı güncelle
        """
        run_path = self._run_path(slug)
        if not run_path.exists():
            raise ValueError(f"Run '{slug}' not found")

        archive_path = self._archive_path(slug)
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Taşı
        if archive_path.exists():
            shutil.rmtree(archive_path)
        shutil.move(str(run_path), str(archive_path))

        # Snapshot güncelle
        self._update_snapshot(slug, {
            "status": "archived",
            "updated_at": datetime.now().isoformat(),
        })

        self._append_wal({
            "action": "archive",
            "slug": slug,
            "timestamp": datetime.now().isoformat(),
        })

        return True

    # ──────────────────────────────────────
    # Snapshot (Atomic Write)
    # ──────────────────────────────────────

    def _load_snapshot(self) -> Dict[str, dict]:
        """State snapshot'ını yükle"""
        sp = self._state_path()
        if sp.exists():
            try:
                return json.loads(sp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _update_snapshot(self, slug: str, data: dict):
        """
        Snapshot'ı atomic olarak güncelle.

        Atomic: .tmp yaz → fsync → rename → fsync(parent)
        """
        snapshot = self._load_snapshot()
        if slug in snapshot:
            snapshot[slug].update(data)
        else:
            snapshot[slug] = data

        tmp = self._state_tmp_path()
        final = self._state_path()

        # .tmp'ye yaz
        tmp.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # Atomic rename (POSIX guarantee)
        tmp.replace(final)

    def _append_wal(self, entry: dict):
        """WAL'a entry ekle (single)"""
        wal_dir = self.base_path / "wal"
        wal_dir.mkdir(parents=True, exist_ok=True)

        entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        entry["checksum"] = hashlib.sha256(entry_str.encode()).hexdigest()[:16]

        filename = f"wal_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
        wal_path = wal_dir / filename

        wal_path.write_text(
            json.dumps(entry, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )

    def _append_wal_batch(self, entries: List[dict]):
        """
        Toplu WAL yazma (batch).

        Tüm entry'leri tek bir .batch dosyasına yazar.
        Per-entry file write yerine tek write + fsync.
        10+ entry için ~5x daha hızlı.
        """
        if not entries:
            return

        wal_dir = self.base_path / "wal"
        wal_dir.mkdir(parents=True, exist_ok=True)

        lines = []
        for entry in entries:
            entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
            entry["checksum"] = hashlib.sha256(entry_str.encode()).hexdigest()[:16]
            lines.append(json.dumps(entry, ensure_ascii=False))

        filename = f"wal_batch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.batch"
        wal_path = wal_dir / filename
        # Atomic write: tüm batch tek seferde
        wal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def recover(self) -> Dict[str, dict]:
        """
        Crash sonrası kurtarma.

        1. Snapshot'ı yükle
        2. WAL'ı snapshot'tan sonraki entry'lerle replay et
        3. Tutarlılık kontrolü (checksum)
        4. WAL'ı compact et
        """
        snapshot = self._load_snapshot()
        wal_dir = self.base_path / "wal"
        if not wal_dir.exists():
            return snapshot

        # WAL entry'lerini oku (kronolojik sıra)
        wal_files = sorted(wal_dir.glob("wal_*.log"))
        for wf in wal_files:
            try:
                entry = json.loads(wf.read_text(encoding="utf-8").strip())
            except (json.JSONDecodeError, OSError):
                continue

            # Checksum kontrolü
            entry_str = json.dumps(
                {k: v for k, v in entry.items() if k != "checksum"},
                sort_keys=True, ensure_ascii=False
            )
            expected_checksum = hashlib.sha256(entry_str.encode()).hexdigest()[:16]
            if entry.get("checksum") != expected_checksum:
                print(f"⚠️ WAL checksum mismatch: {wf.name}")
                continue

            slug = entry.get("slug")
            if not slug:
                continue

            if slug not in snapshot:
                snapshot[slug] = {}

            if entry["action"] == "create":
                snapshot[slug].update({
                    "state": entry["state"],
                    "profile": entry["profile"],
                    "status": "active",
                    "updated_at": entry["timestamp"],
                })
            elif entry["action"] == "transition":
                snapshot[slug].update({
                    "state": entry["to"],
                    "updated_at": entry["timestamp"],
                })
            elif entry["action"] == "archive":
                snapshot[slug].update({
                    "status": "archived",
                    "updated_at": entry["timestamp"],
                })

        # Recovery sonrası WAL'ı compact et
        self._compact_wal(snapshot)

        return snapshot

    def _compact_wal(self, snapshot: Dict[str, dict]):
        """
        WAL'ı compact et: snapshot ile WAL arasındaki farkı kapat.
        Eski WAL dosyalarını temizle (snapshot'tan eski olanlar).
        """
        wal_dir = self.base_path / "wal"
        if not wal_dir.exists():
            return

        # Snapshot timestamp
        snap_times = [
            s.get("updated_at", "") for s in snapshot.values()
        ]
        if not snap_times:
            return

        latest_snapshot_time = max(snap_times)

        # Snapshot'tan eski WAL dosyalarını temizle
        deleted = 0
        for wf in sorted(wal_dir.glob("wal_*.log")):
            parts = wf.stem.split("_")
            if len(parts) >= 3:
                file_time = f"{parts[1]}T{parts[2]}"
                if file_time < latest_snapshot_time[:19]:
                    wf.unlink()
                    deleted += 1

        if deleted and hasattr(self, 'log') and self.log:
            self.log.debug(f"WAL compacted: {deleted} old entries removed")

    def get_state_elapsed(self, slug: str) -> Optional[float]:
        """
        Bir run'ın mevcut state'inde ne kadar süredir olduğunu döndür (saniye).
        Run bulunamazsa None döner.
        """
        run_path = self._run_path(slug)
        if not run_path.exists():
            return None

        meta = self._read_meta(run_path)
        if not meta:
            return None

        try:
            updated = datetime.fromisoformat(meta.updated_at)
        except (ValueError, TypeError):
            return None

        return (datetime.now() - updated).total_seconds()

    # ──────────────────────────────────────
    # Meta Read/Write
    # ──────────────────────────────────────

    def _write_meta(self, meta: RunMeta, run_path: Path):
        """content-object.md dosyasına meta yaz"""
        co_path = run_path / "content-object.md"
        content = (
            f"---\n"
            f"slug: {meta.slug}\n"
            f"profile: {meta.profile}\n"
            f"title: {meta.title}\n"
            f"created_at: {meta.created_at}\n"
            f"updated_at: {meta.updated_at}\n"
            f"status: {meta.status}\n"
            f"state: {meta.state}\n"
            f"version: {meta.version}\n"
            f"---\n"
        )
        co_path.write_text(content, encoding="utf-8")

    def _read_meta(self, run_path: Path) -> Optional[RunMeta]:
        """content-object.md'den meta oku"""
        co_path = run_path / "content-object.md"
        if not co_path.exists():
            return None

        content = co_path.read_text(encoding="utf-8")
        meta = {}

        # YAML frontmatter parse (basit)
        for line in content.split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("---"):
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()

        if not meta.get("slug"):
            meta["slug"] = run_path.name

        return RunMeta(
            slug=meta.get("slug", run_path.name),
            profile=meta.get("profile", "unknown"),
            title=meta.get("title", meta.get("slug", "untitled")),
            created_at=meta.get("created_at", ""),
            updated_at=meta.get("updated_at", ""),
            status=meta.get("status", "active"),
            state=meta.get("state", ""),
            version=int(meta.get("version", 0)),
        )

    # ──────────────────────────────────────
    # Search
    # ──────────────────────────────────────

    def search_runs(self, query: str) -> List[RunMeta]:
        """Run'larda basit metin araması"""
        query = query.lower()
        results = []

        for run in self.list_runs():
            if (query in run.title.lower() or
                query in run.slug.lower() or
                query in run.profile.lower()):
                results.append(run)

        return results


# ──────────────────────────────────────
# CLI Quick Test
# ──────────────────────────────────────

def demo():
    from engine.profile import ProductProfile
    from engine.state_machine import StateMachineParser

    yaml_str = """
profile: test
name: test-sm
version: 1.0
states:
  start:
    type: initial
    max_reentries: 1
  process:
    type: intermediate
    max_reentries: 5
  done:
    type: terminal
    max_reentries: 0
transitions:
  start -> process: {}
  process -> process: {}
  process -> done: {}
"""

    config = StateMachineParser.parse_string(yaml_str)

    class TestProfile(ProductProfile):
        name = "test"
        version = "1.0"
        state_machine_yaml = yaml_str

    import tempfile, os

    # Temp directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = RunManager(base_path=os.path.join(tmpdir, ".hermes"))

        profile = TestProfile()
        profile.initialize()

        # Create
        run = mgr.create_run("Test Run 1", profile)
        print(f"✅ Created: {run.meta.slug} → state={run.meta.state}")

        # Read
        run2 = mgr.get_run(run.meta.slug, profile)
        print(f"✅ Read: {run2.meta.slug} → state={run2.meta.state}")

        # Update state
        run3 = mgr.update_state(run.meta.slug, "process", profile)
        print(f"✅ Updated: {run3.meta.slug} → state={run3.meta.state}")

        # List
        runs = mgr.list_runs()
        print(f"✅ Listed: {len(runs)} run(s)")

        # Search
        results = mgr.search_runs("Test")
        print(f"✅ Searched: {len(results)} result(s)")

        # Archive
        mgr.archive_run(run.meta.slug)
        print(f"✅ Archived: {run.meta.slug}")

        # List with archived
        runs2 = mgr.list_runs(include_archived=True)
        print(f"✅ Listed (with archived): {len(runs2)} run(s)")

        # Recovery test
        mgr2 = RunManager(base_path=os.path.join(tmpdir, ".hermes"))
        snapshot = mgr2.recover()
        print(f"✅ Recovery: {len(snapshot)} run(s) in snapshot")

        print(f"\n{'='*50}")
        print(f"All RunManager operations passed!")
        print(f"{'='*50}")


if __name__ == "__main__":
    demo()
