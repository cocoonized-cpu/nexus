"""
Base event classes and types for NEXUS event system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import Field

from shared.models.base import BaseModel


class EventCategory(str, Enum):
    """Category of events."""

    MARKET_DATA = "market_data"
    OPPORTUNITY = "opportunity"
    POSITION = "position"
    RISK = "risk"
    CAPITAL = "capital"
    SYSTEM = "system"


class EventType(str, Enum):
    """All event types in the system."""

    # Market Data Events
    FUNDING_RATE_UPDATE = "funding_rate.update"
    FUNDING_RATE_UPDATED = "funding_rate.updated"
    UNIFIED_FUNDING_SNAPSHOT = "funding_rate.unified_snapshot"
    PRICE_UPDATE = "price.update"
    LIQUIDITY_UPDATE = "liquidity.update"
    DATA_STALE = "data.stale"
    EXCHANGE_HEALTH_CHANGED = "exchange.health_changed"

    # Opportunity Events
    OPPORTUNITY_DETECTED = "opportunity.detected"
    OPPORTUNITY_SCORED = "opportunity.scored"
    OPPORTUNITY_EXPIRED = "opportunity.expired"
    OPPORTUNITY_ALLOCATED = "opportunity.allocated"

    # Position Events
    POSITION_OPENING = "position.opening"
    POSITION_OPENED = "position.opened"
    POSITION_OPEN_FAILED = "position.open_failed"
    POSITION_UPDATED = "position.updated"
    POSITION_HEALTH_CHANGED = "position.health_changed"
    POSITION_EXIT_TRIGGERED = "position.exit_triggered"
    POSITION_CLOSING = "position.closing"
    POSITION_CLOSED = "position.closed"
    POSITION_EMERGENCY_CLOSE = "position.emergency_close"
    FUNDING_COLLECTED = "funding.collected"

    # Risk Events
    RISK_STATE_UPDATED = "risk.state_updated"
    RISK_LIMIT_WARNING = "risk.limit_warning"
    RISK_LIMIT_BREACH = "risk.limit_breach"
    RISK_MODE_CHANGED = "risk.mode_changed"
    RISK_ALERT = "risk.alert"
    CIRCUIT_BREAKER_TRIGGERED = "risk.circuit_breaker_triggered"
    CIRCUIT_BREAKER_RESET = "risk.circuit_breaker_reset"

    # Capital Events
    CAPITAL_ALLOCATED = "capital.allocated"
    CAPITAL_DEPLOYED = "capital.deployed"
    CAPITAL_RELEASED = "capital.released"
    CAPITAL_TRANSFER = "capital.transfer"

    # System Events
    SYSTEM_STARTED = "system.started"
    SYSTEM_MODE_CHANGED = "system.mode_changed"
    SYSTEM_ERROR = "system.error"
    VENUE_DEGRADED = "venue.degraded"
    VENUE_RESTORED = "venue.restored"


class Event(BaseModel):
    """
    Base event class for all NEXUS events.

    All events in the system inherit from this base class.
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    category: EventCategory
    source: str = Field(..., description="Service that generated the event")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[UUID] = Field(
        None, description="ID to correlate related events"
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_channel(self) -> str:
        """Get the Redis channel for this event."""
        return f"nexus:{self.category.value}:{self.event_type.value}"

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls.model_validate(data)


class EventHandler:
    """Base class for event handlers."""

    async def handle(self, event: Event) -> None:
        """Handle an event. Override in subclasses."""
        raise NotImplementedError

    def can_handle(self, event_type: EventType) -> bool:
        """Check if this handler can handle the given event type."""
        raise NotImplementedError


class EventBus:
    """
    Simple event bus for publish/subscribe pattern.

    In production, this delegates to Redis Pub/Sub.
    """

    def __init__(self):
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._middleware: list[callable] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)

    def add_middleware(self, middleware: callable) -> None:
        """Add middleware to process events before handlers."""
        self._middleware.append(middleware)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event: Event to publish
        """
        # Run middleware
        for middleware in self._middleware:
            event = await middleware(event)
            if event is None:
                return  # Middleware can filter events

        # Call handlers
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler.handle(event)
            except Exception as e:
                # Log error but continue with other handlers
                print(f"Error in handler {handler}: {e}")

    def get_handlers(self, event_type: EventType) -> list[EventHandler]:
        """Get all handlers for an event type."""
        return self._handlers.get(event_type, [])
