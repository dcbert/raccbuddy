"""Relationship scoring and management.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.relationship.manager import RelationshipManager, relationship_manager

__all__ = [
    "RelationshipManager",
    "relationship_manager",
]
