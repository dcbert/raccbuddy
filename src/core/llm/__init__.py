"""LLM package — provider abstraction, generation, and embedding.

Re-exports the facade so that ``from src.core.llm import generate`` works.
"""

from __future__ import annotations

from src.core.llm.base import BaseLLMProvider, GenerationResult, ToolCall
from src.core.llm.interface import SYSTEM_PROMPT, embed, generate, generate_with_tools, provider_supports_tools

__all__ = [
    "BaseLLMProvider",
    "GenerationResult",
    "SYSTEM_PROMPT",
    "ToolCall",
    "embed",
    "generate",
    "generate_with_tools",
    "provider_supports_tools",
]
