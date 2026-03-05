"""LLM-scheduled jobs — allows the model to schedule future messages.

Jobs are persisted in the ``scheduled_jobs`` database table so they survive
bot restarts.  Supports one-shot and recurring (daily/weekly/cron) schedules.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import NamedTuple, Optional

from croniter import croniter
from sqlalchemy import or_, select

from src.utils.telegram_format import md_to_telegram_html

logger = logging.getLogger(__name__)

# Valid recurrence types
RECURRENCE_TYPES = {"daily", "weekly", "cron"}


class ScheduleResult(NamedTuple):
    """Return type for schedule functions with dedup signaling."""

    job_id: str
    is_duplicate: bool


# Reference to the Telegram Application (set once at bot startup)
_app_ref: Optional[object] = None


def set_app_reference(app: object) -> None:
    """Store a reference to the Telegram Application for job scheduling."""
    global _app_ref  # noqa: PLW0603
    _app_ref = app
    logger.info("Scheduled jobs: app reference set")


def _remove_from_job_queue(job_id: str) -> None:
    """Remove a job from the Telegram APScheduler queue by its ID."""
    if _app_ref is None:
        return

    try:
        from telegram.ext import Application

        if isinstance(_app_ref, Application) and _app_ref.job_queue:
            existing = _app_ref.job_queue.get_jobs_by_name(f"llm_job_{job_id}")
            for job in existing:
                job.schedule_removal()
            if existing:
                logger.debug(
                    "Removed %d queue entry/entries for job %s",
                    len(existing),
                    job_id,
                )
    except Exception:
        logger.exception("Failed to remove job %s from queue", job_id)


# ---------------------------------------------------------------------------
# Next-fire-at computation
# ---------------------------------------------------------------------------


def compute_next_fire_at(
    recurrence_type: str,
    recurrence_rule: str,
    from_time: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """Compute the next fire time for a recurring job.

    Args:
        recurrence_type: One of ``"daily"``, ``"weekly"``, ``"cron"``.
        recurrence_rule:
            - daily: ``"HH:MM"`` (24-hour format)
            - weekly: ``"HH:MM|mon,wed,fri"`` (day abbreviations)
            - cron: 5-field cron expression (e.g. ``"30 9 * * 1-5"``)
        from_time: Base time for computation (defaults to now UTC).

    Returns:
        The next fire time as a timezone-aware UTC datetime.
    """
    if from_time is None:
        from_time = datetime.datetime.now(datetime.timezone.utc)

    if recurrence_type == "cron":
        cron = croniter(recurrence_rule, from_time)
        return cron.get_next(datetime.datetime).replace(tzinfo=datetime.timezone.utc)

    if recurrence_type == "daily":
        hour, minute = (int(p) for p in recurrence_rule.split(":"))
        candidate = from_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= from_time:
            candidate += datetime.timedelta(days=1)
        return candidate

    if recurrence_type == "weekly":
        parts = recurrence_rule.split("|")
        time_part = parts[0]
        days_part = parts[1] if len(parts) > 1 else ""
        hour, minute = (int(p) for p in time_part.split(":"))

        day_abbrs = {
            "mon": 0,
            "tue": 1,
            "wed": 2,
            "thu": 3,
            "fri": 4,
            "sat": 5,
            "sun": 6,
        }
        target_days = sorted(
            day_abbrs[d.strip().lower()]
            for d in days_part.split(",")
            if d.strip().lower() in day_abbrs
        )
        if not target_days:
            target_days = [from_time.weekday()]

        current_weekday = from_time.weekday()
        candidate_today = from_time.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

        # Check today first
        if current_weekday in target_days and candidate_today > from_time:
            return candidate_today

        # Find next matching day
        for offset in range(1, 8):
            check_day = (current_weekday + offset) % 7
            if check_day in target_days:
                return candidate_today + datetime.timedelta(days=offset)

    raise ValueError(
        f"Unsupported recurrence_type={recurrence_type!r} "
        f"with rule={recurrence_rule!r}"
    )


# ---------------------------------------------------------------------------
# One-shot scheduling
# ---------------------------------------------------------------------------


async def schedule_llm_job(
    owner_id: int,
    message: str,
    delay_minutes: int,
    reason: str = "",
) -> ScheduleResult:
    """Schedule a one-shot message for future delivery (persisted to DB).

    Performs deduplication: if an identical active one-shot job already
    exists for this owner (same message text, not yet executed, fire_at
    in the future), the existing job_id is returned instead.

    Returns:
        A ``ScheduleResult(job_id, is_duplicate)`` tuple.
    """
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    now = datetime.datetime.now(datetime.timezone.utc)

    # --- Deduplication check ---
    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.owner_id == owner_id,
                    ScheduledJobModel.message == message,
                    ScheduledJobModel.executed.is_(False),
                    ScheduledJobModel.recurrence_type.is_(None),
                    ScheduledJobModel.fire_at > now,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.warning(
                    "Duplicate one-shot job detected — returning existing job %s "
                    "(message: '%s')",
                    existing.job_id,
                    message[:50],
                )
                return ScheduleResult(existing.job_id, is_duplicate=True)
    except Exception:
        logger.exception(
            "Dedup check failed for one-shot job; proceeding with creation"
        )

    job_id = uuid.uuid4().hex[:8]
    fire_at = now + datetime.timedelta(minutes=delay_minutes)

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

    return ScheduleResult(job_id, is_duplicate=False)


# ---------------------------------------------------------------------------
# Recurring scheduling
# ---------------------------------------------------------------------------


async def schedule_recurring_job(
    owner_id: int,
    message: str,
    recurrence_type: str,
    recurrence_rule: str,
    reason: str = "",
) -> ScheduleResult:
    """Create a recurring job and register it with the job queue.

    Performs deduplication: if an identical active recurring job already
    exists for this owner (same message, recurrence_type, recurrence_rule,
    and is_active=True), the existing job_id is returned instead.

    Args:
        owner_id: Telegram user ID.
        message: Prompt/topic to elaborate at delivery time.
        recurrence_type: ``"daily"``, ``"weekly"``, or ``"cron"``.
        recurrence_rule: Rule string matching the type (see ``compute_next_fire_at``).
        reason: Optional reason for the schedule.

    Returns:
        A ``ScheduleResult(job_id, is_duplicate)`` tuple.
    """
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    if recurrence_type not in RECURRENCE_TYPES:
        raise ValueError(
            f"Invalid recurrence_type={recurrence_type!r}; "
            f"must be one of {RECURRENCE_TYPES}"
        )

    # --- Deduplication check ---
    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.owner_id == owner_id,
                    ScheduledJobModel.message == message,
                    ScheduledJobModel.is_active.is_(True),
                    ScheduledJobModel.recurrence_type == recurrence_type,
                    ScheduledJobModel.recurrence_rule == recurrence_rule,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.warning(
                    "Duplicate recurring job detected — returning existing job %s "
                    "(message: '%s', type: %s, rule: %s)",
                    existing.job_id,
                    message[:50],
                    recurrence_type,
                    recurrence_rule,
                )
                return ScheduleResult(existing.job_id, is_duplicate=True)
    except Exception:
        logger.exception(
            "Dedup check failed for recurring job; proceeding with creation"
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    next_fire = compute_next_fire_at(recurrence_type, recurrence_rule, now)
    job_id = uuid.uuid4().hex[:8]

    job = ScheduledJobModel(
        job_id=job_id,
        owner_id=owner_id,
        message=message,
        delay_minutes=0,
        reason=reason,
        fire_at=next_fire,
        recurrence_type=recurrence_type,
        recurrence_rule=recurrence_rule,
        next_fire_at=next_fire,
        is_active=True,
    )

    try:
        async with get_session() as session:
            session.add(job)
            await session.commit()
    except Exception:
        logger.exception("Failed to persist recurring job %s", job_id)
        raise

    delay = (next_fire - now).total_seconds() / 60
    _register_with_job_queue(job_id, delay)

    logger.info(
        "Recurring job %s (%s/%s): '%s' next fire at %s (reason: %s)",
        job_id,
        recurrence_type,
        recurrence_rule,
        message[:50],
        next_fire.isoformat(),
        reason or "none",
    )

    return ScheduleResult(job_id, is_duplicate=False)


# ---------------------------------------------------------------------------
# Restore on restart
# ---------------------------------------------------------------------------


async def restore_pending_jobs() -> int:
    """Re-register all un-executed jobs after a bot restart.

    Jobs whose ``fire_at`` has slipped into the past are marked as executed
    instead of being registered with a near-zero delay.  Active recurring
    jobs have their ``next_fire_at`` recomputed if it slipped into the past.
    """
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    now = datetime.datetime.now(datetime.timezone.utc)
    restored = 0

    try:
        async with get_session() as session:
            # One-shot jobs that haven't fired
            result = await session.execute(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.executed.is_(False),
                    ScheduledJobModel.recurrence_type.is_(None),
                )
            )
            one_shots = result.scalars().all()

            for job in one_shots:
                remaining = (job.fire_at - now).total_seconds()
                if remaining <= 0:
                    job.executed = True
                    logger.warning(
                        "Job %s missed its fire_at (%s) — marking executed",
                        job.job_id,
                        job.fire_at.isoformat(),
                    )
                    continue

                _register_with_job_queue(job.job_id, remaining / 60)
                restored += 1
                logger.info(
                    "Restored pending job %s (fires in %.1f min)",
                    job.job_id,
                    remaining / 60,
                )

            # Recurring jobs that are still active
            result = await session.execute(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.is_active.is_(True),
                    ScheduledJobModel.recurrence_type.isnot(None),
                )
            )
            recurring = result.scalars().all()

            for job in recurring:
                fire_time = job.next_fire_at or job.fire_at
                remaining = (fire_time - now).total_seconds()

                if remaining <= 0:
                    # Recompute next fire time
                    fire_time = compute_next_fire_at(
                        job.recurrence_type,  # type: ignore[arg-type]
                        job.recurrence_rule,  # type: ignore[arg-type]
                        now,
                    )
                    job.next_fire_at = fire_time
                    remaining = (fire_time - now).total_seconds()

                _register_with_job_queue(job.job_id, remaining / 60)
                restored += 1
                logger.info(
                    "Restored recurring job %s (%s) — next fire in %.1f min",
                    job.job_id,
                    job.recurrence_type,
                    remaining / 60,
                )

            await session.commit()
    except Exception:
        logger.exception("Failed to restore pending scheduled jobs")

    if restored:
        logger.info("Restored %d pending scheduled jobs", restored)
    return restored


# ---------------------------------------------------------------------------
# APScheduler integration
# ---------------------------------------------------------------------------


def _register_with_job_queue(job_id: str, delay_minutes: float) -> None:
    """Register a job with the Telegram bot's APScheduler job queue."""
    if _app_ref is None:
        return

    try:
        from telegram.ext import Application

        if isinstance(_app_ref, Application) and _app_ref.job_queue:
            # Remove any existing entry to prevent duplicate registration
            existing = _app_ref.job_queue.get_jobs_by_name(f"llm_job_{job_id}")
            for j in existing:
                j.schedule_removal()

            _app_ref.job_queue.run_once(
                _deliver_scheduled_message,
                when=datetime.timedelta(minutes=delay_minutes),
                data=job_id,
                name=f"llm_job_{job_id}",
            )
            logger.debug("Job %s registered with Telegram job queue", job_id)
    except Exception:
        logger.exception("Failed to register job %s with job queue", job_id)


# ---------------------------------------------------------------------------
# Delivery callback
# ---------------------------------------------------------------------------


async def _generate_job_message(job: object) -> str:
    """Generate a fresh LLM response for a scheduled job.

    Uses the stored ``job.message`` as a task prompt and runs a full
    tool-calling loop so the LLM can use web_search, browse_webpage,
    and other registered tools to fulfil the task.

    For recurring jobs with a previous ``last_response``, that response
    is included as context so the LLM can build on prior iterations.

    Falls back to the raw ``job.message`` if LLM generation fails.
    """
    import json as _json

    from src.core.config import settings
    from src.core.llm.interface import (
        SYSTEM_PROMPT,
        generate_chat,
        generate_with_tools,
        provider_supports_tools,
    )
    from src.core.tools import execute_tool, get_all_tool_schemas

    j = job  # type: ignore[assignment]

    system_content = (
        f"{SYSTEM_PROMPT}\n\n"
        "You are executing a scheduled task for the user. "
        "Use the available tools (web_search, browse_webpage, etc.) if the "
        "task requires looking up information, then deliver a warm, "
        "personalised response with the results. "
        "Keep the final answer concise but informative. "
        "Do NOT mention that this is a scheduled job."
    )

    if j.reason:
        system_content += f"\nTask context: {j.reason}"

    if j.recurrence_type:
        system_content += (
            f"\nThis is a recurring ({j.recurrence_type}) task. "
            "Vary your wording each time to keep it fresh and engaging."
        )

    messages: list[dict] = [
        {"role": "system", "content": system_content},
    ]

    # Include previous response as context for recurring jobs
    if j.recurrence_type and getattr(j, "last_response", None):
        messages.append(
            {
                "role": "assistant",
                "content": f"[Your previous message on this topic]: {j.last_response}",
            }
        )

    messages.append({"role": "user", "content": j.message})

    try:
        # Use the tool-calling loop when the provider supports it
        if provider_supports_tools():
            all_tools = get_all_tool_schemas()
            # Exclude schedule tools to prevent recursive job creation
            all_tools = [
                t
                for t in all_tools
                if t.get("function", {}).get("name")
                not in {
                    "schedule_message",
                    "schedule_recurring_message",
                }
            ]

            for _round in range(settings.max_tool_rounds):
                result = await generate_with_tools(messages, all_tools)

                if result.finished and not result.tool_calls:
                    if result.text and result.text.strip():
                        return result.text.strip()
                    break

                if not result.tool_calls:
                    if result.text and result.text.strip():
                        return result.text.strip()
                    break

                # Append assistant message with tool calls
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": result.text or "",
                }
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": (
                                _json.dumps(tc.arguments)
                                if isinstance(tc.arguments, dict)
                                else str(tc.arguments)
                            ),
                        },
                    }
                    for tc in result.tool_calls
                ]
                messages.append(assistant_msg)

                # Execute each tool and feed results back
                for tc in result.tool_calls:
                    logger.info(
                        "Scheduled job %s tool call: %s(%s)",
                        j.job_id,
                        tc.name,
                        tc.arguments,
                    )
                    tool_result = await execute_tool(tc.name, tc.arguments, j.owner_id)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_result,
                        }
                    )

            else:
                # Exhausted rounds — force a final answer without tools
                logger.warning(
                    "Scheduled job %s tool loop hit %d rounds, forcing final answer",
                    j.job_id,
                    settings.max_tool_rounds,
                )
                result = await generate_with_tools(messages, [])
                if result.text and result.text.strip():
                    return result.text.strip()
        else:
            # Fallback to simple chat generation
            response = await generate_chat(messages)
            if response and response.strip():
                return response.strip()

        logger.warning(
            "LLM returned empty response for job %s; falling back to raw message",
            j.job_id,
        )
    except Exception:
        logger.exception(
            "LLM generation failed for job %s; falling back to raw message",
            j.job_id,
        )

    return j.message


async def _deliver_scheduled_message(context: object) -> None:
    """Callback for the Telegram job queue — generates and sends a message.

    Uses ``_generate_job_message`` to produce a fresh LLM response based
    on the job's stored prompt.  For recurring jobs, computes the next
    fire time and re-registers.

    The implementation uses separate DB sessions for reading and writing
    so that long-running LLM generation (with tool calls) does not hold
    a database connection open and risk stale transactions.
    """
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    ctx = context  # type: ignore[assignment]
    job_id = ctx.job.data  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Phase 1: Load job data from DB (short-lived session)
    # ------------------------------------------------------------------
    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(ScheduledJobModel.job_id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                logger.warning("Scheduled job %s not found in DB", job_id)
                return

            # One-shot: check executed flag
            if not job.recurrence_type and job.executed:
                logger.warning("Scheduled job %s already executed", job_id)
                return

            # Recurring: check is_active flag
            if job.recurrence_type and not job.is_active:
                logger.warning("Recurring job %s is inactive — skipping", job_id)
                return

            # Snapshot the data we need for generation (detach from session)
            owner_id = job.owner_id
            message = job.message
            reason = job.reason
            recurrence_type = job.recurrence_type
            recurrence_rule = job.recurrence_rule
            last_response = job.last_response
    except Exception:
        logger.exception("Failed to load scheduled job %s from DB", job_id)
        return

    # ------------------------------------------------------------------
    # Phase 2: Generate response via LLM (no DB session held open)
    # ------------------------------------------------------------------
    try:
        # Build a lightweight job-like object for _generate_job_message
        class _JobSnapshot:
            pass

        snap = _JobSnapshot()
        snap.job_id = job_id  # type: ignore[attr-defined]
        snap.owner_id = owner_id  # type: ignore[attr-defined]
        snap.message = message  # type: ignore[attr-defined]
        snap.reason = reason  # type: ignore[attr-defined]
        snap.recurrence_type = recurrence_type  # type: ignore[attr-defined]
        snap.last_response = last_response  # type: ignore[attr-defined]

        generated_text = await _generate_job_message(snap)
    except Exception:
        logger.exception("LLM generation failed for scheduled job %s", job_id)
        generated_text = message  # Fallback to raw stored message

    # ------------------------------------------------------------------
    # Phase 3: Send the message to the user
    # ------------------------------------------------------------------
    try:
        await ctx.bot.send_message(  # type: ignore[attr-defined]
            chat_id=owner_id,
            text=md_to_telegram_html(f"\U0001f99d {generated_text}"),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Failed to send scheduled job %s message to user %d",
            job_id,
            owner_id,
        )
        # Still mark as executed below so the job doesn't re-fire forever

    # ------------------------------------------------------------------
    # Phase 4: Update DB state (fresh session)
    # ------------------------------------------------------------------
    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(ScheduledJobModel.job_id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                logger.warning(
                    "Scheduled job %s disappeared from DB before update", job_id
                )
                return

            now = datetime.datetime.now(datetime.timezone.utc)
            job.last_executed_at = now

            if recurrence_type:
                # Store the response for next iteration's context
                job.last_response = generated_text

                # Re-schedule the next occurrence
                next_fire = compute_next_fire_at(
                    recurrence_type,
                    recurrence_rule,  # type: ignore[arg-type]
                    now,
                )
                job.next_fire_at = next_fire
                job.fire_at = next_fire
                await session.commit()

                delay = (next_fire - now).total_seconds() / 60
                _register_with_job_queue(job_id, delay)
                logger.info(
                    "Recurring job %s delivered; next fire at %s",
                    job_id,
                    next_fire.isoformat(),
                )
            else:
                job.executed = True
                await session.commit()
                logger.info("Delivered scheduled job %s to user %d", job_id, owner_id)
    except Exception:
        logger.exception("Failed to update DB state for scheduled job %s", job_id)


# ---------------------------------------------------------------------------
# Query & cancel
# ---------------------------------------------------------------------------


async def get_pending_jobs(owner_id: int) -> list[dict]:
    """Return all pending one-shot + active recurrent jobs for an owner."""
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    now = datetime.datetime.now(datetime.timezone.utc)

    async with get_session() as session:
        result = await session.execute(
            select(ScheduledJobModel).where(
                ScheduledJobModel.owner_id == owner_id,
                or_(
                    # One-shot: not executed, fire_at in future
                    (
                        ScheduledJobModel.recurrence_type.is_(None)
                        & ScheduledJobModel.executed.is_(False)
                        & (ScheduledJobModel.fire_at > now)
                    ),
                    # Recurring: active
                    (
                        ScheduledJobModel.recurrence_type.isnot(None)
                        & ScheduledJobModel.is_active.is_(True)
                    ),
                ),
            )
        )
        jobs = result.scalars().all()

    results: list[dict] = []
    for j in jobs:
        entry: dict = {
            "job_id": j.job_id,
            "message": j.message,
            "reason": j.reason,
        }
        if j.recurrence_type:
            entry["type"] = "recurring"
            entry["recurrence_type"] = j.recurrence_type
            entry["recurrence_rule"] = j.recurrence_rule
            entry["next_fire_at"] = (
                j.next_fire_at.isoformat() if j.next_fire_at else None
            )
        else:
            entry["type"] = "one_shot"
            entry["fire_at"] = j.fire_at.isoformat()
        results.append(entry)

    return results


async def cancel_job(job_id: str) -> bool:
    """Cancel a scheduled job by ID.

    For recurring jobs, sets ``is_active=False``.
    For one-shot jobs, sets ``executed=True``.
    Both cases remove the job from the APScheduler queue.

    The *job_id* is stripped of surrounding brackets and whitespace so
    that IDs copied from ``list_scheduled_jobs`` output work directly.
    """
    from src.core.db.models import ScheduledJobModel
    from src.core.db.session import get_session

    # Sanitise the job_id — the LLM may pass "[abc123]" from the list output
    clean_id = job_id.strip().strip("[]").strip()
    if clean_id != job_id:
        logger.debug("Sanitised job_id: %r -> %r", job_id, clean_id)

    try:
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledJobModel).where(ScheduledJobModel.job_id == clean_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                logger.warning(
                    "cancel_job: job_id=%r (clean=%r) not found in DB",
                    job_id,
                    clean_id,
                )
                return False

            if job.recurrence_type:
                if not job.is_active:
                    logger.info(
                        "cancel_job: recurring job %s is already inactive",
                        clean_id,
                    )
                    return False
                job.is_active = False
            else:
                if job.executed:
                    logger.info(
                        "cancel_job: one-shot job %s is already executed",
                        clean_id,
                    )
                    return False
                job.executed = True

            await session.commit()
            _remove_from_job_queue(clean_id)
            logger.info(
                "Cancelled scheduled job %s (type=%s)",
                clean_id,
                job.recurrence_type or "one-shot",
            )
            return True
    except Exception:
        logger.exception("Failed to cancel job %s", clean_id)

    return False
