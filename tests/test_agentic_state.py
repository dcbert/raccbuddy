"""Tests for src.core.agentic.state."""

from __future__ import annotations

from src.core.agentic.state import AgenticState, CraftedNudge, NudgeCandidate


class TestAgenticState:
    """Validate the TypedDict schemas."""

    def test_nudge_candidate_construction(self) -> None:
        nc = NudgeCandidate(
            skill_name="idle",
            trigger="idle_too_long",
            reason="No messages for 3 hours",
            prompt="Hey, you've been quiet!",
            context={"idle_minutes": 180},
        )
        assert nc["skill_name"] == "idle"
        assert nc["context"]["idle_minutes"] == 180

    def test_crafted_nudge_construction(self) -> None:
        cn = CraftedNudge(
            skill_name="idle",
            trigger="idle_too_long",
            reason="No messages for 3 hours",
            text="Hey there, just checking in!",
        )
        assert cn["text"] == "Hey there, just checking in!"

    def test_agentic_state_partial_update(self) -> None:
        """AgenticState allows partial updates (total=False)."""
        state: AgenticState = {"owner_id": 123, "context": "test context"}
        assert state["owner_id"] == 123
        assert "candidates" not in state
