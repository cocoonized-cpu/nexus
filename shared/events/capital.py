"""
Capital events for NEXUS.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from shared.events.base import Event, EventCategory, EventType


class CapitalAllocatedEvent(Event):
    """Event published when capital is allocated for an opportunity."""

    event_type: EventType = EventType.CAPITAL_ALLOCATED
    category: EventCategory = EventCategory.CAPITAL

    allocation_id: UUID
    opportunity_id: UUID
    amount_usd: Decimal = Decimal("0")
    venue: str = ""
    available_after: Decimal = Decimal("0")
    source: str = "capital-allocator"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "allocation_id": str(self.allocation_id),
            "opportunity_id": str(self.opportunity_id),
            "amount_usd": str(self.amount_usd),
            "venue": self.venue,
            "available_after": str(self.available_after),
        }


class CapitalDeployedEvent(Event):
    """Event published when capital is deployed to a position."""

    event_type: EventType = EventType.CAPITAL_DEPLOYED
    category: EventCategory = EventCategory.CAPITAL

    allocation_id: UUID
    position_id: UUID
    amount_usd: Decimal = Decimal("0")
    venue: str = ""
    total_active: Decimal = Decimal("0")
    utilization_pct: Decimal = Decimal("0")
    source: str = "capital-allocator"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "allocation_id": str(self.allocation_id),
            "position_id": str(self.position_id),
            "amount_usd": str(self.amount_usd),
            "venue": self.venue,
            "total_active": str(self.total_active),
            "utilization_pct": str(self.utilization_pct),
        }


class CapitalReleasedEvent(Event):
    """Event published when capital is released from a position."""

    event_type: EventType = EventType.CAPITAL_RELEASED
    category: EventCategory = EventCategory.CAPITAL

    allocation_id: UUID
    position_id: Optional[UUID] = None
    amount_usd: Decimal = Decimal("0")
    venue: str = ""
    realized_pnl: Decimal = Decimal("0")
    available_after: Decimal = Decimal("0")
    source: str = "capital-allocator"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "allocation_id": str(self.allocation_id),
            "position_id": str(self.position_id) if self.position_id else None,
            "amount_usd": str(self.amount_usd),
            "venue": self.venue,
            "realized_pnl": str(self.realized_pnl),
            "available_after": str(self.available_after),
        }


class CapitalTransferEvent(Event):
    """Event published when capital is transferred between venues."""

    event_type: EventType = EventType.CAPITAL_TRANSFER
    category: EventCategory = EventCategory.CAPITAL

    transfer_id: UUID
    from_venue: str = ""
    to_venue: str = ""
    asset: str = "USDT"
    amount: Decimal = Decimal("0")
    status: str = "initiated"  # initiated, pending, completed, failed
    tx_hash: Optional[str] = None
    fee: Decimal = Decimal("0")
    source: str = "capital-allocator"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "transfer_id": str(self.transfer_id),
            "from_venue": self.from_venue,
            "to_venue": self.to_venue,
            "asset": self.asset,
            "amount": str(self.amount),
            "status": self.status,
            "tx_hash": self.tx_hash,
            "fee": str(self.fee),
        }
