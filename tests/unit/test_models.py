"""Unit tests for shared models."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from shared.models.exchange import MarketType
from shared.models.funding import FundingRateData, FundingRateSource
from shared.models.opportunity import (Opportunity, OpportunityLeg,
                                       OpportunityStatus, OpportunityType,
                                       UOSScores)
from shared.models.position import Position, PositionLeg, PositionStatus


class TestFundingRateData:
    """Tests for FundingRateData model."""

    def test_create_funding_rate(self):
        """Test creating a FundingRateData instance."""
        next_funding = datetime.utcnow() + timedelta(hours=4)
        rate = FundingRateData(
            exchange="binance",
            symbol="BTCUSDT",
            ticker="BTC",
            rate=Decimal("0.0001"),
            next_funding_time=next_funding,
            source=FundingRateSource.EXCHANGE_API,
            predicted_rate=Decimal("0.00012"),
            funding_interval_hours=8,
            timestamp=datetime.utcnow(),
        )

        assert rate.exchange == "binance"
        assert rate.symbol == "BTCUSDT"
        assert rate.ticker == "BTC"
        assert rate.rate == Decimal("0.0001")
        assert rate.funding_interval_hours == 8
        assert rate.source == FundingRateSource.EXCHANGE_API

    def test_funding_rate_annualized(self):
        """Test annualized funding rate calculation."""
        next_funding = datetime.utcnow() + timedelta(hours=4)
        rate = FundingRateData(
            exchange="binance",
            symbol="BTCUSDT",
            ticker="BTC",
            rate=Decimal("0.01"),  # 0.01% per 8 hours
            next_funding_time=next_funding,
            source=FundingRateSource.EXCHANGE_API,
            funding_interval_hours=8,
            timestamp=datetime.utcnow(),
        )

        # 0.01% * 3 times/day * 365 days = 10.95%
        expected_apr = Decimal("0.01") * 3 * 365
        assert rate.rate_annualized == expected_apr


class TestUOSScores:
    """Tests for UOS scoring model."""

    def test_uos_total_calculation(self):
        """Test that UOS total equals sum of components."""
        scores = UOSScores(
            return_score=25,
            risk_score=20,
            execution_score=18,
            timing_score=12,
        )

        calculated_total = (
            scores.return_score
            + scores.risk_score
            + scores.execution_score
            + scores.timing_score
        )
        assert scores.total == calculated_total
        assert scores.total == 75

    def test_uos_score_ranges(self):
        """Test that UOS scores are within valid ranges."""
        scores = UOSScores(
            return_score=25,  # Max 30
            risk_score=20,  # Max 30
            execution_score=18,  # Max 25
            timing_score=12,  # Max 15
        )

        assert 0 <= scores.return_score <= 30
        assert 0 <= scores.risk_score <= 30
        assert 0 <= scores.execution_score <= 25
        assert 0 <= scores.timing_score <= 15
        assert 0 <= scores.total <= 100


class TestOpportunity:
    """Tests for Opportunity model."""

    def test_create_opportunity(self):
        """Test creating an Opportunity instance."""
        primary_leg = OpportunityLeg(
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
            side="long",
            funding_rate=Decimal("-0.0001"),
            receives_funding=True,
            current_price=Decimal("50000"),
            estimated_slippage_pct=Decimal("0.001"),
        )

        hedge_leg = OpportunityLeg(
            exchange="bybit",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
            side="short",
            funding_rate=Decimal("0.0002"),
            receives_funding=False,
            current_price=Decimal("50050"),
            estimated_slippage_pct=Decimal("0.001"),
        )

        scores = UOSScores(
            return_score=25,
            risk_score=20,
            execution_score=18,
            timing_score=12,
        )

        opportunity = Opportunity(
            id=str(uuid4()),
            base_asset="BTC",
            symbol="BTCUSDT",
            opportunity_type=OpportunityType.CROSS_EXCHANGE_PERP,
            primary_leg=primary_leg,
            hedge_leg=hedge_leg,
            gross_funding_rate=Decimal("0.0003"),
            gross_apr=Decimal("32.85"),
            net_apr=Decimal("30.0"),
            scores=scores,
            detected_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            status=OpportunityStatus.DETECTED,
        )

        assert opportunity.symbol == "BTCUSDT"
        assert opportunity.uos_score == 75
        assert opportunity.primary_leg.exchange == "binance"
        assert opportunity.hedge_leg.exchange == "bybit"


class TestPosition:
    """Tests for Position model."""

    def test_create_position(self):
        """Test creating a Position instance."""
        primary_leg = PositionLeg(
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
            side="long",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.0"),
            current_price=Decimal("50100.0"),
            notional_value_usd=Decimal("5000"),
        )

        hedge_leg = PositionLeg(
            exchange="bybit",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
            side="short",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50050.0"),
            current_price=Decimal("50100.0"),
            notional_value_usd=Decimal("5000"),
        )

        position = Position(
            id=uuid4(),
            opportunity_id=uuid4(),
            base_asset="BTC",
            symbol="BTCUSDT",
            opportunity_type=OpportunityType.CROSS_EXCHANGE_PERP,
            primary_leg=primary_leg,
            hedge_leg=hedge_leg,
            total_capital_deployed=Decimal("10000"),
            funding_received=Decimal("50"),
            funding_paid=Decimal("10"),
            status=PositionStatus.ACTIVE,
            opened_at=datetime.utcnow(),
        )

        assert position.symbol == "BTCUSDT"
        assert position.status == PositionStatus.ACTIVE
        assert position.net_funding_pnl == Decimal("40")
