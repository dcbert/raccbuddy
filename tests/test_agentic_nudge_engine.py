"""Tests for execute_nudge_from_agent in src.core.nudges.engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.nudges.engine import execute_nudge_from_agent


class TestExecuteNudgeFromAgent:
    """Validate the pre-crafted nudge delivery path."""

    @pytest.mark.asyncio
    async def test_sends_precrafted_text(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()

        await execute_nudge_from_agent(
            bot,
            user_id=12345,
            trigger="idle",
            text="Hey there!",
        )
        bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="Hey there!",
            parse_mode="HTML",
        )

    @pytest.mark.asyncio
    async def test_handles_send_failure(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=Exception("Telegram error"))

        # Should not raise
        await execute_nudge_from_agent(
            bot,
            user_id=12345,
            trigger="idle",
            text="Hey!",
        )
