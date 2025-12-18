"""Unit tests for UOS Scorer."""

import os
import sys

import pytest

# Add service path for imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/opportunity-detector")
)

from src.detector.scorer import UOSScorer


class TestUOSScorer:
    """Tests for the UOS Scoring system."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scorer = UOSScorer()

    def test_scorer_initialization(self):
        """Test scorer initializes with correct weights."""
        assert self.scorer.weights["return"] == 30
        assert self.scorer.weights["risk"] == 30
        assert self.scorer.weights["execution"] == 25
        assert self.scorer.weights["timing"] == 15

    def test_weights_sum_to_100(self):
        """Test that score weights sum to 100."""
        total = sum(self.scorer.weights.values())
        assert total == 100

    def test_calculate_scores_returns_uos(self):
        """Test that calculate_scores returns UOSScores object."""
        spread_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "bybit",
            "spread_pct": 0.03,
            "annualized_apr": 30.0,
        }

        scores = self.scorer.calculate_scores(spread_data)

        assert hasattr(scores, "return_score")
        assert hasattr(scores, "risk_score")
        assert hasattr(scores, "execution_score")
        assert hasattr(scores, "timing_score")
        assert hasattr(scores, "total")  # computed property

    def test_total_score_is_sum_of_components(self):
        """Test that total score equals sum of component scores."""
        spread_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "bybit",
            "spread_pct": 0.03,
            "annualized_apr": 30.0,
        }

        scores = self.scorer.calculate_scores(spread_data)

        calculated = (
            scores.return_score
            + scores.risk_score
            + scores.execution_score
            + scores.timing_score
        )
        assert scores.total == calculated

    def test_scores_within_valid_ranges(self):
        """Test that all scores are within valid ranges."""
        spread_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "bybit",
            "spread_pct": 0.05,
            "annualized_apr": 50.0,
        }

        scores = self.scorer.calculate_scores(spread_data)

        assert 0 <= scores.return_score <= 30
        assert 0 <= scores.risk_score <= 30
        assert 0 <= scores.execution_score <= 25
        assert 0 <= scores.timing_score <= 15
        assert 0 <= scores.total <= 100

    def test_higher_apr_gives_higher_return_score(self):
        """Test that higher APR results in higher return score."""
        low_apr_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "bybit",
            "spread_pct": 0.01,
            "annualized_apr": 10.0,
        }

        high_apr_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "bybit",
            "spread_pct": 0.05,
            "annualized_apr": 50.0,
        }

        low_scores = self.scorer.calculate_scores(low_apr_data)
        high_scores = self.scorer.calculate_scores(high_apr_data)

        assert high_scores.return_score > low_scores.return_score

    def test_tier1_exchanges_higher_risk_score(self):
        """Test that Tier 1 exchanges result in higher risk score."""
        tier1_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "okx",
            "spread_pct": 0.03,
            "annualized_apr": 30.0,
        }

        mixed_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "gate",
            "spread_pct": 0.03,
            "annualized_apr": 30.0,
        }

        tier1_scores = self.scorer.calculate_scores(tier1_data)
        mixed_scores = self.scorer.calculate_scores(mixed_data)

        assert tier1_scores.risk_score >= mixed_scores.risk_score

    def test_optimal_timing_gives_max_timing_score(self):
        """Test that optimal timing (4-6 hours to funding) gives high score."""
        optimal_data = {
            "symbol": "BTC",
            "long_exchange": "binance",
            "short_exchange": "bybit",
            "spread_pct": 0.03,
            "annualized_apr": 30.0,
            "hours_to_funding": 5,
            "rate_trend": "stable",
        }

        scores = self.scorer.calculate_scores(optimal_data)

        # Optimal timing should give max timing score
        assert scores.timing_score >= 12  # At least 80% of max 15
