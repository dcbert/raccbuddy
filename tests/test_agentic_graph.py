"""Tests for src.core.agentic.graph."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.agentic.graph import (
    context_keeper,
    crafter,
    nudge_planner,
    reflector,
    supervisor_router,
)
from src.core.agentic.state import AgenticState, CraftedNudge, NudgeCandidate


class TestSupervisorRouter:
    """Validate the routing function."""

    def test_routes_to_next_node(self) -> None:
        state: AgenticState = {"next_node": "nudge_planner"}
        assert supervisor_router(state) == "nudge_planner"

    def test_routes_to_end_by_default(self) -> None:
        state: AgenticState = {}
        assert supervisor_router(state) == "__end__"


class TestContextKeeper:
    """Validate the ContextKeeper node."""

    @pytest.mark.asyncio
    async def test_returns_error_without_owner_id(self) -> None:
        with patch("src.core.agentic.graph.settings") as mock_settings:
            mock_settings.owner_telegram_id = 0
            result = await context_keeper({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_builds_context_successfully(self) -> None:
        from src.core.memory import ContextBuilder

        with (
            patch("src.core.agentic.graph.settings") as mock_settings,
            patch.object(
                ContextBuilder,
                "build",
                new_callable=AsyncMock,
                return_value="test context string",
            ),
        ):
            mock_settings.owner_telegram_id = 12345
            mock_settings.max_cycle_tokens = 8192
            result = await context_keeper({"owner_id": 12345})

        assert result["context"] == "test context string"
        assert result["next_node"] == "nudge_planner"


class TestNudgePlanner:
    """Validate the NudgePlanner node."""

    @pytest.mark.asyncio
    async def test_returns_end_on_error(self) -> None:
        result = await nudge_planner({"error": "something broke"})
        assert result["next_node"] == "__end__"

    @pytest.mark.asyncio
    async def test_returns_end_when_no_candidates(self) -> None:
        with patch(
            "src.core.agentic.tools.get_available_nudge_skills",
            new_callable=AsyncMock,
            return_value=[
                {
                    "name": "idle",
                    "trigger": "idle",
                    "cooldown_minutes": 120,
                    "on_cooldown": True,
                },
            ],
        ):
            result = await nudge_planner({"context": "test"})
        assert result["candidates"] == []
        assert result["next_node"] == "__end__"


class TestCrafter:
    """Validate the Crafter node."""

    @pytest.mark.asyncio
    async def test_returns_end_on_empty_candidates(self) -> None:
        result = await crafter({"candidates": []})
        assert result["crafted"] == []

    @pytest.mark.asyncio
    async def test_generates_text_for_candidates(self) -> None:
        candidates = [
            NudgeCandidate(
                skill_name="idle",
                trigger="idle_too_long",
                reason="Quiet for 3h",
                prompt="Check in on user",
                context={},
            ),
        ]
        with patch(
            "src.core.llm.interface.generate",
            new_callable=AsyncMock,
            return_value="Hey there, how's it going?",
        ):
            result = await crafter(
                {"candidates": candidates, "context": "some context"}
            )

        assert len(result["crafted"]) == 1
        assert result["crafted"][0]["text"] == "Hey there, how's it going?"
        assert result["next_node"] == "reflector"


class TestReflector:
    """Validate the Reflector node."""

    @pytest.mark.asyncio
    async def test_approves_nudge(self) -> None:
        crafted = [
            CraftedNudge(
                skill_name="idle",
                trigger="idle",
                reason="test",
                text="Hey!",
            ),
        ]
        with patch(
            "src.core.llm.interface.generate",
            new_callable=AsyncMock,
            return_value="APPROVE — relevant and well-timed",
        ):
            result = await reflector({"crafted": crafted, "context": "ctx"})
        assert len(result["approved"]) == 1
        assert len(result["discarded"]) == 0

    @pytest.mark.asyncio
    async def test_discards_nudge(self) -> None:
        crafted = [
            CraftedNudge(
                skill_name="idle",
                trigger="idle",
                reason="test",
                text="Hey!",
            ),
        ]
        with patch(
            "src.core.llm.interface.generate",
            new_callable=AsyncMock,
            return_value="DISCARD — too annoying",
        ):
            result = await reflector({"crafted": crafted, "context": "ctx"})
        assert len(result["approved"]) == 0
        assert len(result["discarded"]) == 1
