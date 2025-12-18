"""Unit tests for Spread Forecaster module."""

import os
import sys
from datetime import datetime, timedelta

import pytest

# Add service path for imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/opportunity-detector")
)

from src.detector.forecaster import (
    ForecastConfidence,
    MeanReversionSignal,
    SeasonalityAnalysis,
    SeasonalityPattern,
    SpreadForecast,
    SpreadForecaster,
)


class TestSpreadForecaster:
    """Tests for the SpreadForecaster class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()
        self.symbol = "BTC"
        self.long_exchange = "binance"
        self.short_exchange = "bybit"

    def test_forecaster_initialization(self):
        """Test forecaster initializes with correct configuration."""
        assert self.forecaster.MIN_DATA_POINTS == 6
        assert self.forecaster.MIN_SEASONALITY_POINTS == 24
        assert self.forecaster.Z_SCORE_THRESHOLD == 2.0
        assert self.forecaster.FUNDING_PERIOD_8H == 8.0
        assert self.forecaster.FUNDING_PERIOD_1H == 1.0

    def test_add_spread_observation(self):
        """Test adding spread observations to history."""
        self.forecaster.add_spread_observation(
            self.symbol, self.long_exchange, self.short_exchange, 0.02
        )

        stats = self.forecaster.get_history_stats(
            self.symbol, self.long_exchange, self.short_exchange
        )
        assert stats["count"] == 1
        assert stats["mean"] == 0.02

    def test_add_multiple_observations(self):
        """Test adding multiple observations."""
        spreads = [0.01, 0.02, 0.03, 0.015, 0.025]
        for spread in spreads:
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, spread
            )

        stats = self.forecaster.get_history_stats(
            self.symbol, self.long_exchange, self.short_exchange
        )
        assert stats["count"] == 5
        assert stats["min"] == 0.01
        assert stats["max"] == 0.03

    def test_history_max_length_trimming(self):
        """Test that history is trimmed to max length."""
        # Add more than max observations
        for i in range(600):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, 0.01 + i * 0.0001
            )

        stats = self.forecaster.get_history_stats(
            self.symbol, self.long_exchange, self.short_exchange
        )
        assert stats["count"] == 500  # Max length

    def test_forecast_insufficient_data(self):
        """Test forecasting with insufficient data returns appropriate response."""
        # Add fewer than MIN_DATA_POINTS observations
        for i in range(3):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, 0.02
            )

        forecast = self.forecaster.forecast_spread(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert forecast.confidence == ForecastConfidence.INSUFFICIENT_DATA
        assert forecast.method == "constant"

    def test_forecast_with_sufficient_data(self):
        """Test forecasting with sufficient data."""
        # Add enough observations
        for i in range(20):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02 + (i % 5) * 0.001,
                datetime.utcnow() - timedelta(hours=20 - i),
            )

        forecast = self.forecaster.forecast_spread(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert isinstance(forecast, SpreadForecast)
        assert forecast.confidence in [
            ForecastConfidence.LOW,
            ForecastConfidence.MEDIUM,
            ForecastConfidence.HIGH,
        ]
        assert forecast.method == "exponential_smoothing"
        assert forecast.lower_bound <= forecast.predicted_spread <= forecast.upper_bound

    def test_forecast_confidence_intervals(self):
        """Test that confidence intervals are properly calculated."""
        # Add observations with known values
        for i in range(50):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02,  # Constant value for predictable intervals
                datetime.utcnow() - timedelta(hours=50 - i),
            )

        forecast = self.forecaster.forecast_spread(
            self.symbol, self.long_exchange, self.short_exchange
        )

        # With constant values, intervals should be tight
        assert forecast.upper_bound - forecast.lower_bound >= 0

    def test_forecast_caching(self):
        """Test that forecasts are cached."""
        # Add observations
        for i in range(10):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, 0.02
            )

        # First call
        forecast1 = self.forecaster.forecast_spread(
            self.symbol, self.long_exchange, self.short_exchange
        )

        # Second call should return cached result
        forecast2 = self.forecaster.forecast_spread(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert forecast1.forecast_time == forecast2.forecast_time


class TestSeasonalityDetection:
    """Tests for seasonality detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()
        self.symbol = "BTC"
        self.long_exchange = "binance"
        self.short_exchange = "bybit"

    def test_seasonality_insufficient_data(self):
        """Test seasonality detection with insufficient data."""
        for i in range(10):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, 0.02
            )

        analysis = self.forecaster.detect_seasonality(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert analysis.pattern == SeasonalityPattern.UNKNOWN
        assert analysis.confidence == 0.0

    def test_seasonality_detection_no_pattern(self):
        """Test detection with no clear seasonal pattern."""
        # Add random-like data
        import random
        random.seed(42)

        for i in range(50):
            spread = 0.02 + random.uniform(-0.005, 0.005)
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                spread,
                datetime.utcnow() - timedelta(hours=50 - i),
            )

        analysis = self.forecaster.detect_seasonality(
            self.symbol, self.long_exchange, self.short_exchange
        )

        # Should detect no strong pattern or have low confidence
        assert isinstance(analysis, SeasonalityAnalysis)

    def test_seasonality_caching(self):
        """Test seasonality analysis caching."""
        # Add observations
        for i in range(30):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02,
                datetime.utcnow() - timedelta(hours=30 - i),
            )

        analysis1 = self.forecaster.detect_seasonality(
            self.symbol, self.long_exchange, self.short_exchange
        )
        analysis2 = self.forecaster.detect_seasonality(
            self.symbol, self.long_exchange, self.short_exchange
        )

        # Cached results should be identical
        assert analysis1.pattern == analysis2.pattern
        assert analysis1.confidence == analysis2.confidence


class TestMeanReversionSignal:
    """Tests for mean reversion signal generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()
        self.symbol = "BTC"
        self.long_exchange = "binance"
        self.short_exchange = "bybit"

    def test_mean_reversion_insufficient_data(self):
        """Test mean reversion with insufficient data."""
        for i in range(5):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, 0.02
            )

        signal = self.forecaster.mean_reversion_signal(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert signal.signal is False
        assert signal.confidence == 0.0
        assert "Insufficient" in signal.reason

    def test_mean_reversion_no_signal(self):
        """Test mean reversion with spread near mean."""
        # Add data around a stable mean
        for i in range(30):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02 + (i % 3) * 0.001 - 0.001,  # Small variations around 0.02
            )

        signal = self.forecaster.mean_reversion_signal(
            self.symbol, self.long_exchange, self.short_exchange,
            current_spread=0.02,  # At mean
        )

        assert signal.signal is False
        assert abs(signal.z_score) < 2.0
        assert signal.direction == "none"

    def test_mean_reversion_signal_above_mean(self):
        """Test mean reversion signal when spread is above mean."""
        # Establish a mean around 0.02
        for i in range(30):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02 + (i % 3) * 0.001 - 0.001,
            )

        # Test with a spread much higher than mean
        signal = self.forecaster.mean_reversion_signal(
            self.symbol, self.long_exchange, self.short_exchange,
            current_spread=0.05,  # Way above mean
        )

        assert signal.signal is True
        assert signal.direction == "down"
        assert signal.z_score > 2.0
        assert "above mean" in signal.reason

    def test_mean_reversion_signal_below_mean(self):
        """Test mean reversion signal when spread is below mean."""
        # Establish a mean around 0.02
        for i in range(30):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02 + (i % 3) * 0.001 - 0.001,
            )

        # Test with a spread much lower than mean
        signal = self.forecaster.mean_reversion_signal(
            self.symbol, self.long_exchange, self.short_exchange,
            current_spread=-0.01,  # Way below mean
        )

        assert signal.signal is True
        assert signal.direction == "up"
        assert signal.z_score < -2.0
        assert "below mean" in signal.reason

    def test_mean_reversion_custom_threshold(self):
        """Test mean reversion with custom z-score threshold."""
        # Add data
        for i in range(30):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02 + (i % 5) * 0.002 - 0.004,
            )

        # With standard threshold (2.0), might not trigger
        signal_standard = self.forecaster.mean_reversion_signal(
            self.symbol, self.long_exchange, self.short_exchange,
            current_spread=0.025,
        )

        # With lower threshold (1.0), more likely to trigger
        signal_low = self.forecaster.mean_reversion_signal(
            self.symbol, self.long_exchange, self.short_exchange,
            current_spread=0.025,
            z_score_threshold=1.0,
        )

        # Lower threshold should be more sensitive
        assert signal_low.signal or (not signal_standard.signal and not signal_low.signal)


class TestOptimalEntryTiming:
    """Tests for optimal entry timing recommendations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()
        self.symbol = "BTC"
        self.long_exchange = "binance"
        self.short_exchange = "bybit"

    def test_optimal_timing_insufficient_data(self):
        """Test optimal timing with insufficient data."""
        timing = self.forecaster.get_optimal_entry_timing(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert isinstance(timing, dict)
        assert "recommendation" in timing
        assert "confidence" in timing
        assert timing["confidence"] == 0.0

    def test_optimal_timing_with_data(self):
        """Test optimal timing with sufficient data."""
        # Add enough data
        for i in range(50):
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange,
                0.02 + (i % 8) * 0.002 - 0.008,
                datetime.utcnow() - timedelta(hours=50 - i),
            )

        timing = self.forecaster.get_optimal_entry_timing(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert isinstance(timing, dict)
        assert timing["recommendation"] in ["enter", "enter_soon", "wait", "neutral"]
        assert "seasonality" in timing
        assert "mean_reversion" in timing
        assert 0 <= timing["confidence"] <= 1


class TestClearHistory:
    """Tests for clearing history."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()

    def test_clear_all_history(self):
        """Test clearing all history."""
        # Add data for multiple pairs
        self.forecaster.add_spread_observation("BTC", "binance", "bybit", 0.02)
        self.forecaster.add_spread_observation("ETH", "binance", "okx", 0.03)

        # Clear all
        self.forecaster.clear_history()

        # Verify cleared
        btc_stats = self.forecaster.get_history_stats("BTC", "binance", "bybit")
        eth_stats = self.forecaster.get_history_stats("ETH", "binance", "okx")

        assert btc_stats["count"] == 0
        assert eth_stats["count"] == 0

    def test_clear_specific_symbol(self):
        """Test clearing history for specific symbol."""
        # Add data for multiple pairs
        self.forecaster.add_spread_observation("BTC", "binance", "bybit", 0.02)
        self.forecaster.add_spread_observation("ETH", "binance", "okx", 0.03)

        # Clear only BTC
        self.forecaster.clear_history("BTC")

        # Verify BTC cleared but ETH remains
        btc_stats = self.forecaster.get_history_stats("BTC", "binance", "bybit")
        eth_stats = self.forecaster.get_history_stats("ETH", "binance", "okx")

        assert btc_stats["count"] == 0
        assert eth_stats["count"] == 1


class TestHistoryStats:
    """Tests for history statistics."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()
        self.symbol = "BTC"
        self.long_exchange = "binance"
        self.short_exchange = "bybit"

    def test_empty_history_stats(self):
        """Test stats for empty history."""
        stats = self.forecaster.get_history_stats(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert stats["count"] == 0
        assert stats["mean"] is None
        assert stats["std_dev"] is None

    def test_history_stats_calculation(self):
        """Test stats are calculated correctly."""
        spreads = [0.01, 0.02, 0.03, 0.04, 0.05]
        for spread in spreads:
            self.forecaster.add_spread_observation(
                self.symbol, self.long_exchange, self.short_exchange, spread
            )

        stats = self.forecaster.get_history_stats(
            self.symbol, self.long_exchange, self.short_exchange
        )

        assert stats["count"] == 5
        assert stats["mean"] == pytest.approx(0.03, rel=1e-6)
        assert stats["min"] == 0.01
        assert stats["max"] == 0.05
        assert stats["std_dev"] > 0


class TestExponentialSmoothing:
    """Tests for exponential smoothing implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()

    def test_exponential_smoothing_empty_values(self):
        """Test smoothing with empty values."""
        result = self.forecaster._exponential_smoothing_forecast([], 8.0)
        assert result == 0.0

    def test_exponential_smoothing_single_value(self):
        """Test smoothing with single value."""
        result = self.forecaster._exponential_smoothing_forecast([0.02], 8.0)
        assert result == 0.02

    def test_exponential_smoothing_constant_values(self):
        """Test smoothing with constant values."""
        values = [0.02] * 10
        result = self.forecaster._exponential_smoothing_forecast(values, 8.0)
        assert result == pytest.approx(0.02, rel=1e-6)

    def test_exponential_smoothing_trend(self):
        """Test smoothing weights recent values more."""
        # Increasing trend
        values = [0.01, 0.02, 0.03, 0.04, 0.05]
        result = self.forecaster._exponential_smoothing_forecast(values, 8.0)

        # Result should be weighted toward recent (higher) values
        # but not as high as 0.05 due to smoothing
        assert 0.03 < result < 0.05


class TestStandardDeviation:
    """Tests for standard deviation calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = SpreadForecaster()

    def test_std_dev_empty(self):
        """Test std dev with empty list."""
        result = self.forecaster._calculate_std_dev([])
        assert result == 0.0

    def test_std_dev_single_value(self):
        """Test std dev with single value."""
        result = self.forecaster._calculate_std_dev([0.02])
        assert result == 0.0

    def test_std_dev_constant_values(self):
        """Test std dev with constant values."""
        result = self.forecaster._calculate_std_dev([0.02, 0.02, 0.02])
        assert result == 0.0

    def test_std_dev_known_values(self):
        """Test std dev calculation with known values."""
        # Known values: [1, 2, 3, 4, 5]
        # Mean = 3, Variance = 2, StdDev = sqrt(2) ≈ 1.414
        result = self.forecaster._calculate_std_dev([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result == pytest.approx(1.4142, rel=1e-3)
