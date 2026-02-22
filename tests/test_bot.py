"""Tests for src.bot entry point."""

from unittest.mock import MagicMock, patch

from src.bot import main


class TestMain:
    """Validate bot startup logic."""

    @patch("src.bot.settings")
    def test_aborts_without_token(self, mock_settings: MagicMock) -> None:
        mock_settings.telegram_bot_token = ""
        # Should return without raising
        main()

    @patch("src.bot.Application")
    @patch("src.bot.settings")
    def test_starts_with_token(
        self, mock_settings: MagicMock, mock_app_cls: MagicMock
    ) -> None:
        mock_settings.telegram_bot_token = "test-token-123"
        mock_settings.nudge_check_interval_minutes = 60

        mock_app = MagicMock()
        mock_app_cls.builder.return_value.token.return_value.post_init.return_value.build.return_value = (
            mock_app
        )

        main()

        # Should register at least 6 handlers (start, name, analyze, insights, relationship, text)
        assert mock_app.add_handler.call_count >= 6
        mock_app.run_polling.assert_called_once()
