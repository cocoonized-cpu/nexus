"""
Market data events for NEXUS.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from shared.events.base import Event, EventCategory, EventType


class FundingRateUpdateEvent(Event):
    """Event published when funding rate data is updated."""

    event_type: EventType = EventType.FUNDING_RATE_UPDATE
    category: EventCategory = EventCategory.MARKET_DATA

    # Payload fields
    exchange: str = ""
    symbol: str = ""
    rate: Decimal = Decimal("0")
    previous_rate: Optional[Decimal] = None
    next_funding_time: Optional[datetime] = None
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "rate": str(self.rate),
            "previous_rate": str(self.previous_rate) if self.previous_rate else None,
            "next_funding_time": (
                self.next_funding_time.isoformat() if self.next_funding_time else None
            ),
        }


class PriceUpdateEvent(Event):
    """Event published when price data is updated."""

    event_type: EventType = EventType.PRICE_UPDATE
    category: EventCategory = EventCategory.MARKET_DATA

    exchange: str = ""
    symbol: str = ""
    market_type: str = "perpetual"
    bid_price: Decimal = Decimal("0")
    ask_price: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")
    mark_price: Optional[Decimal] = None
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "market_type": self.market_type,
            "bid_price": str(self.bid_price),
            "ask_price": str(self.ask_price),
            "last_price": str(self.last_price),
            "mark_price": str(self.mark_price) if self.mark_price else None,
        }


class LiquidityUpdateEvent(Event):
    """Event published when liquidity data is updated."""

    event_type: EventType = EventType.LIQUIDITY_UPDATE
    category: EventCategory = EventCategory.MARKET_DATA

    exchange: str = ""
    symbol: str = ""
    market_type: str = "perpetual"
    bid_depth_usd: Decimal = Decimal("0")
    ask_depth_usd: Decimal = Decimal("0")
    open_interest_usd: Optional[Decimal] = None
    volume_24h_usd: Decimal = Decimal("0")
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "market_type": self.market_type,
            "bid_depth_usd": str(self.bid_depth_usd),
            "ask_depth_usd": str(self.ask_depth_usd),
            "open_interest_usd": (
                str(self.open_interest_usd) if self.open_interest_usd else None
            ),
            "volume_24h_usd": str(self.volume_24h_usd),
        }


class DataStaleEvent(Event):
    """Event published when data exceeds maximum age threshold."""

    event_type: EventType = EventType.DATA_STALE
    category: EventCategory = EventCategory.MARKET_DATA

    data_type: str = "funding_rate"  # funding_rate, price, liquidity
    exchange: str = ""
    symbol: Optional[str] = None
    last_update: Optional[datetime] = None
    stale_seconds: int = 0
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "data_type": self.data_type,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "stale_seconds": self.stale_seconds,
        }


class ExchangeHealthChangedEvent(Event):
    """Event published when exchange health status changes."""

    event_type: EventType = EventType.EXCHANGE_HEALTH_CHANGED
    category: EventCategory = EventCategory.MARKET_DATA

    exchange: str = ""
    previous_status: str = "unknown"
    current_status: str = "unknown"
    reason: Optional[str] = None
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "previous_status": self.previous_status,
            "current_status": self.current_status,
            "reason": self.reason,
        }


class FundingRateUpdatedEvent(Event):
    """Event published when funding rates are updated (batch update)."""

    event_type: EventType = EventType.FUNDING_RATE_UPDATED
    category: EventCategory = EventCategory.MARKET_DATA

    exchange: str = ""
    symbols_updated: int = 0
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "symbols_updated": self.symbols_updated,
        }


class UnifiedFundingSnapshotEvent(Event):
    """Event published when unified funding rates are aggregated from all sources."""

    event_type: EventType = EventType.UNIFIED_FUNDING_SNAPSHOT
    category: EventCategory = EventCategory.MARKET_DATA

    symbol: str = ""
    exchanges_count: int = 0
    primary_source_count: int = 0
    secondary_source_count: int = 0
    source: str = "funding-aggregator"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "symbol": self.symbol,
            "exchanges_count": self.exchanges_count,
            "primary_source_count": self.primary_source_count,
            "secondary_source_count": self.secondary_source_count,
        }
