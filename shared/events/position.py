"""
Position events for NEXUS.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from shared.events.base import Event, EventCategory, EventType
from shared.models.position import PositionHealthStatus, PositionStatus


class PositionOpeningEvent(Event):
    """Event published when position opening is initiated."""

    event_type: EventType = EventType.POSITION_OPENING
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    opportunity_id: UUID
    symbol: str = ""
    size_usd: Decimal = Decimal("0")
    primary_exchange: str = ""
    hedge_exchange: str = ""
    source: str = "execution-engine"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "opportunity_id": str(self.opportunity_id),
            "symbol": self.symbol,
            "size_usd": str(self.size_usd),
            "primary_exchange": self.primary_exchange,
            "hedge_exchange": self.hedge_exchange,
        }


class PositionOpenedEvent(Event):
    """Event published when position is successfully opened."""

    event_type: EventType = EventType.POSITION_OPENED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    opportunity_id: UUID
    symbol: str = ""
    size_usd: Decimal = Decimal("0")
    primary_exchange: str = ""
    hedge_exchange: str = ""
    entry_cost_pct: Decimal = Decimal("0")
    source: str = "execution-engine"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "opportunity_id": str(self.opportunity_id),
            "symbol": self.symbol,
            "size_usd": str(self.size_usd),
            "primary_exchange": self.primary_exchange,
            "hedge_exchange": self.hedge_exchange,
            "entry_cost_pct": str(self.entry_cost_pct),
        }


class PositionOpenFailedEvent(Event):
    """Event published when position opening fails."""

    event_type: EventType = EventType.POSITION_OPEN_FAILED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    opportunity_id: UUID
    symbol: str = ""
    reason: str = ""
    partial_fills: bool = False
    source: str = "execution-engine"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "opportunity_id": str(self.opportunity_id),
            "symbol": self.symbol,
            "reason": self.reason,
            "partial_fills": self.partial_fills,
        }


class PositionUpdatedEvent(Event):
    """Event published when position metrics are updated."""

    event_type: EventType = EventType.POSITION_UPDATED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    unrealized_pnl: Decimal = Decimal("0")
    return_pct: Decimal = Decimal("0")
    delta_exposure_pct: Decimal = Decimal("0")
    margin_utilization: Decimal = Decimal("0")
    source: str = "position-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "unrealized_pnl": str(self.unrealized_pnl),
            "return_pct": str(self.return_pct),
            "delta_exposure_pct": str(self.delta_exposure_pct),
            "margin_utilization": str(self.margin_utilization),
        }


class PositionHealthChangedEvent(Event):
    """Event published when position health status changes."""

    event_type: EventType = EventType.POSITION_HEALTH_CHANGED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    previous_health: PositionHealthStatus = PositionHealthStatus.HEALTHY
    current_health: PositionHealthStatus = PositionHealthStatus.HEALTHY
    trigger_metric: str = ""
    trigger_value: Decimal = Decimal("0")
    source: str = "position-manager"

    def __init__(self, **data):
        super().__init__(**data)
        # Handle health as either enum or string
        prev_health = self.previous_health.value if hasattr(self.previous_health, 'value') else self.previous_health
        curr_health = self.current_health.value if hasattr(self.current_health, 'value') else self.current_health
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "previous_health": prev_health,
            "current_health": curr_health,
            "trigger_metric": self.trigger_metric,
            "trigger_value": str(self.trigger_value),
        }


class PositionExitTriggeredEvent(Event):
    """Event published when an exit trigger is detected."""

    event_type: EventType = EventType.POSITION_EXIT_TRIGGERED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    trigger_reason: str = ""
    urgency: str = "normal"  # normal, high, immediate
    source: str = "position-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "trigger_reason": self.trigger_reason,
            "urgency": self.urgency,
        }


class PositionClosingEvent(Event):
    """Event published when position closing is initiated."""

    event_type: EventType = EventType.POSITION_CLOSING
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    reason: str = ""
    source: str = "execution-engine"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "reason": self.reason,
        }


class PositionClosedEvent(Event):
    """Event published when position is successfully closed."""

    event_type: EventType = EventType.POSITION_CLOSED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    realized_pnl: Decimal = Decimal("0")
    return_pct: Decimal = Decimal("0")
    funding_collected: Decimal = Decimal("0")
    hold_duration_hours: Decimal = Decimal("0")
    exit_reason: str = ""
    source: str = "execution-engine"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "realized_pnl": str(self.realized_pnl),
            "return_pct": str(self.return_pct),
            "funding_collected": str(self.funding_collected),
            "hold_duration_hours": str(self.hold_duration_hours),
            "exit_reason": self.exit_reason,
        }


class PositionEmergencyCloseEvent(Event):
    """Event published when emergency close is initiated."""

    event_type: EventType = EventType.POSITION_EMERGENCY_CLOSE
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    trigger: str = ""
    source: str = "risk-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "trigger": self.trigger,
        }


class FundingCollectedEvent(Event):
    """Event published when funding payment is collected."""

    event_type: EventType = EventType.FUNDING_COLLECTED
    category: EventCategory = EventCategory.POSITION

    position_id: UUID
    symbol: str = ""
    exchange: str = ""
    funding_rate: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    total_funding_collected: Decimal = Decimal("0")
    funding_periods: int = 0
    source: str = "position-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "funding_rate": str(self.funding_rate),
            "payment_amount": str(self.payment_amount),
            "total_funding_collected": str(self.total_funding_collected),
            "funding_periods": self.funding_periods,
        }
