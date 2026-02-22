"""Base class and registry for injectable chat skills.

Chat skills let users personalise the RaccBuddy experience during
conversation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base chat skill
# ---------------------------------------------------------------------------


class BaseChatSkill(ABC):
    """Abstract base class for all chat skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    def system_prompt_fragment(self) -> str | None:
        return None

    @property
    def tool_schemas(self) -> list[dict[str, Any]]:
        return []

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        owner_id: int,
    ) -> str:
        return f"Tool '{tool_name}' not implemented by skill '{self.name}'."

    async def pre_process(self, message: str, owner_id: int) -> str:
        return message

    async def post_process(self, reply: str, owner_id: int) -> str:
        return reply


# ---------------------------------------------------------------------------
# Chat skill registry
# ---------------------------------------------------------------------------

_chat_skills: dict[str, BaseChatSkill] = {}


def register_chat_skill(skill: BaseChatSkill) -> None:
    """Register a chat skill (built-in or user-provided)."""
    if skill.name in _chat_skills:
        logger.warning("Overwriting existing chat skill: %s", skill.name)
    _chat_skills[skill.name] = skill
    logger.info("Chat skill registered: %s", skill.name)


def unregister_chat_skill(name: str) -> None:
    """Remove a chat skill by name."""
    _chat_skills.pop(name, None)


def get_registered_chat_skills() -> dict[str, BaseChatSkill]:
    """Return a copy of the current chat skill registry."""
    return dict(_chat_skills)


def clear_chat_skills() -> None:
    """Remove all registered chat skills (useful for testing)."""
    _chat_skills.clear()


# ---------------------------------------------------------------------------
# Helpers used by the chat handler / tool executor
# ---------------------------------------------------------------------------


def collect_system_prompt_fragments() -> str:
    """Concatenate all system prompt fragments from registered skills."""
    parts: list[str] = []
    for skill in _chat_skills.values():
        frag = skill.system_prompt_fragment
        if frag:
            parts.append(frag)
    return "\n".join(parts)


def collect_tool_schemas() -> list[dict[str, Any]]:
    """Gather tool schemas from all registered chat skills."""
    schemas: list[dict[str, Any]] = []
    for skill in _chat_skills.values():
        schemas.extend(skill.tool_schemas)
    return schemas


async def dispatch_skill_tool(
    tool_name: str,
    arguments: dict[str, Any],
    owner_id: int,
) -> str | None:
    """Try to execute a tool via the chat skills."""
    for skill in _chat_skills.values():
        owned_names = {
            s["function"]["name"]
            for s in skill.tool_schemas
            if "function" in s
        }
        if tool_name in owned_names:
            return await skill.execute_tool(tool_name, arguments, owner_id)
    return None


async def run_pre_processors(message: str, owner_id: int) -> str:
    """Run all skill pre-processors in registration order."""
    for skill in _chat_skills.values():
        message = await skill.pre_process(message, owner_id)
    return message


async def run_post_processors(reply: str, owner_id: int) -> str:
    """Run all skill post-processors in registration order."""
    for skill in _chat_skills.values():
        reply = await skill.post_process(reply, owner_id)
    return reply
