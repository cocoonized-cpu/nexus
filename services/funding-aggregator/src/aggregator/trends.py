"""
Funding Rate Trend Analysis Module.

Provides trend detection, volatility calculation, and simple forecasting
for funding rates to enhance opportunity scoring.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional
import math

from shared.utils.logging import get_logger

logger = get_logger(__name__)


class TrendDirection(str, Enum):
    """Direction of funding rate trend."""
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNKNOWN = "unknown"


@dataclass
class TrendAnalysis:
    """Result of trend analysis for a funding rate series."""
    direction: TrendDirection
    strength: float  # 0.0 to 1.0, how strong the trend is
    volatility: float  # Standard deviation of rates
    mean: float  # Average rate over window
    slope: float  # Rate of change per period
    r_squared: float  # Goodness of fit (0.0 to 1.0)
    prediction: Optional[float]  # Predicted next rate
    confidence: float  # Confidence in prediction (0.0 to 1.0)


class FundingRateTrendAnalyzer:
    """
    Analyzes funding rate trends for opportunity evaluation.

    Provides:
    - Trend direction detection (rising/falling/stable)
    - Volatility measurement
    - Simple linear extrapolation for prediction
    """

    # Thresholds for trend detection
    SLOPE_THRESHOLD = 0.00001  # Minimum slope to consider as trending
    STABILITY_THRESHOLD = 0.00005  # Max std dev to consider stable
    MIN_DATA_POINTS = 3  # Minimum data points for analysis

    def __init__(self):
        # Cache for recent analyses
        self._analysis_cache: dict[str, tuple[datetime, TrendAnalysis]] = {}
        self._cache_ttl = timedelta(seconds=30)

    def calculate_trend(
        self,
        rates: list[float],
        window: int = 6,
    ) -> TrendDirection:
        """
        Calculate trend direction from recent rates.

        Args:
            rates: List of funding rates (oldest first)
            window: Number of recent rates to consider

        Returns:
            TrendDirection enum
        """
        if len(rates) < self.MIN_DATA_POINTS:
            return TrendDirection.UNKNOWN

        # Use most recent window
        recent = rates[-window:] if len(rates) > window else rates

        if len(recent) < 2:
            return TrendDirection.UNKNOWN

        # Calculate slope using linear regression
        slope = self._calculate_slope(recent)

        if abs(slope) < self.SLOPE_THRESHOLD:
            return TrendDirection.STABLE
        elif slope > 0:
            return TrendDirection.RISING
        else:
            return TrendDirection.FALLING

    def calculate_volatility(self, rates: list[float]) -> float:
        """
        Calculate funding rate volatility (standard deviation).

        Args:
            rates: List of funding rates

        Returns:
            Standard deviation of rates
        """
        if len(rates) < 2:
            return 0.0

        mean = sum(rates) / len(rates)
        variance = sum((r - mean) ** 2 for r in rates) / len(rates)
        return math.sqrt(variance)

    def predict_next_rate(
        self,
        rates: list[float],
        periods_ahead: int = 1,
    ) -> Optional[float]:
        """
        Predict future funding rate using simple linear extrapolation.

        Args:
            rates: List of historical rates (oldest first)
            periods_ahead: Number of periods to predict ahead

        Returns:
            Predicted rate, or None if insufficient data
        """
        if len(rates) < self.MIN_DATA_POINTS:
            return None

        # Linear regression
        n = len(rates)
        x_values = list(range(n))
        y_values = rates

        slope, intercept = self._linear_regression(x_values, y_values)

        # Extrapolate
        future_x = n - 1 + periods_ahead
        prediction = intercept + slope * future_x

        return prediction

    def analyze(
        self,
        rates: list[float],
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> TrendAnalysis:
        """
        Perform comprehensive trend analysis.

        Args:
            rates: List of funding rates (oldest first)
            symbol: Optional symbol for caching
            exchange: Optional exchange for caching

        Returns:
            TrendAnalysis with all metrics
        """
        # Check cache
        if symbol and exchange:
            cache_key = f"{exchange}:{symbol}"
            if cache_key in self._analysis_cache:
                cached_time, cached_analysis = self._analysis_cache[cache_key]
                if datetime.utcnow() - cached_time < self._cache_ttl:
                    return cached_analysis

        # Default values for insufficient data
        if len(rates) < self.MIN_DATA_POINTS:
            return TrendAnalysis(
                direction=TrendDirection.UNKNOWN,
                strength=0.0,
                volatility=0.0,
                mean=rates[0] if rates else 0.0,
                slope=0.0,
                r_squared=0.0,
                prediction=None,
                confidence=0.0,
            )

        # Calculate metrics
        n = len(rates)
        x_values = list(range(n))
        y_values = rates

        slope, intercept = self._linear_regression(x_values, y_values)
        r_squared = self._calculate_r_squared(x_values, y_values, slope, intercept)
        volatility = self.calculate_volatility(rates)
        mean = sum(rates) / n

        # Determine direction
        if abs(slope) < self.SLOPE_THRESHOLD:
            direction = TrendDirection.STABLE
        elif slope > 0:
            direction = TrendDirection.RISING
        else:
            direction = TrendDirection.FALLING

        # Calculate trend strength (0 to 1)
        # Based on slope magnitude relative to volatility
        if volatility > 0:
            strength = min(abs(slope) / volatility, 1.0)
        else:
            strength = 1.0 if abs(slope) > self.SLOPE_THRESHOLD else 0.0

        # Predict next rate
        prediction = intercept + slope * n

        # Confidence based on r_squared and data quantity
        data_confidence = min(n / 10, 1.0)  # More data = more confidence, cap at 10
        confidence = r_squared * data_confidence

        analysis = TrendAnalysis(
            direction=direction,
            strength=strength,
            volatility=volatility,
            mean=mean,
            slope=slope,
            r_squared=r_squared,
            prediction=prediction,
            confidence=confidence,
        )

        # Cache result
        if symbol and exchange:
            self._analysis_cache[cache_key] = (datetime.utcnow(), analysis)

        return analysis

    def _calculate_slope(self, values: list[float]) -> float:
        """Calculate slope of trend line."""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x_values = list(range(n))

        slope, _ = self._linear_regression(x_values, values)
        return slope

    def _linear_regression(
        self,
        x: list[float],
        y: list[float],
    ) -> tuple[float, float]:
        """
        Calculate linear regression slope and intercept.

        Returns:
            Tuple of (slope, intercept)
        """
        n = len(x)
        if n < 2:
            return 0.0, y[0] if y else 0.0

        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_xx = sum(xi * xi for xi in x)

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return 0.0, sum_y / n

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n

        return slope, intercept

    def _calculate_r_squared(
        self,
        x: list[float],
        y: list[float],
        slope: float,
        intercept: float,
    ) -> float:
        """
        Calculate R-squared (coefficient of determination).

        Returns:
            R-squared value between 0 and 1
        """
        if len(y) < 2:
            return 0.0

        mean_y = sum(y) / len(y)

        # Total sum of squares
        ss_tot = sum((yi - mean_y) ** 2 for yi in y)

        if ss_tot == 0:
            return 1.0  # Perfect fit for constant data

        # Residual sum of squares
        ss_res = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y))

        r_squared = 1 - (ss_res / ss_tot)
        return max(0.0, r_squared)  # Clamp to non-negative

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._analysis_cache.clear()


class SpreadTrendAnalyzer:
    """
    Analyzes spread trends between exchange pairs.

    Useful for detecting mean-reverting opportunities and
    spread deterioration.
    """

    def __init__(self):
        self._rate_analyzer = FundingRateTrendAnalyzer()
        # Store historical spreads for analysis
        self._spread_history: dict[str, list[tuple[datetime, float]]] = {}
        self._history_window = 100  # Keep last 100 spreads

    def add_spread(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        spread: float,
    ) -> None:
        """
        Add a spread observation to history.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange
            spread: Spread value
        """
        key = f"{symbol}:{long_exchange}:{short_exchange}"

        if key not in self._spread_history:
            self._spread_history[key] = []

        self._spread_history[key].append((datetime.utcnow(), spread))

        # Trim to window size
        if len(self._spread_history[key]) > self._history_window:
            self._spread_history[key] = self._spread_history[key][-self._history_window:]

    def get_spread_trend(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
    ) -> TrendAnalysis:
        """
        Get trend analysis for a spread pair.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange

        Returns:
            TrendAnalysis for the spread
        """
        key = f"{symbol}:{long_exchange}:{short_exchange}"
        history = self._spread_history.get(key, [])

        if not history:
            return TrendAnalysis(
                direction=TrendDirection.UNKNOWN,
                strength=0.0,
                volatility=0.0,
                mean=0.0,
                slope=0.0,
                r_squared=0.0,
                prediction=None,
                confidence=0.0,
            )

        spreads = [spread for _, spread in history]
        return self._rate_analyzer.analyze(spreads)

    def detect_mean_reversion_signal(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        current_spread: float,
        z_score_threshold: float = 2.0,
    ) -> dict:
        """
        Detect if spread is likely to mean-revert.

        Args:
            symbol: Trading symbol
            long_exchange: Long side exchange
            short_exchange: Short side exchange
            current_spread: Current spread value
            z_score_threshold: Z-score threshold for signal

        Returns:
            Dict with signal information
        """
        key = f"{symbol}:{long_exchange}:{short_exchange}"
        history = self._spread_history.get(key, [])

        if len(history) < 10:
            return {
                "signal": False,
                "z_score": None,
                "mean": None,
                "reason": "Insufficient history",
            }

        spreads = [spread for _, spread in history]
        mean = sum(spreads) / len(spreads)
        std_dev = self._rate_analyzer.calculate_volatility(spreads)

        if std_dev == 0:
            return {
                "signal": False,
                "z_score": 0,
                "mean": mean,
                "reason": "Zero volatility",
            }

        z_score = (current_spread - mean) / std_dev

        signal = abs(z_score) > z_score_threshold

        return {
            "signal": signal,
            "z_score": z_score,
            "mean": mean,
            "std_dev": std_dev,
            "direction": "down" if z_score > 0 else "up",
            "reason": f"Z-score {z_score:.2f} {'exceeds' if signal else 'within'} threshold",
        }


# Singleton instances
funding_rate_trend_analyzer = FundingRateTrendAnalyzer()
spread_trend_analyzer = SpreadTrendAnalyzer()


def calculate_trend(
    rates: list[float],
    window: int = 6,
) -> TrendDirection:
    """Convenience function for trend calculation."""
    return funding_rate_trend_analyzer.calculate_trend(rates, window)


def calculate_volatility(rates: list[float]) -> float:
    """Convenience function for volatility calculation."""
    return funding_rate_trend_analyzer.calculate_volatility(rates)


def predict_next_rate(
    rates: list[float],
    periods_ahead: int = 1,
) -> Optional[float]:
    """Convenience function for rate prediction."""
    return funding_rate_trend_analyzer.predict_next_rate(rates, periods_ahead)


def analyze_trend(
    rates: list[float],
    symbol: Optional[str] = None,
    exchange: Optional[str] = None,
) -> TrendAnalysis:
    """Convenience function for comprehensive analysis."""
    return funding_rate_trend_analyzer.analyze(rates, symbol, exchange)
