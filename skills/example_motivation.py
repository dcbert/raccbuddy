"""Example chat skill: daily motivation.

Drop this file in the skills/ folder. RaccBuddy will auto-load it at
startup and add a motivational twist to replies.
"""

from src.core.skills.chat import BaseChatSkill, register_chat_skill


class DailyMotivationSkill(BaseChatSkill):
    """Add a motivational sentence to every reply."""

    name = "daily_motivation"  # type: ignore[assignment]
    description = "Sprinkle motivational vibes into replies."  # type: ignore[assignment]
    system_prompt_fragment = (  # type: ignore[assignment]
        "When appropriate, end your reply with a short motivational "
        "sentence related to what the user is going through."
    )


register_chat_skill(DailyMotivationSkill())
