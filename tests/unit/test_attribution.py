"""Unit tests for Performance Attribution module.

NOTE: These tests require running with the analytics service in PYTHONPATH.
Run with: PYTHONPATH=services/analytics pytest tests/unit/test_attribution.py
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add service path for imports - use absolute path
_service_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/analytics")
)
if _service_path not in sys.path:
    sys.path.insert(0, _service_path)

# Mock SQLAlchemy engine creation before importing the module
# This prevents the global PerformanceAttribution() from trying to connect to a DB
# Also handle namespace collision with other services' src packages
try:
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        from src.service.attribution import (
            AttributionDimension,
            AttributionResult,
            CohortAnalysis,
            PerformanceAttribution,
            TimePattern,
        )
except ImportError:
    pytest.skip("Cannot import attribution - run with single service PYTHONPATH", allow_module_level=True)


class TestAttributionResult:
    """Tests for AttributionResult dataclass."""

    def test_attribution_result_creation(self):
        """Test creating an AttributionResult."""
        now = datetime.utcnow()
        result = AttributionResult(
            dimension=AttributionDimension.EXCHANGE,
            period_start=now - timedelta(days=30),
            period_end=now,
            total_pnl=Decimal("1000.50"),
            total_trades=50,
            breakdown=[
                {"exchange": "binance", "total_pnl": 600.0},
                {"exchange": "bybit", "total_pnl": 400.50},
            ],
        )

        assert result.dimension == AttributionDimension.EXCHANGE
        assert result.total_pnl == Decimal("1000.50")
        assert result.total_trades == 50
        assert len(result.breakdown) == 2

    def test_attribution_result_has_timestamp(self):
        """Test AttributionResult has generated_at timestamp."""
        result = AttributionResult(
            dimension=AttributionDimension.SYMBOL,
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            total_pnl=Decimal("500"),
            total_trades=25,
            breakdown=[],
        )

        assert result.generated_at is not None
        assert isinstance(result.generated_at, datetime)


class TestCohortAnalysis:
    """Tests for CohortAnalysis dataclass."""

    def test_cohort_analysis_creation(self):
        """Test creating a CohortAnalysis."""
        cohort = CohortAnalysis(
            cohort_name="High (90-100)",
            trade_count=100,
            total_pnl=Decimal("5000"),
            avg_pnl=Decimal("50"),
            win_rate=75.0,
            avg_win=Decimal("80"),
            avg_loss=Decimal("30"),
            sharpe_estimate=1.5,
            best_trade=Decimal("500"),
            worst_trade=Decimal("-100"),
        )

        assert cohort.cohort_name == "High (90-100)"
        assert cohort.trade_count == 100
        assert cohort.win_rate == 75.0
        assert cohort.sharpe_estimate == 1.5


class TestTimePattern:
    """Tests for TimePattern dataclass."""

    def test_time_pattern_creation(self):
        """Test creating a TimePattern."""
        pattern = TimePattern(
            hour_of_day=14,
            day_of_week=2,  # Wednesday
            avg_pnl=Decimal("25.50"),
            trade_count=15,
            win_rate=66.7,
        )

        assert pattern.hour_of_day == 14
        assert pattern.day_of_week == 2
        assert pattern.avg_pnl == Decimal("25.50")
        assert pattern.win_rate == 66.7


class TestAttributionDimensions:
    """Tests for AttributionDimension enum."""

    def test_all_dimensions_defined(self):
        """Test all expected dimensions are defined."""
        expected = ["EXCHANGE", "SYMBOL", "UOS_SCORE", "TIME_PERIOD", "FUNDING_VS_PRICE"]

        for dim in expected:
            assert hasattr(AttributionDimension, dim)

    def test_dimension_values(self):
        """Test dimension values are strings."""
        assert AttributionDimension.EXCHANGE.value == "exchange"
        assert AttributionDimension.SYMBOL.value == "symbol"
        assert AttributionDimension.UOS_SCORE.value == "uos_score"


class TestPerformanceAttributionInit:
    """Tests for PerformanceAttribution initialization."""

    def test_initialization(self):
        """Test PerformanceAttribution initializes correctly."""
        # Create with mock session factory
        mock_factory = MagicMock()
        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        assert attribution._db_session_factory == mock_factory
        assert len(attribution._score_cohorts) == 5

    def test_score_cohorts_cover_full_range(self):
        """Test score cohorts cover 0-100 range."""
        attribution = PerformanceAttribution(db_session_factory=MagicMock())

        cohort_ranges = attribution._score_cohorts

        # First cohort should start at 0
        assert cohort_ranges[0][0] == 0

        # Last cohort should end at 100
        assert cohort_ranges[-1][1] == 100

        # Verify no gaps
        for i in range(len(cohort_ranges) - 1):
            assert cohort_ranges[i][1] == cohort_ranges[i + 1][0]


class TestPnLAnalysis:
    """Tests for P&L analysis logic."""

    def test_analyze_pnl_composition_both_positive(self):
        """Test analysis when both funding and price are positive."""
        attribution = PerformanceAttribution(db_session_factory=MagicMock())

        analysis = attribution._analyze_pnl_composition(
            Decimal("100"),
            Decimal("50"),
        )

        assert "ideal" in analysis.lower()

    def test_analyze_pnl_composition_funding_positive_price_negative(self):
        """Test analysis when funding is positive but price is negative."""
        attribution = PerformanceAttribution(db_session_factory=MagicMock())

        # Funding wins
        analysis = attribution._analyze_pnl_composition(
            Decimal("100"),
            Decimal("-50"),
        )
        assert "strategy working" in analysis.lower() or "offsetting" in analysis.lower()

        # Price wins
        analysis = attribution._analyze_pnl_composition(
            Decimal("100"),
            Decimal("-150"),
        )
        assert "exceeding" in analysis.lower() or "review" in analysis.lower()

    def test_analyze_pnl_composition_both_negative(self):
        """Test analysis when both components are negative."""
        attribution = PerformanceAttribution(db_session_factory=MagicMock())

        analysis = attribution._analyze_pnl_composition(
            Decimal("-100"),
            Decimal("-50"),
        )

        assert "urgent" in analysis.lower() or "review" in analysis.lower()

    def test_empty_breakdown(self):
        """Test empty breakdown structure."""
        attribution = PerformanceAttribution(db_session_factory=MagicMock())

        breakdown = attribution._empty_breakdown()

        assert breakdown["funding_pnl"] == 0
        assert breakdown["price_pnl"] == 0
        assert breakdown["total_pnl"] == 0
        assert breakdown["trade_count"] == 0


class TestPnLBreakdown:
    """Tests for P&L breakdown functionality."""

    @pytest.mark.asyncio
    async def test_get_pnl_breakdown_structure(self):
        """Test P&L breakdown returns correct structure."""
        # Create mock session
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: [100.0, 50.0, 150.0, 10, 15.0][idx]

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        breakdown = await attribution.get_pnl_breakdown()

        assert "funding_pnl" in breakdown
        assert "price_pnl" in breakdown
        assert "total_pnl" in breakdown
        assert "funding_pct" in breakdown
        assert "analysis" in breakdown

    @pytest.mark.asyncio
    async def test_get_pnl_breakdown_no_data(self):
        """Test P&L breakdown handles no data gracefully."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        breakdown = await attribution.get_pnl_breakdown()

        assert breakdown["funding_pnl"] == 0
        assert breakdown["total_pnl"] == 0


class TestExchangeAttribution:
    """Tests for exchange attribution functionality."""

    @pytest.mark.asyncio
    async def test_get_exchange_attribution_returns_result(self):
        """Test exchange attribution returns AttributionResult."""
        # Create mock with two sets of rows (long and short)
        long_rows = [
            MagicMock(_mapping={"exchange": "binance", "side": "long", "trade_count": 5,
                               "total_pnl": 100.0, "avg_pnl": 20.0, "wins": 4}),
        ]
        short_rows = [
            MagicMock(_mapping={"exchange": "binance", "side": "short", "trade_count": 3,
                               "total_pnl": 50.0, "avg_pnl": 16.67, "wins": 2}),
        ]

        mock_long_result = MagicMock()
        mock_long_result.fetchall.return_value = []

        mock_short_result = MagicMock()
        mock_short_result.fetchall.return_value = []

        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_long_result
            return mock_short_result

        mock_session = AsyncMock()
        mock_session.execute = mock_execute
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        result = await attribution.get_exchange_attribution()

        assert isinstance(result, AttributionResult)
        assert result.dimension == AttributionDimension.EXCHANGE


class TestSymbolAttribution:
    """Tests for symbol attribution functionality."""

    @pytest.mark.asyncio
    async def test_get_symbol_attribution_returns_result(self):
        """Test symbol attribution returns AttributionResult."""
        mock_rows = []
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        result = await attribution.get_symbol_attribution()

        assert isinstance(result, AttributionResult)
        assert result.dimension == AttributionDimension.SYMBOL


class TestUOSScoreCohorts:
    """Tests for UOS score cohort analysis."""

    @pytest.mark.asyncio
    async def test_get_uos_score_cohorts_returns_list(self):
        """Test UOS score cohorts returns list of CohortAnalysis."""
        # Mock empty results for each cohort
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: 0

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        cohorts = await attribution.get_uos_score_cohorts()

        assert isinstance(cohorts, list)
        # Should have 5 cohorts (matching score ranges)
        assert len(cohorts) == 5


class TestTimePatterns:
    """Tests for time pattern analysis."""

    @pytest.mark.asyncio
    async def test_get_time_patterns_returns_list(self):
        """Test time patterns returns list of TimePattern."""
        mock_rows = []
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        patterns = await attribution.get_time_patterns()

        assert isinstance(patterns, list)


class TestOptimalScoreThreshold:
    """Tests for optimal score threshold calculation."""

    @pytest.mark.asyncio
    async def test_get_optimal_threshold_returns_dict(self):
        """Test optimal threshold returns dictionary."""
        # Mock empty cohorts
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: 0

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        threshold = await attribution.get_optimal_score_threshold()

        assert isinstance(threshold, dict)
        assert "recommended_threshold" in threshold
        assert "reason" in threshold

    @pytest.mark.asyncio
    async def test_optimal_threshold_defaults_to_75(self):
        """Test optimal threshold defaults to 75 with insufficient data."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: 0

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        threshold = await attribution.get_optimal_score_threshold()

        assert threshold["recommended_threshold"] == 75


class TestFullAttributionReport:
    """Tests for full attribution report generation."""

    @pytest.mark.asyncio
    async def test_get_full_report_structure(self):
        """Test full report has all expected sections."""
        # Mock all database calls to return empty/default values
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: 0

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        report = await attribution.get_full_attribution_report()

        # Check all expected sections
        assert "period" in report
        assert "pnl_breakdown" in report
        assert "exchange_attribution" in report
        assert "symbol_attribution" in report
        assert "uos_score_cohorts" in report
        assert "time_patterns" in report
        assert "optimal_threshold" in report
        assert "generated_at" in report


class TestDateRangeDefaults:
    """Tests for default date range handling."""

    @pytest.mark.asyncio
    async def test_default_date_range_is_30_days(self):
        """Test default date range is 30 days."""
        calls = []

        async def capture_execute(query, params):
            calls.append(params)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            return mock_result

        mock_session = AsyncMock()
        mock_session.execute = capture_execute
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        await attribution.get_pnl_breakdown()

        # Verify start/end params were passed
        assert len(calls) > 0
        params = calls[0]
        assert "start" in params
        assert "end" in params

        # Check range is approximately 30 days
        delta = params["end"] - params["start"]
        assert 29 <= delta.days <= 31


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_pnl_breakdown_handles_db_error(self):
        """Test P&L breakdown handles database errors gracefully."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB Error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        # Should not raise, should return empty breakdown
        breakdown = await attribution.get_pnl_breakdown()

        assert breakdown["total_pnl"] == 0
        assert breakdown["trade_count"] == 0

    @pytest.mark.asyncio
    async def test_exchange_attribution_handles_db_error(self):
        """Test exchange attribution handles database errors gracefully."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB Error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        attribution = PerformanceAttribution(db_session_factory=mock_factory)

        # Should not raise, should return empty result
        result = await attribution.get_exchange_attribution()

        assert result.total_pnl == Decimal("0")
        assert result.total_trades == 0
        assert result.breakdown == []
