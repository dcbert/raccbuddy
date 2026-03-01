"""Proactive Agentic Core — public API.

This module provides the top-level ``init_agentic()`` and
``shutdown_agentic()`` functions.  All internal imports are lazy so that
the agentic subsystem has zero cost when ``AGENTIC_ENABLED=false``.
"""

from __future__ import annotations

import logging

from src.core.config import settings

logger = logging.getLogger(__name__)


async def init_agentic() -> None:
    """Initialize the full agentic subsystem.

    Called from ``post_init`` in ``bot.py`` when ``settings.agentic_enabled``
    is ``True``.  Order:

    1. Tracing (Langfuse)
    2. Metrics (Prometheus)
    3. Engine (graph + checkpointer)
    """
    if not settings.agentic_enabled:
        logger.debug("Agentic subsystem disabled (AGENTIC_ENABLED=false)")
        return

    logger.info("Initializing agentic subsystem…")

    from src.core.agentic.engine import init_engine
    from src.core.agentic.metrics import init_metrics
    from src.core.agentic.tracing import init_tracing

    await init_tracing()
    await init_metrics()
    await init_engine()

    logger.info("Agentic subsystem initialized")


async def shutdown_agentic() -> None:
    """Tear down the agentic subsystem on graceful shutdown."""
    if not settings.agentic_enabled:
        return

    logger.info("Shutting down agentic subsystem…")

    from src.core.agentic.engine import shutdown_engine
    from src.core.agentic.metrics import shutdown_metrics
    from src.core.agentic.tracing import shutdown_tracing

    await shutdown_engine()
    await shutdown_metrics()
    await shutdown_tracing()

    logger.info("Agentic subsystem shut down")
