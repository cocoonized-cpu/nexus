"""
Position models for NEXUS funding rate arbitrage.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import Field, computed_field

from shared.models.base import BaseModel
from shared.models.exchange import MarketType
from shared.models.opportunity import OpportunityType


class PositionStatus(str, Enum):
    """Lifecycle status of a position."""

    PENDING = "pending"  # Awaiting execution window
    OPENING = "opening"  # Orders submitted, awaiting fills
    ACTIVE = "active"  # Position fully established
    CLOSING = "closing"  # Exit orders submitted
    CLOSED = "closed"  # Position fully unwound
    CANCELLED = "cancelled"  # Abandoned before execution
    FAILED = "failed"  # Execution failed
    EMERGENCY_CLOSE = "emergency_close"  # Risk-triggered closure


class PositionHealthStatus(str, Enum):
    """Health status of an active position."""

    HEALTHY = "healthy"  # All metrics within normal range
    ATTENTION = "attention"  # Some metrics approaching limits
    WARNING = "warning"  # Metrics near critical levels
    CRITICAL = "critical"  # Immediate action required


class PositionLeg(BaseModel):
    """
    One leg of an active arbitrage position.

    Represents a single position on one exchange.
    """

    id: UUID = Field(default_factory=uuid4)
    exchange: str
    symbol: str
    market_type: MarketType
    side: str = Field(..., description="'long' or 'short'")

    # Position Details
    quantity: Decimal = Field(..., description="Position size in base asset")
    entry_price: Decimal
    current_price: Decimal
    notional_value_usd: Decimal

    # Perpetual-specific
    margin_used: Decimal = Decimal("0")
    leverage: Decimal = Decimal("1")
    liquidation_price: Optional[Decimal] = None

    # P&L
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    funding_pnl: Decimal = Decimal("0")

    # Execution
    entry_timestamp: datetime = Field(default_factory=datetime.utcnow)
    entry_order_ids: list[str] = Field(default_factory=list)
    entry_fees: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")

    # Exit (when closed)
    exit_timestamp: Optional[datetime] = None
    exit_order_ids: list[str] = Field(default_factory=list)
    exit_fees: Decimal = Decimal("0")
    avg_exit_price: Optional[Decimal] = None

    @computed_field
    @property
    def side_multiplier(self) -> int:
        """Get side multiplier for P&L calculations."""
        return -1 if self.side == "short" else 1

    @computed_field
    @property
    def price_pnl(self) -> Decimal:
        """Calculate P&L from price movement."""
        price_diff = self.current_price - self.entry_price
        return price_diff * self.quantity * self.side_multiplier

    @computed_field
    @property
    def margin_utilization(self) -> Decimal:
        """Calculate margin utilization percentage."""
        if self.margin_used == 0:
            return Decimal("0")
        return self.margin_used / self.notional_value_usd * 100

    @computed_field
    @property
    def distance_to_liquidation(self) -> Optional[Decimal]:
        """Calculate distance to liquidation as percentage."""
        if self.liquidation_price is None or self.current_price == 0:
            return None
        distance = abs(self.current_price - self.liquidation_price)
        return distance / self.current_price * 100


class FundingPayment(BaseModel):
    """Record of a funding payment received or paid."""

    id: UUID = Field(default_factory=uuid4)
    position_id: UUID
    leg_id: UUID
    exchange: str
    symbol: str
    funding_rate: Decimal
    payment_amount: Decimal  # Positive = received, negative = paid
    position_size: Decimal
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Position(BaseModel):
    """
    Complete arbitrage position with all legs.

    Represents an active or historical position with full tracking.
    """

    id: UUID = Field(default_factory=uuid4)
    opportunity_id: Optional[UUID] = None
    opportunity_type: OpportunityType
    base_asset: str
    symbol: str
    status: PositionStatus = PositionStatus.PENDING

    # Legs
    primary_leg: PositionLeg
    hedge_leg: PositionLeg
    additional_legs: list[PositionLeg] = Field(default_factory=list)

    # Financial
    total_capital_deployed: Decimal
    entry_costs_paid: Decimal = Decimal("0")
    exit_costs_paid: Decimal = Decimal("0")
    funding_received: Decimal = Decimal("0")
    funding_paid: Decimal = Decimal("0")

    # Risk Metrics (continuously updated)
    net_delta: Decimal = Decimal("0")
    delta_exposure_pct: Decimal = Decimal("0")
    max_margin_utilization: Decimal = Decimal("0")
    min_liquidation_distance: Optional[Decimal] = None
    health_status: PositionHealthStatus = PositionHealthStatus.HEALTHY

    # Timing
    opened_at: Optional[datetime] = None
    last_funding_collected: Optional[datetime] = None
    funding_periods_collected: int = 0
    expected_next_funding: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # Exit Configuration
    target_funding_rate_min: Decimal = Decimal("0.005")  # 0.005%
    stop_loss_pct: Decimal = Decimal("2")  # 2% loss
    take_profit_pct: Optional[Decimal] = None
    max_hold_periods: int = 72  # 24 hours * 3 for 8h funding

    # Exit Reason (when closed)
    exit_reason: Optional[str] = None

    @computed_field
    @property
    def net_funding_pnl(self) -> Decimal:
        """Calculate net funding P&L."""
        return self.funding_received - self.funding_paid

    @computed_field
    @property
    def price_pnl(self) -> Decimal:
        """Calculate total price P&L across all legs."""
        total = self.primary_leg.price_pnl + self.hedge_leg.price_pnl
        for leg in self.additional_legs:
            total += leg.price_pnl
        return total

    @computed_field
    @property
    def total_unrealized_pnl(self) -> Decimal:
        """Calculate total unrealized P&L."""
        return self.net_funding_pnl + self.price_pnl - self.entry_costs_paid

    @computed_field
    @property
    def total_realized_pnl(self) -> Decimal:
        """Calculate total realized P&L (for closed positions)."""
        if self.status != PositionStatus.CLOSED:
            return Decimal("0")
        return (
            self.net_funding_pnl
            + self.price_pnl
            - self.entry_costs_paid
            - self.exit_costs_paid
        )

    @computed_field
    @property
    def return_pct(self) -> Decimal:
        """Calculate return percentage."""
        if self.total_capital_deployed == 0:
            return Decimal("0")
        pnl = (
            self.total_realized_pnl
            if self.status == PositionStatus.CLOSED
            else self.total_unrealized_pnl
        )
        return pnl / self.total_capital_deployed * 100

    @computed_field
    @property
    def hold_duration_hours(self) -> Optional[float]:
        """Calculate how long position has been open."""
        if self.opened_at is None:
            return None
        end_time = self.closed_at or datetime.utcnow()
        delta = end_time - self.opened_at
        return delta.total_seconds() / 3600

    def calculate_health(self) -> PositionHealthStatus:
        """
        Calculate and update health status based on risk metrics.

        Returns:
            Updated health status
        """
        # Check delta exposure
        if self.delta_exposure_pct > 5:
            return PositionHealthStatus.CRITICAL
        if self.delta_exposure_pct > 3:
            return PositionHealthStatus.WARNING
        if self.delta_exposure_pct > 1:
            return PositionHealthStatus.ATTENTION

        # Check margin utilization
        if self.max_margin_utilization > 85:
            return PositionHealthStatus.CRITICAL
        if self.max_margin_utilization > 70:
            return PositionHealthStatus.WARNING
        if self.max_margin_utilization > 50:
            return PositionHealthStatus.ATTENTION

        # Check liquidation distance
        if self.min_liquidation_distance is not None:
            if self.min_liquidation_distance < 10:
                return PositionHealthStatus.CRITICAL
            if self.min_liquidation_distance < 20:
                return PositionHealthStatus.WARNING
            if self.min_liquidation_distance < 30:
                return PositionHealthStatus.ATTENTION

        return PositionHealthStatus.HEALTHY

    def should_exit(self) -> tuple[bool, Optional[str]]:
        """
        Evaluate all exit triggers.

        Returns:
            Tuple of (should_exit, reason)
        """
        # Risk triggers (immediate)
        if self.health_status == PositionHealthStatus.CRITICAL:
            return True, "critical_health"

        # Funding rate deterioration
        primary_rate = self.primary_leg.funding_pnl / max(
            self.funding_periods_collected, 1
        )
        if (
            self.funding_periods_collected >= 3
            and primary_rate < self.target_funding_rate_min
        ):
            return True, "funding_below_threshold"

        # Stop loss
        if self.return_pct < -self.stop_loss_pct:
            return True, "stop_loss"

        # Take profit
        if self.take_profit_pct is not None and self.return_pct > self.take_profit_pct:
            return True, "take_profit"

        # Max hold time
        if self.funding_periods_collected >= self.max_hold_periods:
            return True, "max_hold_time"

        return False, None

    def update_metrics(self) -> None:
        """Update all calculated metrics."""
        # Calculate delta exposure
        primary_delta = (
            self.primary_leg.notional_value_usd * self.primary_leg.side_multiplier
        )
        hedge_delta = self.hedge_leg.notional_value_usd * self.hedge_leg.side_multiplier
        total_delta = primary_delta + hedge_delta

        for leg in self.additional_legs:
            total_delta += leg.notional_value_usd * leg.side_multiplier

        total_notional = (
            self.primary_leg.notional_value_usd + self.hedge_leg.notional_value_usd
        )
        self.net_delta = total_delta
        self.delta_exposure_pct = (
            abs(total_delta) / total_notional * 100
            if total_notional > 0
            else Decimal("0")
        )

        # Calculate margin utilization
        margin_utils = [self.primary_leg.margin_utilization]
        if self.hedge_leg.market_type == MarketType.PERPETUAL:
            margin_utils.append(self.hedge_leg.margin_utilization)
        self.max_margin_utilization = max(margin_utils)

        # Calculate liquidation distance
        distances = []
        if self.primary_leg.distance_to_liquidation is not None:
            distances.append(self.primary_leg.distance_to_liquidation)
        if self.hedge_leg.distance_to_liquidation is not None:
            distances.append(self.hedge_leg.distance_to_liquidation)
        self.min_liquidation_distance = min(distances) if distances else None

        # Update health status
        self.health_status = self.calculate_health()


class PositionSummary(BaseModel):
    """Summary of a position for display."""

    id: UUID
    symbol: str
    opportunity_type: OpportunityType
    status: PositionStatus
    health_status: PositionHealthStatus
    primary_exchange: str
    hedge_exchange: str
    capital_deployed: Decimal
    unrealized_pnl: Decimal
    return_pct: Decimal
    funding_collected: Decimal
    funding_periods: int
    opened_at: Optional[datetime]

    @classmethod
    def from_position(cls, pos: Position) -> "PositionSummary":
        """Create summary from full position."""
        return cls(
            id=pos.id,
            symbol=pos.symbol,
            opportunity_type=pos.opportunity_type,
            status=pos.status,
            health_status=pos.health_status,
            primary_exchange=pos.primary_leg.exchange,
            hedge_exchange=pos.hedge_leg.exchange,
            capital_deployed=pos.total_capital_deployed,
            unrealized_pnl=pos.total_unrealized_pnl,
            return_pct=pos.return_pct,
            funding_collected=pos.net_funding_pnl,
            funding_periods=pos.funding_periods_collected,
            opened_at=pos.opened_at,
        )
