"""Skill system — nudge skills, chat skills, and registries.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.skills.base import (
    DEFAULT_COOLDOWN_MINUTES,
    BaseNudgeSkill,
    NudgeCheck,
    _is_on_cooldown,
    _mark_fired,
    clear_cooldowns,
    clear_skills,
    get_registered_skills,
    register_skill,
    unregister_skill,
)
from src.core.skills.chat import (
    BaseChatSkill,
    clear_chat_skills,
    collect_system_prompt_fragments,
    collect_tool_schemas,
    dispatch_skill_tool,
    get_registered_chat_skills,
    register_chat_skill,
    run_post_processors,
    run_pre_processors,
    unregister_chat_skill,
)
from src.core.skills.loader import (
    _import_py_files,
    load_all_user_skills,
    load_user_chat_skills,
    load_user_nudge_skills,
)
from src.core.skills.nudge import (
    BOREDOM_IDLE_MINUTES,
    CONTACT_QUIET_DAYS,
    ContactQuietSkill,
    EveningSkill,
    HabitSkill,
    IdleSkill,
)

__all__ = [
    "BaseNudgeSkill",
    "BaseChatSkill",
    "BOREDOM_IDLE_MINUTES",
    "CONTACT_QUIET_DAYS",
    "ContactQuietSkill",
    "DEFAULT_COOLDOWN_MINUTES",
    "EveningSkill",
    "HabitSkill",
    "IdleSkill",
    "NudgeCheck",
    "_import_py_files",
    "_is_on_cooldown",
    "_mark_fired",
    "clear_chat_skills",
    "clear_cooldowns",
    "clear_skills",
    "collect_system_prompt_fragments",
    "collect_tool_schemas",
    "dispatch_skill_tool",
    "get_registered_chat_skills",
    "get_registered_skills",
    "load_all_user_skills",
    "load_user_chat_skills",
    "load_user_nudge_skills",
    "register_chat_skill",
    "register_skill",
    "run_post_processors",
    "run_pre_processors",
    "unregister_chat_skill",
    "unregister_skill",
]
