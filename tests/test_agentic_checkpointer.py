"""Tests for src.core.agentic.checkpointer_registry."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.agentic.checkpointer_registry import (
    BaseCheckpointer,
    _asyncpg_to_psycopg,
    _registry,
    get_checkpointer,
    register_checkpointer,
)


class TestURLConversion:
    """Validate asyncpg → psycopg URL conversion."""

    def test_converts_asyncpg_url(self) -> None:
        url = "postgresql+asyncpg://user:pass@localhost:5432/mydb"
        result = _asyncpg_to_psycopg(url)
        assert result == "postgresql://user:pass@localhost:5432/mydb"

    def test_leaves_plain_url_unchanged(self) -> None:
        url = "postgresql://user:pass@localhost:5432/mydb"
        result = _asyncpg_to_psycopg(url)
        assert result == url


class TestRegistry:
    """Validate checkpointer registration and lookup."""

    def test_builtin_backends_registered(self) -> None:
        assert "postgres" in _registry
        assert "sqlite" in _registry

    def test_get_checkpointer_by_name(self) -> None:
        cp = get_checkpointer("postgres")
        assert cp.name == "postgres"

    def test_get_unknown_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="redis"):
            get_checkpointer("redis")

    def test_register_custom_checkpointer(self) -> None:
        class DummyCheckpointer(BaseCheckpointer):
            @property
            def name(self) -> str:
                return "dummy"

            async def setup(self) -> None:
                pass

            async def teardown(self) -> None:
                pass

            def get_saver(self) -> Any:
                return None

        register_checkpointer(DummyCheckpointer())
        assert "dummy" in _registry
        assert get_checkpointer("dummy").name == "dummy"

        # Clean up
        del _registry["dummy"]

    def test_postgres_checkpointer_raises_before_setup(self) -> None:
        cp = get_checkpointer("postgres")
        with pytest.raises(RuntimeError, match="not set up"):
            cp.get_saver()
