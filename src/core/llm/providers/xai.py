"""xAI (Grok) LLM provider — uses the OpenAI-compatible xAI API.

Requires XAI_API_KEY in the environment.  Uses the xAI embedding
endpoint for vector embeddings.

Supports function/tool calling via the OpenAI-compatible API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.core.config import settings
from src.core.llm.base import BaseLLMProvider, GenerationResult, ToolCall

logger = logging.getLogger(__name__)

XAI_API_BASE = "https://api.x.ai/v1"

MAX_TOOL_ROUNDS = 10


class XAIProvider(BaseLLMProvider):
    """Cloud LLM provider using the xAI (Grok) API."""

    @property
    def name(self) -> str:
        return "xai"

    @property
    def supports_tools(self) -> bool:
        return True

    def _headers(self) -> dict[str, str]:
        if not settings.xai_api_key:
            raise RuntimeError("XAI_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {settings.xai_api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, system: str) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{XAI_API_BASE}/chat/completions",
                headers=self._headers(),
                json={
                    "model": settings.xai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                },
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": settings.xai_model,
            "messages": messages,
            "temperature": 0.7,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{XAI_API_BASE}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices", [])
        if not choices:
            return GenerationResult(text="", finished=True)

        message = choices[0].get("message", {})
        finish_reason = choices[0].get("finish_reason", "stop")

        raw_tool_calls = message.get("tool_calls", [])
        if raw_tool_calls and finish_reason in ("tool_calls", "stop"):
            tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=fn.get("name", ""),
                        arguments=args,
                    )
                )
            return GenerationResult(
                text=message.get("content", "") or "",
                tool_calls=tool_calls,
                finished=False,
            )

        return GenerationResult(
            text=message.get("content", "") or "",
            finished=True,
        )

    async def embed(self, text: str) -> list[float]:
        """Generate embedding via xAI's OpenAI-compatible endpoint.

        Note: By default, RaccBuddy uses Ollama for embeddings (via
        EMBEDDING_PROVIDER=ollama) even when using xAI for chat. This
        method is available if you want to use xAI for embeddings too.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{XAI_API_BASE}/embeddings",
                headers=self._headers(),
                json={
                    "model": settings.xai_embed_model,
                    "input": text,
                    "dimensions": settings.xai_embed_dimensions,
                },
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("data", [])
            if embeddings:
                return embeddings[0].get("embedding", [])
            return []
