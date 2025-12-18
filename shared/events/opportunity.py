"""
Opportunity events for NEXUS.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from shared.events.base import Event, EventCategory, EventType
from shared.models.opportunity import OpportunityType


class OpportunityDetectedEvent(Event):
    """Event published when a new opportunity is detected."""

    event_type: EventType = EventType.OPPORTUNITY_DETECTED
    category: EventCategory = EventCategory.OPPORTUNITY

    opportunity_id: str  # Can be UUID string
    opportunity_type: str = "cross_exchange_perp"
    symbol: str = ""
    base_asset: str = ""
    long_exchange: str = ""
    short_exchange: str = ""
    spread_pct: float = 0
    gross_apr: float = 0
    confidence: str = "medium"
    source: str = "opportunity-detector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "opportunity_id": str(self.opportunity_id),
            "opportunity_type": self.opportunity_type,
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "long_exchange": self.long_exchange,
            "short_exchange": self.short_exchange,
            "spread_pct": str(self.spread_pct),
            "gross_apr": str(self.gross_apr),
            "confidence": self.confidence,
        }


class OpportunityScoredEvent(Event):
    """Event published when an opportunity has been scored."""

    event_type: EventType = EventType.OPPORTUNITY_SCORED
    category: EventCategory = EventCategory.OPPORTUNITY

    opportunity_id: str
    uos_score: int = 0
    return_score: int = 0
    risk_score: int = 0
    execution_score: int = 0
    timing_score: int = 0
    recommended_size_usd: Decimal = Decimal("0")
    source: str = "opportunity-detector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "opportunity_id": str(self.opportunity_id),
            "uos_score": self.uos_score,
            "return_score": self.return_score,
            "risk_score": self.risk_score,
            "execution_score": self.execution_score,
            "timing_score": self.timing_score,
            "recommended_size_usd": str(self.recommended_size_usd),
        }


class OpportunityExpiredEvent(Event):
    """Event published when an opportunity expires or becomes invalid."""

    event_type: EventType = EventType.OPPORTUNITY_EXPIRED
    category: EventCategory = EventCategory.OPPORTUNITY

    opportunity_id: str
    reason: str = "expired"
    symbol: str = ""
    source: str = "opportunity-detector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "opportunity_id": str(self.opportunity_id),
            "reason": self.reason,
            "symbol": self.symbol,
        }


class OpportunityUpdatedEvent(Event):
    """Event published when an opportunity is updated."""

    event_type: EventType = EventType.OPPORTUNITY_SCORED
    category: EventCategory = EventCategory.OPPORTUNITY

    opportunity_id: str
    updates: dict = Field(default_factory=dict)
    source: str = "opportunity-detector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "opportunity_id": str(self.opportunity_id),
            "updates": self.updates,
        }


class OpportunityAllocatedEvent(Event):
    """Event published when capital is allocated to an opportunity."""

    event_type: EventType = EventType.OPPORTUNITY_ALLOCATED
    category: EventCategory = EventCategory.OPPORTUNITY

    opportunity_id: str
    allocation_id: str
    allocated_amount_usd: Decimal = Decimal("0")
    venue: str = ""
    source: str = "capital-allocator"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "opportunity_id": str(self.opportunity_id),
            "allocation_id": str(self.allocation_id),
            "allocated_amount_usd": str(self.allocated_amount_usd),
            "venue": self.venue,
        }
