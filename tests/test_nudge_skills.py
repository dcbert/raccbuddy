"""Tests for nudge_skills and builtin_skills."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.core.skills.nudge import ContactQuietSkill, EveningSkill, HabitSkill, IdleSkill
from src.core.skills.base import (
    BaseNudgeSkill,
    NudgeCheck,
    _is_on_cooldown,
    _mark_fired,
    clear_cooldowns,
    clear_skills,
    get_registered_skills,
    register_skill,
    unregister_skill,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset skill registry and cooldowns between tests."""
    clear_skills()
    clear_cooldowns()
    yield
    clear_skills()
    clear_cooldowns()


# ---------------------------------------------------------------------------
# NudgeCheck
# ---------------------------------------------------------------------------


class TestNudgeCheck:
    def test_defaults(self) -> None:
        c = NudgeCheck(fire=True)
        assert c.fire is True
        assert c.context == {}
        assert c.reason == ""

    def test_with_context(self) -> None:
        c = NudgeCheck(fire=True, context={"name": "Alice"}, reason="test")
        assert c.context["name"] == "Alice"
        assert c.reason == "test"


# ---------------------------------------------------------------------------
# Cooldown tracker
# ---------------------------------------------------------------------------


class TestCooldown:
    def test_not_on_cooldown_initially(self) -> None:
        assert not _is_on_cooldown(1, "idle", 120)

    def test_on_cooldown_after_fire(self) -> None:
        _mark_fired(1, "idle")
        assert _is_on_cooldown(1, "idle", 120)

    def test_cooldown_expires(self) -> None:
        _mark_fired(1, "idle")
        # Should not be on cooldown with 0-minute window
        assert not _is_on_cooldown(1, "idle", 0)

    def test_different_skills_independent(self) -> None:
        _mark_fired(1, "idle")
        assert not _is_on_cooldown(1, "habit", 120)


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------


class _DummySkill(BaseNudgeSkill):
    name = "dummy"  # type: ignore[assignment]
    trigger = "test"  # type: ignore[assignment]
    default_prompt = "Test prompt {who}"  # type: ignore[assignment]

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        return NudgeCheck(fire=True, context={"who": "world"})


class TestRegistry:
    def test_register_and_get(self) -> None:
        register_skill(_DummySkill())
        skills = get_registered_skills()
        assert "dummy" in skills

    def test_unregister(self) -> None:
        register_skill(_DummySkill())
        unregister_skill("dummy")
        assert "dummy" not in get_registered_skills()

    def test_overwrite_warns(self) -> None:
        register_skill(_DummySkill())
        register_skill(_DummySkill())  # should not raise
        assert "dummy" in get_registered_skills()


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_renders_context(self) -> None:
        skill = _DummySkill()
        check = NudgeCheck(fire=True, context={"who": "Alice"})
        assert skill.build_prompt(check) == "Test prompt Alice"

    def test_fallback_on_missing_key(self) -> None:
        skill = _DummySkill()
        check = NudgeCheck(fire=True, context={})
        # Falls back to raw template when key is missing
        assert "{who}" in skill.build_prompt(check)


# ---------------------------------------------------------------------------
# Built-in: IdleSkill
# ---------------------------------------------------------------------------


class TestIdleSkill:
    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.count_messages_since", new_callable=AsyncMock)
    @patch("src.core.skills.nudge.get_idle_contact_ids", new_callable=AsyncMock)
    async def test_fires_when_idle_with_activity(
        self, mock_idle: AsyncMock, mock_count: AsyncMock,
    ) -> None:
        mock_idle.return_value = [(100, datetime.datetime.now())]
        mock_count.return_value = 5
        skill = IdleSkill()
        check = await skill.should_fire(100)
        assert check.fire is True

    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.count_messages_since", new_callable=AsyncMock)
    @patch("src.core.skills.nudge.get_idle_contact_ids", new_callable=AsyncMock)
    async def test_no_fire_when_not_idle(
        self, mock_idle: AsyncMock, mock_count: AsyncMock,
    ) -> None:
        mock_idle.return_value = []  # nobody idle
        skill = IdleSkill()
        check = await skill.should_fire(100)
        assert check.fire is False

    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.count_messages_since", new_callable=AsyncMock)
    @patch("src.core.skills.nudge.get_idle_contact_ids", new_callable=AsyncMock)
    async def test_no_fire_when_idle_but_no_prior_activity(
        self, mock_idle: AsyncMock, mock_count: AsyncMock,
    ) -> None:
        mock_idle.return_value = [(100, datetime.datetime.now())]
        mock_count.return_value = 0  # no prior messages
        skill = IdleSkill()
        check = await skill.should_fire(100)
        assert check.fire is False


# ---------------------------------------------------------------------------
# Built-in: ContactQuietSkill
# ---------------------------------------------------------------------------


class TestContactQuietSkill:
    @pytest.mark.asyncio
    @patch(
        "src.core.skills.nudge.count_messages_from_contact_since",
        new_callable=AsyncMock,
    )
    @patch(
        "src.core.skills.nudge.get_last_message_ts_for_contact",
        new_callable=AsyncMock,
    )
    @patch(
        "src.core.skills.nudge.get_all_contacts_all_platforms",
        new_callable=AsyncMock,
    )
    async def test_fires_for_quiet_contact(
        self, mock_contacts: AsyncMock, mock_last: AsyncMock, mock_count: AsyncMock,
    ) -> None:
        contact = type("C", (), {"id": 42, "contact_name": "Alice"})()
        mock_contacts.return_value = [contact]
        mock_last.return_value = datetime.datetime.now(
            datetime.timezone.utc,
        ) - datetime.timedelta(days=5)
        mock_count.return_value = 3  # was active before
        skill = ContactQuietSkill()
        check = await skill.should_fire(100)
        assert check.fire is True
        assert check.context["contact_name"] == "Alice"

    @pytest.mark.asyncio
    @patch(
        "src.core.skills.nudge.get_all_contacts_all_platforms",
        new_callable=AsyncMock,
    )
    async def test_no_fire_with_no_contacts(
        self, mock_contacts: AsyncMock,
    ) -> None:
        mock_contacts.return_value = []
        skill = ContactQuietSkill()
        check = await skill.should_fire(100)
        assert check.fire is False


# ---------------------------------------------------------------------------
# Built-in: EveningSkill
# ---------------------------------------------------------------------------


class TestEveningSkill:
    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.count_messages_since", new_callable=AsyncMock)
    async def test_fires_in_evening_with_activity(
        self, mock_count: AsyncMock,
    ) -> None:
        mock_count.return_value = 10
        now_evening = datetime.datetime(
            2026, 2, 21, 20, 0, tzinfo=datetime.timezone.utc,
        )
        skill = EveningSkill()
        with patch(
            "src.core.skills.nudge.datetime",
        ) as mock_dt:
            mock_dt.datetime.now.return_value = now_evening
            mock_dt.timedelta = datetime.timedelta
            mock_dt.timezone = datetime.timezone
            check = await skill.should_fire(100)
        assert check.fire is True

    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.count_messages_since", new_callable=AsyncMock)
    async def test_no_fire_during_morning(
        self, mock_count: AsyncMock,
    ) -> None:
        now_morning = datetime.datetime(
            2026, 2, 21, 9, 0, tzinfo=datetime.timezone.utc,
        )
        skill = EveningSkill()
        with patch(
            "src.core.skills.nudge.datetime",
        ) as mock_dt:
            mock_dt.datetime.now.return_value = now_morning
            mock_dt.timedelta = datetime.timedelta
            mock_dt.timezone = datetime.timezone
            check = await skill.should_fire(100)
        assert check.fire is False


# ---------------------------------------------------------------------------
# Built-in: HabitSkill
# ---------------------------------------------------------------------------


class TestHabitSkill:
    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.get_all_habits", new_callable=AsyncMock)
    async def test_fires_when_habits_exist(
        self, mock_habits: AsyncMock,
    ) -> None:
        mock_habits.return_value = [object()]
        skill = HabitSkill()
        check = await skill.should_fire(100)
        assert check.fire is True

    @pytest.mark.asyncio
    @patch("src.core.skills.nudge.get_all_habits", new_callable=AsyncMock)
    async def test_no_fire_when_no_habits(
        self, mock_habits: AsyncMock,
    ) -> None:
        mock_habits.return_value = []
        skill = HabitSkill()
        check = await skill.should_fire(100)
        assert check.fire is False


# ---------------------------------------------------------------------------
# Integration: run_nudge_skills
# ---------------------------------------------------------------------------


class TestRunNudgeSkills:
    @pytest.mark.asyncio
    @patch("src.core.nudges.engine.generate", new_callable=AsyncMock)
    @patch("src.core.nudges.engine.settings")
    async def test_skips_when_no_owner(
        self, mock_settings: AsyncMock, mock_gen: AsyncMock,
    ) -> None:
        mock_settings.owner_telegram_id = 0
        from src.core.nudges import run_nudge_skills
        bot = AsyncMock()
        await run_nudge_skills(bot)
        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.core.nudges.engine.generate", new_callable=AsyncMock)
    @patch("src.core.nudges.engine.settings")
    async def test_sends_nudge_when_skill_fires(
        self, mock_settings: AsyncMock, mock_gen: AsyncMock,
    ) -> None:
        mock_settings.owner_telegram_id = 100
        mock_gen.return_value = "Hey there! 🦝"

        skill = _DummySkill()
        register_skill(skill)

        from src.core.nudges import run_nudge_skills
        bot = AsyncMock()
        await run_nudge_skills(bot)

        mock_gen.assert_called_once()
        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.core.nudges.engine.generate", new_callable=AsyncMock)
    @patch("src.core.nudges.engine.settings")
    async def test_respects_cooldown(
        self, mock_settings: AsyncMock, mock_gen: AsyncMock,
    ) -> None:
        mock_settings.owner_telegram_id = 100
        mock_gen.return_value = "Hey!"

        skill = _DummySkill()
        register_skill(skill)
        _mark_fired(100, "dummy")

        from src.core.nudges import run_nudge_skills
        bot = AsyncMock()
        await run_nudge_skills(bot)

        mock_gen.assert_not_called()
