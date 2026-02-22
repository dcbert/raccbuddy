"""Tests for src.core.state."""

import datetime

from src.core.state import (
    ContactState,
    UserState,
    get_all_contact_states,
    get_contact_state,
    get_state,
    reset_daily_counts,
    update_contact_state,
    update_state,
)


class TestUserState:
    """Validate UserState dataclass defaults."""

    def test_defaults(self) -> None:
        state = UserState(user_id=1)
        assert state.user_id == 1
        assert state.mood == "neutral"
        assert state.last_active is None
        assert state.message_count_today == 0
        assert state.streak_days == 0
        assert state.active_habits == []
        assert state.extra == {}

    def test_mutable_defaults_are_independent(self) -> None:
        a = UserState(user_id=1)
        b = UserState(user_id=2)
        a.active_habits.append("test")
        assert "test" not in b.active_habits


class TestGetState:
    """Validate state retrieval and creation."""

    def test_creates_new_state(self) -> None:
        state = get_state(99999)
        assert state.user_id == 99999

    def test_returns_same_instance(self) -> None:
        a = get_state(88888)
        b = get_state(88888)
        assert a is b


class TestUpdateState:
    """Validate state updates."""

    def test_update_known_fields(self) -> None:
        state = update_state(77777, mood="happy", streak_days=5)
        assert state.mood == "happy"
        assert state.streak_days == 5

    def test_ignores_unknown_fields(self) -> None:
        state = update_state(66666, nonexistent_field="value")
        assert not hasattr(state, "nonexistent_field")

    def test_update_last_active(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        state = update_state(55555, last_active=now)
        assert state.last_active == now


class TestResetDailyCounts:
    """Validate daily counter reset."""

    def test_resets_all_users(self) -> None:
        s1 = get_state(11111)
        s2 = get_state(22222)
        s1.message_count_today = 10
        s2.message_count_today = 20
        reset_daily_counts()
        assert s1.message_count_today == 0
        assert s2.message_count_today == 0


class TestContactState:
    """Validate per-contact state tracking."""

    def test_defaults(self) -> None:
        cs = ContactState(contact_id=100, owner_id=1)
        assert cs.contact_id == 100
        assert cs.owner_id == 1
        assert cs.score == 50
        assert cs.last_message_at is None
        assert cs.message_count == 0
        assert cs.mood == "neutral"

    def test_get_contact_state_creates_new(self) -> None:
        cs = get_contact_state(40001, 50001)
        assert cs.owner_id == 40001
        assert cs.contact_id == 50001

    def test_get_contact_state_returns_same(self) -> None:
        a = get_contact_state(40002, 50002)
        b = get_contact_state(40002, 50002)
        assert a is b

    def test_update_contact_state(self) -> None:
        cs = update_contact_state(40003, 50003, score=75, mood="happy")
        assert cs.score == 75
        assert cs.mood == "happy"

    def test_get_all_contact_states(self) -> None:
        get_contact_state(40004, 50004)
        get_contact_state(40004, 50005)
        get_contact_state(40099, 50006)  # different owner
        states = get_all_contact_states(40004)
        assert len(states) >= 2
        assert all(cs.owner_id == 40004 for cs in states)
