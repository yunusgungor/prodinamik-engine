"""Prodinamik Engine v1.3 — LLM Provider Plugin Base

Abstract base class for LLM/AI provider plugins.
Every LLM provider (OpenAI, Anthropic, Ollama, etc.) implements this ABC
and registers as PluginType.LLM_PROVIDER.

Usage:
    class MyProvider(LLMProviderPlugin):
        @property
        def manifest(self):
            return PluginManifest(id="llm.myprovider", ...)

        def complete(self, messages, **kwargs):
            # Call your API here
            return {"content": "...", "model": "..."}
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from .plugin import PluginBase, PluginManifest, PluginType


@dataclass
class LLMProviderConfig:
    """Configuration for an LLM provider"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 60
    extra: Dict[str, Any] = field(default_factory=dict)


class LLMProviderPlugin(PluginBase):
    """Base class for LLM provider plugins.

    Subclasses must implement:
    - manifest (property)
    - complete()
    - models (property)
    - default_model (property)

    Optionally implement:
    - complete_stream()  (for streaming responses)
    - count_tokens()     (for token accounting)
    """

    plugin_type = PluginType.LLM_PROVIDER
    _abstract = True  # Mark as abstract for plugin discovery

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a completion request to the LLM.

        Args:
            messages: OpenAI-format message list
                [{"role": "system|user|assistant", "content": "..."}]
            temperature: Override default temperature
            max_tokens: Override default max tokens
            model: Override default model name

        Returns:
            dict with at minimum:
                {"content": str, "model": str, "usage": {...}}

        Raises:
            LLMProviderError: On API failure, rate limit, auth error
        """
        ...

    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> Generator[str, None, Dict[str, Any]]:
        """Stream completion chunks. Optional override.

        Yields:
            Content string chunks as they arrive.

        Returns:
            Final dict with {"content": str, "model": str, "usage": {...}}
        """
        raise NotImplementedError("Streaming not supported by this provider")

    @property
    @abstractmethod
    def models(self) -> List[str]:
        """List of available model names"""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model name for this provider"""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate token count. Optional override.

        Default: character-based heuristic (~4 chars/token)
        """
        return len(text) // 4

    # ── Lifecycle hooks (optional) ──

    def on_enable(self) -> None:
        """Called when provider is enabled. Validate API key here."""
        pass

    def on_disable(self) -> None:
        """Called when provider is disabled. Clean up connections."""
        pass


class LLMProviderError(Exception):
    """Base exception for LLM provider errors"""
    pass


class LLMProviderAuthError(LLMProviderError):
    """Authentication/API key error"""
    pass


class LLMProviderRateLimitError(LLMProviderError):
    """Rate limit exceeded"""
    pass


class LLMProviderTimeoutError(LLMProviderError):
    """Request timeout"""
    pass
