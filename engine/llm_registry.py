"""Prodinamik Engine v1.3 — LLM Provider Registry

Central registry for discovering, selecting, and routing
LLM provider plugins. Supports:
- Default provider with fallback chain
- Per-request provider selection
- Provider health checks
- Token usage tracking across providers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type

from .llm_base import (
    LLMProviderPlugin,
    LLMProviderError,
    LLMProviderAuthError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from .log import get_logger


@dataclass
class LLMUsageStats:
    """Token usage statistics per provider"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    last_call: Optional[datetime] = None
    last_error: Optional[str] = None


class LLMProviderRegistry:
    """Registry of LLM provider plugins.

    Usage:
        registry = LLMProviderRegistry()
        registry.register(my_openai_provider)
        registry.register(my_ollama_provider, default=True)

        result = registry.complete(messages)  # uses default
        result = registry.complete(messages, provider="ollama")
    """

    def __init__(self):
        self._providers: Dict[str, LLMProviderPlugin] = {}
        self._default: Optional[str] = None
        self._usage: Dict[str, LLMUsageStats] = {}
        self._log = get_logger()

    # ── Registration ──

    def register(self, provider: LLMProviderPlugin, default: bool = False) -> None:
        """Register an LLM provider plugin.

        Args:
            provider: LLMProviderPlugin instance
            default: Set as default provider
        """
        pid = provider.manifest.id
        self._providers[pid] = provider
        self._usage[pid] = LLMUsageStats()

        if default or self._default is None:
            self._default = pid

        self._log.info("LLM provider registered: %s (default=%s)", pid, default)

    def unregister(self, provider_id: str) -> None:
        """Remove a provider from registry"""
        self._providers.pop(provider_id, None)
        self._usage.pop(provider_id, None)
        if self._default == provider_id:
            # Pick next available
            self._default = next(iter(self._providers)) if self._providers else None

    # ── Resolution ──

    def get_provider(self, provider_id: Optional[str] = None) -> LLMProviderPlugin:
        """Get a provider by ID, or return default.

        Raises:
            LLMProviderError: No providers registered
            KeyError: Provider ID not found
        """
        pid = provider_id or self._default
        if not pid:
            raise LLMProviderError("No LLM providers registered")
        if pid not in self._providers:
            raise KeyError(f"LLM provider '{pid}' not found. Registered: {list(self._providers)}")
        return self._providers[pid]

    @property
    def default(self) -> Optional[str]:
        """Default provider ID"""
        return self._default

    @default.setter
    def default(self, provider_id: str) -> None:
        if provider_id not in self._providers:
            raise KeyError(f"Cannot set default: '{provider_id}' not registered")
        self._default = provider_id

    # ── Completion ──

    def complete(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        fallback: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send completion to (default or specified) provider.

        Args:
            messages: OpenAI-format message list
            provider: Specific provider ID (uses default if None)
            fallback: Try next available provider on failure
            **kwargs: Passed to provider.complete()

        Returns:
            dict with {"content": str, "model": str, "usage": {...}}

        Raises:
            LLMProviderError: All providers failed
        """
        provider_ids = [provider] if provider else list(self._providers.keys())

        errors = []
        for pid in provider_ids:
            if pid not in self._providers:
                continue
            try:
                result = self._providers[pid].complete(messages, **kwargs)
                self._track_success(pid, result)
                return result
            except (LLMProviderAuthError, LLMProviderRateLimitError,
                    LLMProviderTimeoutError, LLMProviderError) as e:
                self._track_failure(pid, str(e))
                errors.append(f"{pid}: {e}")
                if not fallback:
                    raise
                continue
            except Exception as e:
                self._track_failure(pid, str(e))
                errors.append(f"{pid}: {e}")
                if not fallback:
                    raise
                continue

        raise LLMProviderError(
            f"All LLM providers failed: {'; '.join(errors)}"
        )

    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        **kwargs,
    ):
        """Stream completion from provider.

        Yields:
            Content string chunks.

        Raises:
            LLMProviderError: Provider doesn't support streaming or failed
        """
        prov = self.get_provider(provider)
        return prov.complete_stream(messages, **kwargs)

    # ── Health & Stats ──

    def health(self) -> Dict[str, Any]:
        """Health status of all registered providers"""
        result = {}
        for pid, provider in self._providers.items():
            try:
                # Quick test: try listing models
                models = provider.models[:3] if provider.models else []
                result[pid] = {
                    "status": "ok",
                    "models": models,
                    "default_model": provider.default_model,
                }
            except Exception as e:
                result[pid] = {"status": "error", "error": str(e)}
        return result

    def usage_stats(self, provider_id: Optional[str] = None) -> Dict[str, Any]:
        """Usage statistics for provider(s)"""
        if provider_id:
            stats = self._usage.get(provider_id)
            if not stats:
                return {}
            return {provider_id: {
                "total_calls": stats.total_calls,
                "failed_calls": stats.failed_calls,
                "total_prompt_tokens": stats.total_prompt_tokens,
                "total_completion_tokens": stats.total_completion_tokens,
                "last_call": stats.last_call.isoformat() if stats.last_call else None,
                "last_error": stats.last_error,
            }}
        return {
            pid: {
                "total_calls": s.total_calls,
                "failed_calls": s.failed_calls,
                "total_prompt_tokens": s.total_prompt_tokens,
                "total_completion_tokens": s.total_completion_tokens,
                "last_call": s.last_call.isoformat() if s.last_call else None,
                "last_error": s.last_error,
            }
            for pid, s in self._usage.items()
        }

    # ── Internal ──

    def _track_success(self, pid: str, result: Dict[str, Any]) -> None:
        usage = result.get("usage", {})
        stats = self._usage.setdefault(pid, LLMUsageStats())
        stats.total_calls += 1
        stats.total_prompt_tokens += usage.get("prompt_tokens", 0)
        stats.total_completion_tokens += usage.get("completion_tokens", 0)
        stats.last_call = datetime.now()

    def _track_failure(self, pid: str, error: str) -> None:
        stats = self._usage.setdefault(pid, LLMUsageStats())
        stats.failed_calls += 1
        stats.last_error = error
        stats.last_call = datetime.now()

    def list_providers(self) -> List[Dict[str, Any]]:
        """List all registered providers"""
        return [
            {
                "id": pid,
                "name": p.manifest.name,
                "version": p.manifest.version,
                "default": pid == self._default,
                "models": p.models[:5],
                "default_model": p.default_model,
            }
            for pid, p in self._providers.items()
        ]

    @property
    def has_provider(self) -> bool:
        """Whether any LLM provider is registered"""
        return len(self._providers) > 0

    # ── Singleton ──

    _instance: Optional["LLMProviderRegistry"] = None

    @classmethod
    def get_instance(cls) -> "LLMProviderRegistry":
        """Get or create the global LLM provider registry singleton"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)"""
        cls._instance = None
