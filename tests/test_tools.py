"""Tests for src.core.tools — tool definitions and executor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tools import TOOL_SCHEMAS, execute_tool, parse_tool_arguments


# Ensure Ollama provider is used during tool tests (avoids .env interference)
@pytest.fixture(autouse=True)
def _force_ollama():
    with patch("src.core.config.settings") as mock_settings:
        mock_settings.llm_provider = "ollama"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_settings.ollama_model = "llama3.2:3b"
        mock_settings.ollama_embed_model = "nomic-embed-text"
        yield


class TestToolSchemas:
    """Validate tool schema definitions."""

    def test_all_schemas_have_function_key(self) -> None:
        for schema in TOOL_SCHEMAS:
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]

    def test_expected_tools_present(self) -> None:
        names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        assert "analyze_contact" in names
        assert "get_insights" in names
        assert "get_relationship_score" in names
        assert "list_contacts" in names
        assert "summarize_contact" in names
        assert "schedule_message" in names

    def test_schedule_message_has_required_params(self) -> None:
        schema = next(
            s for s in TOOL_SCHEMAS
            if s["function"]["name"] == "schedule_message"
        )
        params = schema["function"]["parameters"]
        assert "message" in params["properties"]
        assert "delay_minutes" in params["properties"]
        assert "message" in params["required"]
        assert "delay_minutes" in params["required"]


class TestParseToolArguments:
    """Validate argument parsing."""

    def test_parse_dict_passthrough(self) -> None:
        args = {"name": "Giulia"}
        assert parse_tool_arguments(args) == args

    def test_parse_json_string(self) -> None:
        result = parse_tool_arguments('{"name": "Giulia"}')
        assert result == {"name": "Giulia"}

    def test_parse_invalid_json_returns_empty(self) -> None:
        assert parse_tool_arguments("not json") == {}

    def test_parse_none_returns_empty(self) -> None:
        assert parse_tool_arguments(None) == {}  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestExecuteTool:
    """Validate tool execution."""

    async def test_unknown_tool_returns_error(self) -> None:
        result = await execute_tool("nonexistent_tool", {}, owner_id=123)
        assert "Error: unknown tool" in result

    @patch("src.core.db.crud.get_all_contacts_all_platforms")
    async def test_list_contacts_empty(
        self, mock_get_contacts: AsyncMock,
    ) -> None:
        mock_get_contacts.return_value = []
        result = await execute_tool("list_contacts", {}, owner_id=123)
        assert "No contacts found" in result

    @patch("src.core.db.crud.get_all_contacts_all_platforms")
    async def test_list_contacts_with_data(
        self, mock_get_contacts: AsyncMock,
    ) -> None:
        contact = MagicMock()
        contact.contact_name = "Giulia"
        contact.platform = "telegram"
        mock_get_contacts.return_value = [contact]

        result = await execute_tool("list_contacts", {}, owner_id=123)
        assert "Giulia" in result
        assert "telegram" in result

    @patch("src.core.db.crud.get_relationship")
    @patch("src.core.db.crud.get_contact_by_name_any_platform")
    async def test_get_relationship_score(
        self,
        mock_get_contact: AsyncMock,
        mock_get_rel: AsyncMock,
    ) -> None:
        contact = MagicMock()
        contact.id = 456
        mock_get_contact.return_value = contact

        rel = MagicMock()
        rel.score = 85
        mock_get_rel.return_value = rel

        result = await execute_tool(
            "get_relationship_score",
            {"contact_name": "Giulia"},
            owner_id=123,
        )
        assert "85" in result
        assert "Giulia" in result

    @patch("src.core.db.crud.get_contact_by_name_any_platform")
    async def test_analyze_contact_not_found(
        self, mock_get_contact: AsyncMock,
    ) -> None:
        mock_get_contact.return_value = None
        result = await execute_tool(
            "analyze_contact",
            {"contact_name": "Unknown"},
            owner_id=123,
        )
        assert "not found" in result

    @patch("src.core.scheduled.jobs.schedule_llm_job")
    async def test_schedule_message(
        self, mock_schedule: AsyncMock,
    ) -> None:
        mock_schedule.return_value = "abc123"
        result = await execute_tool(
            "schedule_message",
            {"message": "Hey!", "delay_minutes": 60, "reason": "reminder"},
            owner_id=123,
        )
        assert "abc123" in result
        assert "1h" in result
