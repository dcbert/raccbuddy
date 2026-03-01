"""Ollama LLM provider — local inference via Ollama HTTP API.

Uses native Ollama HTTP API for generation and AsyncOpenAI client
for embeddings (Ollama is OpenAI-compatible at /v1 endpoint).

Key behaviour:
- ``num_ctx`` is forwarded from ``settings.max_context_tokens`` so
  Ollama's KV-cache matches the configured context window (default 30 000).
- The ``AsyncOpenAI`` client is cached per-instance to reuse connections.
- Input/output token counts are logged on every generation call.
- ``generate_chat()`` uses the ``/api/chat`` endpoint for proper
  multi-turn conversation support.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from openai import AsyncOpenAI

from src.core.config import settings
from src.core.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Local LLM provider backed by the Ollama HTTP API."""

    def __init__(self) -> None:
        # Cached OpenAI-compat client for embeddings (avoids recreating per call)
        self._embed_client: Optional[AsyncOpenAI] = None

    @property
    def name(self) -> str:
        return "ollama"

    def _get_embed_client(self) -> AsyncOpenAI:
        """Return (or lazily create) the cached embedding client."""
        if self._embed_client is None:
            self._embed_client = AsyncOpenAI(
                base_url=f"{settings.ollama_base_url}/v1",
                api_key="ollama",  # Ollama doesn't require auth
            )
        return self._embed_client

    async def generate(self, prompt: str, system: str) -> str:
        """Generate text via the native Ollama /api/generate endpoint.

        Passes ``num_ctx`` so Ollama allocates the correct KV-cache size.
        Logs input/output token counts for observability.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {
                        "num_ctx": settings.max_context_tokens,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        # Log token usage for observability (CLAUDE.md requirement)
        prompt_tokens = data.get("prompt_eval_count", "?")
        output_tokens = data.get("eval_count", "?")
        logger.info(
            "Ollama generate | model=%s | prompt_tokens=%s | output_tokens=%s | num_ctx=%d",
            settings.ollama_model,
            prompt_tokens,
            output_tokens,
            settings.max_context_tokens,
        )

        return data.get("response", "")

    async def generate_chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Generate via Ollama's /api/chat endpoint with multi-turn messages.

        Uses the native chat API so Ollama sees proper alternating
        user/assistant turns, giving it real conversation coherence.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_ctx": settings.max_context_tokens,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        # Log token usage for observability (CLAUDE.md requirement)
        prompt_tokens = data.get("prompt_eval_count", "?")
        output_tokens = data.get("eval_count", "?")
        logger.info(
            "Ollama generate_chat | model=%s | prompt_tokens=%s | output_tokens=%s | num_ctx=%d",
            settings.ollama_model,
            prompt_tokens,
            output_tokens,
            settings.max_context_tokens,
        )

        msg = data.get("message", {})
        return msg.get("content", "")

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings using Ollama's OpenAI-compatible /v1 endpoint.

        The ``AsyncOpenAI`` client is cached per-instance for connection reuse.
        """
        client = self._get_embed_client()
        try:
            response = await client.embeddings.create(
                model=settings.ollama_embed_model,
                input=text,
            )
            if response.data:
                return response.data[0].embedding
            return []
        except Exception as exc:
            logger.error("Ollama embedding failed: %s", exc)
            raise
