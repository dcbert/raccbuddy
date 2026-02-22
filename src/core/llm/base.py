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
