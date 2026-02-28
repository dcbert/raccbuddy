"""
xAI Provider — official xai-sdk (gRPC) with hybrid Agent Tools.

Built-in tools (web_search, x_search, code_execution, …) = opt-in, server-side, auto-chained by Grok.
Custom RaccBuddy tools = always executed locally via existing skill loop.
Privacy-first: built-in tools disabled by default.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from xai_sdk import AsyncClient
from xai_sdk.chat import assistant
from xai_sdk.chat import system as sdk_system
from xai_sdk.chat import tool
from xai_sdk.chat import user as sdk_user
from xai_sdk.tools import code_execution, web_search, x_search

from src.core.config import settings
from src.core.llm.base import BaseLLMProvider, GenerationResult, ToolCall

logger = logging.getLogger(__name__)


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

        self.client = AsyncClient(
            api_key=settings.xai_api_key,
            timeout=360.0,  # long for reasoning + multi-tool chains
        )
        self.model = settings.xai_model
        self.enable_builtin = settings.xai_enable_builtin_tools

        if self.enable_builtin:
            logger.warning("🟡 Grok Built-in Agent Tools ENABLED (web/X/code search) — data leaves machine")
        else:
            logger.info("✅ XAIProvider ready (built-in tools OFF — 100% privacy)")

        logger.info("   model=%s | temperature=%s", self.model, settings.xai_temperature)

    def _build_xai_tools(self, custom_tools: List[Dict[str, Any]]) -> List:
        """Mix optional built-in + always-present custom tools."""
        tools: List = []
        if self.enable_builtin:
            tools.extend([web_search(), x_search(), code_execution()])
        for t in custom_tools:
            if t.get("type") == "function":
                fn = t["function"]
                tools.append(
                    tool(
                        name=fn["name"],
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {"type": "object", "properties": {}}),
                    )
                )
        return tools

    def _build_xai_messages(self, messages: List[Dict[str, Any]]) -> List:
        """Convert standard OpenAI-style messages to xAI SDK objects."""
        xai_msgs = []
        for m in messages:
            role = m.get("role", "").lower()
            content = m.get("content", "")
            if role == "system":
                xai_msgs.append(sdk_system(str(content)))
            elif role == "user":
                xai_msgs.append(sdk_user(str(content)))
            elif role == "assistant":
                xai_msgs.append(assistant(str(content)))
            # tool role messages are handled by the upper-layer loop (no conversion needed here)
        return xai_msgs

    async def generate(self, prompt: str, system: str) -> str:
        """Simple single-turn (used for basic flows)."""
        if not self.client:
            raise RuntimeError("xAI not configured")

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

    async def generate_chat(self, messages: List[Dict[str, str]]) -> str:
        """Native multi-turn chat using the xAI SDK chat.create(...) API."""
        if not self.client:
            raise RuntimeError("xAI not configured")

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

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> GenerationResult:
        """Unified tool-aware generation. Built-in tools auto-chain on xAI side."""
        if not self.client:
            raise RuntimeError("xAI not configured")

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
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
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

        except Exception:
            logger.error("xAI generate_with_tools failed (model=%s)", self.model, exc_info=True)
            raise

    async def embed(self, text: str) -> List[float]:
        """Embeddings (placeholder — use ollama or OpenAI compat if needed)."""
        raise NotImplementedError("xAI embeddings via SDK coming soon or use another provider")