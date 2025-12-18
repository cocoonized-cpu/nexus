"""
Funding rate data models for NEXUS.

Supports dual-source architecture:
- PRIMARY: Direct exchange APIs
- SECONDARY: ArbitrageScanner API for validation and gap-filling
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import Field, computed_field

from shared.models.base import BaseModel


class FundingRateSource(str, Enum):
    """Source of funding rate data."""

    EXCHANGE_API = "exchange_api"
    ARBITRAGESCANNER = "arbitragescanner"


class FundingRateData(BaseModel):
    """
    Funding rate information for a single asset on a single exchange.

    This is the normalized representation used internally, regardless of source.
    """

    exchange: str = Field(..., description="Exchange slug (e.g., 'binance_futures')")
    symbol: str = Field(..., description="Trading pair (e.g., 'BTCUSDT')")
    ticker: Optional[str] = Field(None, description="Base asset (e.g., 'BTC')")
    # Support both 'rate' and 'funding_rate' field names for backward compatibility
    rate: Optional[Decimal] = Field(
        None, description="Funding rate as percentage (e.g., 0.01 = 0.01%)"
    )
    funding_rate: Optional[float] = Field(
        None, description="Funding rate (alias for providers using this name)"
    )
    next_funding_time: Optional[datetime] = Field(
        None, description="Next funding settlement time"
    )
    source: FundingRateSource = Field(
        FundingRateSource.EXCHANGE_API, description="Source of this rate data"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When data was fetched"
    )
    predicted_rate: Optional[Decimal] = Field(
        None, description="Predicted next funding rate (if available)"
    )
    funding_interval_hours: int = Field(
        8, description="Hours between funding settlements"
    )
    is_validated: bool = Field(
        False, description="Whether rate was validated against secondary source"
    )
    is_fallback: bool = Field(
        False, description="Whether this is fallback data from secondary source"
    )
    discrepancy: Optional[Decimal] = Field(
        None, description="Discrepancy with other source (if checked)"
    )

    def model_post_init(self, __context) -> None:
        """Post-init hook to normalize field names and derive ticker."""
        # Derive ticker from symbol if not provided
        if self.ticker is None and self.symbol:
            # Extract base asset from symbol (e.g., 'BTC/USDT:USDT' -> 'BTC')
            parts = self.symbol.replace(":USDT", "").replace(":USD", "").split("/")
            self.ticker = parts[0] if parts else self.symbol

        # Normalize funding_rate to rate
        if self.rate is None and self.funding_rate is not None:
            object.__setattr__(self, "rate", Decimal(str(self.funding_rate)))
        elif self.rate is None:
            object.__setattr__(self, "rate", Decimal("0"))

    @property
    def effective_rate(self) -> Decimal:
        """Get the effective funding rate, handling both field names."""
        if self.rate is not None:
            return self.rate
        if self.funding_rate is not None:
            return Decimal(str(self.funding_rate))
        return Decimal("0")

    @computed_field
    @property
    def rate_annualized(self) -> Decimal:
        """Annualized funding rate based on funding interval."""
        periods_per_year = Decimal(24 / self.funding_interval_hours * 365)
        return self.effective_rate * periods_per_year

    @computed_field
    @property
    def is_positive(self) -> bool:
        """Whether funding rate is positive (longs pay shorts)."""
        return self.effective_rate > 0

    @computed_field
    @property
    def time_to_next_funding_seconds(self) -> int:
        """Seconds until next funding settlement."""
        if self.next_funding_time is None:
            return 0
        delta = self.next_funding_time - datetime.utcnow()
        return max(0, int(delta.total_seconds()))


class FundingRateDiscrepancy(BaseModel):
    """Record of a discrepancy between data sources."""

    exchange: str
    symbol: str
    exchange_api_rate: Decimal
    arbitragescanner_rate: Decimal
    discrepancy: Decimal
    discrepancy_pct: Decimal
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolution_note: Optional[str] = None


class ExchangeFundingRates(BaseModel):
    """All funding rates from a single exchange."""

    exchange: str
    rates: dict[str, FundingRateData] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    source: FundingRateSource
    is_healthy: bool = True
    error_message: Optional[str] = None


class UnifiedFundingSnapshot(BaseModel):
    """
    Complete snapshot of all funding rates across all sources.

    This is the result of the dual-source aggregation process.
    Exchange API data is authoritative; ArbitrageScanner validates and fills gaps.
    """

    rates: dict[str, dict[str, FundingRateData]] = Field(
        default_factory=dict,
        description="Nested dict: symbol -> exchange -> FundingRateData",
    )
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    discrepancies: list[FundingRateDiscrepancy] = Field(default_factory=list)
    exchanges_healthy: dict[str, bool] = Field(default_factory=dict)
    total_symbols: int = 0
    total_rates: int = 0
    exchange_api_rates: int = 0
    arbitragescanner_rates: int = 0
    validated_rates: int = 0

    def get_rate(self, symbol: str, exchange: str) -> Optional[FundingRateData]:
        """Get funding rate for a specific symbol on a specific exchange."""
        return self.rates.get(symbol, {}).get(exchange)

    def get_symbol_rates(self, symbol: str) -> dict[str, FundingRateData]:
        """Get all funding rates for a symbol across exchanges."""
        return self.rates.get(symbol, {})

    def get_exchange_rates(self, exchange: str) -> dict[str, FundingRateData]:
        """Get all funding rates on a specific exchange."""
        result = {}
        for symbol, exchanges in self.rates.items():
            if exchange in exchanges:
                result[symbol] = exchanges[exchange]
        return result

    def get_best_opportunity(
        self, min_spread_pct: Decimal = Decimal("0.01")
    ) -> Optional[tuple[str, str, str, Decimal]]:
        """
        Find the best funding rate arbitrage opportunity.

        Returns tuple of (symbol, long_exchange, short_exchange, spread)
        or None if no opportunity above threshold.
        """
        best: Optional[tuple[str, str, str, Decimal]] = None
        best_spread = Decimal("0")

        for symbol, exchanges in self.rates.items():
            if len(exchanges) < 2:
                continue

            rates_list = list(exchanges.values())
            # Sort by rate: lowest first
            rates_list.sort(key=lambda x: x.rate)

            lowest = rates_list[0]
            highest = rates_list[-1]
            spread = highest.rate - lowest.rate

            if spread > best_spread and spread >= min_spread_pct:
                best_spread = spread
                best = (symbol, lowest.exchange, highest.exchange, spread)

        return best

    def get_opportunities_above_threshold(
        self, min_spread_pct: Decimal = Decimal("0.01")
    ) -> list[tuple[str, str, str, Decimal]]:
        """
        Get all opportunities above the spread threshold.

        Returns list of (symbol, long_exchange, short_exchange, spread) tuples.
        """
        opportunities = []

        for symbol, exchanges in self.rates.items():
            if len(exchanges) < 2:
                continue

            rates_list = list(exchanges.values())
            rates_list.sort(key=lambda x: x.rate)

            lowest = rates_list[0]
            highest = rates_list[-1]
            spread = highest.rate - lowest.rate

            if spread >= min_spread_pct:
                opportunities.append(
                    (symbol, lowest.exchange, highest.exchange, spread)
                )

        # Sort by spread descending
        opportunities.sort(key=lambda x: x[3], reverse=True)
        return opportunities


class ArbitrageScannerToken(BaseModel):
    """
    Token data from ArbitrageScanner API.

    Used for quick opportunity discovery via pre-calculated maxSpread.
    """

    slug: Optional[str] = Field(None, description="Token identifier (e.g., 'bitcoin')")
    symbol: str = Field(..., description="Trading pair or ticker (e.g., 'BTCUSDT' or 'BTC')")
    ticker: Optional[str] = Field(None, description="Base asset (e.g., 'BTC')")
    name: Optional[str] = Field(None, description="Token name (e.g., 'Bitcoin')")
    token_id: Optional[int] = None
    max_spread: Decimal = Field(
        Decimal("0"), description="Pre-calculated maximum spread opportunity"
    )
    rates: list[FundingRateData] = Field(default_factory=list)
    # Alternative structure for exchange data
    exchanges: Optional[dict[str, dict]] = Field(
        None, description="Exchange-specific funding rate data"
    )
    best_long_exchange: Optional[str] = Field(
        None, description="Exchange with lowest funding rate"
    )
    best_short_exchange: Optional[str] = Field(
        None, description="Exchange with highest funding rate"
    )
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context) -> None:
        """Derive fields from available data."""
        # Derive ticker from symbol if not provided
        if self.ticker is None and self.symbol:
            self.ticker = self.symbol

        # Derive slug from name or symbol if not provided
        if self.slug is None:
            if self.name:
                object.__setattr__(self, "slug", self.name.lower().replace(" ", "-"))
            else:
                object.__setattr__(self, "slug", self.symbol.lower())

    @computed_field
    @property
    def exchanges_count(self) -> int:
        """Number of exchanges with rate data for this token."""
        if self.rates:
            return len(self.rates)
        if self.exchanges:
            return len(self.exchanges)
        return 0

    @computed_field
    @property
    def has_arbitrage_opportunity(self) -> bool:
        """Whether there's a meaningful arbitrage opportunity."""
        return self.max_spread > Decimal("0.01")  # 0.01% threshold

    def get_highest_rate(self) -> Optional[FundingRateData]:
        """Get the exchange with highest funding rate."""
        if not self.rates:
            return None
        return max(self.rates, key=lambda x: x.effective_rate)

    def get_lowest_rate(self) -> Optional[FundingRateData]:
        """Get the exchange with lowest funding rate."""
        if not self.rates:
            return None
        return min(self.rates, key=lambda x: x.effective_rate)

    def get_rate_for_exchange(self, exchange: str) -> Optional[FundingRateData]:
        """Get rate for a specific exchange."""
        for rate in self.rates:
            if rate.exchange == exchange:
                return rate
        return None
