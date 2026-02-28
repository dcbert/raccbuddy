"""Tests for src.core.agentic.__init__ (public API)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.agentic import init_agentic, shutdown_agentic


class TestInitAgentic:
    """Validate init and shutdown lifecycle."""

    @pytest.mark.asyncio
    async def test_noop_when_disabled(self) -> None:
        with patch("src.core.agentic.settings") as mock_settings:
            mock_settings.agentic_enabled = False
            await init_agentic()
            await shutdown_agentic()

    @pytest.mark.asyncio
    async def test_calls_subsystems_when_enabled(self) -> None:
        with (
            patch("src.core.agentic.settings") as mock_settings,
            patch(
                "src.core.agentic.tracing.init_tracing",
                new_callable=AsyncMock,
            ) as mock_trace,
            patch(
                "src.core.agentic.metrics.init_metrics",
                new_callable=AsyncMock,
            ) as mock_metrics,
            patch(
                "src.core.agentic.engine.init_engine",
                new_callable=AsyncMock,
            ) as mock_engine,
        ):
            mock_settings.agentic_enabled = True
            await init_agentic()
            mock_trace.assert_called_once()
            mock_metrics.assert_called_once()
            mock_engine.assert_called_once()
