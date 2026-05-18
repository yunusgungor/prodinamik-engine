"""Prodinamik Engine — OpenAI LLM Provider Plugin

Provides access to OpenAI-compatible chat completion APIs.
Supports streaming, token counting, and model listing via the OpenAI Python package.

Environment:
    OPENAI_API_KEY  — Required. Your OpenAI API key.
    OPENAI_BASE_URL — Optional. Custom API base URL (e.g., for proxies).
"""

from __future__ import annotations

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
    import openai
    from openai import OpenAI as OpenAIAsyncClient
    HAS_OPENAI = True
except ImportError:
    openai = None  # type: ignore[assignment]
    OpenAIAsyncClient = None  # type: ignore[assignment,misc]
    HAS_OPENAI = False


class OpenAIProvider(LLMProviderPlugin):
    """LLM provider plugin for OpenAI-compatible APIs.

    Supports GPT-4 and GPT-3.5 series models with streaming and
    standard completion modes. All API errors are mapped to the
    Prodinamik exception hierarchy.
    """

    # ── Manifest ────────────────────────────────

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="prodinamik.llm.openai",
            name="OpenAI LLM Provider",
            version="1.0.0",
            description="OpenAI GPT-4 / GPT-3.5 chat completions via the official Python SDK",
            author="Prodinamik Engine",
            license="MIT",
            plugin_type=PluginType.LLM_PROVIDER,
            homepage="https://openai.com",
            repository="https://github.com/openai/openai-python",
        )

    def __init__(self, engine: Any = None):
        super().__init__(engine)
        self._client: Optional[OpenAIAsyncClient] = None
        self._config = LLMProviderConfig()

    # ── Configuration ───────────────────────────

    def _apply_config(self) -> None:
        """Apply configuration dict to internal config dataclass."""
        self._config = LLMProviderConfig(
            api_key=self._config.api_key or os.getenv("OPENAI_API_KEY", ""),
            base_url=self._config.base_url or os.getenv("OPENAI_BASE_URL", ""),
            model=self._config.model or self.default_model,
            temperature=float(self.get_config("temperature", 0.7)),
            max_tokens=int(self.get_config("max_tokens", 2048)),
            timeout=int(self.get_config("timeout", 60)),
        )

    # ── Lifecycle ───────────────────────────────

    def on_enable(self) -> None:
        """Validate API key and initialise the OpenAI client."""
        if not HAS_OPENAI:
            raise LLMProviderError(
                "OpenAI Python package is not installed. "
                "Run: pip install openai"
            )

        self._apply_config()
        api_key = self._config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise LLMProviderAuthError(
                "OPENAI_API_KEY is not set. "
                "Provide it via the OPENAI_API_KEY environment variable "
                "or pass api_key in the plugin config."
            )

        client_kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": self._config.timeout}
        if self._config.base_url:
            client_kwargs["base_url"] = self._config.base_url

        self._client = OpenAIAsyncClient(**client_kwargs)
        log.info("OpenAI provider enabled (base_url=%s)", self._config.base_url or "default")

    def on_disable(self) -> None:
        """Tear down client on disable."""
        self._client = None
        log.info("OpenAI provider disabled")

    # ── Model Helpers ───────────────────────────

    @property
    def models(self) -> List[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    @property
    def default_model(self) -> str:
        return "gpt-4o"

    # ── Core API ────────────────────────────────

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a chat completion request to OpenAI.

        Returns:
            dict with keys: content, model, usage

        Raises:
            LLMProviderAuthError: Invalid or missing API key.
            LLMProviderRateLimitError: Rate limit exceeded.
            LLMProviderTimeoutError: Request timed out.
            LLMProviderError: Other API errors.
        """
        if self._client is None:
            raise LLMProviderError("OpenAI provider is not enabled")

        try:
            response = self._client.chat.completions.create(
                model=model or self._config.model or self.default_model,
                messages=messages,
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens or self._config.max_tokens,
                stream=False,
                **kwargs,
            )
        except openai.AuthenticationError as exc:
            raise LLMProviderAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise LLMProviderRateLimitError(str(exc)) from exc
        except openai.APITimeoutError as exc:
            raise LLMProviderTimeoutError(str(exc)) from exc
        except openai.APIError as exc:
            raise LLMProviderError(str(exc)) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected OpenAI error: {exc}") from exc

        return {
            "content": response.choices[0].message.content or "",
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
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
        """Stream chat completion chunks from OpenAI.

        Yields:
            Content string deltas as they arrive.

        Returns:
            Final dict with full content, model, and usage.
        """
        if self._client is None:
            raise LLMProviderError("OpenAI provider is not enabled")

        full_content: str = ""
        final_model: str = model or self._config.model or self.default_model
        prompt_tokens: int = 0
        completion_tokens: int = 0

        try:
            stream = self._client.chat.completions.create(
                model=final_model,
                messages=messages,
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens or self._config.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full_content += delta.content
                    yield delta.content

                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0

                if chunk.model:
                    final_model = chunk.model

        except openai.AuthenticationError as exc:
            raise LLMProviderAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise LLMProviderRateLimitError(str(exc)) from exc
        except openai.APITimeoutError as exc:
            raise LLMProviderTimeoutError(str(exc)) from exc
        except openai.APIError as exc:
            raise LLMProviderError(str(exc)) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected OpenAI stream error: {exc}") from exc

        return {
            "content": full_content,
            "model": final_model,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
