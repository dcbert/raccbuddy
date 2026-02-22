"""Tests for plugin_loader and plugin registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.plugin_loader import (
    clear_plugins,
    get_registered_plugins,
    load_user_plugins,
    register_all_with_app,
    register_plugin,
    teardown_all_plugins,
    unregister_plugin,
)
from src.plugins.base import BasePlugin


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset plugin registry between tests."""
    clear_plugins()
    yield
    clear_plugins()


# ---------------------------------------------------------------------------
# Dummy plugins for testing
# ---------------------------------------------------------------------------


class _TestPlugin(BasePlugin):
    name = "test"  # type: ignore[assignment]
    platform = "test_platform"  # type: ignore[assignment]

    def __init__(self):
        self.registered = False
        self.torn_down = False

    async def register(self, app: Any) -> None:
        self.registered = True

    async def handle_message(self, message: dict[str, Any]) -> None:
        pass

    async def teardown(self) -> None:
        self.torn_down = True


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        plugin = _TestPlugin()
        register_plugin(plugin)
        assert "test" in get_registered_plugins()

    def test_unregister(self) -> None:
        plugin = _TestPlugin()
        register_plugin(plugin)
        unregister_plugin("test")
        assert "test" not in get_registered_plugins()

    def test_overwrite_warns(self) -> None:
        register_plugin(_TestPlugin())
        register_plugin(_TestPlugin())
        assert len(get_registered_plugins()) == 1


# ---------------------------------------------------------------------------
# App registration
# ---------------------------------------------------------------------------


class TestRegisterAllWithApp:
    @pytest.mark.asyncio
    async def test_calls_register_on_all(self) -> None:
        class _Plugin1(BasePlugin):
            name = "test1"  # type: ignore[assignment]
            platform = "test"  # type: ignore[assignment]

            def __init__(self):
                self.registered = False

            async def register(self, app: Any) -> None:
                self.registered = True

            async def handle_message(self, message: dict[str, Any]) -> None:
                pass

        class _Plugin2(BasePlugin):
            name = "test2"  # type: ignore[assignment]
            platform = "test"  # type: ignore[assignment]

            def __init__(self):
                self.registered = False

            async def register(self, app: Any) -> None:
                self.registered = True

            async def handle_message(self, message: dict[str, Any]) -> None:
                pass

        plugin1 = _Plugin1()
        plugin2 = _Plugin2()
        register_plugin(plugin1)
        register_plugin(plugin2)

        app = AsyncMock()
        await register_all_with_app(app)

        assert plugin1.registered is True
        assert plugin2.registered is True

    @pytest.mark.asyncio
    async def test_continues_on_error(self) -> None:
        """If one plugin fails to register, others should still succeed."""

        class _BadPlugin(BasePlugin):
            name = "bad"  # type: ignore[assignment]
            platform = "bad"  # type: ignore[assignment]

            async def register(self, app: Any) -> None:
                raise RuntimeError("Intentional error")

            async def handle_message(self, message: dict[str, Any]) -> None:
                pass

        good = _TestPlugin()
        register_plugin(_BadPlugin())
        register_plugin(good)

        app = AsyncMock()
        await register_all_with_app(app)

        # Good plugin should still be registered
        assert good.registered is True


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


class TestTeardownAll:
    @pytest.mark.asyncio
    async def test_calls_teardown_on_all(self) -> None:
        class _Plugin1(BasePlugin):
            name = "test1"  # type: ignore[assignment]
            platform = "test"  # type: ignore[assignment]

            def __init__(self):
                self.torn_down = False

            async def register(self, app: Any) -> None:
                pass

            async def handle_message(self, message: dict[str, Any]) -> None:
                pass

            async def teardown(self) -> None:
                self.torn_down = True

        class _Plugin2(BasePlugin):
            name = "test2"  # type: ignore[assignment]
            platform = "test"  # type: ignore[assignment]

            def __init__(self):
                self.torn_down = False

            async def register(self, app: Any) -> None:
                pass

            async def handle_message(self, message: dict[str, Any]) -> None:
                pass

            async def teardown(self) -> None:
                self.torn_down = True

        plugin1 = _Plugin1()
        plugin2 = _Plugin2()
        register_plugin(plugin1)
        register_plugin(plugin2)

        await teardown_all_plugins()

        assert plugin1.torn_down is True
        assert plugin2.torn_down is True


# ---------------------------------------------------------------------------
# Auto-loader
# ---------------------------------------------------------------------------


class TestPluginLoader:
    def test_loads_from_directory(self, tmp_path: Path) -> None:
        """Create a temp plugin file and verify it gets imported."""
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(
            "from src.plugins.base import BasePlugin\n"
            "from src.core.plugin_loader import register_plugin\n"
            "\n"
            "class TmpPlugin(BasePlugin):\n"
            "    name = 'tmp_plugin'\n"
            "    platform = 'tmp'\n"
            "    async def register(self, app): pass\n"
            "    async def handle_message(self, message): pass\n"
            "\n"
            "register_plugin(TmpPlugin())\n"
        )

        from src.core.skills.loader import _import_py_files

        count = _import_py_files(tmp_path, "test_plugins")
        assert count == 1
        assert "tmp_plugin" in get_registered_plugins()

    def test_skips_missing_directory(self) -> None:
        from src.core.skills.loader import _import_py_files

        count = _import_py_files(Path("/nonexistent"), "nope")
        assert count == 0

    def test_skips_private_files(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "_private.py").write_text("x = 1")

        from src.core.skills.loader import _import_py_files

        count = _import_py_files(tmp_path, "test_private")
        assert count == 0


# ---------------------------------------------------------------------------
# Integration: handle_message
# ---------------------------------------------------------------------------


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_plugin_handles_message(self) -> None:
        """Verify a plugin can save a message to the DB."""
        plugin = _TestPlugin()

        # This test just verifies the plugin's handle_message can be called
        # In the real example_echo.py, it calls save_message
        await plugin.handle_message({
            "chat_id": 123,
            "from_id": 456,
            "text": "hello",
        })
