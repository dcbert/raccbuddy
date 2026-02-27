"""Built-in nudge skills shipped with RaccBuddy.

Each skill implements a cheap, non-LLM ``should_fire`` check so the LLM
is only invoked when real data warrants a nudge.
"""

from __future__ import annotations

import datetime
import logging

from src.core.db.crud import (
    count_messages_from_contact_since,
    count_messages_since,
    get_all_contacts_all_platforms,
    get_all_habits,
    get_idle_contact_ids,
    get_last_message_ts_for_contact,
)
from src.core.skills.base import BaseNudgeSkill, NudgeCheck

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Idle check
# ---------------------------------------------------------------------------

BOREDOM_IDLE_MINUTES = 120
_IDLE_ACTIVITY_WINDOW_MINUTES = 360


class IdleSkill(BaseNudgeSkill):
    """Nudge when the user was active recently but then went idle."""

    name = "idle"  # type: ignore[assignment]
    trigger = "idle"  # type: ignore[assignment]
    default_prompt = (  # type: ignore[assignment]
        "The user has been idle for a while. Send a short, encouraging "
        "nudge to check in. Be cheeky and raccoon-like. Max 2 sentences."
    )

    @property
    def cooldown_minutes(self) -> int:
        return BOREDOM_IDLE_MINUTES

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        now = datetime.datetime.now(datetime.timezone.utc)
        idle_cutoff = now - datetime.timedelta(minutes=BOREDOM_IDLE_MINUTES)
        activity_cutoff = now - datetime.timedelta(
            minutes=_IDLE_ACTIVITY_WINDOW_MINUTES,
        )

        idle_contacts = await get_idle_contact_ids(idle_cutoff)
        owner_is_idle = any(uid == owner_id for uid, _ in idle_contacts)
        if not owner_is_idle:
            return NudgeCheck(fire=False, reason="User is not idle")

        msg_count = await count_messages_since(owner_id, activity_cutoff)
        if msg_count == 0:
            return NudgeCheck(
                fire=False,
                reason="No recent activity — nothing happened",
            )

        return NudgeCheck(
            fire=True,
            reason=f"User idle >{BOREDOM_IDLE_MINUTES}m after {msg_count} msgs",
        )


# ---------------------------------------------------------------------------
# Contact quiet check
# ---------------------------------------------------------------------------

CONTACT_QUIET_DAYS = 3
_CONTACT_ACTIVE_WINDOW_DAYS = 7


class ContactQuietSkill(BaseNudgeSkill):
    """Nudge when a previously-active contact has gone quiet."""

    name = "contact_quiet"  # type: ignore[assignment]
    trigger = "contact_quiet"  # type: ignore[assignment]
    default_prompt = (  # type: ignore[assignment]
        "The user hasn't chatted with {contact_name} in a while. "
        "Nudge them to reach out. Be cheeky and raccoon-like. Max 2 sentences."
    )

    @property
    def cooldown_minutes(self) -> int:
        return 60 * 12

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        now = datetime.datetime.now(datetime.timezone.utc)
        quiet_cutoff = now - datetime.timedelta(days=CONTACT_QUIET_DAYS)
        active_cutoff = now - datetime.timedelta(days=_CONTACT_ACTIVE_WINDOW_DAYS)

        contacts = await get_all_contacts_all_platforms(owner_id)
        quiet_contacts: list[str] = []

        for contact in contacts:
            last_ts = await get_last_message_ts_for_contact(
                contact.id, owner_id,
            )
            if last_ts is None or last_ts >= quiet_cutoff:
                continue

            prior_msgs = await count_messages_from_contact_since(
                contact.id, owner_id, active_cutoff,
            )
            if prior_msgs > 0:
                quiet_contacts.append(contact.contact_name)

        if not quiet_contacts:
            return NudgeCheck(
                fire=False,
                reason="No contacts went quiet after being active",
            )

        return NudgeCheck(
            fire=True,
            context={"contact_name": quiet_contacts[0]},
            reason=f"Quiet contacts: {', '.join(quiet_contacts)}",
        )


# ---------------------------------------------------------------------------
# Evening summary check
# ---------------------------------------------------------------------------


class EveningSkill(BaseNudgeSkill):
    """Send an evening summary only if there was actual activity today."""

    name = "evening"  # type: ignore[assignment]
    trigger = "evening"  # type: ignore[assignment]
    default_prompt = (  # type: ignore[assignment]
        "Send a brief evening summary nudge. Be warm and motivational. "
        "Max 2 sentences."
    )

    @property
    def cooldown_minutes(self) -> int:
        return 60 * 20

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        now = datetime.datetime.now(datetime.timezone.utc)
        hour = now.hour

        if not (18 <= hour <= 23):
            return NudgeCheck(fire=False, reason="Not evening yet")

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        msg_count = await count_messages_since(owner_id, day_start)
        if msg_count == 0:
            return NudgeCheck(fire=False, reason="No messages today")

        return NudgeCheck(
            fire=True,
            reason=f"Evening summary — {msg_count} messages today",
        )


# ---------------------------------------------------------------------------
# Habit check
# ---------------------------------------------------------------------------


class HabitSkill(BaseNudgeSkill):
    """Nudge about detected habits — only if habits actually exist in DB."""

    name = "habit"  # type: ignore[assignment]
    trigger = "habit"  # type: ignore[assignment]
    default_prompt = (  # type: ignore[assignment]
        "The user might be falling into a bad habit. Nudge them gently "
        "with a clear action suggestion. Max 2 sentences."
    )

    @property
    def cooldown_minutes(self) -> int:
        return 60 * 6

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        habits = await get_all_habits(owner_id=owner_id)
        if not habits:
            return NudgeCheck(fire=False, reason="No habits detected")

        return NudgeCheck(
            fire=True,
            context={"habit_count": len(habits)},
            reason=f"{len(habits)} habit(s) detected",
        )
