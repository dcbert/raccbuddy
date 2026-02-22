"""Tests for src.core.relationship."""

from __future__ import annotations

import math

import pytest

from src.core.relationship import RelationshipManager


class TestRelationshipManager:
    """Validate scoring utility functions."""

    def test_singleton_exists(self) -> None:
        from src.core.relationship import relationship_manager

        assert isinstance(relationship_manager, RelationshipManager)
