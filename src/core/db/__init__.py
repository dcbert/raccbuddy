"""Database package — models, session management, and CRUD operations.

Re-exports the full public API so that ``from src.core.db import Contact``
continues to work after the flat-file-to-subpackage migration.
"""

from __future__ import annotations

# CRUD
from src.core.db.crud import (
    count_messages_from_contact_since,
    count_messages_since,
    get_all_contacts,
    get_all_contacts_all_platforms,
    get_all_habits,
    get_all_owner_ids,
    get_contact,
    get_contact_by_id,
    get_contact_by_name,
    get_contact_by_name_any_platform,
    get_contact_name,
    get_contacts_with_messages_since,
    get_idle_contact_ids,
    get_last_message_ts_for_contact,
    get_messages_since,
    get_recent_messages,
    get_recent_messages_for_contact,
    get_relationship,
    get_relevant_summaries,
    get_summary_for_date,
    save_message,
    save_summary,
    upsert_contact,
    upsert_relationship,
)

# Models
from src.core.db.models import (
    Base,
    Contact,
    Habit,
    Message,
    MoodEntry,
    OwnerMemory,
    PersistentContactState,
    PersistentUserState,
    Relationship,
    RelationshipEvent,
    ScheduledJobModel,
    SemanticMemory,
    Summary,
)

# Session / engine
from src.core.db.session import _get_engine, async_session, get_session, init_db

__all__ = [
    # Models
    "Base",
    "Contact",
    "Habit",
    "Message",
    "MoodEntry",
    "OwnerMemory",
    "PersistentContactState",
    "PersistentUserState",
    "Relationship",
    "RelationshipEvent",
    "ScheduledJobModel",
    "SemanticMemory",
    "Summary",
    # Session
    "_get_engine",
    "async_session",
    "get_session",
    "init_db",
    # CRUD
    "count_messages_from_contact_since",
    "count_messages_since",
    "get_all_contacts",
    "get_all_contacts_all_platforms",
    "get_all_habits",
    "get_all_owner_ids",
    "get_contact",
    "get_contact_by_id",
    "get_contact_by_name",
    "get_contact_by_name_any_platform",
    "get_contact_name",
    "get_contacts_with_messages_since",
    "get_idle_contact_ids",
    "get_last_message_ts_for_contact",
    "get_messages_since",
    "get_recent_messages",
    "get_recent_messages_for_contact",
    "get_relationship",
    "get_relevant_summaries",
    "get_summary_for_date",
    "save_message",
    "save_summary",
    "upsert_contact",
    "upsert_relationship",
]
