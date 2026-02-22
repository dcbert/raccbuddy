"""Tests for src.core.sentiment."""

from __future__ import annotations

import pytest

from src.core.sentiment import _MOODS, _VALENCE_MAP, MoodAnalyzer


class TestParseResponse:
    """Validate LLM response parsing."""

    def test_valid_mood_and_valence(self) -> None:
        result = MoodAnalyzer._parse_response("happy\n0.8")
        assert result == ("happy", 0.8)

    def test_valid_mood_no_valence(self) -> None:
        mood, valence = MoodAnalyzer._parse_response("sad")
        assert mood == "sad"
        assert valence == _VALENCE_MAP["sad"]

    def test_unknown_mood_defaults_neutral(self) -> None:
        mood, valence = MoodAnalyzer._parse_response("confused\n0.3")
        assert mood == "neutral"
        assert valence == 0.3

    def test_empty_response(self) -> None:
        mood, valence = MoodAnalyzer._parse_response("")
        assert mood == "neutral"
        assert valence == 0.0

    def test_valence_clamped(self) -> None:
        _, valence = MoodAnalyzer._parse_response("happy\n5.0")
        assert valence == 1.0

        _, valence = MoodAnalyzer._parse_response("sad\n-5.0")
        assert valence == -1.0

    def test_mood_with_prefix_stripped(self) -> None:
        mood, _ = MoodAnalyzer._parse_response("- excited")
        assert mood == "excited"

    def test_all_moods_recognized(self) -> None:
        for m in _MOODS:
            mood, _ = MoodAnalyzer._parse_response(m)
            assert mood == m


class TestDetectMood:
    """Validate detect_mood with mocked LLM."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_neutral(self) -> None:
        analyzer = MoodAnalyzer()
        mood, valence = await analyzer.detect_mood("")
        assert mood == "neutral"
        assert valence == 0.0
