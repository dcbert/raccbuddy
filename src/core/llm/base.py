"""Abstract base class for LLM providers.

Every LLM provider must inherit from BaseLLMProvider and implement
the generate() and embed() methods.  Providers are registered via
the provider registry in ``providers/__init__.py`` and selected by config.

Providers that support function/tool calling should override
``supports_tools`` and ``generate_with_tools()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Represents a single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """Container for a generation response that may include tool calls."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finished: bool = True


class BaseLLMProvider(ABC):
    """Contract that every LLM provider must fulfil."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def supports_tools(self) -> bool:
        return False

    @abstractmethod
    async def generate(self, prompt: str, system: str) -> str: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    async def generate_chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Generate a reply from a proper chat messages sequence.

        Accepts a list of dicts with ``role`` (system/user/assistant) and
        ``content`` keys.  Providers that support the chat/completions API
        should override this for native multi-turn support.

        The default implementation falls back to ``generate()`` by
        extracting the system prompt and concatenating all user messages.
        """
        system = ""
        user_parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system = content
            elif role == "user":
                user_parts.append(content)
            elif role == "assistant":
                user_parts.append(f"[Your previous reply]: {content}")
        prompt = "\n".join(user_parts) if user_parts else ""
        return await self.generate(prompt, system)

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> GenerationResult:
        system = ""
        prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content", "")
            elif msg.get("role") == "user":
                prompt = msg.get("content", "")
        text = await self.generate(prompt, system)
        return GenerationResult(text=text, finished=True)
