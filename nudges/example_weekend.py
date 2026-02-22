"""Example nudge skill: weekend check-in.

Drop this file in the nudges/ folder. RaccBuddy will auto-load it at
startup and send a chill weekend nudge when appropriate.
"""

import datetime

from src.core.skills.base import BaseNudgeSkill, NudgeCheck, register_skill


class WeekendCheckinSkill(BaseNudgeSkill):
    """Send a casual nudge on weekend afternoons."""

    name = "weekend_checkin"  # type: ignore[assignment]
    trigger = "weekend"  # type: ignore[assignment]
    default_prompt = (  # type: ignore[assignment]
        "It's the weekend! Send a relaxed, fun raccoon check-in. "
        "Max 2 sentences."
    )

    @property
    def cooldown_minutes(self) -> int:
        return 60 * 12  # once per 12 hours

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now.weekday() >= 5 and 12 <= now.hour <= 20:
            return NudgeCheck(fire=True, reason="Weekend afternoon")
        return NudgeCheck(fire=False, reason="Not a weekend afternoon")


register_skill(WeekendCheckinSkill())
