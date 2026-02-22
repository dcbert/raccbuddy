"""Four-layer memory system for RaccBuddy.

Re-exports the full public API so that ``from src.core.memory import memory``
and similar imports continue to work.
"""

from __future__ import annotations

from src.core.db.models import OwnerMemory, SemanticMemory
from src.core.memory.base import (
    CHARS_PER_TOKEN,
    EMBED_DIMENSIONS,
    MAX_CONTEXT_CHARS,
    MAX_RECENT_MESSAGES,
    MAX_SUMMARIES,
    OWNER_MEMORY_DEFAULT_IMPORTANCE,
    OWNER_MEMORY_PRUNE_FLOOR,
    Document,
    PostgresMemory,
    build_context_for_contact,
    memory,
)

__all__ = [
    "CHARS_PER_TOKEN",
    "Document",
    "EMBED_DIMENSIONS",
    "MAX_CONTEXT_CHARS",
    "MAX_RECENT_MESSAGES",
    "MAX_SUMMARIES",
    "OWNER_MEMORY_DEFAULT_IMPORTANCE",
    "OWNER_MEMORY_PRUNE_FLOOR",
    "OwnerMemory",
    "PostgresMemory",
    "SemanticMemory",
    "build_context_for_contact",
    "memory",
]
