"""
Risk events for NEXUS.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from shared.events.base import Event, EventCategory, EventType
from shared.models.risk import RiskAlertSeverity, RiskAlertType, RiskMode


class RiskStateUpdatedEvent(Event):
    """Event published when portfolio risk state is updated."""

    event_type: EventType = EventType.RISK_STATE_UPDATED
    category: EventCategory = EventCategory.RISK

    total_exposure_usd: Decimal = Decimal("0")
    gross_exposure_pct: Decimal = Decimal("0")
    net_exposure_pct: Decimal = Decimal("0")
    current_drawdown_pct: Decimal = Decimal("0")
    var_used_pct: Decimal = Decimal("0")
    positions_healthy: int = 0
    positions_at_risk: int = 0
    source: str = "risk-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "total_exposure_usd": str(self.total_exposure_usd),
            "gross_exposure_pct": str(self.gross_exposure_pct),
            "net_exposure_pct": str(self.net_exposure_pct),
            "current_drawdown_pct": str(self.current_drawdown_pct),
            "var_used_pct": str(self.var_used_pct),
            "positions_healthy": self.positions_healthy,
            "positions_at_risk": self.positions_at_risk,
        }


class RiskLimitWarningEvent(Event):
    """Event published when approaching a risk limit."""

    event_type: EventType = EventType.RISK_LIMIT_WARNING
    category: EventCategory = EventCategory.RISK

    alert_type: RiskAlertType = RiskAlertType.CONCENTRATION
    severity: RiskAlertSeverity = RiskAlertSeverity.MEDIUM
    limit_name: str = ""
    current_value: Decimal = Decimal("0")
    limit_value: Decimal = Decimal("0")
    utilization_pct: Decimal = Decimal("0")
    position_id: Optional[UUID] = None
    exchange: Optional[str] = None
    asset: Optional[str] = None
    source: str = "risk-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "limit_name": self.limit_name,
            "current_value": str(self.current_value),
            "limit_value": str(self.limit_value),
            "utilization_pct": str(self.utilization_pct),
            "position_id": str(self.position_id) if self.position_id else None,
            "exchange": self.exchange,
            "asset": self.asset,
        }


class RiskLimitBreachEvent(Event):
    """Event published when a risk limit is breached."""

    event_type: EventType = EventType.RISK_LIMIT_BREACH
    category: EventCategory = EventCategory.RISK

    alert_type: RiskAlertType = RiskAlertType.CONCENTRATION
    severity: RiskAlertSeverity = RiskAlertSeverity.HIGH
    limit_name: str = ""
    current_value: Decimal = Decimal("0")
    limit_value: Decimal = Decimal("0")
    breach_amount: Decimal = Decimal("0")
    action_required: str = ""
    position_id: Optional[UUID] = None
    exchange: Optional[str] = None
    asset: Optional[str] = None
    source: str = "risk-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "limit_name": self.limit_name,
            "current_value": str(self.current_value),
            "limit_value": str(self.limit_value),
            "breach_amount": str(self.breach_amount),
            "action_required": self.action_required,
            "position_id": str(self.position_id) if self.position_id else None,
            "exchange": self.exchange,
            "asset": self.asset,
        }


class RiskModeChangedEvent(Event):
    """Event published when risk mode changes."""

    event_type: EventType = EventType.RISK_MODE_CHANGED
    category: EventCategory = EventCategory.RISK

    previous_mode: RiskMode = RiskMode.STANDARD
    current_mode: RiskMode = RiskMode.STANDARD
    reason: str = ""
    triggered_by: str = ""  # "manual", "automatic", "emergency"
    source: str = "risk-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "previous_mode": self.previous_mode.value,
            "current_mode": self.current_mode.value,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
        }


class RiskAlertEvent(Event):
    """Generic risk alert event."""

    event_type: EventType = EventType.RISK_ALERT
    category: EventCategory = EventCategory.RISK

    alert_type: RiskAlertType = RiskAlertType.CONCENTRATION
    severity: RiskAlertSeverity = RiskAlertSeverity.MEDIUM
    message: str = ""
    details: Optional[dict] = None
    source: str = "risk-manager"

    def __init__(self, **data):
        super().__init__(**data)
        self.payload = {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
        }


class CircuitBreakerEvent(Event):
    """Event published when circuit breaker is triggered or reset."""

    event_type: EventType = EventType.CIRCUIT_BREAKER_TRIGGERED
    category: EventCategory = EventCategory.RISK

    triggered: bool = True
    reason: str = ""
    triggered_by: str = ""  # "drawdown", "exposure", "manual", etc.
    affected_positions: int = 0
    source: str = "risk-manager"

    def __init__(self, **data):
        # Set event type based on triggered flag
        if not data.get("triggered", True):
            data["event_type"] = EventType.CIRCUIT_BREAKER_RESET
        super().__init__(**data)
        self.payload = {
            "triggered": self.triggered,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "affected_positions": self.affected_positions,
        }
