"""
xAI Provider — official xai-sdk (gRPC) with hybrid Agent Tools.

Built-in tools (web_search, x_search, code_execution, …) = opt-in, server-side, auto-chained by Grok.
Custom RaccBuddy tools = always executed locally via existing skill loop.
Privacy-first: built-in tools disabled by default.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

import grpc
from xai_sdk import AsyncClient
from xai_sdk.chat import assistant
from xai_sdk.chat import system as sdk_system
from xai_sdk.chat import tool, tool_result
from xai_sdk.chat import user as sdk_user
from xai_sdk.tools import code_execution, web_search, x_search

from src.core.config import settings
from src.core.llm.base import BaseLLMProvider, GenerationResult, ToolCall

logger = logging.getLogger(__name__)

# gRPC status codes that indicate a transient/connection error worth retrying
_RETRYABLE_GRPC_CODES = {
    grpc.StatusCode.UNKNOWN,
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
    grpc.StatusCode.INTERNAL,
}


class XAIProvider(BaseLLMProvider):
    """Official xAI SDK provider with Grok Agent Tools (built-in) + custom local tools."""

    @property
    def name(self) -> str:
        return "xai"

    @property
    def supports_tools(self) -> bool:
        return True

    def __init__(self) -> None:
        super().__init__()

        if not settings.xai_api_key:
            logger.warning("XAI_API_KEY not configured → xAI provider disabled")
            self.client = None
            return

        self._api_key = settings.xai_api_key
        self._timeout = 360.0  # long for reasoning + multi-tool chains
        self.client = self._create_client()
        self.model = settings.xai_model
        self.enable_builtin = settings.xai_enable_builtin_tools
        self._max_retries = settings.xai_max_retries

        if self.enable_builtin:
            logger.warning(
                "🟡 Grok Built-in Agent Tools ENABLED (web/X/code search) — data leaves machine"
            )
        else:
            logger.info("✅ XAIProvider ready (built-in tools OFF — 100% privacy)")

        logger.info(
            "   model=%s | temperature=%s | max_retries=%d",
            self.model,
            settings.xai_temperature,
            self._max_retries,
        )

    def _create_client(self) -> AsyncClient:
        """Create a fresh xAI AsyncClient (gRPC connection)."""
        return AsyncClient(
            api_key=self._api_key,
            timeout=self._timeout,
        )

    def _reconnect(self) -> None:
        """Tear down the existing gRPC client and create a fresh one.

        Called after a transient connection error (e.g. stale h2 stream)
        so the next attempt uses a clean underlying channel.
        """
        logger.warning("Recreating xAI gRPC client after connection error")
        self.client = self._create_client()

    def _build_xai_tools(self, custom_tools: List[Dict[str, Any]]) -> List:
        """Mix optional built-in + always-present custom tools."""
        tools: List = []
        if self.enable_builtin:
            tools.extend([web_search(), x_search(), code_execution()])
        for t in custom_tools:
            if (
                t.get("type") == "function"
                and t["function"]
                and t["function"].get("name")
                not in ["web_search", "x_search", "code_execution"]
            ):
                fn = t["function"]
                tools.append(
                    tool(
                        name=fn["name"],
                        description=fn.get("description", ""),
                        parameters=fn.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    )
                )
        return tools

    def _build_xai_messages(self, messages: List[Dict[str, Any]]) -> List:
        """Convert standard OpenAI-style messages to xAI SDK objects.

        Handles all roles including assistant tool_calls and tool result
        messages, which are required for the model to see tool responses
        during multi-round tool loops.
        """
        xai_msgs = []
        for m in messages:
            role = m.get("role", "").lower()
            content = m.get("content", "")
            if role == "system":
                xai_msgs.append(sdk_system(str(content)))
            elif role == "user":
                xai_msgs.append(sdk_user(str(content)))
            elif role == "assistant":
                # Plain assistant text message
                xai_msgs.append(assistant(str(content)))
                # If the assistant message carries tool_calls metadata,
                # the xai SDK chat.append(response) pattern expects the raw
                # response object. Since we rebuild from dicts, we emit
                # separate tool_result messages below instead — the assistant
                # text is already appended above.
            elif role == "tool":
                # Tool result from the local execution loop.
                # Per xAI SDK docs: tool_result(result_str, tool_call_id=...)
                tc_id = m.get("tool_call_id")
                xai_msgs.append(tool_result(str(content), tool_call_id=tc_id))
            else:
                logger.debug("Skipping unknown message role: %s", role)
        return xai_msgs

    async def generate(self, prompt: str, system: str) -> str:
        """Simple single-turn (used for basic flows)."""
        if not self.client:
            raise RuntimeError("xAI not configured")

        last_err: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                chat = self.client.chat.create(
                    model=self.model,
                    messages=[sdk_system(system), sdk_user(prompt)],
                )
                response = await chat.sample()

                if hasattr(response, "usage") and response.usage:
                    logger.info(
                        "xAI generate tokens: prompt=%s completion=%s total=%s model=%s",
                        getattr(response.usage, "prompt_tokens", "?"),
                        getattr(response.usage, "completion_tokens", "?"),
                        getattr(response.usage, "total_tokens", "?"),
                        self.model,
                    )

                return response.content or ""

            except grpc.aio.AioRpcError as exc:
                last_err = exc
                if exc.code() not in _RETRYABLE_GRPC_CODES:
                    raise
                logger.warning(
                    "xAI generate: transient gRPC error on attempt %d/%d: %s",
                    attempt,
                    self._max_retries,
                    exc.details(),
                )
                self._reconnect()
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2**attempt, 10))

        if last_err is not None:
            raise last_err
        raise RuntimeError("xAI generate: all retries exhausted")

    async def generate_chat(self, messages: List[Dict[str, str]]) -> str:
        """Native multi-turn chat using the xAI SDK chat.create(...) API."""
        if not self.client:
            raise RuntimeError("xAI not configured")

        last_err: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                chat = self.client.chat.create(
                    model=self.model,
                    messages=self._build_xai_messages(messages),
                )
                response = await chat.sample()

                if hasattr(response, "usage") and response.usage:
                    logger.info(
                        "xAI generate_chat tokens: prompt=%s completion=%s total=%s model=%s",
                        getattr(response.usage, "prompt_tokens", "?"),
                        getattr(response.usage, "completion_tokens", "?"),
                        getattr(response.usage, "total_tokens", "?"),
                        self.model,
                    )

                return response.content or ""

            except grpc.aio.AioRpcError as exc:
                last_err = exc
                if exc.code() not in _RETRYABLE_GRPC_CODES:
                    raise
                logger.warning(
                    "xAI generate_chat: transient gRPC error on attempt %d/%d: %s",
                    attempt,
                    self._max_retries,
                    exc.details(),
                )
                self._reconnect()
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2**attempt, 10))

        if last_err is not None:
            raise last_err
        raise RuntimeError("xAI generate_chat: all retries exhausted")

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> GenerationResult:
        """Unified tool-aware generation. Built-in tools auto-chain on xAI side."""
        if not self.client:
            raise RuntimeError("xAI not configured")

        last_err: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                chat = self.client.chat.create(
                    model=self.model,
                    messages=self._build_xai_messages(messages),
                    tools=self._build_xai_tools(tools),
                )

                response = await chat.sample()

                if hasattr(response, "usage") and response.usage:
                    logger.info(
                        "xAI generate_with_tools tokens: prompt=%s completion=%s total=%s model=%s",
                        getattr(response.usage, "prompt_tokens", "?"),
                        getattr(response.usage, "completion_tokens", "?"),
                        getattr(response.usage, "total_tokens", "?"),
                        self.model,
                    )

                text = response.content or ""
                tool_calls: List[ToolCall] = []

                # Only custom tools appear as tool_calls (built-in are resolved server-side)
                if response.tool_calls:
                    for tc in response.tool_calls:
                        try:
                            args = (
                                json.loads(tc.function.arguments)
                                if tc.function.arguments
                                else {}
                            )
                        except Exception:
                            args = {}
                        tool_calls.append(
                            ToolCall(
                                id=getattr(tc, "id", ""),
                                name=tc.function.name,
                                arguments=args,
                            )
                        )

                return GenerationResult(
                    text=text,
                    tool_calls=tool_calls,
                    finished=len(tool_calls) == 0,
                )

            except grpc.aio.AioRpcError as exc:
                last_err = exc
                if exc.code() not in _RETRYABLE_GRPC_CODES:
                    logger.error(
                        "xAI generate_with_tools failed with non-retryable gRPC error "
                        "(model=%s, code=%s): %s",
                        self.model,
                        exc.code(),
                        exc.details(),
                    )
                    raise
                logger.warning(
                    "xAI generate_with_tools: transient gRPC error on attempt %d/%d: %s",
                    attempt,
                    self._max_retries,
                    exc.details(),
                )
                self._reconnect()
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2**attempt, 10))

            except Exception:
                logger.error(
                    "xAI generate_with_tools failed (model=%s)",
                    self.model,
                    exc_info=True,
                )
                raise

        if last_err is not None:
            raise last_err
        raise RuntimeError("xAI generate_with_tools: all retries exhausted")

    async def embed(self, text: str) -> List[float]:
        """Embeddings (placeholder — use ollama or OpenAI compat if needed)."""
        raise NotImplementedError(
            "xAI embeddings via SDK coming soon or use another provider"
        )
