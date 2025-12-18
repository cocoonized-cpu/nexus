"""
Exchange configuration and status models for NEXUS.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import Field

from shared.models.base import BaseModel


class MarketType(str, Enum):
    """Type of market."""

    SPOT = "spot"
    PERPETUAL = "perpetual"
    FUTURES = "futures"


class ExchangeType(str, Enum):
    """Type of exchange."""

    CEX = "cex"
    DEX = "dex"


class ExchangeTier(str, Enum):
    """Exchange tier classification."""

    TIER_1 = "tier_1"  # Major CEXs: Binance, Bybit, OKX
    TIER_2 = "tier_2"  # Secondary CEXs: Gate, KuCoin, Bitget
    TIER_3 = "tier_3"  # DEXs: Hyperliquid, dYdX


class ExchangeStatus(str, Enum):
    """Current operational status of an exchange connection."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class ExchangeFees(BaseModel):
    """Fee structure for an exchange."""

    spot_maker: Decimal = Field(Decimal("0.001"), description="Spot maker fee")
    spot_taker: Decimal = Field(Decimal("0.001"), description="Spot taker fee")
    perp_maker: Decimal = Field(Decimal("0.0002"), description="Perpetual maker fee")
    perp_taker: Decimal = Field(Decimal("0.0005"), description="Perpetual taker fee")
    withdrawal_fees: dict[str, Decimal] = Field(
        default_factory=dict, description="Withdrawal fee per asset"
    )


class ExchangeRateLimits(BaseModel):
    """Rate limiting configuration for an exchange."""

    requests_per_minute: int = 1200
    orders_per_second: int = 10
    websocket_connections: int = 5


class ExchangeConfig(BaseModel):
    """
    Configuration for an exchange.

    This is stored in the database and used to configure exchange connections.
    """

    slug: str = Field(..., description="Unique exchange identifier")
    display_name: str = Field(..., description="Human-readable exchange name")
    exchange_type: ExchangeType = Field(
        ExchangeType.CEX, description="Type of exchange"
    )
    tier: ExchangeTier = Field(ExchangeTier.TIER_2, description="Exchange tier")
    enabled: bool = Field(True, description="Whether exchange is enabled")

    # API Configuration
    api_type: str = Field("ccxt", description="API implementation type")
    base_url: Optional[str] = Field(None, description="Base API URL (if custom)")
    websocket_url: Optional[str] = Field(None, description="WebSocket URL")

    # Credentials (encrypted in database)
    api_key: Optional[str] = Field(None, description="API key (encrypted)")
    api_secret: Optional[str] = Field(None, description="API secret (encrypted)")
    passphrase: Optional[str] = Field(None, description="Passphrase if required")

    # Fees
    fees: ExchangeFees = Field(default_factory=ExchangeFees)

    # Rate Limits
    rate_limits: ExchangeRateLimits = Field(default_factory=ExchangeRateLimits)

    # Funding Configuration
    funding_interval_hours: int = Field(8, description="Hours between funding")
    funding_times_utc: list[str] = Field(
        default_factory=lambda: ["00:00", "08:00", "16:00"],
        description="Funding settlement times UTC",
    )

    # Features
    supports_portfolio_margin: bool = False
    supports_spot: bool = True
    supports_perpetual: bool = True
    requires_on_chain: bool = False
    chain: Optional[str] = Field(None, description="Blockchain if DEX")

    # URLs
    trading_url_template: Optional[str] = Field(
        None, description="URL template for trading page"
    )

    def get_trading_url(self, symbol: str) -> Optional[str]:
        """Get the trading URL for a specific symbol."""
        if self.trading_url_template:
            return self.trading_url_template.format(symbol=symbol)
        return None

    @property
    def is_dex(self) -> bool:
        """Check if this is a DEX."""
        return self.exchange_type == ExchangeType.DEX


class ExchangeHealth(BaseModel):
    """Current health status of an exchange connection."""

    exchange: str
    status: ExchangeStatus = ExchangeStatus.HEALTHY
    last_successful_request: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    consecutive_errors: int = 0
    latency_ms: Optional[int] = None
    rate_limit_remaining: Optional[int] = None

    def record_success(self, latency_ms: int) -> None:
        """Record a successful API call."""
        self.status = ExchangeStatus.HEALTHY
        self.last_successful_request = datetime.utcnow()
        self.consecutive_errors = 0
        self.latency_ms = latency_ms

    def record_error(self, error: str) -> None:
        """Record a failed API call."""
        self.last_error = error
        self.last_error_time = datetime.utcnow()
        self.consecutive_errors += 1

        if self.consecutive_errors >= 5:
            self.status = ExchangeStatus.OFFLINE
        elif self.consecutive_errors >= 2:
            self.status = ExchangeStatus.DEGRADED


class PriceData(BaseModel):
    """Price information for a market."""

    exchange: str
    symbol: str
    market_type: MarketType = MarketType.PERPETUAL
    # Support both naming conventions
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    # Alternative field names from providers
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    volume_24h: Optional[float] = None
    open_interest: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context) -> None:
        """Normalize field names."""
        if self.bid_price is None and self.bid is not None:
            object.__setattr__(self, "bid_price", Decimal(str(self.bid)))
        if self.ask_price is None and self.ask is not None:
            object.__setattr__(self, "ask_price", Decimal(str(self.ask)))
        if self.last_price is None and self.mark_price is not None:
            object.__setattr__(self, "last_price", Decimal(str(self.mark_price)))

    @property
    def mid_price(self) -> Decimal:
        """Calculate mid price."""
        bid = self.bid_price or (Decimal(str(self.bid)) if self.bid else Decimal("0"))
        ask = self.ask_price or (Decimal(str(self.ask)) if self.ask else Decimal("0"))
        if bid == 0 or ask == 0:
            return Decimal("0")
        return (bid + ask) / 2

    @property
    def spread(self) -> Decimal:
        """Calculate spread as percentage."""
        mid = self.mid_price
        if mid == 0:
            return Decimal("0")
        bid = self.bid_price or (Decimal(str(self.bid)) if self.bid else Decimal("0"))
        ask = self.ask_price or (Decimal(str(self.ask)) if self.ask else Decimal("0"))
        return (ask - bid) / mid * 100


class LiquidityData(BaseModel):
    """Order book depth and trading activity."""

    exchange: str
    symbol: str
    market_type: MarketType = MarketType.PERPETUAL
    bid_depth: list[tuple[Decimal, Decimal]] = Field(
        default_factory=list, description="List of (price, quantity) tuples"
    )
    ask_depth: list[tuple[Decimal, Decimal]] = Field(default_factory=list)
    cumulative_bid_depth_usd: Decimal = Decimal("0")
    cumulative_ask_depth_usd: Decimal = Decimal("0")
    # Alternative field names from providers
    bid_liquidity_usd: Optional[float] = None
    ask_liquidity_usd: Optional[float] = None
    spread_pct: Optional[float] = None
    depth_imbalance: Optional[float] = None
    open_interest: Optional[Decimal] = None
    open_interest_usd: Optional[Decimal] = None
    volume_24h: Decimal = Decimal("0")
    volume_24h_usd: Decimal = Decimal("0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context) -> None:
        """Normalize field names."""
        if self.cumulative_bid_depth_usd == 0 and self.bid_liquidity_usd is not None:
            object.__setattr__(
                self, "cumulative_bid_depth_usd", Decimal(str(self.bid_liquidity_usd))
            )
        if self.cumulative_ask_depth_usd == 0 and self.ask_liquidity_usd is not None:
            object.__setattr__(
                self, "cumulative_ask_depth_usd", Decimal(str(self.ask_liquidity_usd))
            )

    def get_depth_at_size(self, size_usd: Decimal, side: str = "buy") -> Decimal:
        """
        Calculate expected slippage for a given order size.

        Args:
            size_usd: Order size in USD
            side: 'buy' or 'sell'

        Returns:
            Expected slippage as percentage
        """
        depth = self.ask_depth if side == "buy" else self.bid_depth
        if not depth:
            return Decimal("999")  # No liquidity

        remaining = size_usd
        weighted_price = Decimal("0")
        total_filled = Decimal("0")

        for price, qty in depth:
            level_value = price * qty
            if remaining <= level_value:
                weighted_price += price * remaining
                total_filled += remaining
                break
            weighted_price += price * level_value
            total_filled += level_value
            remaining -= level_value

        if total_filled == 0:
            return Decimal("999")

        avg_price = weighted_price / total_filled
        best_price = depth[0][0]
        slippage = abs(avg_price - best_price) / best_price * 100
        return slippage
