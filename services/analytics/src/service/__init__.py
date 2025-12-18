"""Analytics service module."""

from src.service.core import AnalyticsService
from src.service.attribution import (
    PerformanceAttribution,
    AttributionResult,
    AttributionDimension,
    CohortAnalysis,
    TimePattern,
    performance_attribution,
    get_pnl_breakdown,
    get_exchange_attribution,
    get_full_report,
)

__all__ = [
    "AnalyticsService",
    # Attribution
    "PerformanceAttribution",
    "AttributionResult",
    "AttributionDimension",
    "CohortAnalysis",
    "TimePattern",
    "performance_attribution",
    "get_pnl_breakdown",
    "get_exchange_attribution",
    "get_full_report",
]
