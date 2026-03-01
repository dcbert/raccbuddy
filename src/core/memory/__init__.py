"""Four-layer memory system for RaccBuddy.

Re-exports the full public API so that ``from src.core.memory import memory``
and similar imports continue to work.

The ``context_builder`` singleton is the canonical entry-point for
assembling prompt context before any LLM call.
"""

from __future__ import annotations

from src.core.db.models import OwnerMemory, SemanticMemory
from src.core.memory.base import (
    CHARS_PER_TOKEN,
    OWNER_MEMORY_DEFAULT_IMPORTANCE,
    OWNER_MEMORY_PRUNE_FLOOR,
    Document,
    PostgresMemory,
    build_context_for_contact,
    memory,
)
from src.core.memory.context_builder import ContextBuilder, context_builder

__all__ = [
    "CHARS_PER_TOKEN",
    "ContextBuilder",
    "Document",
    "OWNER_MEMORY_DEFAULT_IMPORTANCE",
    "OWNER_MEMORY_PRUNE_FLOOR",
    "OwnerMemory",
    "PostgresMemory",
    "SemanticMemory",
    "build_context_for_contact",
    "context_builder",
    "memory",
]
