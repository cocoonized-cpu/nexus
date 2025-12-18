"""
Opportunity models for NEXUS funding rate arbitrage.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import Field, computed_field

from shared.models.base import BaseModel
from shared.models.exchange import MarketType


class OpportunityType(str, Enum):
    """Type of arbitrage opportunity."""

    SPOT_PERP = "spot_perp"  # Type A: Single venue spot-perp
    CROSS_EXCHANGE_PERP = "cross_exchange_perp"  # Type B: Cross-exchange perpetual
    CEX_DEX = "cex_dex"  # Type C: CEX-DEX hybrid
    TRIANGULAR = "triangular"  # Type D: Multi-leg triangular
    TEMPORAL = "temporal"  # Type E: Time-based funding capture


class OpportunityStatus(str, Enum):
    """Status of an opportunity."""

    DETECTED = "detected"  # Just found
    VALIDATED = "validated"  # Confirmed valid
    SCORED = "scored"  # UOS score calculated
    ALLOCATED = "allocated"  # Capital allocated
    EXECUTING = "executing"  # Being executed
    EXECUTED = "executed"  # Position opened
    EXPIRED = "expired"  # No longer valid
    REJECTED = "rejected"  # Failed validation or risk check


class OpportunityConfidence(str, Enum):
    """Confidence level of opportunity data."""

    HIGH = "high"  # Both sources agree
    MEDIUM = "medium"  # Only one source or minor discrepancy
    LOW = "low"  # Data uncertainty


class OpportunityLeg(BaseModel):
    """
    One side of an arbitrage opportunity.

    Represents either the funding-receiving leg or the hedging leg.
    """

    exchange: str = Field(..., description="Exchange slug")
    symbol: Optional[str] = Field(None, description="Trading pair")
    market_type: MarketType = MarketType.PERPETUAL
    side: str = Field(..., description="'long' or 'short'")
    funding_rate: float = Field(0, description="Funding rate (0 for spot)")
    receives_funding: bool = Field(
        False, description="Whether this leg receives funding payments"
    )
    current_price: Optional[Decimal] = None
    available_liquidity_usd: Decimal = Decimal("0")
    estimated_slippage_pct: Decimal = Decimal("0")
    estimated_slippage: Optional[float] = None  # Alternative field name
    fee_rate: Decimal = Field(
        Decimal("0.0005"), description="Expected fee rate (taker assumed)"
    )

    @computed_field
    @property
    def is_short(self) -> bool:
        """Check if this is a short position."""
        return self.side == "short"

    @computed_field
    @property
    def side_multiplier(self) -> int:
        """Get side multiplier for P&L calculations."""
        return -1 if self.is_short else 1


class UOSScores(BaseModel):
    """
    Unified Opportunity Score (UOS) components.

    Total score is 0-100, composed of:
    - Return Score: 0-30 points
    - Risk Score: 0-30 points
    - Execution Score: 0-25 points
    - Timing Score: 0-15 points
    """

    return_score: int = Field(0, ge=0, le=30)
    risk_score: int = Field(0, ge=0, le=30)
    execution_score: int = Field(0, ge=0, le=25)
    timing_score: int = Field(0, ge=0, le=15)

    # Sub-components for analysis
    base_return_score: Decimal = Decimal("0")
    persistence_bonus: Decimal = Decimal("0")
    history_bonus: Decimal = Decimal("0")
    stability_score: Decimal = Decimal("0")
    basis_score: Decimal = Decimal("0")
    liquidation_score: Decimal = Decimal("0")
    liquidity_score: Decimal = Decimal("0")
    slippage_score: Decimal = Decimal("0")
    reliability_score: Decimal = Decimal("0")

    @computed_field
    @property
    def total(self) -> int:
        """Calculate total UOS score."""
        return (
            self.return_score
            + self.risk_score
            + self.execution_score
            + self.timing_score
        )

    @computed_field
    @property
    def quality(self) -> str:
        """Get quality classification based on score."""
        score = self.total
        if score >= 80:
            return "exceptional"
        if score >= 60:
            return "strong"
        if score >= 40:
            return "moderate"
        if score >= 20:
            return "weak"
        return "poor"


class BotActionStatus(str, Enum):
    """Bot action status for an opportunity."""

    AUTO_TRADE = "auto_trade"  # Will be automatically executed
    MANUAL_ONLY = "manual_only"  # Can execute manually, not auto-traded
    WAITING = "waiting"  # Blocked by temporary conditions
    BLOCKED = "blocked"  # Cannot be executed


class BotActionDetail(BaseModel):
    """Individual rule evaluation detail for bot action."""

    rule: str = Field(..., description="Rule identifier (e.g., 'uos_score', 'auto_execute')")
    passed: bool = Field(..., description="Whether this rule passed")
    current: Optional[str] = Field(None, description="Current value (as string for display)")
    threshold: Optional[str] = Field(None, description="Threshold value (as string for display)")
    message: str = Field(..., description="Human-readable explanation")


class BotAction(BaseModel):
    """
    Bot trading action status for an opportunity.

    Explains why the bot is or isn't trading this opportunity
    and what action the user can take.
    """

    status: BotActionStatus = Field(..., description="Overall action status")
    reason: str = Field(..., description="Brief explanation (one line)")
    details: list[BotActionDetail] = Field(
        default_factory=list, description="Detailed rule evaluations"
    )
    user_action: Optional[str] = Field(
        None, description="What user can do to enable trading (if blocked)"
    )
    can_execute: bool = Field(
        True, description="Whether manual execution is possible"
    )


class Opportunity(BaseModel):
    """
    Complete arbitrage opportunity.

    Represents a potential trade setup with all necessary information
    for evaluation, allocation, and execution.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    opportunity_type: str = Field("funding_arbitrage", description="Type of opportunity")
    base_asset: Optional[str] = Field(None, description="Base asset (e.g., 'BTC')")
    symbol: str = Field(..., description="Full symbol (e.g., 'BTCUSDT')")
    status: str = Field("detected", description="Opportunity status")

    # Legs - support both naming conventions
    primary_leg: Optional[OpportunityLeg] = Field(
        None, description="The leg that receives funding"
    )
    hedge_leg: Optional[OpportunityLeg] = Field(None, description="The hedging leg")
    long_leg: Optional[OpportunityLeg] = Field(None, description="Long leg (alias)")
    short_leg: Optional[OpportunityLeg] = Field(None, description="Short leg (alias)")
    additional_legs: list[OpportunityLeg] = Field(
        default_factory=list, description="Additional legs for complex strategies"
    )

    # Financial Metrics - support both naming conventions
    gross_funding_rate: Optional[Decimal] = Field(
        None, description="Net funding rate (received - paid)"
    )
    funding_spread: Optional[float] = Field(None, description="Funding spread (alias)")
    funding_spread_pct: Optional[float] = Field(None, description="Funding spread percentage")
    gross_apr: Optional[Decimal] = Field(None, description="Annualized gross return")
    estimated_net_apr: Optional[float] = Field(None, description="Estimated net APR")
    total_entry_cost: Decimal = Decimal("0")
    total_exit_cost: Decimal = Decimal("0")
    net_apr: Optional[Decimal] = Field(None, description="Net APR after costs")
    basis: Decimal = Field(Decimal("0"), description="Price difference between legs")
    basis_risk: Decimal = Field(Decimal("0"), description="Historical basis volatility")

    # Scoring - support both field names
    scores: Optional[UOSScores] = Field(None, description="UOS scores")
    uos_score_direct: Optional[int] = Field(None, description="Direct UOS score (for incoming data)")
    uos_breakdown: Optional[UOSScores] = Field(None, description="UOS breakdown (alias)")
    confidence: OpportunityConfidence = OpportunityConfidence.MEDIUM

    # Recommendations
    recommended_size_usd: Decimal = Decimal("0")
    minimum_hold_periods: int = 2
    maximum_hold_periods: int = 24

    # Metadata
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    validated_at: Optional[datetime] = None
    expires_at: datetime = Field(default_factory=datetime.utcnow)
    data_source: str = Field("exchange_api", description="Primary data source used")

    def model_post_init(self, __context) -> None:
        """Normalize field names."""
        # Normalize legs
        if self.primary_leg is None and self.long_leg is not None:
            object.__setattr__(self, "primary_leg", self.long_leg)
        if self.hedge_leg is None and self.short_leg is not None:
            object.__setattr__(self, "hedge_leg", self.short_leg)

        # Normalize scores
        if self.scores is None and self.uos_breakdown is not None:
            object.__setattr__(self, "scores", self.uos_breakdown)

    @property
    def uos_score(self) -> int:
        """Get the total UOS score."""
        if self.uos_score_direct is not None:
            return self.uos_score_direct
        if self.scores is not None:
            return self.scores.total
        if self.uos_breakdown is not None:
            return self.uos_breakdown.total
        return 0

    @computed_field
    @property
    def is_expired(self) -> bool:
        """Check if opportunity has expired."""
        now = datetime.utcnow()
        # Handle both timezone-aware and naive datetimes
        if self.expires_at.tzinfo is not None:
            now = now.replace(tzinfo=self.expires_at.tzinfo)
        return now > self.expires_at

    @computed_field
    @property
    def is_actionable(self) -> bool:
        """Check if opportunity can be acted upon."""
        return (
            self.status in ["validated", "scored", OpportunityStatus.VALIDATED.value, OpportunityStatus.SCORED.value]
            and not self.is_expired
            and self.uos_score >= 40
        )

    @property
    def spread(self) -> Decimal:
        """Calculate the funding rate spread."""
        if self.funding_spread is not None:
            return Decimal(str(self.funding_spread))
        if self.primary_leg and self.hedge_leg:
            return Decimal(str(self.primary_leg.funding_rate - self.hedge_leg.funding_rate))
        if self.long_leg and self.short_leg:
            return Decimal(str(self.long_leg.funding_rate - self.short_leg.funding_rate))
        return Decimal("0")

    def estimate_profit(
        self, size_usd: Decimal, hold_periods: int
    ) -> dict[str, Decimal]:
        """
        Estimate profit for a given size and hold time.

        Args:
            size_usd: Position size in USD
            hold_periods: Number of funding periods to hold

        Returns:
            Dictionary with profit breakdown
        """
        gross_funding = self.gross_funding_rate * size_usd * hold_periods / 100
        entry_cost = self.total_entry_cost * size_usd / 100
        exit_cost = self.total_exit_cost * size_usd / 100
        net_profit = gross_funding - entry_cost - exit_cost

        return {
            "gross_funding": gross_funding,
            "entry_cost": entry_cost,
            "exit_cost": exit_cost,
            "net_profit": net_profit,
            "return_pct": net_profit / size_usd * 100 if size_usd > 0 else Decimal("0"),
        }

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate opportunity constraints.

        Returns:
            Tuple of (is_valid, list of violations)
        """
        violations = []

        # Check minimum spread
        if self.gross_funding_rate < Decimal("0.01"):
            violations.append(f"Gross funding rate too low: {self.gross_funding_rate}%")

        # Check net APR
        if self.net_apr < Decimal("10"):
            violations.append(f"Net APR below threshold: {self.net_apr}%")

        # Check liquidity
        min_liquidity = self.recommended_size_usd * 3
        if self.primary_leg.available_liquidity_usd < min_liquidity:
            violations.append("Insufficient primary leg liquidity")
        if self.hedge_leg.available_liquidity_usd < min_liquidity:
            violations.append("Insufficient hedge leg liquidity")

        # Check slippage
        if self.primary_leg.estimated_slippage_pct > Decimal("0.1"):
            violations.append(
                f"Primary leg slippage too high: {self.primary_leg.estimated_slippage_pct}%"
            )
        if self.hedge_leg.estimated_slippage_pct > Decimal("0.1"):
            violations.append(
                f"Hedge leg slippage too high: {self.hedge_leg.estimated_slippage_pct}%"
            )

        return len(violations) == 0, violations


class OpportunitySummary(BaseModel):
    """Summary of an opportunity for display."""

    id: UUID
    symbol: str
    opportunity_type: OpportunityType
    long_exchange: str
    short_exchange: str
    spread_pct: Decimal
    net_apr: Decimal
    uos_score: int
    confidence: OpportunityConfidence
    status: OpportunityStatus
    detected_at: datetime

    @classmethod
    def from_opportunity(cls, opp: Opportunity) -> "OpportunitySummary":
        """Create summary from full opportunity."""
        long_leg = opp.primary_leg if not opp.primary_leg.is_short else opp.hedge_leg
        short_leg = opp.hedge_leg if not opp.primary_leg.is_short else opp.primary_leg

        return cls(
            id=opp.id,
            symbol=opp.symbol,
            opportunity_type=opp.opportunity_type,
            long_exchange=long_leg.exchange,
            short_exchange=short_leg.exchange,
            spread_pct=opp.gross_funding_rate,
            net_apr=opp.net_apr,
            uos_score=opp.uos_score,
            confidence=opp.confidence,
            status=opp.status,
            detected_at=opp.detected_at,
        )
