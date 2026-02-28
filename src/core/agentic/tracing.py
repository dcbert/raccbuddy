"""Optional Langfuse tracing for the agentic subsystem.

When ``settings.langfuse_enabled`` is ``True``, this module initializes
a Langfuse client that the graph and engine can use to trace agentic
cycles.  When disabled, all functions are safe no-ops.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_client: Any = None


async def init_tracing() -> None:
    """Initialize the Langfuse client if tracing is enabled."""
    global _langfuse_client  # noqa: PLW0603

    if not settings.langfuse_enabled:
        logger.debug("Langfuse tracing disabled")
        return

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse tracing initialized (host=%s)", settings.langfuse_host)
    except ImportError:
        logger.warning(
            "langfuse package not installed — tracing disabled. "
            "Install with: pip install langfuse"
        )
    except Exception:
        logger.exception("Failed to initialize Langfuse tracing")


async def shutdown_tracing() -> None:
    """Flush and close the Langfuse client."""
    global _langfuse_client  # noqa: PLW0603
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
            _langfuse_client.shutdown()
            logger.info("Langfuse tracing shut down")
        except Exception:
            logger.warning("Error shutting down Langfuse", exc_info=True)
        _langfuse_client = None


def get_langfuse() -> Any:
    """Return the Langfuse client (or ``None`` if disabled)."""
    return _langfuse_client


def trace_cycle(cycle_id: str, metadata: dict[str, Any] | None = None) -> Any:
    """Create a new Langfuse trace for an agentic cycle.

    Args:
        cycle_id: Unique identifier for this cycle.
        metadata: Optional metadata to attach to the trace.

    Returns:
        A Langfuse trace object, or ``None`` if tracing is disabled.
    """
    if _langfuse_client is None:
        return None
    try:
        return _langfuse_client.trace(
            name="agentic_cycle",
            id=cycle_id,
            metadata=metadata or {},
        )
    except Exception:
        logger.warning("Failed to create Langfuse trace", exc_info=True)
        return None
