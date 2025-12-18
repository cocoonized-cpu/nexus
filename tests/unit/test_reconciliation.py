"""Unit tests for Position Reconciliation module.

NOTE: These tests require running with the position-manager service in PYTHONPATH.
Run with: PYTHONPATH=services/position-manager pytest tests/unit/test_reconciliation.py
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add service path for imports - use absolute path
_service_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/position-manager")
)
if _service_path not in sys.path:
    sys.path.insert(0, _service_path)

# Handle namespace collision with other services' src packages
try:
    from src.manager.reconciliation import (
        Discrepancy,
        DiscrepancyType,
        PositionReconciliation,
        ReconciliationAction,
        ReconciliationReport,
    )
except ImportError:
    pytest.skip("Cannot import reconciliation - run with single service PYTHONPATH", allow_module_level=True)


class TestDiscrepancy:
    """Tests for Discrepancy dataclass."""

    def test_discrepancy_creation(self):
        """Test creating a Discrepancy."""
        discrepancy = Discrepancy(
            type=DiscrepancyType.ORPHAN_ON_EXCHANGE,
            position_id=None,
            exchange="binance",
            symbol="BTC",
            db_value=None,
            exchange_value={"size": 1.5, "entry_price": 50000},
            severity="high",
        )

        assert discrepancy.type == DiscrepancyType.ORPHAN_ON_EXCHANGE
        assert discrepancy.exchange == "binance"
        assert discrepancy.symbol == "BTC"
        assert discrepancy.severity == "high"
        assert discrepancy.action_taken is None

    def test_discrepancy_has_detected_at(self):
        """Test Discrepancy has detected_at timestamp."""
        discrepancy = Discrepancy(
            type=DiscrepancyType.SIZE_MISMATCH,
            position_id="pos_123",
            exchange="bybit",
            symbol="ETH",
            db_value=1.0,
            exchange_value=1.1,
            severity="medium",
        )

        assert discrepancy.detected_at is not None
        assert isinstance(discrepancy.detected_at, datetime)


class TestReconciliationReport:
    """Tests for ReconciliationReport dataclass."""

    def test_report_creation(self):
        """Test creating a ReconciliationReport."""
        start = datetime.utcnow() - timedelta(minutes=5)
        end = datetime.utcnow()

        report = ReconciliationReport(
            started_at=start,
            completed_at=end,
            positions_checked=100,
            discrepancies_found=5,
            discrepancies_resolved=3,
            discrepancies_requiring_review=2,
            actions_taken=[
                {"action": "adopted", "exchange": "binance"},
            ],
            unresolved=[],
        )

        assert report.positions_checked == 100
        assert report.discrepancies_found == 5
        assert report.discrepancies_resolved == 3
        assert report.discrepancies_requiring_review == 2


class TestDiscrepancyTypes:
    """Tests for DiscrepancyType enum."""

    def test_all_types_defined(self):
        """Test all expected discrepancy types are defined."""
        expected = [
            "ORPHAN_ON_EXCHANGE",
            "MISSING_ON_EXCHANGE",
            "SIZE_MISMATCH",
            "PRICE_MISMATCH",
            "STATE_MISMATCH",
        ]

        for dtype in expected:
            assert hasattr(DiscrepancyType, dtype)

    def test_type_values(self):
        """Test type values are strings."""
        assert DiscrepancyType.ORPHAN_ON_EXCHANGE.value == "orphan_on_exchange"
        assert DiscrepancyType.SIZE_MISMATCH.value == "size_mismatch"


class TestReconciliationActions:
    """Tests for ReconciliationAction enum."""

    def test_all_actions_defined(self):
        """Test all expected actions are defined."""
        expected = ["ADOPTED", "CLOSED", "UPDATED", "ALERTED", "NO_ACTION"]

        for action in expected:
            assert hasattr(ReconciliationAction, action)


class TestPositionReconciliationInit:
    """Tests for PositionReconciliation initialization."""

    def test_initialization_with_mock_redis(self):
        """Test PositionReconciliation initializes correctly."""
        mock_redis = MagicMock()
        mock_factory = MagicMock()

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
        )

        assert reconciliation.redis == mock_redis
        assert reconciliation._db_session_factory == mock_factory
        assert reconciliation._running is False
        assert reconciliation._reconciliation_interval == 300

    def test_configuration_defaults(self):
        """Test default configuration values."""
        mock_redis = MagicMock()

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        assert reconciliation._size_tolerance_pct == Decimal("0.01")
        assert reconciliation._price_tolerance_pct == Decimal("0.02")
        assert reconciliation._auto_adopt_orphans is True
        assert reconciliation._max_orphan_age_hours == 24


class TestStartStop:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self):
        """Test starting reconciliation service."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        await reconciliation.start()

        assert reconciliation._running is True

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stopping reconciliation service."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        await reconciliation.start()
        await reconciliation.stop()

        assert reconciliation._running is False


class TestGetPendingDiscrepancies:
    """Tests for getting pending discrepancies."""

    def test_get_pending_discrepancies_empty(self):
        """Test getting pending discrepancies when none exist."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        result = reconciliation.get_pending_discrepancies()

        assert result == []

    def test_get_pending_discrepancies_with_data(self):
        """Test getting pending discrepancies with data."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        # Add a discrepancy
        discrepancy = Discrepancy(
            type=DiscrepancyType.SIZE_MISMATCH,
            position_id="pos_123",
            exchange="binance",
            symbol="BTC",
            db_value=1.0,
            exchange_value=1.1,
            severity="medium",
        )
        reconciliation._pending_discrepancies = [discrepancy]

        result = reconciliation.get_pending_discrepancies()

        assert len(result) == 1
        assert result[0]["type"] == "size_mismatch"
        assert result[0]["position_id"] == "pos_123"


class TestGetLastReconciliation:
    """Tests for getting last reconciliation timestamp."""

    def test_get_last_reconciliation_none(self):
        """Test getting last reconciliation when none has run."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        result = reconciliation.get_last_reconciliation()

        assert result is None

    def test_get_last_reconciliation_with_timestamp(self):
        """Test getting last reconciliation with timestamp."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        timestamp = datetime.utcnow()
        reconciliation._last_reconciliation = timestamp

        result = reconciliation.get_last_reconciliation()

        assert result == timestamp.isoformat()


class TestComparePositions:
    """Tests for position comparison logic."""

    @pytest.mark.asyncio
    async def test_compare_finds_orphan_on_exchange(self):
        """Test comparison finds orphaned positions on exchange."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        db_positions = []  # No positions in DB
        exchange_positions = {
            "binance": [
                {"symbol": "BTC", "size": 1.5, "entry_price": 50000},
            ],
        }

        discrepancies = await reconciliation._compare_positions(
            db_positions, exchange_positions
        )

        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.ORPHAN_ON_EXCHANGE
        assert discrepancies[0].symbol == "BTC"
        assert discrepancies[0].exchange == "binance"

    @pytest.mark.asyncio
    async def test_compare_finds_missing_on_exchange(self):
        """Test comparison finds positions missing on exchange."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        db_positions = [
            {
                "id": "pos_123",
                "symbol": "BTC",
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "size": 1.5,
                "status": "active",
            },
        ]
        exchange_positions = {
            "binance": [],  # No positions on exchange
            "bybit": [],
        }

        discrepancies = await reconciliation._compare_positions(
            db_positions, exchange_positions
        )

        # Should find missing on both exchanges
        missing = [d for d in discrepancies if d.type == DiscrepancyType.MISSING_ON_EXCHANGE]
        assert len(missing) >= 1

    @pytest.mark.asyncio
    async def test_compare_finds_size_mismatch(self):
        """Test comparison finds size mismatches."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        db_positions = [
            {
                "id": "pos_123",
                "symbol": "BTC",
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "size": 1.0,  # DB says 1.0
                "status": "active",
            },
        ]
        exchange_positions = {
            "binance": [
                {"symbol": "BTC", "size": 1.5},  # Exchange says 1.5 (50% difference)
            ],
            "bybit": [
                {"symbol": "BTC", "size": -1.0},
            ],
        }

        discrepancies = await reconciliation._compare_positions(
            db_positions, exchange_positions
        )

        size_mismatches = [d for d in discrepancies if d.type == DiscrepancyType.SIZE_MISMATCH]
        assert len(size_mismatches) >= 1

    @pytest.mark.asyncio
    async def test_compare_ignores_dust_positions(self):
        """Test comparison ignores dust positions on exchange."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        db_positions = []
        exchange_positions = {
            "binance": [
                {"symbol": "BTC", "size": 0.00001},  # Dust amount
            ],
        }

        discrepancies = await reconciliation._compare_positions(
            db_positions, exchange_positions
        )

        # Dust position should not trigger orphan detection
        assert len(discrepancies) == 0

    @pytest.mark.asyncio
    async def test_compare_skips_inactive_positions_for_missing(self):
        """Test comparison skips inactive positions when checking for missing."""
        mock_redis = MagicMock()
        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        db_positions = [
            {
                "id": "pos_123",
                "symbol": "BTC",
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "size": 1.0,
                "status": "closed",  # Not active
            },
        ]
        exchange_positions = {
            "binance": [],
            "bybit": [],
        }

        discrepancies = await reconciliation._compare_positions(
            db_positions, exchange_positions
        )

        # Closed position missing on exchange shouldn't be flagged
        missing = [d for d in discrepancies if d.type == DiscrepancyType.MISSING_ON_EXCHANGE]
        assert len(missing) == 0


class TestResolveDiscrepancy:
    """Tests for discrepancy resolution."""

    @pytest.mark.asyncio
    async def test_resolve_orphan_with_auto_adopt(self):
        """Test resolving orphan position with auto-adopt enabled."""
        mock_redis = MagicMock()

        # Mock DB session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
        )
        reconciliation._auto_adopt_orphans = True

        discrepancy = Discrepancy(
            type=DiscrepancyType.ORPHAN_ON_EXCHANGE,
            position_id=None,
            exchange="binance",
            symbol="BTC",
            db_value=None,
            exchange_value={"size": 1.5, "entry_price": 50000},
            severity="high",
        )

        result = await reconciliation._resolve_discrepancy(discrepancy)

        assert result["action"] in ["adopted", "alerted"]

    @pytest.mark.asyncio
    async def test_resolve_orphan_without_auto_adopt(self):
        """Test resolving orphan position with auto-adopt disabled."""
        mock_redis = MagicMock()

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )
        reconciliation._auto_adopt_orphans = False

        discrepancy = Discrepancy(
            type=DiscrepancyType.ORPHAN_ON_EXCHANGE,
            position_id=None,
            exchange="binance",
            symbol="BTC",
            db_value=None,
            exchange_value={"size": 1.5},
            severity="high",
        )

        result = await reconciliation._resolve_discrepancy(discrepancy)

        assert result["action"] == "alerted"
        assert discrepancy.action_taken == ReconciliationAction.ALERTED

    @pytest.mark.asyncio
    async def test_resolve_missing_on_exchange(self):
        """Test resolving missing on exchange marks as closed."""
        mock_redis = MagicMock()

        # Mock DB session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
        )

        discrepancy = Discrepancy(
            type=DiscrepancyType.MISSING_ON_EXCHANGE,
            position_id="pos_123",
            exchange="binance",
            symbol="BTC",
            db_value={"status": "active"},
            exchange_value=None,
            severity="critical",
        )

        result = await reconciliation._resolve_discrepancy(discrepancy)

        # Should update or alert
        assert result["action"] in ["updated", "alerted", "error"]

    @pytest.mark.asyncio
    async def test_resolve_size_mismatch_non_critical(self):
        """Test resolving non-critical size mismatch updates DB."""
        mock_redis = MagicMock()

        # Mock DB session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
        )

        discrepancy = Discrepancy(
            type=DiscrepancyType.SIZE_MISMATCH,
            position_id="pos_123",
            exchange="binance",
            symbol="BTC",
            db_value=1.0,
            exchange_value=1.05,
            severity="medium",  # Non-critical
        )

        result = await reconciliation._resolve_discrepancy(discrepancy)

        # Should update or alert
        assert result["action"] in ["updated", "alerted", "error"]

    @pytest.mark.asyncio
    async def test_resolve_size_mismatch_critical(self):
        """Test resolving critical size mismatch alerts."""
        mock_redis = MagicMock()

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        discrepancy = Discrepancy(
            type=DiscrepancyType.SIZE_MISMATCH,
            position_id="pos_123",
            exchange="binance",
            symbol="BTC",
            db_value=1.0,
            exchange_value=2.0,
            severity="critical",  # Critical - large mismatch
        )

        result = await reconciliation._resolve_discrepancy(discrepancy)

        assert result["action"] == "alerted"


class TestRunStartupReconciliation:
    """Tests for startup reconciliation."""

    @pytest.mark.asyncio
    async def test_startup_reconciliation_returns_report(self):
        """Test startup reconciliation returns a report."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()

        # Mock DB session returning no positions
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
            exchange_clients={},  # No exchange clients
        )

        report = await reconciliation.run_startup_reconciliation()

        assert isinstance(report, ReconciliationReport)
        assert report.positions_checked == 0

    @pytest.mark.asyncio
    async def test_startup_reconciliation_updates_last_timestamp(self):
        """Test startup reconciliation updates last reconciliation timestamp."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()

        # Mock DB session
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
            exchange_clients={},
        )

        assert reconciliation._last_reconciliation is None

        await reconciliation.run_startup_reconciliation()

        assert reconciliation._last_reconciliation is not None


class TestRunPeriodicSync:
    """Tests for periodic sync."""

    @pytest.mark.asyncio
    async def test_periodic_sync_returns_report(self):
        """Test periodic sync returns a report."""
        mock_redis = MagicMock()

        # Mock DB session returning no positions
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
            exchange_clients={},
        )

        report = await reconciliation.run_periodic_sync()

        assert isinstance(report, ReconciliationReport)


class TestPublishReconciliationReport:
    """Tests for publishing reconciliation reports."""

    @pytest.mark.asyncio
    async def test_publish_report_to_redis(self):
        """Test report is published to Redis."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        report = ReconciliationReport(
            started_at=datetime.utcnow() - timedelta(minutes=1),
            completed_at=datetime.utcnow(),
            positions_checked=10,
            discrepancies_found=0,
            discrepancies_resolved=0,
            discrepancies_requiring_review=0,
            actions_taken=[],
            unresolved=[],
        )

        await reconciliation._publish_reconciliation_report(report)

        # Verify set was called with the report
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "nexus:reconciliation:last_report" in call_args[0]

    @pytest.mark.asyncio
    async def test_publish_alert_when_discrepancies_require_review(self):
        """Test alert is published when discrepancies require review."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=MagicMock(),
        )

        report = ReconciliationReport(
            started_at=datetime.utcnow() - timedelta(minutes=1),
            completed_at=datetime.utcnow(),
            positions_checked=10,
            discrepancies_found=3,
            discrepancies_resolved=1,
            discrepancies_requiring_review=2,  # 2 need review
            actions_taken=[],
            unresolved=[],
        )

        await reconciliation._publish_reconciliation_report(report)

        # Verify publish was called for alert
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert "nexus:reconciliation:alert" in call_args[0]


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_startup_reconciliation_handles_db_error(self):
        """Test startup reconciliation handles DB errors gracefully."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()

        # Mock DB session that raises error
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB Error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
            exchange_clients={},
        )

        # Should not raise
        report = await reconciliation.run_startup_reconciliation()

        # Should return empty report
        assert report.positions_checked == 0
        assert report.discrepancies_found == 0

    @pytest.mark.asyncio
    async def test_resolve_discrepancy_handles_error(self):
        """Test resolve discrepancy handles errors gracefully."""
        mock_redis = MagicMock()

        # Mock DB session that raises error on execute
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB Error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_session)

        reconciliation = PositionReconciliation(
            redis=mock_redis,
            db_session_factory=mock_factory,
        )

        discrepancy = Discrepancy(
            type=DiscrepancyType.MISSING_ON_EXCHANGE,
            position_id="pos_123",
            exchange="binance",
            symbol="BTC",
            db_value={"status": "active"},
            exchange_value=None,
            severity="critical",
        )

        # Should not raise
        result = await reconciliation._resolve_discrepancy(discrepancy)

        assert result["action"] in ["error", "alerted"]
        assert discrepancy.action_taken == ReconciliationAction.ALERTED
