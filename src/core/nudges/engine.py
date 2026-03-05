"""Proactive nudge detection and delivery.

The nudge engine uses injectable skills to decide without LLM calls
whether a nudge is warranted.
"""

from __future__ import annotations

import logging

from src.core.config import settings
from src.utils.telegram_format import md_to_telegram_html
from src.core.db.crud import get_all_habits
from src.core.llm.interface import generate
from src.core.skills.base import (
    _is_on_cooldown,
    _mark_fired,
    get_registered_skills,
    register_skill,
)
from src.core.skills.nudge import ContactQuietSkill, EveningSkill, HabitSkill, IdleSkill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto-register built-in skills
# ---------------------------------------------------------------------------


def _register_builtins() -> None:
    """Register the default skill set (idempotent)."""
    existing = get_registered_skills()
    for skill_cls in (IdleSkill, ContactQuietSkill, EveningSkill, HabitSkill):
        inst = skill_cls()
        if inst.name not in existing:
            register_skill(inst)


_register_builtins()


# ---------------------------------------------------------------------------
# Skill-based nudge engine
# ---------------------------------------------------------------------------


async def run_nudge_skills(bot: object) -> None:
    """Evaluate every registered skill and send nudges where warranted."""
    owner_id = settings.owner_telegram_id
    if not owner_id:
        return

    for name, skill in get_registered_skills().items():
        try:
            if _is_on_cooldown(owner_id, name, skill.cooldown_minutes):
                logger.debug("Skill %s on cooldown for owner %d", name, owner_id)
                continue

            check = await skill.should_fire(owner_id)
            if not check.fire:
                logger.debug(
                    "Skill %s did not fire: %s",
                    name,
                    check.reason,
                )
                continue

            prompt = skill.build_prompt(check)
            logger.info(
                "Skill %s fired for owner %d — reason: %s",
                name,
                owner_id,
                check.reason,
            )
            await send_nudge(bot, owner_id, skill.trigger, prompt)
            _mark_fired(owner_id, name)

        except Exception:
            logger.exception("Error evaluating skill %s", name)


# ---------------------------------------------------------------------------
# Legacy entry-points
# ---------------------------------------------------------------------------


async def check_idle_users(bot: object) -> None:
    """Legacy entry-point — no-op for backward compatibility."""
    pass


async def check_contact_patterns(bot: object) -> None:
    """Legacy entry-point — no-op for backward compatibility."""
    pass


# ---------------------------------------------------------------------------
# Core send helper
# ---------------------------------------------------------------------------


async def send_nudge(
    bot: object,
    user_id: int,
    trigger: str,
    prompt: str,
) -> None:
    """Generate LLM text and deliver the nudge to the user."""
    try:
        response = await generate(prompt)
        await bot.send_message(  # type: ignore[attr-defined]
            chat_id=user_id,
            text=md_to_telegram_html(response),
            parse_mode="HTML",
        )
        logger.info("Nudge sent to user %d (trigger: %s)", user_id, trigger)
    except Exception:
        logger.exception("Failed to send nudge to user %d", user_id)


async def execute_nudge_from_agent(
    bot: object,
    user_id: int,
    trigger: str,
    text: str,
) -> None:
    """Deliver a pre-crafted nudge from the agentic engine.

    Unlike ``send_nudge``, this function does **not** call the LLM — the
    Crafter node has already generated the final text.

    Args:
        bot: The Telegram bot instance.
        user_id: The recipient's Telegram user ID.
        trigger: The nudge trigger name (for logging).
        text: The final nudge text to deliver.
    """
    try:
        await bot.send_message(  # type: ignore[attr-defined]
            chat_id=user_id,
            text=md_to_telegram_html(text),
            parse_mode="HTML",
        )
        logger.info(
            "Agentic nudge sent to user %d (trigger: %s)",
            user_id,
            trigger,
        )
    except Exception:
        logger.exception(
            "Failed to send agentic nudge to user %d (trigger: %s)",
            user_id,
            trigger,
        )


async def detect_habits(user_id: int) -> list:
    """Retrieve detected habits for a user.

    Args:
        user_id: The owner's Telegram user ID.

    Returns:
        List of ``Habit`` rows belonging to the user.
    """
    return await get_all_habits(owner_id=user_id)
