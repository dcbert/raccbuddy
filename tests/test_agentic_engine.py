"""Tests for src.core.agentic.engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agentic.engine import _deliver_nudge, run_agentic_cycle


class TestRunAgenticCycle:
    """Validate the cycle orchestrator."""

    @pytest.mark.asyncio
    async def test_skips_when_graph_not_initialized(self) -> None:
        """Should log error and return without crashing."""
        with patch("src.core.agentic.engine._compiled_graph", None):
            bot = MagicMock()
            await run_agentic_cycle(bot)
            bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_owner_id(self) -> None:
        with (
            patch("src.core.agentic.engine._compiled_graph", MagicMock()),
            patch("src.core.agentic.engine.settings") as mock_settings,
        ):
            mock_settings.owner_telegram_id = 0
            bot = MagicMock()
            await run_agentic_cycle(bot)


class TestDeliverNudge:
    """Validate nudge delivery from the agentic engine."""

    @pytest.mark.asyncio
    async def test_delivers_nudge_successfully(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()

        nudge = {
            "skill_name": "idle",
            "trigger": "idle_too_long",
            "text": "Hey, how's it going?",
        }

        with (
            patch(
                "src.core.nudges.engine.execute_nudge_from_agent",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch("src.core.skills.base._mark_fired") as mock_mark,
        ):
            await _deliver_nudge(bot, 12345, nudge)
            mock_exec.assert_called_once_with(
                bot,
                12345,
                trigger="idle_too_long",
                text="Hey, how's it going?",
            )
            mock_mark.assert_called_once_with(12345, "idle")

    @pytest.mark.asyncio
    async def test_handles_delivery_failure_gracefully(self) -> None:
        bot = MagicMock()
        nudge = {
            "skill_name": "idle",
            "trigger": "idle_too_long",
            "text": "Hey!",
        }

        with patch(
            "src.core.nudges.engine.execute_nudge_from_agent",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            # Should not raise
            await _deliver_nudge(bot, 12345, nudge)
