"""Tests for src.plugins.base."""

from typing import Any

import pytest

from src.plugins.base import BasePlugin


class DummyPlugin(BasePlugin):
    """Concrete implementation for testing the abstract base."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def platform(self) -> str:
        return "test"

    async def register(self, app: Any) -> None:
        pass

    async def handle_message(self, message: dict[str, Any]) -> None:
        pass


class IncompletePlugin(BasePlugin):
    """Intentionally incomplete — missing required methods."""

    @property
    def name(self) -> str:
        return "incomplete"


class TestBasePlugin:
    """Validate the plugin contract."""

    def test_concrete_plugin_instantiates(self) -> None:
        plugin = DummyPlugin()
        assert plugin.name == "dummy"
        assert plugin.platform == "test"

    def test_incomplete_plugin_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            IncompletePlugin()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_teardown_default(self) -> None:
        plugin = DummyPlugin()
        # Should not raise
        await plugin.teardown()

    @pytest.mark.asyncio
    async def test_handle_message(self) -> None:
        plugin = DummyPlugin()
        await plugin.handle_message({"text": "hello"})
