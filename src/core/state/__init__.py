"""Persistent user and contact state management.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.state.persistent import (
    ContactState,
    UserState,
    flush_all_dirty,
    flush_contact_state,
    flush_state,
    get_all_contact_states,
    get_contact_state,
    get_state,
    load_all_states,
    reset_daily_counts,
    update_contact_state,
    update_state,
)

__all__ = [
    "ContactState",
    "UserState",
    "flush_all_dirty",
    "flush_contact_state",
    "flush_state",
    "get_all_contact_states",
    "get_contact_state",
    "get_state",
    "load_all_states",
    "reset_daily_counts",
    "update_contact_state",
    "update_state",
]
