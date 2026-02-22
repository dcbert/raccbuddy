"""Tests for src.core.db models and CRUD interface."""

from src.core.db import (
    Base,
    Contact,
    Habit,
    Message,
    Relationship,
    Summary,
    get_all_contacts,
    get_all_habits,
    get_all_owner_ids,
    get_contact,
    get_contact_by_id,
    get_contact_by_name,
    get_contact_name,
    get_contacts_with_messages_since,
    get_idle_contact_ids,
    get_last_message_ts_for_contact,
    get_messages_since,
    get_recent_messages,
    get_relationship,
    get_relevant_summaries,
    get_session,
    get_summary_for_date,
    save_message,
    save_summary,
    upsert_contact,
)


class TestModels:
    """Validate ORM model structure and defaults."""

    def test_message_tablename(self) -> None:
        assert Message.__tablename__ == "messages"

    def test_summary_tablename(self) -> None:
        assert Summary.__tablename__ == "summaries"

    def test_relationship_tablename(self) -> None:
        assert Relationship.__tablename__ == "relationships"

    def test_habit_tablename(self) -> None:
        assert Habit.__tablename__ == "habits"

    def test_contact_tablename(self) -> None:
        assert Contact.__tablename__ == "contacts"

    def test_all_models_inherit_base(self) -> None:
        for model in (Message, Summary, Relationship, Habit, Contact):
            assert issubclass(model, Base)

    def test_relationship_default_score(self) -> None:
        r = Relationship.__table__.columns["score"]
        assert r.default.arg == 50

    def test_habit_columns_exist(self) -> None:
        cols = {c.name for c in Habit.__table__.columns}
        expected = {
            "id",
            "trigger",
            "frequency",
            "correlation",
            "last_detected",
            "suggestion",
        }
        assert expected.issubset(cols)

    def test_summary_has_embedding_column(self) -> None:
        cols = {c.name for c in Summary.__table__.columns}
        assert "embedding" in cols

    def test_message_has_index_on_chat_id(self) -> None:
        chat_col = Message.__table__.columns["chat_id"]
        assert chat_col.index is True

    def test_message_has_from_contact_id_column(self) -> None:
        cols = {c.name for c in Message.__table__.columns}
        assert "from_contact_id" in cols

    def test_message_from_contact_id_is_nullable(self) -> None:
        """Owner direct messages have no contact — from_contact_id is nullable."""
        col = Message.__table__.columns["from_contact_id"]
        assert col.nullable is True

    def test_contact_columns_exist(self) -> None:
        cols = {c.name for c in Contact.__table__.columns}
        expected = {"id", "owner_id", "contact_handle", "contact_name", "platform"}
        assert expected.issubset(cols)

    def test_contact_has_unique_constraint(self) -> None:
        constraints = [
            c.name
            for c in Contact.__table__.constraints
            if hasattr(c, "name") and c.name
        ]
        assert "uq_owner_contact_handle" in constraints


class TestCrudExports:
    """Verify all CRUD functions are importable from the db module."""

    def test_session_factory_callable(self) -> None:
        assert callable(get_session)

    def test_message_crud_exports(self) -> None:
        for fn in (save_message, get_recent_messages, get_messages_since,
                    get_idle_contact_ids, get_last_message_ts_for_contact):
            assert callable(fn)

    def test_contact_crud_exports(self) -> None:
        for fn in (upsert_contact, get_contact, get_contact_by_name,
                    get_contact_name, get_all_contacts, get_all_owner_ids):
            assert callable(fn)

    def test_summary_crud_exports(self) -> None:
        for fn in (save_summary, get_summary_for_date,
                    get_relevant_summaries, get_contacts_with_messages_since):
            assert callable(fn)

    def test_relationship_crud_exports(self) -> None:
        assert callable(get_relationship)

    def test_habit_crud_exports(self) -> None:
        assert callable(get_all_habits)
