"""Tests for src.handlers.start."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handlers.start import start_handler


@pytest.mark.asyncio
class TestStartHandler:
    """Validate /start command behaviour."""

    async def test_sends_welcome_with_user_id(self) -> None:
        """When no owner is configured, show Telegram ID in welcome."""
        from src.core.config import Settings

        with patch("src.handlers.start.settings", Settings(telegram_bot_token="t", owner_telegram_id=0)):
            update = MagicMock()
            update.effective_user.first_name = "Davide"
            update.effective_user.id = 123
            update.message.reply_text = AsyncMock()

            await start_handler(update, MagicMock())

            update.message.reply_text.assert_called_once()
            text = update.message.reply_text.call_args[0][0]
            assert "Davide" in text
            assert "123" in text
            assert "OWNER_TELEGRAM_ID" in text

    async def test_configured_owner_gets_short_welcome(self) -> None:
        from src.core.config import Settings

        with patch("src.handlers.start.settings", Settings(telegram_bot_token="t", owner_telegram_id=123)):
            update = MagicMock()
            update.effective_user.first_name = "Davide"
            update.effective_user.id = 123
            update.message.reply_text = AsyncMock()

            await start_handler(update, MagicMock())

            text = update.message.reply_text.call_args[0][0]
            assert "Welcome back" in text

    async def test_non_owner_rejected(self) -> None:
        from src.core.config import Settings

        with patch("src.handlers.start.settings", Settings(telegram_bot_token="t", owner_telegram_id=123)):
            update = MagicMock()
            update.effective_user.first_name = "Stranger"
            update.effective_user.id = 999
            update.message.reply_text = AsyncMock()

            await start_handler(update, MagicMock())

            text = update.message.reply_text.call_args[0][0]
            assert "denied" in text.lower() or "private" in text.lower()

    async def test_uses_friend_fallback(self) -> None:
        from src.core.config import Settings

        with patch("src.handlers.start.settings", Settings(telegram_bot_token="t", owner_telegram_id=0)):
            update = MagicMock()
            update.effective_user.first_name = None
            update.effective_user.id = 456
            update.message.reply_text = AsyncMock()

            await start_handler(update, MagicMock())

            text = update.message.reply_text.call_args[0][0]
            assert "friend" in text

    async def test_no_user_returns_early(self) -> None:
        update = MagicMock()
        update.effective_user = None
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        await start_handler(update, MagicMock())

        update.message.reply_text.assert_not_called()

    async def test_no_message_returns_early(self) -> None:
        update = MagicMock()
        update.effective_user = MagicMock()
        update.message = None

        await start_handler(update, MagicMock())
