"""LLM provider registry and factory.

Add new providers by:
1. Create a module in src/core/llm/providers/  (see ollama.py as template).
2. Register it in PROVIDER_REGISTRY below.
3. Set LLM_PROVIDER=<name> in .env.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.core.llm.base import BaseLLMProvider
from src.core.llm.providers.ollama import OllamaProvider
from src.core.llm.providers.xai import XAIProvider

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "ollama": OllamaProvider,
    "xai": XAIProvider,
}

_active_provider: Optional[BaseLLMProvider] = None
_active_embedding_provider: Optional[BaseLLMProvider] = None


def get_provider() -> BaseLLMProvider:
    """Return the active LLM provider (lazily initialised)."""
    global _active_provider

    if _active_provider is not None:
        return _active_provider

    from src.core.config import settings

    name = settings.llm_provider.lower()
    cls = PROVIDER_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(PROVIDER_REGISTRY))
        raise ValueError(
            f"Unknown LLM provider '{name}'. Available: {available}"
        )

    _active_provider = cls()
    logger.info("LLM provider initialized: %s", _active_provider.name)
    return _active_provider


def get_embedding_provider() -> BaseLLMProvider:
    """Return the active embedding provider (lazily initialised).

    Can be different from the main LLM provider, e.g., use Ollama for
    embeddings while using xAI for chat completions.
    """
    global _active_embedding_provider

    if _active_embedding_provider is not None:
        return _active_embedding_provider

    from src.core.config import settings

    name = settings.embedding_provider.lower()
    cls = PROVIDER_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(PROVIDER_REGISTRY))
        raise ValueError(
            f"Unknown embedding provider '{name}'. Available: {available}"
        )

    _active_embedding_provider = cls()
    logger.info("Embedding provider initialized: %s", _active_embedding_provider.name)
    return _active_embedding_provider


def reset_provider() -> None:
    """Clear the cached provider instances."""
    global _active_provider, _active_embedding_provider
    _active_provider = None
    _active_embedding_provider = None


def register_provider(name: str, cls: type[BaseLLMProvider]) -> None:
    """Register a custom LLM provider class."""
    if not issubclass(cls, BaseLLMProvider):
        raise TypeError(f"{cls} must inherit from BaseLLMProvider")
    PROVIDER_REGISTRY[name] = cls
    logger.info("Registered LLM provider: %s", name)


__all__ = [
    "BaseLLMProvider",
    "PROVIDER_REGISTRY",
    "get_provider",
    "get_embedding_provider",
    "register_provider",
    "reset_provider",
]
