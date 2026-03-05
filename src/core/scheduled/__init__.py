"""Scheduled job management.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.scheduled.jobs import (
    ScheduleResult,
    cancel_job,
    compute_next_fire_at,
    get_pending_jobs,
    restore_pending_jobs,
    schedule_llm_job,
    schedule_recurring_job,
    set_app_reference,
)

__all__ = [
    "ScheduleResult",
    "cancel_job",
    "compute_next_fire_at",
    "get_pending_jobs",
    "restore_pending_jobs",
    "schedule_llm_job",
    "schedule_recurring_job",
    "set_app_reference",
]
