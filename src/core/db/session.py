"""Async engine, session factory, and database initialisation."""

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


def _get_engine():
    """Return an engine bound to the current event loop."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    if loop_id not in _engines:
        _engines[loop_id] = create_async_engine(
            settings.database_url, echo=False,
        )
    return _engines[loop_id]


def get_session() -> AsyncSession:
    """Return a new async session bound to the current event loop."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    if loop_id not in _session_factories:
        _session_factories[loop_id] = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False,
        )
    return _session_factories[loop_id]()


async_session = get_session


async def init_db() -> None:
    """Create the pgvector extension and all tables."""
    async with _get_engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
