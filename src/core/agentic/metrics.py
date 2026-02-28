"""Optional Prometheus metrics for the agentic subsystem.

When ``settings.prometheus_enabled`` is ``True``, this module exposes
counters and histograms that track agentic cycle performance.
When disabled, all metric objects are no-op stubs.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.config import settings

logger = logging.getLogger(__name__)

_server: Any = None


# ---------------------------------------------------------------------------
# Metric stubs (replaced with real Prometheus objects when enabled)
# ---------------------------------------------------------------------------


class _NoOpMetric:
    """No-op stand-in when Prometheus is disabled."""

    def inc(self, amount: float = 1) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def labels(self, **kwargs: Any) -> "_NoOpMetric":
        return self


cycles_total: Any = _NoOpMetric()
nudges_approved_total: Any = _NoOpMetric()
nudges_discarded_total: Any = _NoOpMetric()
cycle_duration_seconds: Any = _NoOpMetric()
cycle_errors_total: Any = _NoOpMetric()


async def init_metrics() -> None:
    """Initialize Prometheus metrics and start the HTTP server."""
    global cycles_total, nudges_approved_total, nudges_discarded_total  # noqa: PLW0603
    global cycle_duration_seconds, cycle_errors_total, _server  # noqa: PLW0603

    if not settings.prometheus_enabled:
        logger.debug("Prometheus metrics disabled")
        return

    try:
        from prometheus_client import Counter, Histogram, start_http_server

        cycles_total = Counter(
            "raccbuddy_agentic_cycles_total",
            "Total agentic cycles executed",
        )
        nudges_approved_total = Counter(
            "raccbuddy_agentic_nudges_approved_total",
            "Nudges approved by the Reflector",
        )
        nudges_discarded_total = Counter(
            "raccbuddy_agentic_nudges_discarded_total",
            "Nudges discarded by the Reflector",
        )
        cycle_duration_seconds = Histogram(
            "raccbuddy_agentic_cycle_duration_seconds",
            "Duration of a single agentic cycle",
            buckets=[1, 5, 10, 30, 60, 120],
        )
        cycle_errors_total = Counter(
            "raccbuddy_agentic_cycle_errors_total",
            "Agentic cycles that ended in error",
        )

        start_http_server(settings.prometheus_port)
        logger.info(
            "Prometheus metrics server started on port %d",
            settings.prometheus_port,
        )
    except ImportError:
        logger.warning(
            "prometheus_client package not installed — metrics disabled. "
            "Install with: pip install prometheus-client"
        )
    except Exception:
        logger.exception("Failed to initialize Prometheus metrics")


async def shutdown_metrics() -> None:
    """Shut down the Prometheus metrics server (no-op currently)."""
    logger.debug("Prometheus metrics shutdown (no-op)")
