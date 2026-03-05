"""Tests for src.core.scheduled.jobs — one-shot and recurring scheduling."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduled import (
    ScheduleResult,
    cancel_job,
    compute_next_fire_at,
    get_pending_jobs,
    schedule_llm_job,
    schedule_recurring_job,
    set_app_reference,
)
from src.core.scheduled.jobs import (
    _deliver_scheduled_message,
    _generate_job_message,
    _remove_from_job_queue,
    restore_pending_jobs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session():
    """Return an async-context-manager-compatible mock session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    return session


@pytest.fixture(autouse=True)
def _clear_app_ref():
    """Reset app reference between tests."""
    set_app_reference(None)  # type: ignore[arg-type]
    yield
    set_app_reference(None)  # type: ignore[arg-type]


# ===========================================================================
# compute_next_fire_at
# ===========================================================================


class TestComputeNextFireAt:
    """Validate next-fire-at computation for daily, weekly, cron."""

    def test_daily_future_today(self) -> None:
        base = datetime.datetime(2026, 3, 1, 8, 0, tzinfo=datetime.timezone.utc)
        result = compute_next_fire_at("daily", "09:00", base)
        assert result == datetime.datetime(
            2026, 3, 1, 9, 0, tzinfo=datetime.timezone.utc
        )

    def test_daily_past_today_wraps_to_tomorrow(self) -> None:
        base = datetime.datetime(2026, 3, 1, 10, 0, tzinfo=datetime.timezone.utc)
        result = compute_next_fire_at("daily", "09:00", base)
        assert result == datetime.datetime(
            2026, 3, 2, 9, 0, tzinfo=datetime.timezone.utc
        )

    def test_weekly_next_matching_day(self) -> None:
        # 2026-03-01 is a Sunday (weekday=6)
        base = datetime.datetime(2026, 3, 1, 10, 0, tzinfo=datetime.timezone.utc)
        result = compute_next_fire_at("weekly", "09:00|mon,wed,fri", base)
        # Next Monday is March 2
        assert result.weekday() == 0  # Monday
        assert result.day == 2

    def test_weekly_today_future_time(self) -> None:
        # 2026-03-02 is Monday (weekday=0)
        base = datetime.datetime(2026, 3, 2, 8, 0, tzinfo=datetime.timezone.utc)
        result = compute_next_fire_at("weekly", "09:00|mon,fri", base)
        # Today is Monday and 09:00 > 08:00, should fire today
        assert result.day == 2
        assert result.hour == 9

    def test_cron_basic(self) -> None:
        base = datetime.datetime(2026, 3, 1, 8, 0, tzinfo=datetime.timezone.utc)
        result = compute_next_fire_at("cron", "30 9 * * *", base)
        assert result.hour == 9
        assert result.minute == 30

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported recurrence_type"):
            compute_next_fire_at("hourly", "09:00")


# ===========================================================================
# _remove_from_job_queue
# ===========================================================================


class TestRemoveFromJobQueue:
    """Validate APScheduler queue removal helper."""

    def test_removes_matching_jobs(self) -> None:
        mock_job = MagicMock()
        mock_queue = MagicMock()
        mock_queue.get_jobs_by_name.return_value = [mock_job]

        mock_app = MagicMock(spec=["job_queue"])
        mock_app.job_queue = mock_queue

        with patch("src.core.scheduled.jobs.isinstance", return_value=True):
            # Directly set the app ref and call
            import src.core.scheduled.jobs as jobs_mod

            old = jobs_mod._app_ref
            jobs_mod._app_ref = mock_app
            try:
                _remove_from_job_queue("test123")
                mock_queue.get_jobs_by_name.assert_called_once_with("llm_job_test123")
                mock_job.schedule_removal.assert_called_once()
            finally:
                jobs_mod._app_ref = old

    def test_noop_when_no_app_ref(self) -> None:
        _remove_from_job_queue("test123")  # Should not raise


# ===========================================================================
# schedule_llm_job
# ===========================================================================


@pytest.mark.asyncio
class TestScheduleLLMJob:
    """Validate one-shot job scheduling (DB-backed) with deduplication."""

    @patch("src.core.db.session.get_session")
    async def test_creates_job_and_returns_id(
        self, mock_get_session: MagicMock
    ) -> None:
        # First session: dedup check (no duplicate found)
        dedup_session = _mock_session()
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None
        dedup_session.execute = AsyncMock(return_value=dedup_result)

        # Second session: job creation
        create_session = _mock_session()

        mock_get_session.side_effect = [dedup_session, create_session]

        result = await schedule_llm_job(
            owner_id=123,
            message="Check on Giulia",
            delay_minutes=60,
            reason="reminder",
        )
        assert result.job_id
        assert len(result.job_id) == 8
        assert result.is_duplicate is False
        create_session.add.assert_called_once()
        create_session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_multiple_jobs_get_unique_ids(
        self, mock_get_session: MagicMock
    ) -> None:
        sessions = []
        for _ in range(4):  # 2 dedup + 2 create
            s = _mock_session()
            dedup_result = MagicMock()
            dedup_result.scalar_one_or_none.return_value = None
            s.execute = AsyncMock(return_value=dedup_result)
            sessions.append(s)
        mock_get_session.side_effect = sessions

        id1 = await schedule_llm_job(123, "msg1", 30)
        id2 = await schedule_llm_job(123, "msg2", 60)
        assert id1.job_id != id2.job_id

    @patch("src.core.db.session.get_session")
    async def test_dedup_returns_existing_oneshot(
        self, mock_get_session: MagicMock
    ) -> None:
        """Scheduling an identical one-shot job returns the existing job_id."""
        existing_job = MagicMock()
        existing_job.job_id = "existing1"

        dedup_session = _mock_session()
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = existing_job
        dedup_session.execute = AsyncMock(return_value=dedup_result)
        mock_get_session.return_value = dedup_session

        result = await schedule_llm_job(
            owner_id=123,
            message="Check on Giulia",
            delay_minutes=60,
            reason="reminder",
        )
        assert result.job_id == "existing1"
        assert result.is_duplicate is True
        # No new job should be added
        dedup_session.add.assert_not_called()


# ===========================================================================
# schedule_recurring_job
# ===========================================================================


@pytest.mark.asyncio
class TestScheduleRecurringJob:
    """Validate recurring job creation with deduplication."""

    @patch("src.core.db.session.get_session")
    async def test_creates_recurring_daily(self, mock_get_session: MagicMock) -> None:
        # First session: dedup check (no duplicate)
        dedup_session = _mock_session()
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None
        dedup_session.execute = AsyncMock(return_value=dedup_result)

        # Second session: job creation
        create_session = _mock_session()

        mock_get_session.side_effect = [dedup_session, create_session]

        result = await schedule_recurring_job(
            owner_id=123,
            message="Good morning!",
            recurrence_type="daily",
            recurrence_rule="09:00",
            reason="daily check-in",
        )
        assert result.job_id
        assert len(result.job_id) == 8
        assert result.is_duplicate is False
        create_session.add.assert_called_once()
        # Verify the model was created with correct recurrence fields
        added_model = create_session.add.call_args[0][0]
        assert added_model.recurrence_type == "daily"
        assert added_model.recurrence_rule == "09:00"
        assert added_model.is_active is True

    @patch("src.core.db.session.get_session")
    async def test_rejects_invalid_recurrence_type(
        self, mock_get_session: MagicMock
    ) -> None:
        with pytest.raises(ValueError, match="Invalid recurrence_type"):
            await schedule_recurring_job(
                owner_id=123,
                message="test",
                recurrence_type="hourly",
                recurrence_rule="09:00",
            )

    @patch("src.core.db.session.get_session")
    async def test_dedup_returns_existing_recurring(
        self, mock_get_session: MagicMock
    ) -> None:
        """Scheduling an identical recurring job returns the existing job_id."""
        existing_job = MagicMock()
        existing_job.job_id = "rec_exist"

        dedup_session = _mock_session()
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = existing_job
        dedup_session.execute = AsyncMock(return_value=dedup_result)
        mock_get_session.return_value = dedup_session

        result = await schedule_recurring_job(
            owner_id=123,
            message="Good morning!",
            recurrence_type="daily",
            recurrence_rule="09:00",
        )
        assert result.job_id == "rec_exist"
        assert result.is_duplicate is True
        dedup_session.add.assert_not_called()


# ===========================================================================
# get_pending_jobs
# ===========================================================================


@pytest.mark.asyncio
class TestGetPendingJobs:
    """Validate pending job retrieval."""

    @patch("src.core.db.session.get_session")
    async def test_returns_pending_jobs(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        mock_job = MagicMock()
        mock_job.job_id = "abc12345"
        mock_job.message = "test"
        mock_job.fire_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"
        mock_job.reason = "test reason"
        mock_job.recurrence_type = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        pending = await get_pending_jobs(123)
        assert len(pending) == 1
        assert pending[0]["job_id"] == "abc12345"
        assert pending[0]["type"] == "one_shot"

    @patch("src.core.db.session.get_session")
    async def test_returns_recurring_jobs(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        mock_job = MagicMock()
        mock_job.job_id = "rec12345"
        mock_job.message = "daily check"
        mock_job.reason = "daily"
        mock_job.recurrence_type = "daily"
        mock_job.recurrence_rule = "09:00"
        mock_job.next_fire_at.isoformat.return_value = "2026-03-02T09:00:00+00:00"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        pending = await get_pending_jobs(123)
        assert len(pending) == 1
        assert pending[0]["type"] == "recurring"
        assert pending[0]["recurrence_type"] == "daily"


# ===========================================================================
# cancel_job
# ===========================================================================


@pytest.mark.asyncio
class TestCancelJob:
    """Validate job cancellation."""

    @patch("src.core.db.session.get_session")
    async def test_cancel_existing_oneshot(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        mock_job = MagicMock()
        mock_job.executed = False
        mock_job.recurrence_type = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await cancel_job("abc12345")
        assert result is True
        assert mock_job.executed is True
        mock_session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_cancel_recurring_sets_inactive(
        self, mock_get_session: MagicMock
    ) -> None:
        mock_session = _mock_session()

        mock_job = MagicMock()
        mock_job.recurrence_type = "daily"
        mock_job.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await cancel_job("rec12345")
        assert result is True
        assert mock_job.is_active is False
        mock_session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_cancel_nonexistent_job(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await cancel_job("nonexistent")
        assert result is False

    @patch("src.core.db.session.get_session")
    async def test_cancel_already_executed(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        mock_job = MagicMock()
        mock_job.executed = True
        mock_job.recurrence_type = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await cancel_job("done123")
        assert result is False


# ===========================================================================
# restore_pending_jobs
# ===========================================================================


@pytest.mark.asyncio
class TestRestorePendingJobs:
    """Validate restore on bot restart."""

    @patch("src.core.db.session.get_session")
    async def test_skips_past_due(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        past_job = MagicMock()
        past_job.job_id = "past123"
        past_job.fire_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        past_job.executed = False
        past_job.recurrence_type = None

        # Two calls: first for one-shots, second for recurring
        oneshot_result = MagicMock()
        oneshot_result.scalars.return_value.all.return_value = [past_job]
        recurring_result = MagicMock()
        recurring_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[oneshot_result, recurring_result])
        mock_get_session.return_value = mock_session

        restored = await restore_pending_jobs()
        assert restored == 0
        assert past_job.executed is True
        mock_session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_restores_future_job(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        future_job = MagicMock()
        future_job.job_id = "future1"
        future_job.fire_at = datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(hours=1)
        future_job.executed = False
        future_job.recurrence_type = None

        oneshot_result = MagicMock()
        oneshot_result.scalars.return_value.all.return_value = [future_job]
        recurring_result = MagicMock()
        recurring_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[oneshot_result, recurring_result])
        mock_get_session.return_value = mock_session

        restored = await restore_pending_jobs()
        assert restored == 1

    @patch("src.core.db.session.get_session")
    async def test_restores_recurring_job(self, mock_get_session: MagicMock) -> None:
        mock_session = _mock_session()

        rec_job = MagicMock()
        rec_job.job_id = "rec123"
        rec_job.recurrence_type = "daily"
        rec_job.recurrence_rule = "09:00"
        rec_job.is_active = True
        rec_job.next_fire_at = datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(hours=2)
        rec_job.fire_at = rec_job.next_fire_at

        oneshot_result = MagicMock()
        oneshot_result.scalars.return_value.all.return_value = []
        recurring_result = MagicMock()
        recurring_result.scalars.return_value.all.return_value = [rec_job]

        mock_session.execute = AsyncMock(side_effect=[oneshot_result, recurring_result])
        mock_get_session.return_value = mock_session

        restored = await restore_pending_jobs()
        assert restored == 1

    @patch("src.core.scheduled.jobs.compute_next_fire_at")
    @patch("src.core.db.session.get_session")
    async def test_restores_recurring_recomputes_missed(
        self, mock_get_session: MagicMock, mock_compute: MagicMock
    ) -> None:
        mock_session = _mock_session()

        future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            hours=1
        )
        mock_compute.return_value = future_time

        rec_job = MagicMock()
        rec_job.job_id = "rec_past"
        rec_job.recurrence_type = "daily"
        rec_job.recurrence_rule = "09:00"
        rec_job.is_active = True
        rec_job.next_fire_at = datetime.datetime(
            2020, 1, 1, tzinfo=datetime.timezone.utc
        )
        rec_job.fire_at = rec_job.next_fire_at

        oneshot_result = MagicMock()
        oneshot_result.scalars.return_value.all.return_value = []
        recurring_result = MagicMock()
        recurring_result.scalars.return_value.all.return_value = [rec_job]

        mock_session.execute = AsyncMock(side_effect=[oneshot_result, recurring_result])
        mock_get_session.return_value = mock_session

        restored = await restore_pending_jobs()
        assert restored == 1
        mock_compute.assert_called_once()
        assert rec_job.next_fire_at == future_time


# ===========================================================================
# _deliver_scheduled_message
# ===========================================================================


@pytest.mark.asyncio
class TestDeliverScheduledMessage:
    """Validate delivery callback behaviour."""

    @patch("src.core.scheduled.jobs._generate_job_message", new_callable=AsyncMock)
    @patch("src.core.db.session.get_session")
    async def test_oneshot_delivery_marks_executed(
        self, mock_get_session: MagicMock, mock_gen: AsyncMock
    ) -> None:
        mock_gen.return_value = "Generated hello!"
        mock_session = _mock_session()

        mock_job = MagicMock()
        mock_job.job_id = "del123"
        mock_job.owner_id = 42
        mock_job.message = "Hello!"
        mock_job.executed = False
        mock_job.recurrence_type = None
        mock_job.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        ctx = MagicMock()
        ctx.job.data = "del123"
        ctx.bot.send_message = AsyncMock()

        await _deliver_scheduled_message(ctx)

        mock_gen.assert_called_once()
        snap = mock_gen.call_args[0][0]
        assert snap.job_id == "del123"
        assert snap.message == "Hello!"
        ctx.bot.send_message.assert_called_once()
        assert mock_job.executed is True

    @patch("src.core.scheduled.jobs._generate_job_message", new_callable=AsyncMock)
    @patch("src.core.scheduled.jobs._register_with_job_queue")
    @patch("src.core.scheduled.jobs.compute_next_fire_at")
    @patch("src.core.db.session.get_session")
    async def test_recurring_delivery_reregisters(
        self,
        mock_get_session: MagicMock,
        mock_compute: MagicMock,
        mock_register: MagicMock,
        mock_gen: AsyncMock,
    ) -> None:
        mock_gen.return_value = "Fresh daily reminder!"
        mock_session = _mock_session()

        future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            hours=24
        )
        mock_compute.return_value = future_time

        mock_job = MagicMock()
        mock_job.job_id = "rec_del"
        mock_job.owner_id = 42
        mock_job.message = "Daily reminder"
        mock_job.executed = False
        mock_job.recurrence_type = "daily"
        mock_job.recurrence_rule = "09:00"
        mock_job.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        ctx = MagicMock()
        ctx.job.data = "rec_del"
        ctx.bot.send_message = AsyncMock()

        await _deliver_scheduled_message(ctx)

        mock_gen.assert_called_once()
        snap = mock_gen.call_args[0][0]
        assert snap.job_id == "rec_del"
        assert snap.message == "Daily reminder"
        ctx.bot.send_message.assert_called_once()
        mock_compute.assert_called_once()
        mock_register.assert_called_once()
        assert mock_job.next_fire_at == future_time
        # Recurring job should store last_response
        assert mock_job.last_response == "Fresh daily reminder!"
        # Recurring job should NOT set executed=True
        assert mock_job.executed is False  # not changed from initial False


# ===========================================================================
# _generate_job_message
# ===========================================================================


@pytest.mark.asyncio
class TestGenerateJobMessage:
    """Validate LLM-based message generation for scheduled jobs."""

    @patch("src.core.llm.interface.provider_supports_tools", return_value=False)
    @patch("src.core.llm.interface.generate_chat", new_callable=AsyncMock)
    async def test_generates_fresh_response(
        self, mock_chat: AsyncMock, _mock_pst: MagicMock
    ) -> None:
        mock_chat.return_value = "Hey! Time to stretch."

        job = MagicMock()
        job.job_id = "gen123"
        job.message = "Remind me to stretch"
        job.reason = "wellness"
        job.recurrence_type = None
        job.last_response = None

        result = await _generate_job_message(job)
        assert result == "Hey! Time to stretch."
        mock_chat.assert_called_once()

        # Verify the messages structure
        messages = mock_chat.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert "wellness" in messages[0]["content"]
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Remind me to stretch"

    @patch("src.core.llm.interface.provider_supports_tools", return_value=False)
    @patch("src.core.llm.interface.generate_chat", new_callable=AsyncMock)
    async def test_includes_last_response_for_recurring(
        self, mock_chat: AsyncMock, _mock_pst: MagicMock
    ) -> None:
        mock_chat.return_value = "A new daily message!"

        job = MagicMock()
        job.job_id = "rec_gen"
        job.message = "Daily motivation"
        job.reason = ""
        job.recurrence_type = "daily"
        job.last_response = "Yesterday's motivation text"

        result = await _generate_job_message(job)
        assert result == "A new daily message!"

        messages = mock_chat.call_args[0][0]
        # Should include previous response as context
        prev_msg = [m for m in messages if "previous" in m.get("content", "").lower()]
        assert len(prev_msg) == 1
        assert "Yesterday's motivation text" in prev_msg[0]["content"]

    @patch("src.core.llm.interface.generate_chat", new_callable=AsyncMock)
    async def test_fallback_on_llm_failure(self, mock_chat: AsyncMock) -> None:
        mock_chat.side_effect = RuntimeError("LLM down")

        job = MagicMock()
        job.job_id = "fail1"
        job.message = "Fallback text"
        job.reason = ""
        job.recurrence_type = None
        job.last_response = None

        result = await _generate_job_message(job)
        assert result == "Fallback text"

    @patch("src.core.llm.interface.generate_chat", new_callable=AsyncMock)
    async def test_fallback_on_empty_response(self, mock_chat: AsyncMock) -> None:
        mock_chat.return_value = "   "

        job = MagicMock()
        job.job_id = "empty1"
        job.message = "Fallback text"
        job.reason = ""
        job.recurrence_type = None
        job.last_response = None

        result = await _generate_job_message(job)
        assert result == "Fallback text"


# ===========================================================================
# Job handler commands
# ===========================================================================


@pytest.mark.asyncio
class TestJobHandlers:
    """Validate Telegram command handlers for jobs."""

    @patch("src.handlers.jobs.get_pending_jobs", new_callable=AsyncMock)
    async def test_jobs_handler_empty(self, mock_get: AsyncMock) -> None:
        from src.handlers.jobs import jobs_handler

        mock_get.return_value = []

        update = MagicMock()
        update.effective_user.id = 0
        update.message.reply_text = AsyncMock()
        context = MagicMock()

        with patch("src.handlers.jobs.reject_non_owner", new_callable=AsyncMock) as rno:
            rno.return_value = False
            await jobs_handler(update, context)

        update.message.reply_text.assert_called_once_with("No scheduled jobs.")

    @patch("src.handlers.jobs.cancel_job", new_callable=AsyncMock)
    async def test_cancel_handler_success(self, mock_cancel: AsyncMock) -> None:
        from src.handlers.jobs import cancel_handler

        mock_cancel.return_value = True

        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["abc123"]

        with patch("src.handlers.jobs.reject_non_owner", new_callable=AsyncMock) as rno:
            rno.return_value = False
            await cancel_handler(update, context)

        update.message.reply_text.assert_called_once_with("Job abc123 cancelled.")

    @patch("src.handlers.jobs.schedule_llm_job", new_callable=AsyncMock)
    async def test_schedule_handler_creates_job(self, mock_schedule: AsyncMock) -> None:
        from src.handlers.jobs import schedule_handler

        mock_schedule.return_value = ScheduleResult("newjob01", is_duplicate=False)

        update = MagicMock()
        update.effective_user.id = 42
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["30", "Take", "a", "break"]

        with patch("src.handlers.jobs.reject_non_owner", new_callable=AsyncMock) as rno:
            rno.return_value = False
            await schedule_handler(update, context)

        mock_schedule.assert_called_once_with(
            owner_id=42,
            message="Take a break",
            delay_minutes=30,
            reason="user_command",
        )
        update.message.reply_text.assert_called_once()

    @patch("src.handlers.jobs.schedule_llm_job", new_callable=AsyncMock)
    async def test_schedule_handler_rejects_bad_minutes(
        self, mock_schedule: AsyncMock
    ) -> None:
        from src.handlers.jobs import schedule_handler

        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["abc", "hello"]

        with patch("src.handlers.jobs.reject_non_owner", new_callable=AsyncMock) as rno:
            rno.return_value = False
            await schedule_handler(update, context)

        mock_schedule.assert_not_called()
        update.message.reply_text.assert_called_once_with(
            "First argument must be a number (minutes)."
        )
