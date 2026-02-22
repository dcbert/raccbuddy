"""Persistent user and contact state backed by PostgreSQL.

State survives bot restarts.  An in-memory write-through cache keeps the
public API synchronous (``get_state`` / ``get_contact_state``).  Writes
are flushed to the database asynchronously via ``flush_state`` /
``flush_contact_state``.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass wrappers (keep the same public shape as before)
# ---------------------------------------------------------------------------


@dataclass
class UserState:
    """Tracks the current session state for a single user."""

    user_id: int
    mood: str = "neutral"
    last_active: datetime.datetime | None = None
    message_count_today: int = 0
    streak_days: int = 0
    active_habits: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    _dirty: bool = field(default=False, repr=False)


@dataclass
class ContactState:
    """Tracks per-contact relationship state."""

    contact_id: int
    owner_id: int
    score: int = 50
    last_message_at: datetime.datetime | None = None
    message_count: int = 0
    mood: str = "neutral"
    _dirty: bool = field(default=False, repr=False)


# ---------------------------------------------------------------------------
# In-memory cache (write-through to DB)
# ---------------------------------------------------------------------------

_states: dict[int, UserState] = {}
_contact_states: dict[tuple[int, int], ContactState] = {}


# ---------------------------------------------------------------------------
# Synchronous getters (cache-first, same public API)
# ---------------------------------------------------------------------------


def get_state(user_id: int) -> UserState:
    """Get or create the state object for a user (from cache)."""
    if user_id not in _states:
        _states[user_id] = UserState(user_id=user_id)
    return _states[user_id]


def update_state(user_id: int, **kwargs: Any) -> UserState:
    """Update specific fields on a user's state."""
    state = get_state(user_id)
    for key, value in kwargs.items():
        if hasattr(state, key) and not key.startswith("_"):
            setattr(state, key, value)
    state._dirty = True
    return state


def reset_daily_counts() -> None:
    """Reset daily counters for all tracked users."""
    for state in _states.values():
        state.message_count_today = 0
        state._dirty = True


def get_contact_state(owner_id: int, contact_id: int) -> ContactState:
    """Get or create the per-contact state (from cache)."""
    key = (owner_id, contact_id)
    if key not in _contact_states:
        _contact_states[key] = ContactState(contact_id=contact_id, owner_id=owner_id)
    return _contact_states[key]


def update_contact_state(owner_id: int, contact_id: int, **kwargs: Any) -> ContactState:
    """Update specific fields on a contact's state."""
    state = get_contact_state(owner_id, contact_id)
    for key, value in kwargs.items():
        if hasattr(state, key) and not key.startswith("_"):
            setattr(state, key, value)
    state._dirty = True
    return state


def get_all_contact_states(owner_id: int) -> list[ContactState]:
    """Return all contact states for a given owner."""
    return [cs for (oid, _), cs in _contact_states.items() if oid == owner_id]


# ---------------------------------------------------------------------------
# Async DB persistence — load / flush
# ---------------------------------------------------------------------------


async def load_all_states() -> None:
    """Load all persistent states from the database into cache at startup."""
    from src.core.db.models import PersistentContactState, PersistentUserState
    from src.core.db.session import get_session

    try:
        async with get_session() as session:
            result = await session.execute(select(PersistentUserState))
            for row in result.scalars().all():
                us = UserState(
                    user_id=row.user_id,
                    mood=row.mood,
                    last_active=row.last_active,
                    message_count_today=row.message_count_today,
                    streak_days=row.streak_days,
                    extra=row.extra or {},
                )
                _states[row.user_id] = us

            result = await session.execute(select(PersistentContactState))
            for row in result.scalars().all():
                cs = ContactState(
                    contact_id=row.contact_id,
                    owner_id=row.owner_id,
                    score=row.score,
                    last_message_at=row.last_message_at,
                    message_count=row.message_count,
                    mood=row.mood,
                )
                _contact_states[(row.owner_id, row.contact_id)] = cs

        logger.info(
            "Loaded %d user states, %d contact states from DB",
            len(_states), len(_contact_states),
        )
    except Exception:
        logger.warning("Failed to load persistent states — starting fresh", exc_info=True)


async def flush_state(user_id: int) -> None:
    """Persist a single user state to the database."""
    from src.core.db.models import PersistentUserState
    from src.core.db.session import get_session

    state = _states.get(user_id)
    if state is None:
        return

    try:
        async with get_session() as session:
            result = await session.execute(
                select(PersistentUserState).where(
                    PersistentUserState.user_id == user_id,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.mood = state.mood
                existing.last_active = state.last_active
                existing.message_count_today = state.message_count_today
                existing.streak_days = state.streak_days
                existing.extra = state.extra
            else:
                session.add(PersistentUserState(
                    user_id=state.user_id,
                    mood=state.mood,
                    last_active=state.last_active,
                    message_count_today=state.message_count_today,
                    streak_days=state.streak_days,
                    extra=state.extra,
                ))
            await session.commit()
        state._dirty = False
    except Exception:
        logger.warning("Failed to flush user state for %d", user_id, exc_info=True)


async def flush_contact_state(owner_id: int, contact_id: int) -> None:
    """Persist a single contact state to the database."""
    from src.core.db.models import PersistentContactState
    from src.core.db.session import get_session

    key = (owner_id, contact_id)
    state = _contact_states.get(key)
    if state is None:
        return

    try:
        async with get_session() as session:
            result = await session.execute(
                select(PersistentContactState).where(
                    PersistentContactState.owner_id == owner_id,
                    PersistentContactState.contact_id == contact_id,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.score = state.score
                existing.last_message_at = state.last_message_at
                existing.message_count = state.message_count
                existing.mood = state.mood
            else:
                session.add(PersistentContactState(
                    owner_id=state.owner_id,
                    contact_id=state.contact_id,
                    score=state.score,
                    last_message_at=state.last_message_at,
                    message_count=state.message_count,
                    mood=state.mood,
                ))
            await session.commit()
        state._dirty = False
    except Exception:
        logger.warning(
            "Failed to flush contact state for owner=%d contact=%d",
            owner_id, contact_id, exc_info=True,
        )


async def flush_all_dirty() -> None:
    """Flush all dirty states to the database (call periodically)."""
    for uid, state in _states.items():
        if state._dirty:
            await flush_state(uid)

    for (oid, cid), state in _contact_states.items():
        if state._dirty:
            await flush_contact_state(oid, cid)
