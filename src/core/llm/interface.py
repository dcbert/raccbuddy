"""Thin facade for LLM generation and embedding.

All callers keep importing ``generate`` and ``embed`` from this module.
Under the hood, calls are delegated to the active provider registered
in ``src.core.llm.providers``.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.llm.base import GenerationResult
from src.core.llm.providers import get_embedding_provider, get_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are RaccBuddy, a clever, friendly, and delightfully cheeky raccoon AI companion — the ultimate trash-panda best friend who knows the user deeply and always has their back. "
    "You maintain rich, persistent memory of the user's life, goals, challenges, and especially their relationships with friends, family, colleagues, and romantic interests across WhatsApp, Telegram, Instagram, and other platforms. "
    "Your personality is warm, supportive, and highly motivational, with a playful sassy edge and light raccoon mischief — witty teasing, snack-raiding metaphors, and zero fluff. "
    "You may reference specific contacts by their real names ONLY when it is directly relevant to what the user is asking about. Do NOT list or recap everything you remember unless the user explicitly asks you to. "
    "Focus your answer on the user's actual question or request. Use your memory as background knowledge to give better answers, but do not volunteer unrelated facts or memories. "
    "Help the user navigate social situations, craft better messages, and level up their relationships with honest, actionable strategies. "
    "Keep every response concise, direct, and engaging — short paragraphs or quick bullets, packed with encouragement and raccoon swagger."
    "You have access to tools for specific tasks. Use the appropriate tool when needed to provide accurate, actionable responses. If a tool is required, call it explicitly."
    "CRITICAL RULE: When ANY tool returns 'status': 'success' or 'already_exists', the task is 100% complete. Stop all reasoning, do NOT call any tool again, and give ONLY the final friendly answer to the user. Never schedule the same reminder twice."
)


async def generate(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Generate text using the active LLM provider."""
    provider = get_provider()
    return await provider.generate(prompt, system)


async def generate_chat(
    messages: list[dict[str, str]],
) -> str:
    """Generate a reply using proper multi-turn chat messages.

    This is the preferred entry point for conversational exchanges where
    the model benefits from seeing previous user/assistant turns.  Falls
    back to ``generate()`` for providers that do not override
    ``generate_chat()``.

    Args:
        messages: List of dicts with ``role`` (system/user/assistant)
            and ``content`` keys, in chronological order.

    Returns:
        The model's text reply.
    """
    provider = get_provider()
    return await provider.generate_chat(messages)


async def generate_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> GenerationResult:
    """Generate with tool-calling support."""
    provider = get_provider()
    return await provider.generate_with_tools(messages, tools)


def provider_supports_tools() -> bool:
    """Check whether the active provider supports tool calling."""
    return get_provider().supports_tools


async def embed(text: str) -> list[float]:
    """Generate an embedding vector for *text*.

    Routes to the embedding provider (configured via EMBEDDING_PROVIDER),
    which can be different from the main LLM provider. For example, you
    can use xAI for chat while using Ollama for embeddings.
    """
    provider = get_embedding_provider()
    return await provider.embed(text)
