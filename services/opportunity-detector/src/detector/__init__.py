"""Opportunity detection module."""

from src.detector.manager import OpportunityDetector
from src.detector.scorer import UOSScorer
from src.detector.forecaster import (
    SpreadForecaster,
    SpreadForecast,
    SeasonalityAnalysis,
    MeanReversionSignal,
    ForecastConfidence,
    SeasonalityPattern,
    spread_forecaster,
    forecast_spread,
    detect_seasonality,
    mean_reversion_signal,
    get_optimal_entry_timing,
)

__all__ = [
    "OpportunityDetector",
    "UOSScorer",
    # Forecaster
    "SpreadForecaster",
    "SpreadForecast",
    "SeasonalityAnalysis",
    "MeanReversionSignal",
    "ForecastConfidence",
    "SeasonalityPattern",
    "spread_forecaster",
    "forecast_spread",
    "detect_seasonality",
    "mean_reversion_signal",
    "get_optimal_entry_timing",
]
