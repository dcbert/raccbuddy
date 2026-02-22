"""Base class and registry for injectable nudge skills.

Users can create custom nudge skills by subclassing ``BaseNudgeSkill`` and
registering them with ``register_skill()``.
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
# Cooldown tracker
# ---------------------------------------------------------------------------

_cooldowns: dict[tuple[int, str], datetime.datetime] = {}

DEFAULT_COOLDOWN_MINUTES = 120


def _is_on_cooldown(owner_id: int, skill_name: str, cooldown_minutes: int) -> bool:
    """Return ``True`` if the skill fired recently for this owner."""
    key = (owner_id, skill_name)
    last = _cooldowns.get(key)
    if last is None:
        return False
    elapsed = datetime.datetime.now(datetime.timezone.utc) - last
    return elapsed < datetime.timedelta(minutes=cooldown_minutes)


def _mark_fired(owner_id: int, skill_name: str) -> None:
    """Record that a skill just fired for an owner."""
    _cooldowns[(owner_id, skill_name)] = datetime.datetime.now(
        datetime.timezone.utc,
    )


# ---------------------------------------------------------------------------
# Abstract base skill
# ---------------------------------------------------------------------------


class BaseNudgeSkill(ABC):
    """Abstract base class for all nudge skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def trigger(self) -> str:
        ...

    @property
    @abstractmethod
    def default_prompt(self) -> str:
        ...

    @property
    def cooldown_minutes(self) -> int:
        return DEFAULT_COOLDOWN_MINUTES

    @abstractmethod
    async def should_fire(self, owner_id: int) -> NudgeCheck:
        ...

    def build_prompt(self, check: NudgeCheck) -> str:
        """Render the final prompt string from the template + context."""
        try:
            return self.default_prompt.format(**check.context)
        except KeyError:
            return self.default_prompt


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------

_skills: dict[str, BaseNudgeSkill] = {}


def register_skill(skill: BaseNudgeSkill) -> None:
    """Register a nudge skill (built-in or user-provided)."""
    if skill.name in _skills:
        logger.warning("Overwriting existing nudge skill: %s", skill.name)
    _skills[skill.name] = skill
    logger.info("Nudge skill registered: %s", skill.name)


def unregister_skill(name: str) -> None:
    """Remove a nudge skill by name."""
    _skills.pop(name, None)


def get_registered_skills() -> dict[str, BaseNudgeSkill]:
    """Return a copy of the current skill registry."""
    return dict(_skills)


def clear_skills() -> None:
    """Remove all registered skills (useful for testing)."""
    _skills.clear()


def clear_cooldowns() -> None:
    """Reset all cooldown state (useful for testing)."""
    _cooldowns.clear()
