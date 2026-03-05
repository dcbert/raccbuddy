"""Telegram command handlers for scheduled job management.

Commands:
- ``/jobs``              — list all pending/active jobs
- ``/cancel <job_id>``   — cancel a specific job
- ``/schedule <minutes> <message>`` — quick-schedule a one-shot reminder
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.core.auth import reject_non_owner
from src.core.scheduled.jobs import cancel_job, get_pending_jobs, schedule_llm_job

logger = logging.getLogger(__name__)


async def jobs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/jobs`` — list all pending one-shot and active recurring jobs."""
    if await reject_non_owner(update):
        return
    if not update.message or not update.effective_user:
        return

    owner_id = update.effective_user.id
    jobs = await get_pending_jobs(owner_id)

    if not jobs:
        await update.message.reply_text("No scheduled jobs.")
        return

    lines: list[str] = []
    for j in jobs:
        if j.get("type") == "recurring":
            lines.append(
                f"\u2022 [{j['job_id']}] recurring "
                f"({j['recurrence_type']}: {j['recurrence_rule']})\n"
                f"  {j['message'][:80]}"
            )
        else:
            lines.append(
                f"\u2022 [{j['job_id']}] at {j.get('fire_at', 'N/A')}\n"
                f"  {j['message'][:80]}"
            )

    await update.message.reply_text(
        f"Scheduled jobs ({len(jobs)}):\n\n" + "\n\n".join(lines)
    )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/cancel <job_id>`` — cancel a scheduled job."""
    if await reject_non_owner(update):
        return
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text("Usage: /cancel <job_id>")
        return

    job_id = context.args[0]
    success = await cancel_job(job_id)

    if success:
        await update.message.reply_text(f"Job {job_id} cancelled.")
    else:
        await update.message.reply_text(f"Job {job_id} not found or already cancelled.")


async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/schedule <minutes> <message>`` — quick-schedule a one-shot reminder."""
    if await reject_non_owner(update):
        return
    if not update.message or not update.effective_user:
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /schedule <minutes> <message>")
        return

    try:
        delay_minutes = int(context.args[0])
    except ValueError:
        await update.message.reply_text("First argument must be a number (minutes).")
        return

    if delay_minutes < 1:
        await update.message.reply_text("Delay must be at least 1 minute.")
        return

    message = " ".join(context.args[1:])
    owner_id = update.effective_user.id

    result = await schedule_llm_job(
        owner_id=owner_id,
        message=message,
        delay_minutes=delay_minutes,
        reason="user_command",
    )
    job_id = result.job_id

    hours = delay_minutes // 60
    mins = delay_minutes % 60
    time_str = ""
    if hours:
        time_str += f"{hours}h"
    if mins:
        time_str += f"{mins}m"

    await update.message.reply_text(
        f"Scheduled reminder [{job_id}] in {time_str}:\n{message}"
    )
