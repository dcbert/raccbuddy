"""Tests for src.core.scheduled_jobs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduled import cancel_job, get_pending_jobs, schedule_llm_job, set_app_reference


@pytest.fixture(autouse=True)
def _clear_app_ref():
    """Reset app reference between tests."""
    set_app_reference(None)  # type: ignore[arg-type]
    yield


@pytest.mark.asyncio
class TestScheduleLLMJob:
    """Validate job scheduling (DB-backed)."""

    @patch("src.core.db.session.get_session")
    async def test_creates_job_and_returns_id(self, mock_get_session: MagicMock) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        job_id = await schedule_llm_job(
            owner_id=123,
            message="Check on Giulia",
            delay_minutes=60,
            reason="reminder",
        )
        assert job_id
        assert len(job_id) == 8
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_multiple_jobs_get_unique_ids(self, mock_get_session: MagicMock) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        id1 = await schedule_llm_job(123, "msg1", 30)
        id2 = await schedule_llm_job(123, "msg2", 60)
        assert id1 != id2


@pytest.mark.asyncio
class TestGetPendingJobs:
    """Validate pending job retrieval."""

    @patch("src.core.db.session.get_session")
    async def test_returns_pending_jobs(self, mock_get_session: MagicMock) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Mock DB result
        mock_job = MagicMock()
        mock_job.job_id = "abc12345"
        mock_job.message = "test"
        mock_job.fire_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"
        mock_job.reason = "test reason"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        pending = await get_pending_jobs(123)
        assert len(pending) == 1
        assert pending[0]["job_id"] == "abc12345"


@pytest.mark.asyncio
class TestCancelJob:
    """Validate job cancellation."""

    @patch("src.core.db.session.get_session")
    async def test_cancel_existing_job(self, mock_get_session: MagicMock) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_job = MagicMock()
        mock_job.executed = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await cancel_job("abc12345")
        assert result is True
        assert mock_job.executed is True
        mock_session.commit.assert_called_once()

    @patch("src.core.db.session.get_session")
    async def test_cancel_nonexistent_job(self, mock_get_session: MagicMock) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await cancel_job("nonexistent")
        assert result is False
