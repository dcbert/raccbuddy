"""Mood and sentiment analysis.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.sentiment.analyzer import _MOODS, _VALENCE_MAP, MoodAnalyzer, mood_analyzer

__all__ = [
    "MoodAnalyzer",
    "_MOODS",
    "_VALENCE_MAP",
    "mood_analyzer",
]
