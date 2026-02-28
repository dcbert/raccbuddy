"""Checkpointer registry for LangGraph state persistence.

Provides a pluggable backend registry so users can swap between
PostgreSQL (default) and SQLite checkpointers, or register custom ones.

URL conversion
--------------
``langgraph-checkpoint-postgres`` uses ``psycopg3`` (not ``asyncpg``),
so we convert ``postgresql+asyncpg://`` → ``postgresql://`` here.
This conversion is localized — no existing DB code is touched.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from src.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseCheckpointer(ABC):
    """Abstract checkpointer that wraps a LangGraph-compatible saver."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique backend name (e.g. ``"postgres"``, ``"sqlite"``)."""

    @abstractmethod
    async def setup(self) -> None:
        """Create tables / initialize the backend."""

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up connections on shutdown."""

    @abstractmethod
    def get_saver(self) -> Any:
        """Return the underlying LangGraph ``BaseCheckpointSaver``."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, BaseCheckpointer] = {}


def register_checkpointer(cp: BaseCheckpointer) -> None:
    """Register a checkpointer backend.

    Args:
        cp: The checkpointer instance to register.
    """
    _registry[cp.name] = cp
    logger.info("Checkpointer registered: %s", cp.name)


def get_checkpointer(name: str | None = None) -> BaseCheckpointer:
    """Return the checkpointer for *name* (default: config setting).

    Args:
        name: Backend name.  Falls back to ``settings.checkpointer_backend``.

    Returns:
        The registered checkpointer.

    Raises:
        KeyError: If no checkpointer with that name is registered.
    """
    key = name or settings.checkpointer_backend
    if key not in _registry:
        raise KeyError(
            f"Checkpointer '{key}' not registered. "
            f"Available: {list(_registry.keys())}"
        )
    return _registry[key]


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _asyncpg_to_psycopg(url: str) -> str:
    """Convert a SQLAlchemy asyncpg URL to a plain psycopg3-compatible URL.

    ``postgresql+asyncpg://user:pass@host/db``
      → ``postgresql://user:pass@host/db``
    """
    return url.replace("postgresql+asyncpg://", "postgresql://")


# ---------------------------------------------------------------------------
# Built-in: PostgreSQL checkpointer
# ---------------------------------------------------------------------------


class PostgresCheckpointer(BaseCheckpointer):
    """PostgreSQL-backed checkpointer using ``langgraph-checkpoint-postgres``."""

    def __init__(self) -> None:
        self._saver: Any = None

    @property
    def name(self) -> str:
        return "postgres"

    async def setup(self) -> None:
        """Create checkpoint tables via ``AsyncPostgresSaver.setup()``.

        Note: This creates a separate psycopg3 connection pool (not the
        SQLAlchemy asyncpg pool from ``db/session.py``) because
        ``langgraph-checkpoint-postgres`` requires psycopg3.
        """
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        conn_string = _asyncpg_to_psycopg(settings.database_url)
        # Use a small pool — checkpoint writes are infrequent
        self._saver = AsyncPostgresSaver.from_conn_string(
            conn_string,
            pool_size=2,
        )
        await self._saver.setup()
        logger.info(
            "PostgresCheckpointer: tables ready (separate psycopg3 pool, size=2)"
        )

    async def teardown(self) -> None:
        """Close the underlying connection pool."""
        if self._saver is not None:
            try:
                await self._saver.conn.close()
            except Exception:
                logger.warning("PostgresCheckpointer teardown error", exc_info=True)
            self._saver = None

    def get_saver(self) -> Any:
        if self._saver is None:
            raise RuntimeError("PostgresCheckpointer not set up — call setup() first")
        return self._saver


# ---------------------------------------------------------------------------
# Built-in: SQLite checkpointer (lightweight / dev)
# ---------------------------------------------------------------------------


class SQLiteCheckpointer(BaseCheckpointer):
    """SQLite-backed checkpointer using ``langgraph-checkpoint-sqlite``."""

    def __init__(self, path: str = "agentic_checkpoints.db") -> None:
        self._path = path
        self._saver: Any = None

    @property
    def name(self) -> str:
        return "sqlite"

    async def setup(self) -> None:
        """Create the SQLite checkpoint database."""
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        self._saver = AsyncSqliteSaver.from_conn_string(self._path)
        await self._saver.setup()
        logger.info("SQLiteCheckpointer: DB ready at %s", self._path)

    async def teardown(self) -> None:
        """Close the underlying connection."""
        if self._saver is not None:
            try:
                await self._saver.conn.close()
            except Exception:
                logger.warning("SQLiteCheckpointer teardown error", exc_info=True)
            self._saver = None

    def get_saver(self) -> Any:
        if self._saver is None:
            raise RuntimeError("SQLiteCheckpointer not set up — call setup() first")
        return self._saver


# ---------------------------------------------------------------------------
# Auto-register built-in backends
# ---------------------------------------------------------------------------

register_checkpointer(PostgresCheckpointer())
register_checkpointer(SQLiteCheckpointer())
