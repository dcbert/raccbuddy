"""Base plugin class for RaccBuddy extensions.

Every plugin must inherit from BasePlugin, implement the required methods,
and register itself with the application to push messages to the core queue.
"""

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """Abstract base class for all RaccBuddy platform plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier."""
        ...

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform this plugin connects to (e.g. 'whatsapp')."""
        ...

    @abstractmethod
    async def register(self, app: Any) -> None:
        """Register plugin handlers with the bot application."""
        ...

    @abstractmethod
    async def handle_message(self, message: dict[str, Any]) -> None:
        """Process an incoming message and push it to the core queue."""
        ...

    async def teardown(self) -> None:
        """Clean up resources. Override if the plugin holds connections."""
