"""Prodinamik Engine — Anthropic LLM Provider Plugin

Provides access to Anthropic Claude models via the official Python SDK.
Responses are converted to an OpenAI-compatible format for engine consistency.

Environment:
    ANTHROPIC_API_KEY — Required. Your Anthropic API key.
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
    import anthropic
    from anthropic import Anthropic as AnthropicClient
    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    AnthropicClient = None  # type: ignore[assignment,misc]
    HAS_ANTHROPIC = False


class AnthropicProvider(LLMProviderPlugin):
    """LLM provider plugin for Anthropic Claude models.

    Supports Claude Sonnet 4, 3.5 Sonnet, and 3 Haiku with message-level
    completions. All API errors are mapped to the Prodinamik exception
    hierarchy.
    """

    # ── Manifest ────────────────────────────────

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="prodinamik.llm.anthropic",
            name="Anthropic LLM Provider",
            version="1.0.0",
            description="Anthropic Claude chat completions (Sonnet 4, Sonnet 3.5, Haiku 3)",
            author="Prodinamik Engine",
            license="MIT",
            plugin_type=PluginType.LLM_PROVIDER,
            homepage="https://anthropic.com",
            repository="https://github.com/anthropics/anthropic-sdk-python",
        )

    def __init__(self, engine: Any = None):
        super().__init__(engine)
        self._client: Optional[AnthropicClient] = None
        self._config = LLMProviderConfig()

    # ── Configuration ───────────────────────────

    def _apply_config(self) -> None:
        self._config = LLMProviderConfig(
            api_key=self._config.api_key or os.getenv("ANTHROPIC_API_KEY", ""),
            model=self._config.model or self.default_model,
            temperature=float(self.get_config("temperature", 0.7)),
            max_tokens=int(self.get_config("max_tokens", 2048)),
            timeout=int(self.get_config("timeout", 60)),
        )

    # ── Lifecycle ───────────────────────────────

    def on_enable(self) -> None:
        """Validate API key and initialise the Anthropic client."""
        if not HAS_ANTHROPIC:
            raise LLMProviderError(
                "Anthropic Python package is not installed. "
                "Run: pip install anthropic"
            )

        self._apply_config()
        api_key = self._config.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise LLMProviderAuthError(
                "ANTHROPIC_API_KEY is not set. "
                "Provide it via the ANTHROPIC_API_KEY environment variable "
                "or pass api_key in the plugin config."
            )

        self._client = AnthropicClient(
            api_key=api_key,
            timeout=self._config.timeout,
        )
        log.info("Anthropic provider enabled")

    def on_disable(self) -> None:
        """Tear down client on disable."""
        self._client = None
        log.info("Anthropic provider disabled")

    # ── Model Helpers ───────────────────────────

    @property
    def models(self) -> List[str]:
        return ["claude-sonnet-4", "claude-3.5-sonnet", "claude-3-haiku"]

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4"

    # ── Internal Helpers ────────────────────────

    @staticmethod
    def _convert_to_openai_messages(
        messages: List[Dict[str, str]],
    ) -> tuple[str, List[Dict[str, str]]]:
        """Split system prompt from messages for Anthropic's API.

        Anthropic separates the system prompt from the conversation
        messages, whereas OpenAI includes it as a message with role
        ``system``. This method extracts the system message if present.
        """
        system: str = ""
        converted: List[Dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system += (system and "\n\n" or "") + content
            else:
                converted.append({"role": role, "content": content})
        if not converted:
            converted.append({"role": "user", "content": "..."})
        return system, converted

    # ── Core API ────────────────────────────────

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a message completion request to Anthropic.

        Returns:
            dict with keys: content, model, usage
            (OpenAI-compatible format)

        Raises:
            LLMProviderAuthError: Invalid or missing API key.
            LLMProviderRateLimitError: Rate limit exceeded.
            LLMProviderTimeoutError: Request timed out.
            LLMProviderError: Other API errors.
        """
        if self._client is None:
            raise LLMProviderError("Anthropic provider is not enabled")

        resolved_model = model or self._config.model or self.default_model
        system, converted_messages = self._convert_to_openai_messages(messages)

        kwargs_body: Dict[str, Any] = dict(kwargs)
        if "system" in kwargs_body:
            system = system or kwargs_body.pop("system")

        try:
            response = self._client.messages.create(
                model=resolved_model,
                system=system or None,
                messages=converted_messages,
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens or self._config.max_tokens,
                **kwargs_body,
            )
        except anthropic.AuthenticationError as exc:
            raise LLMProviderAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LLMProviderRateLimitError(str(exc)) from exc
        except anthropic.APITimeoutError as exc:
            raise LLMProviderTimeoutError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 429:
                raise LLMProviderRateLimitError(str(exc)) from exc
            raise LLMProviderError(str(exc)) from exc
        except anthropic.APIError as exc:
            raise LLMProviderError(str(exc)) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected Anthropic error: {exc}") from exc

        # Convert Anthropic response to OpenAI-compatible format
        content_parts: List[str] = []
        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)

        return {
            "content": "".join(content_parts),
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (
                    (response.usage.input_tokens if response.usage else 0)
                    + (response.usage.output_tokens if response.usage else 0)
                ),
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
        """Stream message completion chunks from Anthropic.

        Anthropic streaming emits ``ContentBlockDeltaEvent`` objects
        with ``delta.text`` for each content chunk.

        Yields:
            Content string deltas as they arrive.

        Returns:
            Final dict with full content, model, and usage.
        """
        if self._client is None:
            raise LLMProviderError("Anthropic provider is not enabled")

        resolved_model = model or self._config.model or self.default_model
        system, converted_messages = self._convert_to_openai_messages(messages)

        full_content: str = ""
        final_model: str = resolved_model
        input_tokens: int = 0
        output_tokens: int = 0

        try:
            with self._client.messages.stream(
                model=resolved_model,
                system=system or None,
                messages=converted_messages,
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens or self._config.max_tokens,
                **kwargs,
            ) as stream:
                for text_delta in stream.text_deltas:
                    full_content += text_delta
                    yield text_delta

                final_response = stream.get_final_message()
                final_model = final_response.model
                if final_response.usage:
                    input_tokens = final_response.usage.input_tokens
                    output_tokens = final_response.usage.output_tokens

        except anthropic.AuthenticationError as exc:
            raise LLMProviderAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LLMProviderRateLimitError(str(exc)) from exc
        except anthropic.APITimeoutError as exc:
            raise LLMProviderTimeoutError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 429:
                raise LLMProviderRateLimitError(str(exc)) from exc
            raise LLMProviderError(str(exc)) from exc
        except anthropic.APIError as exc:
            raise LLMProviderError(str(exc)) from exc
        except Exception as exc:
            raise LLMProviderError(f"Unexpected Anthropic stream error: {exc}") from exc

        return {
            "content": full_content,
            "model": final_model,
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }
