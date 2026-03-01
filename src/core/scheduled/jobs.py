"""LLM-scheduled jobs — allows the model to schedule future messages.

Jobs are persisted in the ``scheduled_jobs`` database table so they survive
bot restarts.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)

# Reference to the Telegram Application (set once at bot startup)
_app_ref: Optional[object] = None


def set_app_reference(app: object) -> None:
    """Store a reference to the Telegram Application for job scheduling."""
    global _app_ref  # noqa: PLW0603
    _app_ref = app
    logger.info("Scheduled jobs: app reference set")


async def schedule_llm_job(
    owner_id: int,
    message: str,
    delay_minutes: int,
    reason: str = "",
) -> str:
    """Schedule a message for future delivery (persisted to DB)."""
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    job_id = uuid.uuid4().hex[:8]
    fire_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=delay_minutes
    )

    job = ScheduledJobModel(
        job_id=job_id,
        owner_id=owner_id,
        message=message,
        delay_minutes=delay_minutes,
        reason=reason,
        fire_at=fire_at,
    )

    try:
        async with get_session() as session:
            session.add(job)
            await session.commit()
    except Exception:
        logger.exception("Failed to persist scheduled job %s", job_id)

    logger.info(
        "LLM scheduled job %s: '%s' in %dm (reason: %s)",
        job_id,
        message[:50],
        delay_minutes,
        reason or "none",
    )

    _register_with_job_queue(job_id, delay_minutes)

    return job_id


async def restore_pending_jobs() -> int:
    """Re-register all un-executed future jobs after a bot restart."""
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    now = datetime.datetime.now(datetime.timezone.utc)
    restored = 0

    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.executed.is_(False),
                    ScheduledJobModel.fire_at > now,
                )
            )
            pending = result.scalars().all()

            for job in pending:
                remaining = (job.fire_at - now).total_seconds()
                remaining_minutes = max(0.1, remaining / 60)
                _register_with_job_queue(job.job_id, remaining_minutes)
                restored += 1
                logger.info(
                    "Restored pending job %s (fires in %.1f min)",
                    job.job_id,
                    remaining_minutes,
                )
    except Exception:
        logger.exception("Failed to restore pending scheduled jobs")

    if restored:
        logger.info("Restored %d pending scheduled jobs", restored)
    return restored


def _register_with_job_queue(job_id: str, delay_minutes: float) -> None:
    """Register a job with the Telegram bot's APScheduler job queue."""
    if _app_ref is None:
        return

    try:
        from telegram.ext import Application

        if isinstance(_app_ref, Application) and _app_ref.job_queue:
            _app_ref.job_queue.run_once(
                _deliver_scheduled_message,
                when=datetime.timedelta(minutes=delay_minutes),
                data=job_id,
                name=f"llm_job_{job_id}",
            )
            logger.debug("Job %s registered with Telegram job queue", job_id)
    except Exception:
        logger.exception("Failed to register job %s with job queue", job_id)


async def _deliver_scheduled_message(context: object) -> None:
    """Callback for the Telegram job queue — sends the scheduled message."""
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    ctx = context  # type: ignore[assignment]
    job_id = ctx.job.data  # type: ignore[attr-defined]

    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(ScheduledJobModel.job_id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                logger.warning("Scheduled job %s not found in DB", job_id)
                return

            if job.executed:
                logger.warning("Scheduled job %s already executed", job_id)
                return

            await ctx.bot.send_message(  # type: ignore[attr-defined]
                chat_id=job.owner_id,
                text=f"🦝 Scheduled reminder:\n\n{job.message}",
            )
            job.executed = True
            await session.commit()
            logger.info("Delivered scheduled job %s to user %d", job_id, job.owner_id)
    except Exception:
        logger.exception("Failed to deliver scheduled job %s", job_id)


async def get_pending_jobs(owner_id: int) -> list[dict]:
    """Return all pending (non-executed, future) jobs for an owner."""
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    now = datetime.datetime.now(datetime.timezone.utc)

    async with get_session() as session:
        result = await session.execute(
            select(ScheduledJobModel).where(
                ScheduledJobModel.owner_id == owner_id,
                ScheduledJobModel.executed.is_(False),
                ScheduledJobModel.fire_at > now,
            )
        )
        jobs = result.scalars().all()

    return [
        {
            "job_id": j.job_id,
            "message": j.message,
            "fire_at": j.fire_at.isoformat(),
            "reason": j.reason,
        }
        for j in jobs
    ]


async def cancel_job(job_id: str) -> bool:
    """Cancel a scheduled job by ID."""
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(ScheduledJobModel.job_id == job_id)
            )
            job = result.scalar_one_or_none()

            if job and not job.executed:
                job.executed = True
                await session.commit()
                logger.info("Cancelled scheduled job %s", job_id)
                return True
    except Exception:
        logger.exception("Failed to cancel job %s", job_id)

    return False
