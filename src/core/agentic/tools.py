"""Adapt existing RaccBuddy tools and skills into LangGraph tool format.

This module wraps the existing ``tools/registry`` and ``skills/base``
registrations so that the agentic graph nodes can invoke them without
importing framework-specific details.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.config import settings
from src.core.skills.base import (
    BaseNudgeSkill,
    NudgeCheck,
    _is_on_cooldown,
    get_registered_skills,
)
from src.core.tools.registry import execute_tool, get_all_tool_schemas

logger = logging.getLogger(__name__)


async def get_available_nudge_skills() -> list[dict[str, Any]]:
    """Return nudge skills that are not on cooldown for the owner.

    Returns:
        List of dicts with ``name``, ``trigger``, ``cooldown_minutes``.
    """
    owner_id = settings.owner_telegram_id
    result: list[dict[str, Any]] = []
    for name, skill in get_registered_skills().items():
        on_cd = _is_on_cooldown(owner_id, name, skill.cooldown_minutes)
        result.append(
            {
                "name": name,
                "trigger": skill.trigger,
                "cooldown_minutes": skill.cooldown_minutes,
                "on_cooldown": on_cd,
            }
        )
    return result


async def evaluate_nudge_skill(skill_name: str) -> NudgeCheck | None:
    """Evaluate a single nudge skill's ``should_fire`` for the owner.

    Args:
        skill_name: The registered skill name.

    Returns:
        The ``NudgeCheck`` result, or ``None`` if the skill is not found.
    """
    owner_id = settings.owner_telegram_id
    skills = get_registered_skills()
    skill: BaseNudgeSkill | None = skills.get(skill_name)
    if skill is None:
        logger.warning("Skill '%s' not found in registry", skill_name)
        return None
    return await skill.should_fire(owner_id)


def get_tool_schemas_for_agent() -> list[dict[str, Any]]:
    """Return all tool schemas in the format usable by LLM tool-calling."""
    return get_all_tool_schemas()


async def execute_tool_for_agent(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Execute a registered tool and return the result string.

    Args:
        tool_name: The tool's registered name.
        arguments: The tool's arguments dict.

    Returns:
        The tool's result as a string.
    """
    owner_id = settings.owner_telegram_id
    return await execute_tool(tool_name, arguments, owner_id)
