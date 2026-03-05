"""Tests for the AppLog model and DatabaseLogHandler."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.db.log_handler import DatabaseLogHandler, _in_db_handler
from src.core.db.models import AppLog

# ===========================================================================
# AppLog model
# ===========================================================================


class TestAppLogModel:
    """Validate the AppLog ORM model definition."""

    def test_tablename(self) -> None:
        assert AppLog.__tablename__ == "app_logs"

    def test_columns_exist(self) -> None:
        col_names = {c.name for c in AppLog.__table__.columns}
        expected = {
            "id",
            "level",
            "logger_name",
            "message",
            "traceback",
            "module",
            "func_name",
            "line_no",
            "created_at",
        }
        assert expected.issubset(col_names)

    def test_level_not_nullable(self) -> None:
        col = AppLog.__table__.c.level
        assert col.nullable is False

    def test_level_indexed(self) -> None:
        col = AppLog.__table__.c.level
        assert col.index is True

    def test_logger_name_not_nullable(self) -> None:
        col = AppLog.__table__.c.logger_name
        assert col.nullable is False

    def test_logger_name_indexed(self) -> None:
        col = AppLog.__table__.c.logger_name
        assert col.index is True

    def test_message_not_nullable(self) -> None:
        col = AppLog.__table__.c.message
        assert col.nullable is False

    def test_traceback_nullable(self) -> None:
        col = AppLog.__table__.c.traceback
        assert col.nullable is True

    def test_module_nullable(self) -> None:
        col = AppLog.__table__.c.module
        assert col.nullable is True

    def test_func_name_nullable(self) -> None:
        col = AppLog.__table__.c.func_name
        assert col.nullable is True

    def test_line_no_nullable(self) -> None:
        col = AppLog.__table__.c.line_no
        assert col.nullable is True


# ===========================================================================
# DatabaseLogHandler
# ===========================================================================


def _mock_session():
    """Return an async-context-manager-compatible mock session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    return session


class TestDatabaseLogHandler:
    """Validate the handler constructor and level threshold."""

    def test_default_level_is_warning(self) -> None:
        handler = DatabaseLogHandler()
        assert handler.level == logging.WARNING

    def test_custom_level(self) -> None:
        handler = DatabaseLogHandler(level=logging.ERROR)
        assert handler.level == logging.ERROR


@pytest.mark.asyncio
class TestDatabaseLogHandlerPersist:
    """Validate _persist writes correct AppLog entries to DB."""

    @patch("src.core.db.session.get_session")
    async def test_persists_warning_record(self, mock_get_session: MagicMock) -> None:
        session = _mock_session()
        mock_get_session.return_value = session

        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="test_module.py",
            lineno=42,
            msg="something went wrong",
            args=(),
            exc_info=None,
        )

        await handler._persist(record)

        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert isinstance(entry, AppLog)
        assert entry.level == "WARNING"
        assert entry.logger_name == "test.logger"
        assert entry.message == "something went wrong"
        assert entry.traceback is None
        assert entry.module == "test_module"
        assert entry.func_name is None  # LogRecord sets funcName only from stack
        assert entry.line_no == 42
        session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_persists_error_with_traceback(
        self, mock_get_session: MagicMock
    ) -> None:
        session = _mock_session()
        mock_get_session.return_value = session

        handler = DatabaseLogHandler()

        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="my.module",
            level=logging.ERROR,
            pathname="my_module.py",
            lineno=99,
            msg="an error occurred",
            args=(),
            exc_info=exc_info,
        )

        await handler._persist(record)

        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert entry.level == "ERROR"
        assert entry.traceback is not None
        assert "ValueError: boom" in entry.traceback

    @patch("src.core.db.session.get_session")
    async def test_db_failure_does_not_propagate(
        self, mock_get_session: MagicMock
    ) -> None:
        """DB errors inside _persist are silently swallowed."""
        mock_get_session.side_effect = RuntimeError("DB is down")

        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="x",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="fail",
            args=(),
            exc_info=None,
        )

        # Should not raise
        await handler._persist(record)

    @patch("src.core.db.session.get_session")
    async def test_commit_failure_does_not_propagate(
        self, mock_get_session: MagicMock
    ) -> None:
        """Commit failure is silently swallowed."""
        session = _mock_session()
        session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
        mock_get_session.return_value = session

        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="x",
            level=logging.WARNING,
            pathname="x.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )

        # Should not raise
        await handler._persist(record)


# ===========================================================================
# Recursion guard
# ===========================================================================


class TestRecursionGuardSync:
    """Verify the contextvars-based recursion guard (sync tests)."""

    def test_emit_skips_when_guard_is_set(self) -> None:
        """When _in_db_handler is already True, emit() does nothing."""
        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="x",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="recursive",
            args=(),
            exc_info=None,
        )

        token = _in_db_handler.set(True)
        try:
            # Should return immediately without scheduling a task
            handler.emit(record)
        finally:
            _in_db_handler.reset(token)


@pytest.mark.asyncio
class TestRecursionGuardAsync:
    """Verify the contextvars-based recursion guard (async tests)."""

    @patch("src.core.db.session.get_session")
    async def test_guard_is_reset_after_persist(
        self, mock_get_session: MagicMock
    ) -> None:
        """After _persist completes, the guard is reset to False."""
        session = _mock_session()
        mock_get_session.return_value = session

        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="x",
            level=logging.WARNING,
            pathname="x.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )

        assert _in_db_handler.get(False) is False
        await handler._persist(record)
        assert _in_db_handler.get(False) is False

    @patch("src.core.db.session.get_session")
    async def test_guard_is_reset_after_persist_failure(
        self, mock_get_session: MagicMock
    ) -> None:
        """Even when _persist fails, the guard is reset."""
        mock_get_session.side_effect = RuntimeError("DB down")

        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="x",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="fail",
            args=(),
            exc_info=None,
        )

        await handler._persist(record)
        assert _in_db_handler.get(False) is False


# ===========================================================================
# emit() integration — schedules async tasks
# ===========================================================================


@pytest.mark.asyncio
class TestEmitIntegration:
    """Verify that emit() schedules _persist as an asyncio task."""

    @patch("src.core.db.session.get_session")
    async def test_emit_schedules_task(self, mock_get_session: MagicMock) -> None:
        """emit() called inside a running loop schedules a _persist task."""
        session = _mock_session()
        mock_get_session.return_value = session

        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="integration.test",
            level=logging.WARNING,
            pathname="integ.py",
            lineno=10,
            msg="integration test",
            args=(),
            exc_info=None,
        )

        handler.emit(record)
        # Allow the scheduled task to run
        await asyncio.sleep(0)

        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert isinstance(entry, AppLog)
        assert entry.logger_name == "integration.test"


class TestEmitNoLoop:
    """Tests for emit() behaviour when no event loop is running."""

    def test_emit_without_loop_does_not_raise(self) -> None:
        """emit() called outside an event loop silently does nothing."""
        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="no.loop",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="no loop",
            args=(),
            exc_info=None,
        )

        # Running outside of async — should not raise
        # (We need to ensure there's no running loop; this test class
        # itself runs under an event loop, so we patch asyncio.)
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            handler.emit(record)
