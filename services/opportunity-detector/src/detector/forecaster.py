"""
Spread Forecasting Module.

Provides spread prediction, seasonality detection, and mean reversion signals
to enhance opportunity scoring and timing decisions.

Key features:
- Forecast future spread values using exponential smoothing
- Detect 8-hour funding cycle seasonality
- Generate mean reversion trading signals
- Confidence intervals for predictions
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from shared.utils.logging import get_logger

logger = get_logger(__name__)


class ForecastConfidence(str, Enum):
    """Confidence level of forecast."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class SeasonalityPattern(str, Enum):
    """Detected seasonality pattern."""
    FUNDING_8H = "funding_8h"  # 8-hour funding cycle
    FUNDING_1H = "funding_1h"  # 1-hour funding (Hyperliquid, dYdX)
    DAILY = "daily"  # 24-hour pattern
    NONE = "none"
    UNKNOWN = "unknown"


@dataclass
class SpreadForecast:
    """Result of spread forecasting."""
    predicted_spread: float
    lower_bound: float  # Lower confidence interval
    upper_bound: float  # Upper confidence interval
    confidence: ForecastConfidence
    horizon_hours: float
    forecast_time: datetime
    method: str  # Forecasting method used
    error_estimate: float  # Estimated prediction error


@dataclass
class SeasonalityAnalysis:
    """Result of seasonality detection."""
    pattern: SeasonalityPattern
    period_hours: float
    amplitude: float  # Strength of seasonal component
    phase_hours: float  # Current position in cycle
    next_peak_hours: float  # Hours until next seasonal peak
    next_trough_hours: float  # Hours until next seasonal trough
    confidence: float  # 0.0 to 1.0


@dataclass
class MeanReversionSignal:
    """Mean reversion trading signal."""
    signal: bool
    direction: str  # "up" (spread expected to increase) or "down" (expected to decrease)
    z_score: float
    current_spread: float
    mean_spread: float
    std_dev: float
    expected_reversion: float  # Expected spread after reversion
    confidence: float  # 0.0 to 1.0
    reason: str


class SpreadForecaster:
    """
    Forecasts future spread values for arbitrage opportunities.

    Uses multiple techniques:
    - Exponential smoothing for short-term prediction
    - Seasonality decomposition for funding cycles
    - Mean reversion detection for trading signals
    """

    # Configuration
    MIN_DATA_POINTS = 6  # Minimum points for forecasting
    MIN_SEASONALITY_POINTS = 24  # Minimum for seasonality detection
    Z_SCORE_THRESHOLD = 2.0  # Threshold for mean reversion signal

    # Funding cycle periods (hours)
    FUNDING_PERIOD_8H = 8.0
    FUNDING_PERIOD_1H = 1.0

    def __init__(self):
        # Historical spread data: {pair_key: [(timestamp, spread), ...]}
        self._spread_history: dict[str, list[tuple[datetime, float]]] = {}
        self._history_max_length = 500  # Keep last 500 observations

        # Cache for computed forecasts
        self._forecast_cache: dict[str, tuple[datetime, SpreadForecast]] = {}
        self._cache_ttl = timedelta(seconds=30)

        # Seasonality cache
        self._seasonality_cache: dict[str, tuple[datetime, SeasonalityAnalysis]] = {}
        self._seasonality_cache_ttl = timedelta(minutes=5)

    def add_spread_observation(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        spread: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Add a spread observation to history.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange
            spread: Current spread value
            timestamp: Observation timestamp (defaults to now)
        """
        key = self._make_pair_key(symbol, long_exchange, short_exchange)

        if key not in self._spread_history:
            self._spread_history[key] = []

        ts = timestamp or datetime.utcnow()
        self._spread_history[key].append((ts, spread))

        # Trim to max length
        if len(self._spread_history[key]) > self._history_max_length:
            self._spread_history[key] = self._spread_history[key][-self._history_max_length:]

    def forecast_spread(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        horizon_hours: float = 8.0,
    ) -> SpreadForecast:
        """
        Forecast future spread value.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange
            horizon_hours: Prediction horizon in hours

        Returns:
            SpreadForecast with prediction and confidence intervals
        """
        key = self._make_pair_key(symbol, long_exchange, short_exchange)

        # Check cache
        if key in self._forecast_cache:
            cached_time, cached_forecast = self._forecast_cache[key]
            if (datetime.utcnow() - cached_time < self._cache_ttl and
                abs(cached_forecast.horizon_hours - horizon_hours) < 0.5):
                return cached_forecast

        history = self._spread_history.get(key, [])

        # Insufficient data case
        if len(history) < self.MIN_DATA_POINTS:
            current = history[-1][1] if history else 0.0
            return SpreadForecast(
                predicted_spread=current,
                lower_bound=current,
                upper_bound=current,
                confidence=ForecastConfidence.INSUFFICIENT_DATA,
                horizon_hours=horizon_hours,
                forecast_time=datetime.utcnow() + timedelta(hours=horizon_hours),
                method="constant",
                error_estimate=0.0,
            )

        spreads = [s for _, s in history]

        # Use exponential smoothing
        forecast = self._exponential_smoothing_forecast(spreads, horizon_hours)

        # Calculate confidence intervals
        std_dev = self._calculate_std_dev(spreads)
        error_multiplier = 1 + (horizon_hours / 8) * 0.5  # Error grows with horizon
        error_estimate = std_dev * error_multiplier

        # Determine confidence level
        n_points = len(spreads)
        if n_points >= 48 and std_dev < abs(forecast) * 0.3:
            confidence = ForecastConfidence.HIGH
        elif n_points >= 12:
            confidence = ForecastConfidence.MEDIUM
        else:
            confidence = ForecastConfidence.LOW

        result = SpreadForecast(
            predicted_spread=forecast,
            lower_bound=forecast - 1.96 * error_estimate,
            upper_bound=forecast + 1.96 * error_estimate,
            confidence=confidence,
            horizon_hours=horizon_hours,
            forecast_time=datetime.utcnow() + timedelta(hours=horizon_hours),
            method="exponential_smoothing",
            error_estimate=error_estimate,
        )

        # Cache result
        self._forecast_cache[key] = (datetime.utcnow(), result)

        return result

    def detect_seasonality(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
    ) -> SeasonalityAnalysis:
        """
        Detect seasonality pattern in spread data.

        Identifies 8-hour funding cycles or other periodic patterns.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange

        Returns:
            SeasonalityAnalysis with pattern information
        """
        key = self._make_pair_key(symbol, long_exchange, short_exchange)

        # Check cache
        if key in self._seasonality_cache:
            cached_time, cached_analysis = self._seasonality_cache[key]
            if datetime.utcnow() - cached_time < self._seasonality_cache_ttl:
                return cached_analysis

        history = self._spread_history.get(key, [])

        # Insufficient data
        if len(history) < self.MIN_SEASONALITY_POINTS:
            return SeasonalityAnalysis(
                pattern=SeasonalityPattern.UNKNOWN,
                period_hours=0.0,
                amplitude=0.0,
                phase_hours=0.0,
                next_peak_hours=0.0,
                next_trough_hours=0.0,
                confidence=0.0,
            )

        # Analyze for 8-hour cycle (most common for funding)
        analysis_8h = self._analyze_periodicity(history, self.FUNDING_PERIOD_8H)
        analysis_1h = self._analyze_periodicity(history, self.FUNDING_PERIOD_1H)

        # Select strongest pattern
        if analysis_8h["strength"] > analysis_1h["strength"] and analysis_8h["strength"] > 0.3:
            pattern = SeasonalityPattern.FUNDING_8H
            period = self.FUNDING_PERIOD_8H
            analysis = analysis_8h
        elif analysis_1h["strength"] > 0.3:
            pattern = SeasonalityPattern.FUNDING_1H
            period = self.FUNDING_PERIOD_1H
            analysis = analysis_1h
        else:
            pattern = SeasonalityPattern.NONE
            period = 0.0
            analysis = {"strength": 0.0, "phase": 0.0, "amplitude": 0.0}

        # Calculate time to next peak/trough
        if period > 0:
            phase = analysis["phase"]
            next_peak = (period - phase) % period
            next_trough = (period / 2 - phase) % period
        else:
            next_peak = 0.0
            next_trough = 0.0

        result = SeasonalityAnalysis(
            pattern=pattern,
            period_hours=period,
            amplitude=analysis["amplitude"],
            phase_hours=analysis["phase"],
            next_peak_hours=next_peak,
            next_trough_hours=next_trough,
            confidence=analysis["strength"],
        )

        # Cache result
        self._seasonality_cache[key] = (datetime.utcnow(), result)

        return result

    def mean_reversion_signal(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        current_spread: Optional[float] = None,
        z_score_threshold: Optional[float] = None,
    ) -> MeanReversionSignal:
        """
        Generate mean reversion trading signal.

        Identifies when spread is significantly above or below its mean,
        suggesting reversion is likely.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange
            current_spread: Current spread (uses latest if not provided)
            z_score_threshold: Custom z-score threshold

        Returns:
            MeanReversionSignal with trading recommendation
        """
        key = self._make_pair_key(symbol, long_exchange, short_exchange)
        history = self._spread_history.get(key, [])

        threshold = z_score_threshold or self.Z_SCORE_THRESHOLD

        # Insufficient data
        if len(history) < self.MIN_DATA_POINTS * 2:
            return MeanReversionSignal(
                signal=False,
                direction="none",
                z_score=0.0,
                current_spread=current_spread or 0.0,
                mean_spread=0.0,
                std_dev=0.0,
                expected_reversion=0.0,
                confidence=0.0,
                reason="Insufficient historical data",
            )

        spreads = [s for _, s in history]

        # Use current spread or latest observation
        current = current_spread if current_spread is not None else spreads[-1]

        # Calculate statistics
        mean = sum(spreads) / len(spreads)
        std_dev = self._calculate_std_dev(spreads)

        if std_dev == 0:
            return MeanReversionSignal(
                signal=False,
                direction="none",
                z_score=0.0,
                current_spread=current,
                mean_spread=mean,
                std_dev=0.0,
                expected_reversion=mean,
                confidence=0.0,
                reason="Zero volatility - no reversion expected",
            )

        # Calculate z-score
        z_score = (current - mean) / std_dev

        # Generate signal
        signal = abs(z_score) > threshold

        if z_score > threshold:
            direction = "down"  # Spread above mean, expect decrease
            expected_reversion = mean + std_dev  # Partial reversion
            reason = f"Spread {z_score:.2f}σ above mean - expecting decrease"
        elif z_score < -threshold:
            direction = "up"  # Spread below mean, expect increase
            expected_reversion = mean - std_dev
            reason = f"Spread {abs(z_score):.2f}σ below mean - expecting increase"
        else:
            direction = "none"
            expected_reversion = mean
            reason = f"Spread within {threshold}σ of mean - no signal"

        # Confidence based on data quantity and consistency
        data_confidence = min(len(spreads) / 100, 1.0)
        z_confidence = min(abs(z_score) / 3.0, 1.0) if signal else 0.0
        confidence = data_confidence * (0.5 + 0.5 * z_confidence)

        return MeanReversionSignal(
            signal=signal,
            direction=direction,
            z_score=z_score,
            current_spread=current,
            mean_spread=mean,
            std_dev=std_dev,
            expected_reversion=expected_reversion,
            confidence=confidence,
            reason=reason,
        )

    def get_optimal_entry_timing(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
    ) -> dict[str, Any]:
        """
        Determine optimal entry timing based on seasonality and mean reversion.

        Returns:
            Dict with timing recommendations
        """
        seasonality = self.detect_seasonality(symbol, long_exchange, short_exchange)
        mean_reversion = self.mean_reversion_signal(symbol, long_exchange, short_exchange)

        # Default recommendation
        recommendation = "neutral"
        wait_hours = 0.0
        reasons = []

        # Check mean reversion signal
        if mean_reversion.signal:
            if mean_reversion.direction == "down":
                # Spread is high - might want to wait
                recommendation = "wait"
                wait_hours = 2.0  # Wait for reversion
                reasons.append(f"Spread elevated ({mean_reversion.z_score:.1f}σ above mean)")
            else:
                # Spread is low - good entry
                recommendation = "enter"
                reasons.append(f"Spread depressed ({abs(mean_reversion.z_score):.1f}σ below mean)")

        # Check seasonality timing
        if seasonality.pattern != SeasonalityPattern.NONE:
            if seasonality.next_peak_hours < 2.0:
                # Peak coming soon
                if recommendation != "wait":
                    recommendation = "enter_soon"
                    reasons.append(f"Funding peak in {seasonality.next_peak_hours:.1f}h")
            elif seasonality.next_trough_hours < 2.0:
                # Trough coming - might want to wait
                recommendation = "wait"
                wait_hours = max(wait_hours, seasonality.next_trough_hours + 1.0)
                reasons.append(f"Funding trough in {seasonality.next_trough_hours:.1f}h")

        # Calculate confidence
        confidence = (
            seasonality.confidence * 0.4 +
            mean_reversion.confidence * 0.6
        )

        return {
            "recommendation": recommendation,
            "wait_hours": wait_hours,
            "reasons": reasons,
            "seasonality": {
                "pattern": seasonality.pattern.value,
                "next_peak_hours": seasonality.next_peak_hours,
                "next_trough_hours": seasonality.next_trough_hours,
            },
            "mean_reversion": {
                "signal": mean_reversion.signal,
                "direction": mean_reversion.direction,
                "z_score": mean_reversion.z_score,
            },
            "confidence": confidence,
        }

    def _make_pair_key(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
    ) -> str:
        """Create a unique key for a spread pair."""
        return f"{symbol}:{long_exchange}:{short_exchange}"

    def _exponential_smoothing_forecast(
        self,
        values: list[float],
        horizon_hours: float,
        alpha: float = 0.3,
    ) -> float:
        """
        Simple exponential smoothing forecast.

        Args:
            values: Historical values
            horizon_hours: Forecast horizon
            alpha: Smoothing factor (0 to 1)

        Returns:
            Forecasted value
        """
        if not values:
            return 0.0

        # Initialize with first value
        smoothed = values[0]

        # Apply exponential smoothing
        for value in values[1:]:
            smoothed = alpha * value + (1 - alpha) * smoothed

        # For multi-step forecast, the point forecast is the last smoothed value
        # (simple ES produces flat forecasts)
        return smoothed

    def _calculate_std_dev(self, values: list[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _analyze_periodicity(
        self,
        history: list[tuple[datetime, float]],
        period_hours: float,
    ) -> dict[str, float]:
        """
        Analyze data for periodicity at a given frequency.

        Uses autocorrelation to detect periodic patterns.

        Returns:
            Dict with strength, phase, and amplitude of periodic component
        """
        if len(history) < self.MIN_SEASONALITY_POINTS:
            return {"strength": 0.0, "phase": 0.0, "amplitude": 0.0}

        spreads = [s for _, s in history]
        timestamps = [ts for ts, _ in history]

        # Calculate mean and center the data
        mean = sum(spreads) / len(spreads)
        centered = [s - mean for s in spreads]

        # Estimate samples per period based on average time between observations
        if len(timestamps) >= 2:
            total_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
            avg_interval_hours = total_hours / (len(timestamps) - 1)
            samples_per_period = int(period_hours / avg_interval_hours) if avg_interval_hours > 0 else 0
        else:
            samples_per_period = 0

        if samples_per_period < 2 or samples_per_period >= len(centered):
            return {"strength": 0.0, "phase": 0.0, "amplitude": 0.0}

        # Calculate autocorrelation at lag = samples_per_period
        n = len(centered)
        lag = samples_per_period

        # Autocorrelation
        numerator = sum(centered[i] * centered[i + lag] for i in range(n - lag))
        denominator = sum(c ** 2 for c in centered)

        if denominator == 0:
            return {"strength": 0.0, "phase": 0.0, "amplitude": 0.0}

        autocorr = numerator / denominator

        # Strength is absolute autocorrelation (0 to 1)
        strength = max(0, min(abs(autocorr), 1.0))

        # Estimate amplitude (half the range of periodic component)
        amplitude = (max(spreads) - min(spreads)) / 2 * strength

        # Estimate phase (hours into current cycle)
        if timestamps:
            latest = timestamps[-1]
            hours_of_day = latest.hour + latest.minute / 60
            phase = hours_of_day % period_hours
        else:
            phase = 0.0

        return {
            "strength": strength,
            "phase": phase,
            "amplitude": amplitude,
        }

    def clear_history(self, symbol: Optional[str] = None) -> None:
        """Clear spread history."""
        if symbol:
            # Clear for specific symbol
            keys_to_remove = [k for k in self._spread_history if k.startswith(f"{symbol}:")]
            for key in keys_to_remove:
                del self._spread_history[key]
        else:
            # Clear all
            self._spread_history.clear()

        self._forecast_cache.clear()
        self._seasonality_cache.clear()

    def get_history_stats(self, symbol: str, long_exchange: str, short_exchange: str) -> dict[str, Any]:
        """Get statistics about stored history for a pair."""
        key = self._make_pair_key(symbol, long_exchange, short_exchange)
        history = self._spread_history.get(key, [])

        if not history:
            return {
                "count": 0,
                "oldest": None,
                "newest": None,
                "mean": None,
                "std_dev": None,
                "min": None,
                "max": None,
            }

        spreads = [s for _, s in history]
        timestamps = [ts for ts, _ in history]

        return {
            "count": len(history),
            "oldest": timestamps[0].isoformat(),
            "newest": timestamps[-1].isoformat(),
            "mean": sum(spreads) / len(spreads),
            "std_dev": self._calculate_std_dev(spreads),
            "min": min(spreads),
            "max": max(spreads),
        }


# Singleton instance
spread_forecaster = SpreadForecaster()


# Convenience functions
def forecast_spread(
    symbol: str,
    long_exchange: str,
    short_exchange: str,
    horizon_hours: float = 8.0,
) -> SpreadForecast:
    """Convenience function to forecast spread."""
    return spread_forecaster.forecast_spread(symbol, long_exchange, short_exchange, horizon_hours)


def detect_seasonality(
    symbol: str,
    long_exchange: str,
    short_exchange: str,
) -> SeasonalityAnalysis:
    """Convenience function to detect seasonality."""
    return spread_forecaster.detect_seasonality(symbol, long_exchange, short_exchange)


def mean_reversion_signal(
    symbol: str,
    long_exchange: str,
    short_exchange: str,
    current_spread: Optional[float] = None,
) -> MeanReversionSignal:
    """Convenience function for mean reversion signal."""
    return spread_forecaster.mean_reversion_signal(
        symbol, long_exchange, short_exchange, current_spread
    )


def get_optimal_entry_timing(
    symbol: str,
    long_exchange: str,
    short_exchange: str,
) -> dict[str, Any]:
    """Convenience function for optimal entry timing."""
    return spread_forecaster.get_optimal_entry_timing(symbol, long_exchange, short_exchange)
