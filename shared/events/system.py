"""
System events for NEXUS.
"""

from decimal import Decimal
from typing import Optional

from pydantic import Field

from shared.events.base import Event, EventCategory, EventType
from shared.models.risk import RiskMode


class SystemStartedEvent(Event):
    """Event published when system starts up."""

    event_type: EventType = EventType.SYSTEM_STARTED
    category: EventCategory = EventCategory.SYSTEM

    version: str = ""
    mode: RiskMode = RiskMode.STANDARD
    services_online: list[str] = Field(default_factory=list)
    exchanges_connected: list[str] = Field(default_factory=list)
    source: str = "gateway"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "version": self.version,
            "mode": self.mode.value,
            "services_online": self.services_online,
            "exchanges_connected": self.exchanges_connected,
        }


class SystemModeChangedEvent(Event):
    """Event published when system operational mode changes."""

    event_type: EventType = EventType.SYSTEM_MODE_CHANGED
    category: EventCategory = EventCategory.SYSTEM

    previous_mode: RiskMode = RiskMode.STANDARD
    current_mode: RiskMode = RiskMode.STANDARD
    reason: str = ""
    changed_by: str = ""
    source: str = "gateway"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "previous_mode": self.previous_mode.value,
            "current_mode": self.current_mode.value,
            "reason": self.reason,
            "changed_by": self.changed_by,
        }


class SystemErrorEvent(Event):
    """Event published when a system error occurs."""

    event_type: EventType = EventType.SYSTEM_ERROR
    category: EventCategory = EventCategory.SYSTEM

    error_code: str = ""
    error_message: str = ""
    severity: str = "error"  # warning, error, critical
    service: str = ""
    stack_trace: Optional[str] = None
    recoverable: bool = True
    source: str = "gateway"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "severity": self.severity,
            "service": self.service,
            "stack_trace": self.stack_trace,
            "recoverable": self.recoverable,
        }


class VenueDegradedEvent(Event):
    """Event published when an exchange connection degrades."""

    event_type: EventType = EventType.VENUE_DEGRADED
    category: EventCategory = EventCategory.SYSTEM

    exchange: str = ""
    reason: str = ""
    consecutive_errors: int = 0
    last_error: Optional[str] = None
    positions_affected: int = 0
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "reason": self.reason,
            "consecutive_errors": self.consecutive_errors,
            "last_error": self.last_error,
            "positions_affected": self.positions_affected,
        }


class VenueRestoredEvent(Event):
    """Event published when an exchange connection is restored."""

    event_type: EventType = EventType.VENUE_RESTORED
    category: EventCategory = EventCategory.SYSTEM

    exchange: str = ""
    downtime_seconds: int = 0
    source: str = "data-collector"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "exchange": self.exchange,
            "downtime_seconds": self.downtime_seconds,
        }
