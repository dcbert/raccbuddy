"""Tests for chat_skills, skill_loader, and chat handler /skills integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.skills.chat import (
    BaseChatSkill,
    clear_chat_skills,
    collect_system_prompt_fragments,
    collect_tool_schemas,
    dispatch_skill_tool,
    get_registered_chat_skills,
    register_chat_skill,
    run_post_processors,
    run_pre_processors,
    unregister_chat_skill,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset chat skills between tests."""
    clear_chat_skills()
    yield
    clear_chat_skills()


# ---------------------------------------------------------------------------
# Dummy skills for testing
# ---------------------------------------------------------------------------


class _PromptSkill(BaseChatSkill):
    name = "prompt_test"  # type: ignore[assignment]
    description = "Adds extra prompt."  # type: ignore[assignment]
    system_prompt_fragment = "Be extra helpful."  # type: ignore[assignment]

    async def pre_process(self, message: str, owner_id: int) -> str:
        return message.upper()

    async def post_process(self, reply: str, owner_id: int) -> str:
        return reply + " [processed]"


class _ToolSkill(BaseChatSkill):
    name = "tool_test"  # type: ignore[assignment]
    description = "Provides a test tool."  # type: ignore[assignment]

    @property
    def tool_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    async def execute_tool(self, tool_name, arguments, owner_id):
        return "tool_executed"


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestChatSkillRegistry:
    def test_register_and_get(self) -> None:
        register_chat_skill(_PromptSkill())
        assert "prompt_test" in get_registered_chat_skills()

    def test_unregister(self) -> None:
        register_chat_skill(_PromptSkill())
        unregister_chat_skill("prompt_test")
        assert "prompt_test" not in get_registered_chat_skills()

    def test_overwrite_warns(self) -> None:
        register_chat_skill(_PromptSkill())
        register_chat_skill(_PromptSkill())
        assert len(get_registered_chat_skills()) == 1


# ---------------------------------------------------------------------------
# System prompt fragments
# ---------------------------------------------------------------------------


class TestSystemPromptFragments:
    def test_empty_when_no_skills(self) -> None:
        assert collect_system_prompt_fragments() == ""

    def test_collects_fragments(self) -> None:
        register_chat_skill(_PromptSkill())
        result = collect_system_prompt_fragments()
        assert "Be extra helpful" in result

    def test_skips_none_fragments(self) -> None:
        register_chat_skill(_ToolSkill())  # no fragment
        assert collect_system_prompt_fragments() == ""


# ---------------------------------------------------------------------------
# Tool schemas & dispatch
# ---------------------------------------------------------------------------


class TestToolSchemaCollection:
    def test_empty_when_no_skills(self) -> None:
        assert collect_tool_schemas() == []

    def test_collects_schemas(self) -> None:
        register_chat_skill(_ToolSkill())
        schemas = collect_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "test_tool"


class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_to_skill(self) -> None:
        register_chat_skill(_ToolSkill())
        result = await dispatch_skill_tool("test_tool", {}, 100)
        assert result == "tool_executed"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown(self) -> None:
        result = await dispatch_skill_tool("unknown_tool", {}, 100)
        assert result is None


# ---------------------------------------------------------------------------
# Pre/post processors
# ---------------------------------------------------------------------------


class TestPrePostProcessors:
    @pytest.mark.asyncio
    async def test_pre_process(self) -> None:
        register_chat_skill(_PromptSkill())
        result = await run_pre_processors("hello", 100)
        assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_post_process(self) -> None:
        register_chat_skill(_PromptSkill())
        result = await run_post_processors("reply", 100)
        assert result == "reply [processed]"

    @pytest.mark.asyncio
    async def test_identity_without_skills(self) -> None:
        result = await run_pre_processors("hello", 100)
        assert result == "hello"
        result = await run_post_processors("reply", 100)
        assert result == "reply"


# ---------------------------------------------------------------------------
# Skill loader
# ---------------------------------------------------------------------------


class TestSkillLoader:
    def test_loads_from_directory(self, tmp_path: Path) -> None:
        """Create a temp skill file and verify it gets imported."""
        skill_file = tmp_path / "my_skill.py"
        skill_file.write_text(
            "from src.core.skills.chat import BaseChatSkill, register_chat_skill\n"
            "\n"
            "class TmpSkill(BaseChatSkill):\n"
            "    name = 'tmp_skill'\n"
            "    description = 'Temp skill'\n"
            "\n"
            "register_chat_skill(TmpSkill())\n"
        )

        from src.core.skills.loader import _import_py_files

        count = _import_py_files(tmp_path, "test_skills")
        assert count == 1
        assert "tmp_skill" in get_registered_chat_skills()

    def test_skips_missing_directory(self) -> None:
        from src.core.skills.loader import _import_py_files

        count = _import_py_files(Path("/nonexistent"), "nope")
        assert count == 0

    def test_skips_private_files(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "_private.py").write_text("x = 1")

        from src.core.skills.loader import _import_py_files

        count = _import_py_files(tmp_path, "test_private")
        assert count == 0


# ---------------------------------------------------------------------------
# Integration: _build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_plain_without_skills(self) -> None:
        from src.core.llm import SYSTEM_PROMPT
        from src.handlers.chat import _build_system_prompt

        assert _build_system_prompt() == SYSTEM_PROMPT

    def test_appends_fragments(self) -> None:
        from src.core.llm import SYSTEM_PROMPT
        from src.handlers.chat import _build_system_prompt

        register_chat_skill(_PromptSkill())
        result = _build_system_prompt()
        assert result.startswith(SYSTEM_PROMPT)
        assert "Be extra helpful" in result


# ---------------------------------------------------------------------------
# Integration: get_all_tool_schemas
# ---------------------------------------------------------------------------


class TestGetAllToolSchemas:
    def test_includes_builtins(self) -> None:
        from src.core.tools import TOOL_SCHEMAS, get_all_tool_schemas

        all_schemas = get_all_tool_schemas()
        assert len(all_schemas) >= len(TOOL_SCHEMAS)

    def test_includes_skill_tools(self) -> None:
        from src.core.tools import TOOL_SCHEMAS, get_all_tool_schemas

        register_chat_skill(_ToolSkill())
        all_schemas = get_all_tool_schemas()
        assert len(all_schemas) == len(TOOL_SCHEMAS) + 1
        names = {s["function"]["name"] for s in all_schemas}
        assert "test_tool" in names
