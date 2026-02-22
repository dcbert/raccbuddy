"""RaccBuddy Telegram bot entry point.

Runs the Telegram bot and the REST API (FastAPI) concurrently so that
external bridges (WhatsApp, etc.) can push messages into the core.
"""

import logging
import threading

import uvicorn
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.api import api
from src.core.config import settings
from src.core.db import init_db
from src.core.memory import memory
from src.core.nudges import run_nudge_skills
from src.core.plugin_loader import load_user_plugins, register_all_with_app
from src.core.scheduled import restore_pending_jobs, set_app_reference
from src.core.skills.loader import load_all_user_skills
from src.core.state import flush_all_dirty, load_all_states
from src.handlers.chat import analyze_handler, chat_handler, contacts_handler, insights_handler, name_handler, relationship_handler, skills_handler
from src.handlers.start import start_handler
from src.summarizer import summarize_all_contacts

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Initialize database and schedule background jobs after startup."""
    await init_db()
    await memory.setup()
    logger.info("Database initialized (memory system ready)")

    # Restore persistent state from DB
    await load_all_states()

    # Load user-provided nudge and chat skills from nudges/ and skills/
    loaded = load_all_user_skills()
    logger.info("Loaded %d user skill file(s)", loaded)

    # Load user-provided platform plugins from plugins/
    loaded_plugins = load_user_plugins()
    logger.info("Loaded %d user platform plugin(s)", loaded_plugins)

    # Register all plugins with the app
    await register_all_with_app(application)

    # Register app reference so LLM-scheduled jobs can use the job queue
    set_app_reference(application)

    # Restore any pending scheduled jobs from the database
    restored = await restore_pending_jobs()
    if restored:
        logger.info("Restored %d pending scheduled jobs", restored)

    # Schedule periodic nudge checks
    if application.job_queue:
        application.job_queue.run_repeating(
            nudge_job,
            interval=settings.nudge_check_interval_minutes * 60,
            first=60,
        )
        # Daily summarization job (every 6 hours)
        application.job_queue.run_repeating(
            summary_job,
            interval=6 * 3600,
            first=300,
        )
        # Periodic state flush (every 5 minutes)
        application.job_queue.run_repeating(
            state_flush_job,
            interval=300,
            first=120,
        )
        logger.info("Nudge, summary, and state-flush schedulers started")


async def nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job — evaluate all nudge skills once per cycle."""
    if context.bot:
        await run_nudge_skills(context.bot)


async def summary_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job: daily summaries, owner reflection, and pruning."""
    await summarize_all_contacts()

    owner_id = settings.owner_telegram_id
    if owner_id:
        await memory.consolidate_memories(owner_id)
        await memory.prune_old_memories(
            days=settings.owner_memory_retention_days,
        )

        # Run habit detection after summarisation
        try:
            from src.core.habits import habit_detector

            await habit_detector.run_full_detection(owner_id)
        except Exception:
            logger.warning("Habit detection failed", exc_info=True)


async def state_flush_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job: flush dirty in-memory state to the database."""
    try:
        await flush_all_dirty()
    except Exception:
        logger.warning("State flush job failed", exc_info=True)


def _start_api_server() -> None:
    """Run the FastAPI server in a background thread.

    This allows the Telegram bot and the REST API to coexist in the
    same process without blocking each other.
    """
    uvicorn.run(
        api,
        host="0.0.0.0",
        port=settings.api_port,
        log_level="info",
    )


def main() -> None:
    """Build and run the Telegram bot + REST API."""
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set — aborting.")
        return

    # Start the FastAPI REST API in a daemon thread
    api_thread = threading.Thread(target=_start_api_server, daemon=True)
    api_thread.start()
    logger.info("REST API started on port %d", settings.api_port)

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("name", name_handler))
    app.add_handler(CommandHandler("analyze", analyze_handler))
    app.add_handler(CommandHandler("insights", insights_handler))
    app.add_handler(CommandHandler("relationship", relationship_handler))
    app.add_handler(CommandHandler("contacts", contacts_handler))
    app.add_handler(CommandHandler("skills", skills_handler))

    # Message handler for all non-command text (including forwarded)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    logger.info("RaccBuddy is starting... 🦝")
    app.run_polling()


if __name__ == "__main__":
    main()
