"""Nudge engine — proactive nudge detection and delivery.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.nudges.engine import (
    check_contact_patterns,
    check_idle_users,
    detect_habits,
    run_nudge_skills,
    send_nudge,
)
from src.core.skills.nudge import BOREDOM_IDLE_MINUTES

__all__ = [
    "BOREDOM_IDLE_MINUTES",
    "check_contact_patterns",
    "check_idle_users",
    "detect_habits",
    "run_nudge_skills",
    "send_nudge",
]
