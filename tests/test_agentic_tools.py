"""Tests for src.core.agentic.tools."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.agentic.tools import (
    evaluate_nudge_skill,
    get_available_nudge_skills,
    get_tool_schemas_for_agent,
)


class TestAgenticTools:
    """Validate tool/skill wrappers for the agentic layer."""

    def test_get_tool_schemas_returns_list(self) -> None:
        schemas = get_tool_schemas_for_agent()
        assert isinstance(schemas, list)
        assert len(schemas) > 0

    @pytest.mark.asyncio
    async def test_get_available_nudge_skills(self) -> None:
        with patch("src.core.agentic.tools.settings") as mock_settings:
            mock_settings.owner_telegram_id = 12345
            skills = await get_available_nudge_skills()
        assert isinstance(skills, list)
        for skill in skills:
            assert "name" in skill
            assert "on_cooldown" in skill

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_skill(self) -> None:
        with patch("src.core.agentic.tools.settings") as mock_settings:
            mock_settings.owner_telegram_id = 12345
            result = await evaluate_nudge_skill("nonexistent_skill_xyz")
        assert result is None
