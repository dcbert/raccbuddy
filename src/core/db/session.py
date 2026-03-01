"""Async engine, session factory, and database initialisation.

Engine configuration
--------------------
The engine is created lazily on first use and keyed by the running
asyncio event loop.  This allows the Telegram bot (main loop) and
optional background threads to each have an independent connection pool
without contention.

Connection pool settings are driven by config so they can be tuned for
production without changing code:
- ``DB_POOL_SIZE``      — steady-state connections (default 10)
- ``DB_MAX_OVERFLOW``   — burst connections above pool_size (default 20)
- ``DB_POOL_TIMEOUT``   — seconds to wait for a connection (default 30)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.core.db.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Loop-aware engine / session factory
# ---------------------------------------------------------------------------

_engines: dict[int, Any] = {}
_session_factories: dict[int, async_sessionmaker[AsyncSession]] = {}


def _get_engine() -> Any:
    """Return an async engine bound to the current event loop.

    Engines are cached per event loop so they are not shared across
    threads (asyncpg pools are not thread-safe).

    Returns:
        The ``AsyncEngine`` for the current event loop.
    """
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    if loop_id not in _engines:
        _engines[loop_id] = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,  # Drop stale connections before use
        )
        logger.debug(
            "Created async DB engine (loop=%d, pool_size=%d, max_overflow=%d)",
            loop_id,
            settings.db_pool_size,
            settings.db_max_overflow,
        )
    return _engines[loop_id]


def get_session() -> AsyncSession:
    """Return a new async session bound to the current event loop.

    Usage::

        async with get_session() as session:
            result = await session.execute(stmt)

    Returns:
        A fresh ``AsyncSession`` from the loop-local session factory.
    """
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    if loop_id not in _session_factories:
        _session_factories[loop_id] = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factories[loop_id]()


# Backward-compatible alias
async_session = get_session


async def init_db() -> None:
    """Create the pgvector extension and all ORM tables.

    Safe to call on every startup — ``CREATE EXTENSION IF NOT EXISTS`` and
    ``create_all`` are idempotent.
    """
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialised (pgvector extension + all tables ready)")
