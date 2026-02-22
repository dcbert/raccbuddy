"""Habit detection and analysis.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.habits.detector import HabitDetector, habit_detector

__all__ = [
    "HabitDetector",
    "habit_detector",
]
