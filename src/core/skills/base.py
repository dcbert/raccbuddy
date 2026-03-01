"""Base class and registry for injectable nudge skills.

Users can create custom nudge skills by subclassing ``BaseNudgeSkill`` and
registering them with ``register_skill()``.

Cooldown persistence
--------------------
Cooldown state is maintained in an in-memory write-through cache backed by
the ``nudge_cooldowns`` database table.  On startup, ``load_cooldowns_from_db``
must be called (done inside ``post_init`` in ``bot.py``) so that cooldowns
survive bot restarts.
"""

from __future__ import annotations

import datetime
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type returned by every skill's ``should_fire``
# ---------------------------------------------------------------------------


@dataclass
class NudgeCheck:
    """Result of a non-LLM precondition check."""

    fire: bool
    context: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ---------------------------------------------------------------------------
# In-memory cooldown cache (write-through to DB)
# ---------------------------------------------------------------------------

_cooldowns: dict[tuple[int, str], datetime.datetime] = {}

DEFAULT_COOLDOWN_MINUTES = 120


def _is_on_cooldown(owner_id: int, skill_name: str, cooldown_minutes: int) -> bool:
    """Return ``True`` if the skill fired recently for this owner.

    Checks the in-memory cache first (fast path).  The cache is populated
    at startup by ``load_cooldowns_from_db`` so this is correct even after
    a restart.

    Args:
        owner_id: The owner's Telegram user ID.
        skill_name: Unique name of the nudge skill.
        cooldown_minutes: How long the cooldown lasts in minutes.

    Returns:
        ``True`` when the skill is still on cooldown.
    """
    key = (owner_id, skill_name)
    last = _cooldowns.get(key)
    if last is None:
        return False
    elapsed = datetime.datetime.now(datetime.timezone.utc) - last
    return elapsed < datetime.timedelta(minutes=cooldown_minutes)


def _mark_fired(owner_id: int, skill_name: str) -> None:
    """Record that a skill just fired; update both cache and DB.

    The DB write is fire-and-forget (scheduled as an asyncio task) to avoid
    blocking the nudge engine.

    Args:
        owner_id: The owner's Telegram user ID.
        skill_name: Unique name of the nudge skill.
    """
    import asyncio

    now = datetime.datetime.now(datetime.timezone.utc)
    _cooldowns[(owner_id, skill_name)] = now

    # Persist to DB asynchronously (best-effort — in-memory cache is primary)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_persist_cooldown(owner_id, skill_name, now))
    except RuntimeError:
        pass  # No running loop (e.g., test context) — skip DB write


async def _persist_cooldown(
    owner_id: int,
    skill_name: str,
    fired_at: datetime.datetime,
) -> None:
    """Upsert the cooldown row for an owner/skill pair.

    Args:
        owner_id: The owner's Telegram user ID.
        skill_name: Unique name of the nudge skill.
        fired_at: UTC timestamp when the skill fired.
    """
    from sqlalchemy.dialects.postgresql import insert

    from src.core.db.models import NudgeCooldown
    from src.core.db.session import get_session

    try:
        async with get_session() as session:
            stmt = (
                insert(NudgeCooldown)
                .values(
                    owner_id=owner_id,
                    skill_name=skill_name,
                    last_fired_at=fired_at,
                )
                .on_conflict_do_update(
                    constraint="uq_owner_skill_cooldown",
                    set_={"last_fired_at": fired_at},
                )
            )
            await session.execute(stmt)
            await session.commit()
    except Exception:
        logger.warning(
            "Failed to persist cooldown for owner=%d skill=%s",
            owner_id,
            skill_name,
            exc_info=True,
        )


async def load_cooldowns_from_db() -> int:
    """Populate the in-memory cooldown cache from the database.

    Must be called once at bot startup (in ``post_init``) so that cooldowns
    accumulated before the last restart are honoured.

    Returns:
        Number of cooldown records loaded.
    """
    from src.core.db.models import NudgeCooldown
    from src.core.db.session import get_session
    from sqlalchemy import select

    try:
        async with get_session() as session:
            result = await session.execute(select(NudgeCooldown))
            rows = result.scalars().all()

        for row in rows:
            _cooldowns[(row.owner_id, row.skill_name)] = row.last_fired_at

        logger.info("Loaded %d nudge cooldowns from DB", len(rows))
        return len(rows)
    except Exception:
        logger.warning("Failed to load nudge cooldowns from DB", exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Abstract base skill
# ---------------------------------------------------------------------------


class BaseNudgeSkill(ABC):
    """Abstract base class for all nudge skills."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def trigger(self) -> str: ...

    @property
    @abstractmethod
    def default_prompt(self) -> str: ...

    @property
    def cooldown_minutes(self) -> int:
        return DEFAULT_COOLDOWN_MINUTES

    @abstractmethod
    async def should_fire(self, owner_id: int) -> NudgeCheck: ...

    def build_prompt(self, check: NudgeCheck) -> str:
        """Render the final prompt string from the template + context.

        Args:
            check: The ``NudgeCheck`` result containing the context dict.

        Returns:
            The formatted prompt string.
        """
        try:
            return self.default_prompt.format(**check.context)
        except KeyError:
            return self.default_prompt


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------

_skills: dict[str, BaseNudgeSkill] = {}


def register_skill(skill: BaseNudgeSkill) -> None:
    """Register a nudge skill (built-in or user-provided).

    Args:
        skill: The skill instance to register.
    """
    if skill.name in _skills:
        logger.warning("Overwriting existing nudge skill: %s", skill.name)
    _skills[skill.name] = skill
    logger.info("Nudge skill registered: %s", skill.name)


def unregister_skill(name: str) -> None:
    """Remove a nudge skill by name.

    Args:
        name: The skill's unique name.
    """
    _skills.pop(name, None)


def get_registered_skills() -> dict[str, BaseNudgeSkill]:
    """Return a shallow copy of the current skill registry."""
    return dict(_skills)


def clear_skills() -> None:
    """Remove all registered skills (useful for testing)."""
    _skills.clear()


def clear_cooldowns() -> None:
    """Reset all in-memory cooldown state (useful for testing)."""
    _cooldowns.clear()
