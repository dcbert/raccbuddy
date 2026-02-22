# Custom Platform Plugins

Drop your custom platform plugin files here. RaccBuddy will auto-load any `.py`
file in this directory at startup and register them with the bot.

## What are platform plugins?

Platform plugins extend RaccBuddy to ingest messages from additional platforms
beyond Telegram (the default). For example, you could create a WhatsApp plugin,
Discord plugin, Slack plugin, etc.

Each plugin:
- Connects to an external messaging platform
- Listens for incoming messages
- Forwards them to RaccBuddy's core for processing

## How to create a plugin

1. Create a new `.py` file in this folder (e.g. `whatsapp_plugin.py`).
2. Subclass `BasePlugin` from `src.plugins.base`.
3. Implement all required methods.
4. Call `register_plugin()` at module level (plugin registry will be auto-created).

### Template

```python
"""WhatsApp platform plugin for RaccBuddy."""

import logging
from typing import Any

from src.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class WhatsAppPlugin(BasePlugin):
    """Forwards WhatsApp messages to RaccBuddy core."""

    @property
    def name(self) -> str:
        return "whatsapp"

    @property
    def platform(self) -> str:
        return "whatsapp"

    async def register(self, app: Any) -> None:
        """Register this plugin with the Telegram bot application.

        The `app` is the Telegram Application instance. You can use it
        to send replies back via Telegram.
        """
        logger.info("WhatsApp plugin registered")
        # Store app reference for later use
        self.app = app

    async def handle_message(self, message: dict[str, Any]) -> None:
        """Process an incoming WhatsApp message.

        This is called by your bridge service (e.g., whatsapp-service)
        via the REST API endpoint.
        """
        from src.core.db import save_message

        chat_id = message.get("chat_id")
        from_id = message.get("from_id")
        text = message.get("text")
        owner_id = message.get("owner_id")

        # Save to database
        await save_message(
            platform=self.platform,
            chat_id=chat_id,
            from_id=from_id,
            text_content=text,
            contact_id=from_id if from_id != owner_id else None,
        )

        logger.info("Saved WhatsApp message from %s", from_id)

    async def teardown(self) -> None:
        """Clean up resources when the bot shuts down."""
        logger.info("WhatsApp plugin teardown")


# Auto-register when imported
from src.core.plugin_loader import register_plugin
register_plugin(WhatsAppPlugin())
```

### Key rules

- **`register(app)`** is called once at bot startup. Store the `app` reference
  if you need to send messages back via Telegram.
- **`handle_message(message)`** is called for each incoming message from your
  platform. Save it to the DB using `save_message()`.
- **`teardown()`** is optional — override it if you need to close connections
  or clean up resources.

### Connecting your platform

Your plugin needs a bridge service that:
1. Connects to the external platform (WhatsApp, Discord, etc.)
2. Listens for incoming messages
3. POSTs them to the RaccBuddy REST API at `/api/messages`

Example bridge payload:

```json
{
  "platform": "whatsapp",
  "chat_id": 123456,
  "from_id": 789012,
  "text": "Hello from WhatsApp",
  "owner_id": 789012
}
```

See `whatsapp-service/` for a working example using `whatsapp-web.js`.

### Available helpers

```python
from src.core.db import (
    save_message,
    get_contact,
    upsert_contact,
)
from src.core.llm import generate
from src.core.memory import build_context_for_contact
```

See `src/plugins/base.py` for the full `BasePlugin` API.
