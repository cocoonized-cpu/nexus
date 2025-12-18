"""
Risk management models for NEXUS.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import Field

from shared.models.base import BaseModel


class RiskAlertSeverity(str, Enum):
    """Severity level of risk alerts."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAlertType(str, Enum):
    """Type of risk alert."""

    POSITION_HEALTH = "position_health"
    DELTA_EXPOSURE = "delta_exposure"
    MARGIN_WARNING = "margin_warning"
    LIQUIDATION_RISK = "liquidation_risk"
    CONCENTRATION = "concentration"
    DRAWDOWN = "drawdown"
    VAR_BREACH = "var_breach"
    VENUE_EXPOSURE = "venue_exposure"
    ASSET_EXPOSURE = "asset_exposure"
    EXCHANGE_DEGRADED = "exchange_degraded"
    DATA_ANOMALY = "data_anomaly"


class RiskMode(str, Enum):
    """Operational risk mode."""

    DISCOVERY = "discovery"  # Paper trading, no real orders
    CONSERVATIVE = "conservative"  # Reduced sizes, stricter limits
    STANDARD = "standard"  # Normal operation
    AGGRESSIVE = "aggressive"  # Larger sizes (use with caution)
    EMERGENCY = "emergency"  # Close only, no new positions


class RiskLimits(BaseModel):
    """
    Risk limits configuration.

    Stored in database and adjustable at runtime.
    """

    # Position Limits
    max_position_size_usd: Decimal = Decimal("50000")
    max_position_size_pct: Decimal = Decimal("5")  # % of total capital
    max_leverage: Decimal = Decimal("3")

    # Concentration Limits
    max_venue_exposure_pct: Decimal = Decimal("35")  # % per venue
    max_asset_exposure_pct: Decimal = Decimal("20")  # % per asset
    max_correlated_exposure_pct: Decimal = Decimal("40")

    # Portfolio Limits
    max_gross_exposure_pct: Decimal = Decimal("200")
    max_net_exposure_pct: Decimal = Decimal("10")
    max_drawdown_pct: Decimal = Decimal("5")
    max_var_pct: Decimal = Decimal("2")  # 95% 1-day VaR

    # Position Health Limits
    max_delta_exposure_pct: Decimal = Decimal("2")  # Per position
    min_liquidation_distance_pct: Decimal = Decimal("20")
    max_margin_utilization_pct: Decimal = Decimal("70")

    # Timing Limits
    min_hold_funding_periods: int = 2
    max_hold_days: int = 30

    def get_adjusted_limits(self, mode: RiskMode) -> "RiskLimits":
        """
        Get limits adjusted for operational mode.

        Args:
            mode: Current risk mode

        Returns:
            Adjusted limits
        """
        if mode == RiskMode.CONSERVATIVE:
            return RiskLimits(
                max_position_size_usd=self.max_position_size_usd * Decimal("0.5"),
                max_position_size_pct=self.max_position_size_pct * Decimal("0.5"),
                max_leverage=min(self.max_leverage, Decimal("2")),
                max_venue_exposure_pct=self.max_venue_exposure_pct * Decimal("0.7"),
                max_asset_exposure_pct=self.max_asset_exposure_pct * Decimal("0.7"),
                max_correlated_exposure_pct=self.max_correlated_exposure_pct
                * Decimal("0.7"),
                max_gross_exposure_pct=self.max_gross_exposure_pct * Decimal("0.7"),
                max_net_exposure_pct=self.max_net_exposure_pct,
                max_drawdown_pct=self.max_drawdown_pct * Decimal("0.6"),
                max_var_pct=self.max_var_pct * Decimal("0.7"),
                max_delta_exposure_pct=self.max_delta_exposure_pct,
                min_liquidation_distance_pct=self.min_liquidation_distance_pct
                * Decimal("1.5"),
                max_margin_utilization_pct=self.max_margin_utilization_pct
                * Decimal("0.7"),
                min_hold_funding_periods=self.min_hold_funding_periods,
                max_hold_days=self.max_hold_days,
            )
        elif mode == RiskMode.AGGRESSIVE:
            return RiskLimits(
                max_position_size_usd=self.max_position_size_usd * Decimal("1.5"),
                max_position_size_pct=self.max_position_size_pct * Decimal("1.5"),
                max_leverage=min(self.max_leverage * Decimal("1.5"), Decimal("5")),
                max_venue_exposure_pct=min(
                    self.max_venue_exposure_pct * Decimal("1.3"), Decimal("50")
                ),
                max_asset_exposure_pct=min(
                    self.max_asset_exposure_pct * Decimal("1.3"), Decimal("30")
                ),
                max_correlated_exposure_pct=min(
                    self.max_correlated_exposure_pct * Decimal("1.3"), Decimal("50")
                ),
                max_gross_exposure_pct=min(
                    self.max_gross_exposure_pct * Decimal("1.3"), Decimal("300")
                ),
                max_net_exposure_pct=self.max_net_exposure_pct * Decimal("1.5"),
                max_drawdown_pct=self.max_drawdown_pct * Decimal("2"),
                max_var_pct=self.max_var_pct * Decimal("1.5"),
                max_delta_exposure_pct=self.max_delta_exposure_pct * Decimal("1.5"),
                min_liquidation_distance_pct=self.min_liquidation_distance_pct
                * Decimal("0.7"),
                max_margin_utilization_pct=min(
                    self.max_margin_utilization_pct * Decimal("1.2"), Decimal("85")
                ),
                min_hold_funding_periods=self.min_hold_funding_periods,
                max_hold_days=self.max_hold_days,
            )
        elif mode == RiskMode.EMERGENCY:
            # In emergency mode, no new positions allowed
            return RiskLimits(
                max_position_size_usd=Decimal("0"),
                max_position_size_pct=Decimal("0"),
                max_leverage=Decimal("0"),
                max_venue_exposure_pct=Decimal("0"),
                max_asset_exposure_pct=Decimal("0"),
                max_correlated_exposure_pct=Decimal("0"),
                max_gross_exposure_pct=Decimal("0"),
                max_net_exposure_pct=Decimal("0"),
                max_drawdown_pct=self.max_drawdown_pct,
                max_var_pct=self.max_var_pct,
                max_delta_exposure_pct=self.max_delta_exposure_pct,
                min_liquidation_distance_pct=self.min_liquidation_distance_pct,
                max_margin_utilization_pct=self.max_margin_utilization_pct,
                min_hold_funding_periods=0,
                max_hold_days=0,
            )
        return self

    def check_position_allowed(
        self,
        position_size_usd: Decimal,
        position_size_pct: Decimal,
        venue_exposure_after: Decimal,
        asset_exposure_after: Decimal,
    ) -> tuple[bool, list[str]]:
        """
        Check if a new position is allowed under current limits.

        Returns:
            Tuple of (allowed, list of violations)
        """
        violations = []

        if position_size_usd > self.max_position_size_usd:
            violations.append(
                f"Position size ${position_size_usd} exceeds max ${self.max_position_size_usd}"
            )

        if position_size_pct > self.max_position_size_pct:
            violations.append(
                f"Position size {position_size_pct}% exceeds max {self.max_position_size_pct}%"
            )

        if venue_exposure_after > self.max_venue_exposure_pct:
            violations.append(
                f"Venue exposure {venue_exposure_after}% would exceed max {self.max_venue_exposure_pct}%"
            )

        if asset_exposure_after > self.max_asset_exposure_pct:
            violations.append(
                f"Asset exposure {asset_exposure_after}% would exceed max {self.max_asset_exposure_pct}%"
            )

        return len(violations) == 0, violations


class RiskAlert(BaseModel):
    """A risk alert triggered by the system."""

    id: UUID = Field(default_factory=uuid4)
    alert_type: RiskAlertType
    severity: RiskAlertSeverity
    title: str
    message: str
    position_id: Optional[UUID] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    current_value: Optional[Decimal] = None
    threshold_value: Optional[Decimal] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None

    @property
    def is_acknowledged(self) -> bool:
        """Check if alert has been acknowledged."""
        return self.acknowledged_at is not None

    @property
    def is_resolved(self) -> bool:
        """Check if alert has been resolved."""
        return self.resolved_at is not None


class RiskState(BaseModel):
    """
    Current risk state of the portfolio.

    Continuously updated by the risk manager.
    """

    # Portfolio Metrics
    total_capital_usd: Decimal = Decimal("0")
    total_exposure_usd: Decimal = Decimal("0")
    gross_exposure_pct: Decimal = Decimal("0")
    net_exposure_pct: Decimal = Decimal("0")
    portfolio_delta: Decimal = Decimal("0")
    portfolio_var: Decimal = Decimal("0")
    current_drawdown_pct: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    current_equity: Decimal = Decimal("0")

    # Exposure Breakdowns
    venue_exposures: dict[str, Decimal] = Field(default_factory=dict)
    asset_exposures: dict[str, Decimal] = Field(default_factory=dict)
    strategy_exposures: dict[str, Decimal] = Field(default_factory=dict)

    # Risk Budget
    var_budget_used_pct: Decimal = Decimal("0")
    drawdown_budget_remaining_pct: Decimal = Decimal("100")

    # Position Health Summary
    positions_total: int = 0
    positions_healthy: int = 0
    positions_attention: int = 0
    positions_warning: int = 0
    positions_critical: int = 0

    # Current Mode
    risk_mode: RiskMode = RiskMode.STANDARD

    # Active Alerts
    active_alerts: int = 0
    critical_alerts: int = 0

    # Last Update
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def update_drawdown(self, current_equity: Decimal) -> None:
        """Update drawdown calculations."""
        self.current_equity = current_equity

        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        if self.peak_equity > 0:
            self.current_drawdown_pct = (
                (self.peak_equity - current_equity) / self.peak_equity * 100
            )
        else:
            self.current_drawdown_pct = Decimal("0")

    def can_add_risk(
        self, additional_var: Decimal, limits: RiskLimits
    ) -> tuple[bool, Optional[str]]:
        """
        Check if additional risk can be taken.

        Args:
            additional_var: Additional VaR from new position
            limits: Current risk limits

        Returns:
            Tuple of (can_add, reason if not)
        """
        if self.risk_mode == RiskMode.EMERGENCY:
            return False, "System in emergency mode"

        # Check VaR budget
        new_var_pct = self.var_budget_used_pct + (
            additional_var / self.total_capital_usd * 100
            if self.total_capital_usd > 0
            else Decimal("100")
        )
        if new_var_pct > limits.max_var_pct:
            return (
                False,
                f"VaR budget would exceed limit ({new_var_pct}% > {limits.max_var_pct}%)",
            )

        # Check drawdown budget
        if self.current_drawdown_pct > limits.max_drawdown_pct * Decimal("0.75"):
            return False, f"Drawdown too high ({self.current_drawdown_pct}%)"

        # Check for critical positions
        if self.positions_critical > 0:
            return False, f"{self.positions_critical} position(s) in critical state"

        return True, None


class RiskCheckResult(BaseModel):
    """Result of a risk check."""

    approved: bool
    max_approved_size: Decimal = Decimal("0")
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    adjusted_limits_applied: bool = False
    risk_mode: RiskMode = RiskMode.STANDARD
