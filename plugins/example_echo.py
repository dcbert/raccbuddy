"""Example platform plugin: simple echo bot.

This is a minimal example showing how to create a custom platform plugin.
Drop this file in the plugins/ folder and RaccBuddy will auto-load it.

In production, you'd replace this with a real bridge to WhatsApp, Discord,
Slack, or any other messaging platform.
"""

import logging
from typing import Any

from src.core.plugin_loader import register_plugin
from src.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class EchoPlugin(BasePlugin):
    """Example plugin that logs incoming messages."""

    @property
    def name(self) -> str:
        return "echo_example"

    @property
    def platform(self) -> str:
        return "echo"

    async def register(self, app: Any) -> None:
        """Called once at bot startup."""
        logger.info("Echo plugin registered")
        self.app = app

    async def handle_message(self, message: dict[str, Any]) -> None:
        """Process an incoming message from the 'echo' platform.

        In a real plugin, you'd:
        1. Validate the message
        2. Save it to the database
        3. Optionally trigger a response
        """
        from src.core.db import save_message

        chat_id = message.get("chat_id", 0)
        from_id = message.get("from_id", 0)
        text = message.get("text", "")
        owner_id = message.get("owner_id", from_id)

        logger.info("Echo plugin received message: %s", text)

        # Save to database
        await save_message(
            platform=self.platform,
            chat_id=chat_id,
            from_id=from_id,
            text_content=text,
            contact_id=from_id if from_id != owner_id else None,
        )

    async def teardown(self) -> None:
        """Called during bot shutdown."""
        logger.info("Echo plugin teardown")


# Register the plugin so it's available at bot startup
register_plugin(EchoPlugin())
