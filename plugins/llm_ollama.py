"""Prodinamik Engine — Ollama LLM Provider Plugin

Provides access to locally-hosted Ollama chat completion APIs over HTTP.
Uses the ``requests`` library — no Ollama-specific Python package required.

Environment:
    OLLAMA_BASE_URL — Optional. Base URL for the Ollama server.
                      Default: http://localhost:11434
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Generator, List, Optional

from engine.llm_base import (
    LLMProviderError,
    LLMProviderAuthError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    LLMProviderPlugin,
    LLMProviderConfig,
)
from engine.plugin import PluginManifest, PluginType

log = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore[assignment]
    HAS_REQUESTS = False


class OllamaProvider(LLMProviderPlugin):
    """LLM provider plugin for Ollama (local LLM server via REST API).

    Communicates with a local Ollama instance via HTTP. No API key
    is required since the server is typically run on localhost.
    """

    # ── Manifest ────────────────────────────────

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="prodinamik.llm.ollama",
            name="Ollama LLM Provider",
            version="1.0.0",
            description="Local LLM inference via Ollama (llama3, mistral, codellama, etc.)",
            author="Prodinamik Engine",
            license="MIT",
            plugin_type=PluginType.LLM_PROVIDER,
            homepage="https://ollama.ai",
            repository="https://github.com/ollama/ollama",
        )

    def __init__(self, engine: Any = None):
        super().__init__(engine)
        self._base_url: str = ""
        self._session: Optional[requests.Session] = None
        self._config = LLMProviderConfig()

    # ── Configuration ───────────────────────────

    def _apply_config(self) -> None:
        self._base_url = (
            self._config.base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self._config = LLMProviderConfig(
            base_url=self._base_url,
            model=self._config.model or self.default_model,
            temperature=float(self.get_config("temperature", 0.7)),
            max_tokens=int(self.get_config("max_tokens", 2048)),
            timeout=int(self.get_config("timeout", 120)),
        )

    # ── Lifecycle ───────────────────────────────

    def on_enable(self) -> None:
        """Initialise HTTP session and verify Ollama is reachable."""
        if not HAS_REQUESTS:
            raise LLMProviderError(
                "The `requests` library is required for the Ollama provider. "
                "Run: pip install requests"
            )

        self._apply_config()
        self._session = requests.Session()
        self._session.timeout = self._config.timeout

        # Quick connectivity check
        try:
            resp = self._session.get(f"{self._base_url}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            log.warning(
                "Ollama server not reachable at %s — will retry on first use: %s",
                self._base_url,
                exc,
            )
        except requests.RequestException as exc:
            log.warning("Ollama health check failed: %s", exc)

        log.info("Ollama provider enabled (base_url=%s)", self._base_url)

    def on_disable(self) -> None:
        """Close HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
        log.info("Ollama provider disabled")

    # ── Model Helpers ───────────────────────────

    @property
    def models(self) -> List[str]:
        """Fetch available models from Ollama, or return defaults on failure."""
        if not self._session:
            return ["llama3", "mistral", "codellama"]

        try:
            resp = self._session.get(
                f"{self._base_url}/api/tags",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])] or [
                "llama3",
                "mistral",
                "codellama",
            ]
        except Exception as exc:
            log.debug("Could not fetch Ollama model list: %s", exc)
            return ["llama3", "mistral", "codellama"]

    @property
    def default_model(self) -> str:
        return "llama3"

    # ── Core API ────────────────────────────────

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a chat completion request to Ollama.

        Returns:
            dict with keys: content, model, usage

        Raises:
            LLMProviderError: Connection or API failure.
            LLMProviderTimeoutError: Request timed out.
        """
        if self._session is None:
            raise LLMProviderError("Ollama provider is not enabled")

        payload: Dict[str, Any] = {
            "model": model or self._config.model or self.default_model,
            "messages": messages,
            "options": {
                "temperature": temperature if temperature is not None else self._config.temperature,
                "num_predict": max_tokens or self._config.max_tokens,
            },
            "stream": False,
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._config.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.ConnectionError as exc:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self._base_url}: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise LLMProviderTimeoutError(
                f"Ollama request timed out after {self._config.timeout}s: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise LLMProviderError(f"Ollama API error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"Ollama returned invalid JSON: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected Ollama error: {exc}") from exc

        return {
            "content": data.get("message", {}).get("content", ""),
            "model": data.get("model", model or self._config.model or self.default_model),
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0)
                + data.get("eval_count", 0),
            },
        }

    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Generator[str, None, Dict[str, Any]]:
        """Stream chat completion chunks from Ollama.

        Ollama returns newline-delimited JSON objects when ``stream`` is True.
        Each object contains a ``message`` dict with ``content``.

        Yields:
            Content string deltas as they arrive.

        Returns:
            Final dict with full content, model, and usage.
        """
        if self._session is None:
            raise LLMProviderError("Ollama provider is not enabled")

        payload: Dict[str, Any] = {
            "model": model or self._config.model or self.default_model,
            "messages": messages,
            "options": {
                "temperature": temperature if temperature is not None else self._config.temperature,
                "num_predict": max_tokens or self._config.max_tokens,
            },
            "stream": True,
        }

        full_content: str = ""
        final_model: str = model or self._config.model or self.default_model
        prompt_tokens: int = 0
        completion_tokens: int = 0

        try:
            with self._session.post(
                f"{self._base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self._config.timeout,
            ) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "message" in chunk:
                        delta = chunk["message"].get("content", "")
                        if delta:
                            full_content += delta
                            yield delta

                    if chunk.get("done"):
                        final_model = chunk.get("model", final_model)
                        prompt_tokens = chunk.get("prompt_eval_count", 0)
                        completion_tokens = chunk.get("eval_count", 0)
                        break

        except requests.ConnectionError as exc:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self._base_url}: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise LLMProviderTimeoutError(
                f"Ollama stream timed out after {self._config.timeout}s: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise LLMProviderError(f"Ollama stream error: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected Ollama stream error: {exc}") from exc

        return {
            "content": full_content,
            "model": final_model,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
