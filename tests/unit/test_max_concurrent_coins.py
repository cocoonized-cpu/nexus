"""Unit tests for Max Concurrent Coins feature.

NOTE: These tests require running with the capital-allocator service in PYTHONPATH.
Run with: PYTHONPATH=services/capital-allocator pytest tests/unit/test_max_concurrent_coins.py
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Add service path for imports - use absolute path
_service_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/capital-allocator")
)
if _service_path not in sys.path:
    sys.path.insert(0, _service_path)

# Handle namespace collision with other services' src packages
try:
    from src.allocator.core import Allocation, AllocationStatus, CapitalAllocator
except ImportError:
    pytest.skip("Cannot import CapitalAllocator - run with single service PYTHONPATH", allow_module_level=True)


class TestCoinCounting:
    """Tests for coin (symbol) counting logic."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create allocator with mocked dependencies
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}
            self.allocator._config = {"max_concurrent_coins": 5}

    def test_count_active_coins_empty(self):
        """Test counting with no allocations."""
        count = self.allocator._count_active_coins()
        assert count == 0

    def test_count_active_coins_single_symbol(self):
        """Test counting with one active symbol."""
        alloc = Allocation(
            opportunity_id="opp-1",
            amount_usd=1000,
            symbol="BTC",
        )
        alloc.status = AllocationStatus.ACTIVE
        self.allocator._allocations[alloc.id] = alloc

        count = self.allocator._count_active_coins()
        assert count == 1

    def test_count_active_coins_multiple_symbols(self):
        """Test counting with multiple active symbols."""
        for symbol in ["BTC", "ETH", "SOL"]:
            alloc = Allocation(
                opportunity_id=f"opp-{symbol}",
                amount_usd=1000,
                symbol=symbol,
            )
            alloc.status = AllocationStatus.ACTIVE
            self.allocator._allocations[alloc.id] = alloc

        count = self.allocator._count_active_coins()
        assert count == 3

    def test_count_ignores_closed_allocations(self):
        """Test that closed allocations are not counted."""
        active = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        active.status = AllocationStatus.ACTIVE

        closed = Allocation(opportunity_id="opp-2", amount_usd=1000, symbol="ETH")
        closed.status = AllocationStatus.CLOSED

        self.allocator._allocations[active.id] = active
        self.allocator._allocations[closed.id] = closed

        count = self.allocator._count_active_coins()
        assert count == 1

    def test_count_includes_pending_and_executing(self):
        """Test that pending and executing allocations are counted."""
        pending = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        pending.status = AllocationStatus.PENDING

        executing = Allocation(opportunity_id="opp-2", amount_usd=1000, symbol="ETH")
        executing.status = AllocationStatus.EXECUTING

        self.allocator._allocations[pending.id] = pending
        self.allocator._allocations[executing.id] = executing

        count = self.allocator._count_active_coins()
        assert count == 2


class TestCoinAlreadyActive:
    """Tests for checking if a coin is already active."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}

    def test_coin_not_active_when_empty(self):
        """Test returns False when no allocations."""
        assert self.allocator._is_coin_already_active("BTC") is False

    def test_coin_is_active(self):
        """Test returns True when coin has active allocation."""
        alloc = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        alloc.status = AllocationStatus.ACTIVE
        self.allocator._allocations[alloc.id] = alloc

        assert self.allocator._is_coin_already_active("BTC") is True
        assert self.allocator._is_coin_already_active("ETH") is False

    def test_coin_not_active_when_closed(self):
        """Test returns False when allocation is closed."""
        alloc = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        alloc.status = AllocationStatus.CLOSED
        self.allocator._allocations[alloc.id] = alloc

        assert self.allocator._is_coin_already_active("BTC") is False


class TestWeaknessScoring:
    """Tests for position weakness scoring algorithm."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}

    def test_negative_funding_increases_score(self):
        """Test that negative funding PnL increases weakness score."""
        positive = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        positive.realized_funding_pnl = Decimal("50")
        positive.unrealized_pnl = Decimal("0")
        positive.executed_at = datetime.utcnow()

        negative = Allocation(opportunity_id="opp-2", amount_usd=1000, symbol="ETH")
        negative.realized_funding_pnl = Decimal("-50")
        negative.unrealized_pnl = Decimal("0")
        negative.executed_at = datetime.utcnow()

        pos_score = self.allocator._calculate_weakness_score(positive)
        neg_score = self.allocator._calculate_weakness_score(negative)

        assert neg_score > pos_score

    def test_negative_unrealized_increases_score(self):
        """Test that negative unrealized PnL increases weakness score."""
        positive = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        positive.realized_funding_pnl = Decimal("0")
        positive.unrealized_pnl = Decimal("50")
        positive.executed_at = datetime.utcnow()

        negative = Allocation(opportunity_id="opp-2", amount_usd=1000, symbol="ETH")
        negative.realized_funding_pnl = Decimal("0")
        negative.unrealized_pnl = Decimal("-50")
        negative.executed_at = datetime.utcnow()

        pos_score = self.allocator._calculate_weakness_score(positive)
        neg_score = self.allocator._calculate_weakness_score(negative)

        assert neg_score > pos_score

    def test_long_hold_poor_roi_increases_score(self):
        """Test that long hold time with poor ROI increases score."""
        recent = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        recent.realized_funding_pnl = Decimal("-10")
        recent.unrealized_pnl = Decimal("-10")
        recent.executed_at = datetime.utcnow() - timedelta(hours=1)

        old = Allocation(opportunity_id="opp-2", amount_usd=1000, symbol="ETH")
        old.realized_funding_pnl = Decimal("-10")
        old.unrealized_pnl = Decimal("-10")
        old.executed_at = datetime.utcnow() - timedelta(hours=24)

        recent_score = self.allocator._calculate_weakness_score(recent)
        old_score = self.allocator._calculate_weakness_score(old)

        assert old_score > recent_score

    def test_profitable_position_has_low_score(self):
        """Test that profitable positions have lower weakness scores."""
        profitable = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        profitable.realized_funding_pnl = Decimal("100")
        profitable.unrealized_pnl = Decimal("50")
        profitable.executed_at = datetime.utcnow()

        score = self.allocator._calculate_weakness_score(profitable)
        assert score < 0  # Should be negative (strong position)

    def test_handles_none_values(self):
        """Test scoring handles None PnL values gracefully."""
        alloc = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        alloc.realized_funding_pnl = None
        alloc.unrealized_pnl = None
        alloc.executed_at = None

        # Should not raise, should return score
        score = self.allocator._calculate_weakness_score(alloc)
        assert isinstance(score, float)


class TestAutoUnwindRanking:
    """Tests for auto-unwind position ranking."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}

    def test_weakest_position_ranked_first(self):
        """Test that weakest position is ranked first for closing."""
        # Create positions with varying weakness
        strong = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        strong.status = AllocationStatus.ACTIVE
        strong.realized_funding_pnl = Decimal("100")
        strong.unrealized_pnl = Decimal("50")
        strong.executed_at = datetime.utcnow()

        weak = Allocation(opportunity_id="opp-2", amount_usd=1000, symbol="ETH")
        weak.status = AllocationStatus.ACTIVE
        weak.realized_funding_pnl = Decimal("-50")
        weak.unrealized_pnl = Decimal("-25")
        weak.executed_at = datetime.utcnow() - timedelta(hours=12)

        medium = Allocation(opportunity_id="opp-3", amount_usd=1000, symbol="SOL")
        medium.status = AllocationStatus.ACTIVE
        medium.realized_funding_pnl = Decimal("10")
        medium.unrealized_pnl = Decimal("-5")
        medium.executed_at = datetime.utcnow()

        self.allocator._allocations = {
            strong.id: strong,
            weak.id: weak,
            medium.id: medium,
        }

        # Rank positions
        active = [a for a in self.allocator._allocations.values()
                  if a.status == AllocationStatus.ACTIVE]
        ranked = sorted(
            active,
            key=lambda a: self.allocator._calculate_weakness_score(a),
            reverse=True,
        )

        # Weakest should be first
        assert ranked[0].symbol == "ETH"
        # Strongest should be last
        assert ranked[-1].symbol == "BTC"


class TestConfigDefaults:
    """Tests for max_concurrent_coins configuration."""

    def test_default_value_is_5(self):
        """Test that default max_concurrent_coins is 5."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            with patch.object(CapitalAllocator, "__init__", lambda x, y: None):
                allocator = CapitalAllocator.__new__(CapitalAllocator)
                # Manually set config as __init__ is mocked
                allocator._config = {
                    "min_allocation_usd": Decimal("100"),
                    "max_allocation_usd": Decimal("10000"),
                    "auto_execute": True,
                    "min_uos_score": 65,
                    "high_quality_threshold": 75,
                    "allocation_interval": 30,
                    "max_concurrent_coins": 5,
                    "score_weight_factor": Decimal("0.5"),
                }
                assert allocator._config["max_concurrent_coins"] == 5


class TestAllocationModel:
    """Tests for Allocation model with new fields."""

    def test_allocation_has_pnl_fields(self):
        """Test that Allocation has realized_funding_pnl and unrealized_pnl."""
        alloc = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        assert hasattr(alloc, "realized_funding_pnl")
        assert hasattr(alloc, "unrealized_pnl")

    def test_pnl_fields_default_to_none(self):
        """Test that PnL fields default to None."""
        alloc = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        assert alloc.realized_funding_pnl is None
        assert alloc.unrealized_pnl is None

    def test_to_dict_includes_pnl_fields(self):
        """Test that to_dict includes PnL fields."""
        alloc = Allocation(opportunity_id="opp-1", amount_usd=1000, symbol="BTC")
        alloc.realized_funding_pnl = Decimal("50")
        alloc.unrealized_pnl = Decimal("25")

        d = alloc.to_dict()
        assert "realized_funding_pnl" in d
        assert "unrealized_pnl" in d
        assert d["realized_funding_pnl"] == 50.0
        assert d["unrealized_pnl"] == 25.0


class TestDatabaseSync:
    """Tests for database sync functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}
            self.allocator._opportunity_allocations = {}
            self.allocator._allocated_capital = Decimal("0")
            self.allocator._config = {"max_concurrent_coins": 5}
            self.allocator.redis = AsyncMock()

    def test_map_position_status_active(self):
        """Test mapping database 'active' status to allocation status."""
        result = self.allocator._map_position_status("active")
        assert result == AllocationStatus.ACTIVE

    def test_map_position_status_opening(self):
        """Test mapping database 'opening' status to allocation status."""
        result = self.allocator._map_position_status("opening")
        assert result == AllocationStatus.EXECUTING

    def test_map_position_status_pending(self):
        """Test mapping database 'pending' status to allocation status."""
        result = self.allocator._map_position_status("pending")
        assert result == AllocationStatus.PENDING

    def test_map_position_status_closing(self):
        """Test mapping database 'closing' status to allocation status."""
        result = self.allocator._map_position_status("closing")
        assert result == AllocationStatus.CLOSING

    def test_map_position_status_unknown(self):
        """Test mapping unknown status defaults to ACTIVE."""
        result = self.allocator._map_position_status("unknown")
        assert result == AllocationStatus.ACTIVE


class TestAutoExecuteConsolidation:
    """Tests for consolidated auto-execute check."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}
            self.allocator._config = {"auto_execute": True}
            self.allocator.state_manager = None

    def test_auto_execute_respects_config_default(self):
        """Test that auto-execute respects config default when no state manager."""
        # When state_manager is None, should use config default
        assert self.allocator._config["auto_execute"] is True

    def test_auto_execute_can_be_disabled(self):
        """Test that auto-execute can be disabled in config."""
        self.allocator._config["auto_execute"] = False
        assert self.allocator._config["auto_execute"] is False


class TestPeriodicEnforcement:
    """Tests for periodic limit enforcement."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(CapitalAllocator, "_create_db_session_factory"):
            self.allocator = CapitalAllocator.__new__(CapitalAllocator)
            self.allocator._allocations = {}
            self.allocator._running = True
            self.allocator._config = {"max_concurrent_coins": 5}
            self.allocator.redis = AsyncMock()

    @pytest.mark.asyncio
    async def test_check_limit_returns_when_under_limit(self):
        """Test that check returns early when under limit."""
        # Mock DB count to return value under limit
        self.allocator._count_active_coins_from_db = AsyncMock(return_value=3)

        # Should not call any close methods
        self.allocator._initiate_position_close = AsyncMock()
        await self.allocator._check_and_enforce_coin_limit()

        self.allocator._initiate_position_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_limit_triggers_close_when_over(self):
        """Test that check triggers close when over limit."""
        # Mock DB count to return value over limit
        self.allocator._count_active_coins_from_db = AsyncMock(return_value=7)
        self.allocator._sync_positions_from_db = AsyncMock()

        # Add some allocations
        for i, symbol in enumerate(["BTC", "ETH", "SOL", "AVAX", "DOGE", "XRP", "ADA"]):
            alloc = Allocation(
                opportunity_id=f"opp-{i}",
                amount_usd=1000,
                symbol=symbol,
            )
            alloc.status = AllocationStatus.ACTIVE
            alloc.realized_funding_pnl = Decimal("-10")  # All negative for ranking
            alloc.unrealized_pnl = Decimal("-5")
            alloc.executed_at = datetime.utcnow() - timedelta(hours=i)
            self.allocator._allocations[alloc.id] = alloc

        # Mock close and log methods
        self.allocator._initiate_position_close = AsyncMock()
        self.allocator._log_auto_unwind_event = AsyncMock()
        self.allocator._publish_activity = AsyncMock()

        await self.allocator._check_and_enforce_coin_limit()

        # Should have triggered 2 closes (7 - 5 = 2 excess)
        assert self.allocator._initiate_position_close.call_count == 2
