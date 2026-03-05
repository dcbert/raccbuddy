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
- ``generate_with_tools()`` supports Ollama's native tool/function calling.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI

from src.core.config import settings
from src.core.llm.base import BaseLLMProvider, GenerationResult, ToolCall

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Local LLM provider backed by the Ollama HTTP API."""

    def __init__(self) -> None:
        # Cached OpenAI-compat client for embeddings (avoids recreating per call)
        self._embed_client: Optional[AsyncOpenAI] = None

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def supports_tools(self) -> bool:
        return True

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
                        "num_batch": 64,
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

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> GenerationResult:
        """Tool-aware generation via Ollama's /api/chat endpoint.

        Converts OpenAI-style messages (with ``tool_call_id``) to
        Ollama's format and parses tool calls from the response.
        """
        ollama_messages = self._convert_messages_for_ollama(messages)

        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_ctx": settings.max_context_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        # Log token usage
        prompt_tokens = data.get("prompt_eval_count", "?")
        output_tokens = data.get("eval_count", "?")
        logger.info(
            "Ollama generate_with_tools | model=%s | prompt_tokens=%s | "
            "output_tokens=%s | num_ctx=%d",
            settings.ollama_model,
            prompt_tokens,
            output_tokens,
            settings.max_context_tokens,
        )

        msg = data.get("message", {})
        text = msg.get("content", "")
        tool_calls: list[ToolCall] = []

        raw_tool_calls = msg.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            logger.warning(
                "Ollama response has invalid 'tool_calls' format: %s", raw_tool_calls
            )
            raw_tool_calls = []
        if raw_tool_calls:
            logger.info("Ollama response includes %d tool calls", len(raw_tool_calls))
        if len(raw_tool_calls) == 0:
            logger.info("Ollama response includes no tool calls")
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            # Ollama returns arguments as a dict already
            raw_args = fn.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Failed to parse tool. '%s' arguments as JSON: %s",
                        fn_name,
                        raw_args,
                    )
                    raw_args = {}
            logger.info(
                "Parsed tool call from Ollama | name=%s | arguments=%s",
                fn_name,
                raw_args,
            )
            tool_calls.append(
                ToolCall(
                    id=f"ollama_{uuid.uuid4().hex[:8]}",
                    name=fn_name,
                    arguments=raw_args,
                )
            )

        return GenerationResult(
            text=text,
            tool_calls=tool_calls,
            finished=len(tool_calls) == 0,
        )

    @staticmethod
    def _convert_messages_for_ollama(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert OpenAI-style messages to Ollama's expected format.

        Key differences:
        - Tool result messages: Ollama does not use ``tool_call_id``.
        - Assistant tool_call messages: arguments must be a dict (not JSON string).
        """
        converted: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "")

            if role == "tool":
                # Ollama expects: {"role": "tool", "content": "..."}
                converted.append(
                    {
                        "role": "tool",
                        "content": msg.get("content", ""),
                    }
                )
            elif role == "assistant" and "tool_calls" in msg:
                # Ensure arguments are dicts (Ollama expects objects, not strings)
                ollama_tcs = []
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", {})
                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args)
                        except (json.JSONDecodeError, TypeError):
                            raw_args = {}
                    ollama_tcs.append(
                        {
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": raw_args,
                            },
                        }
                    )
                converted.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content", ""),
                        "tool_calls": ollama_tcs,
                    }
                )
            else:
                # system, user, plain assistant — pass through
                converted.append(
                    {
                        "role": role,
                        "content": msg.get("content", ""),
                    }
                )

        return converted

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
