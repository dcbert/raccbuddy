"""Async-safe logging handler that persists WARNING+ records to PostgreSQL.

Usage — attach once in ``bot.py`` after the database is initialised::

    from src.core.db.log_handler import DatabaseLogHandler

    logging.getLogger().addHandler(DatabaseLogHandler())

Every :pyclass:`logging.LogRecord` at WARNING level or above is
captured and written to the ``app_logs`` table via a fire-and-forget
asyncio task.  A :pymod:`contextvars`-based recursion guard prevents
infinite loops when the DB layer itself emits log records.
"""

from __future__ import annotations

import contextvars
import logging
import traceback as _tb

_in_db_handler: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_in_db_handler",
    default=False,
)


class DatabaseLogHandler(logging.Handler):
    """Custom :class:`logging.Handler` that persists records to ``app_logs``.

    Only records at ``WARNING`` level and above are persisted.  The handler
    schedules an asyncio task for each record so that it never blocks the
    calling coroutine.  If no running event loop is available (e.g. during
    early startup or after shutdown), the record is silently dropped.

    Errors inside the handler are swallowed — they must never propagate
    back to the application or break the standard logging pipeline.
    """

    def __init__(self, level: int = logging.WARNING) -> None:
        super().__init__(level)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        """Schedule an async DB write for *record*.

        If the current context is already inside a ``_persist`` call
        (recursion guard), the record is silently skipped to avoid
        infinite loops.
        """
        if _in_db_handler.get(False):
            return

        try:
            import asyncio

            loop = asyncio.get_running_loop()
            loop.create_task(self._persist(record))
        except RuntimeError:
            # No running event loop — nothing we can do.
            pass

    # --------------------------------------------------------------------- #
    # Internal
    # --------------------------------------------------------------------- #

    async def _persist(self, record: logging.LogRecord) -> None:
        """Write a single log record to the ``app_logs`` table."""
        token = _in_db_handler.set(True)
        try:
            from src.core.db.models import AppLog
            from src.core.db.session import get_session

            tb_text: str | None = None
            if record.exc_info and record.exc_info[1] is not None:
                tb_text = "".join(_tb.format_exception(*record.exc_info))

            entry = AppLog(
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                traceback=tb_text,
                module=record.module,
                func_name=record.funcName,
                line_no=record.lineno,
            )

            async with get_session() as session:
                session.add(entry)
                await session.commit()
        except Exception:
            # Never let DB logging break the application.
            pass
        finally:
            _in_db_handler.reset(token)
