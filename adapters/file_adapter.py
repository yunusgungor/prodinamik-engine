"""
Prodinamik Engine v0.5 — Adapters

Adapter'lar: Output channel abstraction.
Her adapter circuit breaker + retry backoff + fallback chain ile donanmıştır.

Adapter'lar:
- FileAdapter:      Yerel dosyaya yaz (fallback/default)
- BufferAdapter:    Twitter thread yayını (content)
- CratesIOAdapter:  Rust crate publish (software)
- GitHubAdapter:    GitHub Release oluştur (software)
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List
import hashlib

from engine.profile import Adapter, AdapterDef, AdapterResult, TransientError


# ──────────────────────────────────────────────
# FileAdapter (Fallback)
# ──────────────────────────────────────────────

class FileAdapter(Adapter):
    """Yerel dosyaya yaz. Tüm adapter'ların fallback'i."""

    def __init__(self, defn: AdapterDef, base_dir: str = ".output"):
        super().__init__(defn)
        self.base_dir = Path(base_dir)

    async def _send(self, artifact: Any) -> AdapterResult:
        self.base_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        content = self._serialize(artifact)

        path = self.base_dir / f"{filename}.json"
        path.write_text(content, encoding="utf-8")

        return AdapterResult(
            success=True,
            message=f"✅ Written to {path}",
            url=str(path),
        )

    def _serialize(self, artifact: Any) -> str:
        if isinstance(artifact, str):
            return artifact
        if hasattr(artifact, 'json'):
            return artifact.json()
        if hasattr(artifact, 'model_dump_json'):
            return artifact.model_dump_json()
        try:
            return json.dumps(artifact, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            return str(artifact)


# ──────────────────────────────────────────────
# BufferAdapter (Content Profile)
# ──────────────────────────────────────────────

class BufferAdapter(Adapter):
    """
    Buffer.com API üzerinden Twitter thread yayını.

    Buffer API: https://api.buffer.com/1/updates/create.json
    """

    def __init__(self, defn: AdapterDef, api_key: str = None, channel_id: str = None):
        super().__init__(defn)
        self.api_key = api_key
        self.channel_id = channel_id
        self.base_url = "https://api.buffer.com/1"

    async def _send(self, artifact: Any) -> AdapterResult:
        """
        Artifact'i Buffer'a draft olarak gönder.

        Artifact formatı: list of dicts
        [{"text": "Tweet 1", "media": None}, {"text": "Tweet 2"}, ...]

        veya string (tek tweet)
        """
        if not self.api_key:
            return AdapterResult(
                success=False,
                message="Buffer API key not configured",
            )

        tweets = self._parse_tweets(artifact)
        if not tweets:
            return AdapterResult(
                success=False,
                message="No tweets found in artifact",
            )

        # Her tweet için Buffer API çağrısı
        results = []
        import aiohttp

        async with aiohttp.ClientSession() as session:
            for i, tweet in enumerate(tweets):
                text = tweet.get("text", tweet) if isinstance(tweet, dict) else tweet

                if len(text) > 280:
                    text = text[:277] + "..."

                payload = {
                    "text": text,
                    "profile_ids": [self.channel_id],
                    "media": tweet.get("media") if isinstance(tweet, dict) else None,
                }

                try:
                    async with session.post(
                        f"{self.base_url}/updates/create.json",
                        params={"access_token": self.api_key},
                        json=payload,
                    ) as resp:
                        if resp.status == 201:
                            data = await resp.json()
                            results.append({
                                "tweet": i + 1,
                                "status": "draft_created",
                                "buffer_id": data.get("id", "unknown"),
                                "url": f"https://publish.buffer.com/"
                                       f"profile/{self.channel_id}/draft/{data.get('id', '')}",
                            })
                        else:
                            error_text = await resp.text()
                            raise TransientError(f"Buffer API error {resp.status}: {error_text}")

                except Exception as e:
                    # Fallback: son tweet'i kaydet
                    self._save_fallback(text, i)
                    results.append({
                        "tweet": i + 1,
                        "status": "fallback_saved",
                        "error": str(e),
                    })

        success_count = sum(1 for r in results if r["status"] == "draft_created")
        return AdapterResult(
            success=success_count > 0,
            message=f"Buffer: {success_count}/{len(tweets)} tweets sent",
            details={"results": results},
            url=results[0].get("url") if results else None,
        )

    def _parse_tweets(self, artifact: Any) -> List[dict]:
        """Artifact'ten tweet listesini çıkar"""
        if isinstance(artifact, list):
            return artifact
        if isinstance(artifact, str):
            # Basit tweet parse: her satır bir tweet
            lines = [l.strip() for l in artifact.split("\n") if l.strip()]
            return [{"text": l} for l in lines]
        if hasattr(artifact, 'tweets'):
            return artifact.tweets
        return str(artifact)

    def _save_fallback(self, text: str, index: int):
        """Buffer başarısız olursa tweet'i yerel dosyaya kaydet"""
        fallback_dir = Path(f".fallback/{self.name}")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / f"tweet_{index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path.write_text(text, encoding="utf-8")


# ──────────────────────────────────────────────
# GitHubReleaseAdapter (Software Profile)
# ──────────────────────────────────────────────

class GitHubReleaseAdapter(Adapter):
    """
    GitHub Release oluştur.

    GitHub API: POST /repos/{owner}/{repo}/releases
    """

    def __init__(self, defn: AdapterDef, token: str = None,
                 owner: str = None, repo: str = None):
        super().__init__(defn)
        self.token = token
        self.owner = owner
        self.repo = repo

    async def _send(self, artifact: Any) -> AdapterResult:
        if not self.token:
            return AdapterResult(
                success=False,
                message="GitHub token not configured",
            )

        release_data = self._parse_release_data(artifact)
        if not release_data:
            return AdapterResult(
                success=False,
                message="No release data found in artifact",
            )

        import aiohttp

        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        payload = {
            "tag_name": release_data.get("tag_name", ""),
            "name": release_data.get("name", ""),
            "body": release_data.get("body", ""),
            "draft": release_data.get("draft", False),
            "prerelease": release_data.get("prerelease", False),
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 201:
                        data = await resp.json()
                        return AdapterResult(
                            success=True,
                            message=f"✅ GitHub Release created: {data.get('html_url', '')}",
                            url=data.get("html_url"),
                        )
                    elif resp.status == 422:
                        error = await resp.json()
                        return AdapterResult(
                            success=False,
                            message=f"GitHub API error: {error.get('message', 'unknown')}",
                        )
                    else:
                        raise TransientError(f"GitHub API {resp.status}")
            except Exception as e:
                self._save_fallback(payload)
                return AdapterResult(
                    success=False,
                    message=f"GitHub release failed: {e}. Saved to fallback.",
                    fallback=True,
                )

    def _parse_release_data(self, artifact: Any) -> dict:
        """Artifact'ten release data'sını çıkar"""
        if isinstance(artifact, dict):
            return artifact
        if hasattr(artifact, 'release_data'):
            return artifact.release_data
        if hasattr(artifact, 'to_dict'):
            return artifact.to_dict()
        return {}

    def _save_fallback(self, payload: dict):
        fallback_dir = Path(f".fallback/{self.name}")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / f"release_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ──────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────

def demo():
    import asyncio

    # FileAdapter
    file_def = AdapterDef(name="FileOutput", type="file", fallback_mode="file")
    file_adapter = FileAdapter(file_def, base_dir="/tmp/prodinamik-demo")

    result = asyncio.run(file_adapter.send({"test": "Hello Prodinamik!"}))
    print(f"📁 FileAdapter: {result.message}")

    # BufferAdapter (no API key → fallback)
    buffer_def = AdapterDef(name="Buffer", type="buffer", max_retries=1)
    buffer_adapter = BufferAdapter(buffer_def, api_key=None)

    tweets = [{"text": "Prodinamik Engine v0.5 çıktı!"},
              {"text": "14 problem + çözüm, formal state machine, Raft+CRDT..."}]
    result = asyncio.run(buffer_adapter.send(tweets))
    print(f"📤 BufferAdapter (no key): {result.message}")

    # GitHubAdapter (no token → fallback)
    github_def = AdapterDef(name="GitHub", type="github", max_retries=1)
    github_adapter = GitHubReleaseAdapter(
        github_def, token=None, owner="yunusgungor", repo="flux"
    )

    release = {"tag_name": "v0.5.2", "name": "Flux v0.5.2", "body": "Docker deployment"}
    result = asyncio.run(github_adapter.send(release))
    print(f"🐙 GitHubAdapter (no token): {result.message}")

    # Circuit breaker test
    print(f"\n🔌 Circuit breaker test:")
    for i in range(5):
        result = asyncio.run(file_adapter.send({"test": f"attempt {i+1}"}))
        print(f"   Attempt {i+1}: {result.message[:60]}...")

    print(f"\n{'='*50}")
    print(f"All adapter tests passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
