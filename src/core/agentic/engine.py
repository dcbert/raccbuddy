"""ProactiveEngine — orchestrates the agentic cycle.

``init_engine()`` builds the graph and attaches the checkpointer.
``run_agentic_cycle(bot)`` runs one full cycle and delivers approved nudges.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from src.core.agentic import metrics as agentic_metrics
from src.core.agentic import tracing as agentic_tracing
from src.core.config import settings

logger = logging.getLogger(__name__)

_compiled_graph: Any = None


async def init_engine() -> None:
    """Build the LangGraph and compile it with the configured checkpointer.

    Must be called once during startup (inside ``init_agentic``).
    """
    global _compiled_graph  # noqa: PLW0603

    from src.core.agentic.checkpointer_registry import get_checkpointer
    from src.core.agentic.graph import build_graph

    checkpointer = get_checkpointer()
    await checkpointer.setup()

    graph = build_graph()
    _compiled_graph = graph.compile(checkpointer=checkpointer.get_saver())
    logger.info(
        "ProactiveEngine: graph compiled with '%s' checkpointer", checkpointer.name
    )


async def shutdown_engine() -> None:
    """Tear down the checkpointer on shutdown."""
    global _compiled_graph  # noqa: PLW0603

    from src.core.agentic.checkpointer_registry import get_checkpointer

    try:
        checkpointer = get_checkpointer()
        await checkpointer.teardown()
    except Exception:
        logger.warning("Engine checkpointer teardown failed", exc_info=True)

    _compiled_graph = None
    logger.info("ProactiveEngine: shutdown complete")


async def run_agentic_cycle(bot: object) -> None:
    """Execute one full agentic cycle and deliver approved nudges.

    Args:
        bot: The Telegram bot instance (must have ``send_message``).
    """
    if _compiled_graph is None:
        logger.error("ProactiveEngine: graph not initialized — skipping cycle")
        return

    cycle_id = str(uuid.uuid4())
    owner_id = settings.owner_telegram_id
    if not owner_id:
        logger.warning("ProactiveEngine: no owner_id configured — skipping")
        return

    # Thread ID for LangGraph checkpointing (one per owner, survives restarts)
    thread_id = f"owner-{owner_id}"
    config = {"configurable": {"thread_id": thread_id}}

    agentic_tracing.trace_cycle(cycle_id, {"owner_id": owner_id})
    agentic_metrics.cycles_total.inc()
    start = time.monotonic()

    try:
        # Run the full graph
        result = await _compiled_graph.ainvoke(
            {"owner_id": owner_id, "cycle_id": cycle_id},
            config=config,
        )

        approved = result.get("approved", [])
        discarded = result.get("discarded", [])
        error = result.get("error")

        if error:
            logger.warning("Agentic cycle %s had error: %s", cycle_id, error)
            agentic_metrics.cycle_errors_total.inc()
            return

        logger.info(
            "Agentic cycle %s complete: %d approved, %d discarded",
            cycle_id,
            len(approved),
            len(discarded),
        )

        agentic_metrics.nudges_approved_total.inc(len(approved))
        agentic_metrics.nudges_discarded_total.inc(len(discarded))

        # Deliver approved nudges
        for nudge in approved:
            await _deliver_nudge(bot, owner_id, nudge)

    except Exception:
        logger.exception("Agentic cycle %s failed", cycle_id)
        agentic_metrics.cycle_errors_total.inc()
    finally:
        elapsed = time.monotonic() - start
        agentic_metrics.cycle_duration_seconds.observe(elapsed)
        logger.info("Agentic cycle %s took %.1fs", cycle_id, elapsed)


async def _deliver_nudge(bot: object, user_id: int, nudge: dict) -> None:
    """Deliver a single approved nudge via the existing engine helper.

    Args:
        bot: The Telegram bot instance.
        user_id: The owner's Telegram user ID.
        nudge: A ``CraftedNudge`` dict with ``skill_name``, ``trigger``, ``text``.
    """
    from src.core.nudges.engine import execute_nudge_from_agent
    from src.core.skills.base import _mark_fired

    try:
        await execute_nudge_from_agent(
            bot,
            user_id,
            trigger=nudge["trigger"],
            text=nudge["text"],
        )
        _mark_fired(user_id, nudge["skill_name"])
        logger.info(
            "Agentic nudge delivered: %s (trigger=%s)",
            nudge["skill_name"],
            nudge["trigger"],
        )
    except Exception:
        logger.exception(
            "Failed to deliver agentic nudge: %s",
            nudge["skill_name"],
        )
