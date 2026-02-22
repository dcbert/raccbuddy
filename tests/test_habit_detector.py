"""Tests for src.core.habit_detector."""

from __future__ import annotations

from src.core.habits import HabitDetector


class TestParseLLMHabits:
    """Validate LLM output parsing."""

    def test_parses_valid_habit_lines(self) -> None:
        raw = (
            "HABIT: Always mentions gym on Mondays | SUGGESTION: Schedule workouts\n"
            "HABIT: Vents about work on Wednesdays | SUGGESTION: Prepare destress tips\n"
        )
        result = HabitDetector._parse_llm_habits(raw)
        assert len(result) == 2
        assert result[0]["trigger"] == "Always mentions gym on Mondays"
        assert result[0]["suggestion"] == "Schedule workouts"

    def test_skips_non_habit_lines(self) -> None:
        raw = "Some preamble text\nHABIT: Real habit | SUGGESTION: Tip\nAnother line"
        result = HabitDetector._parse_llm_habits(raw)
        assert len(result) == 1

    def test_handles_missing_suggestion(self) -> None:
        raw = "HABIT: Checks phone before bed"
        result = HabitDetector._parse_llm_habits(raw)
        assert len(result) == 1
        assert result[0]["suggestion"] is None or result[0]["suggestion"] == ""

    def test_empty_input(self) -> None:
        assert HabitDetector._parse_llm_habits("") == []

    def test_truncates_long_trigger(self) -> None:
        long_habit = "HABIT: " + "x" * 300 + " | SUGGESTION: tip"
        result = HabitDetector._parse_llm_habits(long_habit)
        assert len(result[0]["trigger"]) <= 200
