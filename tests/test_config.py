"""Tests for src.core.config."""

import os
from unittest.mock import patch

from src.core.config import Settings


class TestSettings:
    """Validate configuration loading and defaults."""

    def test_default_database_url(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            s = Settings(telegram_bot_token="test-token")
        assert "raccbuddy" in s.database_url
        assert s.database_url.startswith("postgresql+asyncpg://")

    def test_default_ollama_values(self) -> None:
        # Check class-level defaults (not env-overridden values)
        fields = Settings.model_fields
        assert fields["ollama_base_url"].default == "http://localhost:11434"
        assert fields["ollama_model"].default == "llama3.2:3b"
        assert fields["ollama_embed_model"].default == "nomic-embed-text"

    def test_token_limits(self) -> None:
        """Test token limit configuration (uses env/defaults)."""
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings()
        # If .env file exists, values may differ from hardcoded defaults
        # Just verify the attributes exist and are positive
        assert s.max_context_tokens > 0
        assert s.max_summary_words > 0

    def test_default_owner_telegram_id(self) -> None:
        """Test owner_telegram_id configuration (uses env/defaults)."""
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings()
        # If .env file exists, owner_telegram_id may be set
        # Just verify the attribute exists and is an int
        assert isinstance(s.owner_telegram_id, int)

    def test_custom_values_from_env(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "custom-token",
            "OLLAMA_MODEL": "qwen2.5:7b",
            "NUDGE_CHECK_INTERVAL_MINUTES": "30",
            "OWNER_TELEGRAM_ID": "123456789",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings()
        assert s.telegram_bot_token == "custom-token"
        assert s.ollama_model == "qwen2.5:7b"
        assert s.nudge_check_interval_minutes == 30
        assert s.owner_telegram_id == 123456789

    def test_new_v020_settings_have_sensible_defaults(self) -> None:
        """All settings added in the v0.2.0 professionalization pass have correct class defaults."""
        fields = Settings.model_fields
        # Context / memory
        assert fields["max_context_tokens"].default == 30_000
        assert fields["embed_dimensions"].default == 768
        assert fields["memory_recent_messages"].default == 15
        assert fields["memory_semantic_chunks"].default == 6
        assert fields["memory_max_summaries"].default == 3
        assert 0.0 < fields["memory_owner_budget_ratio"].default < 1.0
        assert 0.0 < fields["memory_contact_budget_ratio"].default < 1.0
        assert 0.0 < fields["memory_min_owner_relevance"].default < 1.0
        # Conversation history
        assert fields["memory_conversation_turns"].default == 10
        # DB pool
        assert fields["db_pool_size"].default > 0
        assert fields["db_max_overflow"].default > 0
        assert fields["db_pool_timeout"].default > 0
        # Misc
        assert fields["max_tool_rounds"].default > 0
        assert (
            fields["api_secret_key"].default == ""
        )  # empty = auth disabled by default

    def test_context_tokens_overridable(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "MAX_CONTEXT_TOKENS": "8192",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings()
        assert s.max_context_tokens == 8192

    def test_api_secret_key_overridable(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "API_SECRET_KEY": "supersecret",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings()
        assert s.api_secret_key == "supersecret"

    def test_agentic_settings_defaults(self) -> None:
        """Agentic settings have correct defaults."""
        fields = Settings.model_fields
        assert fields["agentic_enabled"].default is False
        assert fields["checkpointer_backend"].default == "postgres"
        assert fields["max_cycle_tokens"].default == 8192
        assert fields["agentic_cycle_interval_minutes"].default == 30
        assert fields["langfuse_enabled"].default is False
        assert fields["prometheus_enabled"].default is False
        assert fields["prometheus_port"].default == 9090

    def test_agentic_settings_overridable(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "AGENTIC_ENABLED": "true",
            "MAX_CYCLE_TOKENS": "4096",
            "AGENTIC_CYCLE_INTERVAL_MINUTES": "15",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings()
        assert s.agentic_enabled is True
        assert s.max_cycle_tokens == 4096
        assert s.agentic_cycle_interval_minutes == 15
