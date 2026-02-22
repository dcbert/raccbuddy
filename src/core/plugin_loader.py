"""Plugin registry and auto-loader for user-provided platform plugins.

At startup, call ``load_user_plugins()`` to import every ``.py`` file
from the ``plugins/`` directory in the project root. Each file is expected
to call ``register_plugin()`` at module level.
"""

from __future__ import annotations

import logging
from typing import Any

from src.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------

_plugins: dict[str, BasePlugin] = {}


def register_plugin(plugin: BasePlugin) -> None:
    """Register a platform plugin (built-in or user-provided)."""
    if plugin.name in _plugins:
        logger.warning("Overwriting existing plugin: %s", plugin.name)
    _plugins[plugin.name] = plugin
    logger.info("Plugin registered: %s (%s)", plugin.name, plugin.platform)


def unregister_plugin(name: str) -> None:
    """Remove a plugin by name."""
    _plugins.pop(name, None)


def get_registered_plugins() -> dict[str, BasePlugin]:
    """Return a copy of the current plugin registry."""
    return dict(_plugins)


def clear_plugins() -> None:
    """Remove all registered plugins (useful for testing)."""
    _plugins.clear()


async def register_all_with_app(app: Any) -> None:
    """Call ``register(app)`` on all registered plugins.

    This should be called once during bot startup (in post_init).
    """
    for name, plugin in _plugins.items():
        try:
            await plugin.register(app)
            logger.info("Plugin '%s' registered with app", name)
        except Exception:
            logger.exception("Failed to register plugin '%s'", name)


async def teardown_all_plugins() -> None:
    """Call ``teardown()`` on all registered plugins.

    This should be called during bot shutdown.
    """
    for name, plugin in _plugins.items():
        try:
            await plugin.teardown()
            logger.info("Plugin '%s' torn down", name)
        except Exception:
            logger.exception("Failed to teardown plugin '%s'", name)


def load_user_plugins() -> int:
    """Import user-provided plugins from ``plugins/``."""
    from pathlib import Path

    # Re-use _import_py_files from skill_loader
    from src.core.skills.loader import _import_py_files

    project_root = Path(__file__).resolve().parent.parent.parent
    plugins_dir = project_root / "plugins"

    count = _import_py_files(plugins_dir, "user_plugins")
    if count:
        logger.info("Loaded %d user platform plugin(s)", count)
    return count
