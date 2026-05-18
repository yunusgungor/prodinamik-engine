"""Prodinamik Engine v1.1 — Plugin Repository & Community Registry

Local plugin index and remote plugin repository concept.

Architecture:
    Local Index          Community Registry
    ├── ~/plugins/       ├── GitHub-based index
    ├── ./plugins/       ├── Plugin manifest registry
    └── installed.json   └── Download + install flow

Design:
    - Community registry is a URL index of plugin manifests
    - Plugins are downloaded as Python modules/tarballs
    - Cryptographic hash verification on install
    - Dependency resolution across repository plugins
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from .log import get_logger
from .plugin import PluginManifest, PluginType, PluginStatus


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────


DEFAULT_REPOSITORY_URL = "https://plugins.prodinamik.dev/v1"
LOCAL_INDEX_FILE = "installed.json"  # Relative to storage_dir
PLUGIN_STORAGE_DIR = "~/.hermes/plugins"
COMMUNITY_INDEX_URLS = [
    "https://raw.githubusercontent.com/yunusgungor/prodinamik-plugins/main/index.json",
]


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class RepositoryPlugin:
    """A plugin available in the community repository"""
    id: str
    name: str
    version: str
    description: str
    download_url: str
    checksum: str
    checksum_algorithm: str = "sha256"
    plugin_type: str = "other"
    author: str = ""
    license: str = "MIT"
    dependencies: List[str] = field(default_factory=list)
    engine_version: str = ">=1.1.0"
    published_at: Optional[str] = None
    homepage: str = ""


@dataclass
class InstallRecord:
    """Record of an installed plugin"""
    id: str
    version: str
    source: str  # "local", "repository", "builtin"
    installed_at: str
    checksum: str = ""
    install_path: str = ""
    enabled: bool = False


# ──────────────────────────────────────────────
# Plugin Repository
# ──────────────────────────────────────────────


class PluginRepository:
    """Plugin repository manager — local index + remote registry

    Manages the lifecycle of plugin installation from remote sources.
    Works in conjunction with PluginRegistry for enable/disable.

    Usage:
        repo = PluginRepository()
        repo.refresh_index()           # Fetch remote plugin index
        plugins = repo.search("slack") # Search available plugins
        repo.install("prodinamik.slack")
    """

    def __init__(
        self,
        storage_dir: str = PLUGIN_STORAGE_DIR,
        index_urls: Optional[List[str]] = None,
    ):
        self.storage_dir = os.path.expanduser(storage_dir)
        self.index_urls = index_urls or list(COMMUNITY_INDEX_URLS)
        self.log = get_logger()

        # Local state
        self._remote_index: Dict[str, RepositoryPlugin] = {}
        self._local_records: Dict[str, InstallRecord] = {}
        self._last_refresh: Optional[datetime] = None

        # Ensure storage directory exists
        os.makedirs(self.storage_dir, exist_ok=True)

        # Load local index
        self._load_local_index()

    # ── Local Index ────────────────────────────

    def _local_index_path(self) -> str:
        return os.path.join(self.storage_dir, LOCAL_INDEX_FILE)

    def _load_local_index(self) -> None:
        """Load installed plugins index from disk"""
        index_path = self._local_index_path()
        if not os.path.exists(index_path):
            self._local_records = {}
            return

        try:
            with open(index_path) as f:
                data = json.load(f)
            self._local_records = {
                r["id"]: InstallRecord(**r)
                for r in data.get("installed", [])
            }
        except (json.JSONDecodeError, KeyError) as e:
            self.log.warning(f"Failed to load local plugin index: {e}")
            self._local_records = {}

    def _save_local_index(self) -> None:
        """Save installed plugins index to disk"""
        index_path = self._local_index_path()
        os.makedirs(os.path.dirname(index_path), exist_ok=True)

        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "installed": [
                {
                    "id": r.id,
                    "version": r.version,
                    "source": r.source,
                    "installed_at": r.installed_at,
                    "checksum": r.checksum,
                    "install_path": r.install_path,
                    "enabled": r.enabled,
                }
                for r in self._local_records.values()
            ],
        }

        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    # ── Remote Index ───────────────────────────

    def refresh_index(self) -> int:
        """Fetch remote plugin index from all configured URLs

        Returns count of plugins discovered.
        """
        total = 0

        for url in self.index_urls:
            try:
                plugins = self._fetch_index(url)
                for plugin in plugins:
                    self._remote_index[plugin.id] = plugin
                total += len(plugins)
                self.log.info(f"Fetched {len(plugins)} plugins from {url}")
            except Exception as e:
                self.log.warning(f"Failed to fetch index from {url}: {e}")

        self._last_refresh = datetime.now()

        # Also try to load from local cache if remote failed
        if total == 0:
            self._load_cached_remote_index()

        return total

    def _fetch_index(self, url: str) -> List[RepositoryPlugin]:
        """Fetch and parse a plugin index from URL

        In production, this would use HTTP requests.
        For now, returns empty list with logging.
        """
        # Stub: In production, this would do:
        #   import httpx
        #   resp = httpx.get(url, timeout=10)
        #   resp.raise_for_status()
        #   return [RepositoryPlugin(**p) for p in resp.json()]
        self.log.debug(f"Repository fetch from {url} (stub)")
        return []

    def _load_cached_remote_index(self) -> None:
        """Load a cached copy of the remote index"""
        cache_path = os.path.join(self.storage_dir, "remote_index_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    data = json.load(f)
                for p in data.get("plugins", []):
                    self._remote_index[p["id"]] = RepositoryPlugin(**p)
                self.log.info(f"Loaded {len(data.get('plugins', []))} "
                              f"plugins from cache")
            except Exception:
                pass

    def _cache_remote_index(self) -> None:
        """Cache the current remote index to disk"""
        cache_path = os.path.join(self.storage_dir, "remote_index_cache.json")
        try:
            with open(cache_path, "w") as f:
                json.dump({
                    "version": 1,
                    "cached_at": datetime.now().isoformat(),
                    "plugins": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "version": p.version,
                            "description": p.description,
                            "download_url": p.download_url,
                            "checksum": p.checksum,
                            "plugin_type": p.plugin_type,
                            "author": p.author,
                            "license": p.license,
                            "dependencies": p.dependencies,
                            "engine_version": p.engine_version,
                            "homepage": p.homepage,
                        }
                        for p in self._remote_index.values()
                    ],
                }, f, indent=2)
        except Exception as e:
            self.log.warning(f"Failed to cache remote index: {e}")

    # ── Search ─────────────────────────────────

    def search(self, query: str) -> List[RepositoryPlugin]:
        """Search available plugins by name, description, or ID

        Searches both remote index and locally available plugins.
        """
        query = query.lower()
        results = []

        for plugin in self._remote_index.values():
            if (query in plugin.id.lower()
                    or query in plugin.name.lower()
                    or query in plugin.description.lower()):
                results.append(plugin)

        # Sort by relevance (ID match > name match > description match)
        def relevance(p: RepositoryPlugin) -> int:
            if query == p.id.lower():
                return 0
            if query in p.id.lower():
                return 1
            if query in p.name.lower():
                return 2
            return 3

        results.sort(key=relevance)
        return results

    def list_available(self) -> List[RepositoryPlugin]:
        """List all plugins available in the repository"""
        return list(self._remote_index.values())

    def list_installed(self) -> List[InstallRecord]:
        """List all locally installed plugins"""
        return list(self._local_records.values())

    def get_available(self, plugin_id: str) -> Optional[RepositoryPlugin]:
        """Get a plugin from the remote index by ID"""
        return self._remote_index.get(plugin_id)

    def get_installed(self, plugin_id: str) -> Optional[InstallRecord]:
        """Get install record for a locally installed plugin"""
        return self._local_records.get(plugin_id)

    def is_installed(self, plugin_id: str) -> bool:
        """Check if a plugin is installed locally"""
        return plugin_id in self._local_records

    # ── Install / Uninstall ────────────────────

    def install(self, plugin_id: str) -> Tuple[bool, str]:
        """Install a plugin from the repository

        Downloads, verifies checksum, and registers locally.
        Does NOT enable the plugin (use PluginRegistry.enable for that).

        Returns: (success, message)
        """
        # Check if already installed
        if plugin_id in self._local_records:
            return False, f"Plugin '{plugin_id}' is already installed"

        # Get from remote index
        remote = self._remote_index.get(plugin_id)
        if not remote:
            return False, f"Plugin '{plugin_id}' not found in repository"

        # Verify engine compatibility
        if not self._check_engine_compatibility(remote.engine_version):
            return False, (
                f"Plugin '{plugin_id}' requires engine {remote.engine_version}, "
                f"but current engine is not compatible"
            )

        # Download and install
        install_path = os.path.join(self.storage_dir, plugin_id)
        try:
            os.makedirs(install_path, exist_ok=True)

            # Download plugin (stub)
            downloaded = self._download_plugin(remote, install_path)
            if not downloaded:
                return False, f"Failed to download plugin '{plugin_id}'"

            # Verify checksum
            if remote.checksum:
                computed = self._compute_checksum(install_path)
                if computed != remote.checksum:
                    shutil.rmtree(install_path, ignore_errors=True)
                    return False, (
                        f"Checksum mismatch for '{plugin_id}': "
                        f"expected {remote.checksum}, got {computed}"
                    )

            # Record installation
            record = InstallRecord(
                id=plugin_id,
                version=remote.version,
                source="repository",
                installed_at=datetime.now().isoformat(),
                checksum=remote.checksum,
                install_path=install_path,
                enabled=False,
            )
            self._local_records[plugin_id] = record
            self._save_local_index()

            self.log.info(f"Plugin installed: {plugin_id} v{remote.version}")
            return True, f"Plugin '{plugin_id}' v{remote.version} installed"

        except Exception as e:
            # Clean up on failure
            if os.path.exists(install_path):
                shutil.rmtree(install_path, ignore_errors=True)
            return False, f"Installation failed: {e}"

    def uninstall(self, plugin_id: str) -> Tuple[bool, str]:
        """Uninstall a plugin"""
        record = self._local_records.get(plugin_id)
        if not record:
            return False, f"Plugin '{plugin_id}' is not installed"

        # Remove files
        if record.install_path and os.path.exists(record.install_path):
            shutil.rmtree(record.install_path, ignore_errors=True)

        # Remove from index
        del self._local_records[plugin_id]
        self._save_local_index()

        self.log.info(f"Plugin uninstalled: {plugin_id}")
        return True, f"Plugin '{plugin_id}' uninstalled"

    # ── Local Install from Directory ───────────

    def install_local(self, source_path: str, plugin_id: Optional[str] = None) -> Tuple[bool, str]:
        """Install a plugin from a local directory or .py file

        Copies the plugin to the managed storage directory.
        """
        source = Path(source_path)
        if not source.exists():
            return False, f"Source not found: {source_path}"

        # Determine target ID
        target_id = plugin_id or source.stem

        # Target path
        install_path = Path(self.storage_dir) / target_id
        if install_path.exists():
            return False, f"Plugin '{target_id}' already installed at {install_path}"

        try:
            if source.is_file():
                install_path.mkdir(parents=True)
                shutil.copy2(str(source), str(install_path / source.name))
            elif source.is_dir():
                shutil.copytree(str(source), str(install_path),
                                ignore=lambda d, files: [f for f in files
                                    if f in ("__pycache__", ".git") or f.endswith(".pyc")])

            # Read version from PluginManifest if possible
            version = self._detect_version(install_path) or "0.0.0"

            record = InstallRecord(
                id=target_id,
                version=version,
                source="local",
                installed_at=datetime.now().isoformat(),
                install_path=str(install_path),
                enabled=False,
            )
            self._local_records[target_id] = record
            self._save_local_index()

            self.log.info(f"Local plugin installed: {target_id} from {source_path}")
            return True, f"Plugin '{target_id}' installed from {source_path}"

        except Exception as e:
            if install_path.exists():
                shutil.rmtree(str(install_path), ignore_errors=True)
            return False, f"Local install failed: {e}"

    # ── Internal ───────────────────────────────

    def _check_engine_compatibility(self, version_spec: str) -> bool:
        """Check if the current engine version satisfies the requirement

        Simple version comparison. In production, use packaging.version.
        """
        try:
            from . import __version__ as engine_ver
        except ImportError:
            return True  # Can't check, assume compatible

        engine_parts = [int(x) for x in engine_ver.split(".")]
        spec = version_spec.strip()

        if spec.startswith(">="):
            required = spec[2:].strip()
            required_parts = [int(x) for x in required.split(".")]
            return engine_parts >= required_parts
        if spec.startswith(">"):
            required = spec[1:].strip()
            required_parts = [int(x) for x in required.split(".")]
            return engine_parts > required_parts
        if spec.startswith("=="):
            required = spec[2:].strip()
            return engine_ver == required
        if spec.startswith("~="):
            required = spec[2:].strip()
            required_parts = [int(x) for x in required.split(".")]
            return engine_parts[:len(required_parts)] == required_parts
        return True  # Default: compatible

    def _download_plugin(self, plugin: RepositoryPlugin, target_dir: str) -> bool:
        """Download a plugin from its download URL

        Stub — in production, this would use HTTP streaming.
        For development, creates a minimal plugin template.
        """
        # In production: httpx.stream, verify checksum during download
        # For now, create a stub plugin file
        init_path = os.path.join(target_dir, "__init__.py")
        plugin_content = f'''"""
{plugin.name} — Prodinamik Engine Plugin
Auto-generated from repository: {plugin.id} v{plugin.version}
"""

from engine.plugin import PluginBase, PluginManifest, PluginType


class {plugin.id.replace(".", "_").replace("-", "_")}Plugin(PluginBase):
    """Plugin: {plugin.name}"""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="{plugin.id}",
            name="{plugin.name}",
            version="{plugin.version}",
            description="{plugin.description}",
            plugin_type=PluginType.{plugin.plugin_type.upper()},
            author="{plugin.author}",
            license="{plugin.license}",
        )
'''
        with open(init_path, "w") as f:
            f.write(plugin_content)

        # Create manifest
        manifest = {
            "id": plugin.id,
            "name": plugin.name,
            "version": plugin.version,
            "type": plugin.plugin_type,
        }
        manifest_path = os.path.join(target_dir, "plugin.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return True

    def _compute_checksum(self, path: str) -> str:
        """Compute SHA256 checksum of a directory or file"""
        sha = hashlib.sha256()

        if os.path.isfile(path):
            with open(path, "rb") as f:
                sha.update(f.read())
        else:
            for root, dirs, files in os.walk(path):
                dirs.sort()
                files.sort()
                for fname in files:
                    filepath = os.path.join(root, fname)
                    if fname.endswith(".pyc") or "__pycache__" in filepath:
                        continue
                    with open(filepath, "rb") as f:
                        sha.update(f.read())

        return sha.hexdigest()

    def _detect_version(self, path: Path) -> Optional[str]:
        """Try to detect version from plugin files"""
        init_file = path / "__init__.py"
        if init_file.exists():
            content = init_file.read_text()
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith('version') or line.startswith('__version__'):
                    if "=" in line:
                        value = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return value
        return None

    # ── Repository Management ──────────────────

    def register_index(self, url: str) -> None:
        """Register an additional remote index URL"""
        if url not in self.index_urls:
            self.index_urls.append(url)
            self.log.info(f"Registered plugin index: {url}")

    def local_index_snapshot(self) -> Dict[str, Any]:
        """Snapshot of local plugin index for dashboard"""
        return {
            "installed": len(self._local_records),
            "available_remote": len(self._remote_index),
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "plugins": [
                {
                    "id": r.id,
                    "version": r.version,
                    "source": r.source,
                    "enabled": r.enabled,
                }
                for r in self._local_records.values()
            ],
        }
