"""Ollama LLM provider — local inference via Ollama HTTP API.

Uses native Ollama HTTP API for generation and AsyncOpenAI client
for embeddings (Ollama is OpenAI-compatible at /v1 endpoint).
"""

from __future__ import annotations

import logging

import httpx
from openai import AsyncOpenAI

from src.core.config import settings
from src.core.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Local LLM provider backed by the Ollama HTTP API."""

    @property
    def name(self) -> str:
        return "ollama"

    async def generate(self, prompt: str, system: str) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings using Ollama's OpenAI-compatible endpoint.

        Uses AsyncOpenAI client pointing to Ollama's /v1 endpoint.
        Ollama provides OpenAI-compatible API at /v1 (separate from /api).
        """
        # Create OpenAI client pointing to Ollama's OpenAI-compatible endpoint
        client = AsyncOpenAI(
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",  # Ollama doesn't require auth, but client needs a value
        )

        try:
            response = await client.embeddings.create(
                model=settings.ollama_embed_model,
                input=text,
            )
            if response.data and len(response.data) > 0:
                return response.data[0].embedding
            return []
        except Exception as exc:
            logger.error("Ollama embedding failed: %s", exc)
            raise
