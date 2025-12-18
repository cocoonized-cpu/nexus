"""
NEXUS Event System

Event definitions and utilities for the event-driven architecture.
"""

from shared.events.base import Event, EventCategory, EventType
from shared.events.capital import (CapitalAllocatedEvent, CapitalDeployedEvent,
                                   CapitalReleasedEvent, CapitalTransferEvent)
from shared.events.market import (DataStaleEvent, FundingRateUpdateEvent,
                                  LiquidityUpdateEvent, PriceUpdateEvent)
from shared.events.opportunity import (OpportunityAllocatedEvent,
                                       OpportunityDetectedEvent,
                                       OpportunityExpiredEvent,
                                       OpportunityScoredEvent)
from shared.events.position import (FundingCollectedEvent, PositionClosedEvent,
                                    PositionClosingEvent,
                                    PositionEmergencyCloseEvent,
                                    PositionExitTriggeredEvent,
                                    PositionHealthChangedEvent,
                                    PositionOpenedEvent,
                                    PositionOpenFailedEvent,
                                    PositionOpeningEvent, PositionUpdatedEvent)
from shared.events.risk import (RiskLimitBreachEvent, RiskLimitWarningEvent,
                                RiskModeChangedEvent, RiskStateUpdatedEvent)
from shared.events.system import (SystemErrorEvent, SystemModeChangedEvent,
                                  SystemStartedEvent, VenueDegradedEvent,
                                  VenueRestoredEvent)

__all__ = [
    # Base
    "Event",
    "EventType",
    "EventCategory",
    # Market
    "FundingRateUpdateEvent",
    "PriceUpdateEvent",
    "LiquidityUpdateEvent",
    "DataStaleEvent",
    # Opportunity
    "OpportunityDetectedEvent",
    "OpportunityScoredEvent",
    "OpportunityExpiredEvent",
    "OpportunityAllocatedEvent",
    # Position
    "PositionOpeningEvent",
    "PositionOpenedEvent",
    "PositionOpenFailedEvent",
    "PositionUpdatedEvent",
    "PositionHealthChangedEvent",
    "PositionExitTriggeredEvent",
    "PositionClosingEvent",
    "PositionClosedEvent",
    "PositionEmergencyCloseEvent",
    "FundingCollectedEvent",
    # Risk
    "RiskStateUpdatedEvent",
    "RiskLimitWarningEvent",
    "RiskLimitBreachEvent",
    "RiskModeChangedEvent",
    # Capital
    "CapitalAllocatedEvent",
    "CapitalDeployedEvent",
    "CapitalReleasedEvent",
    "CapitalTransferEvent",
    # System
    "SystemStartedEvent",
    "SystemModeChangedEvent",
    "SystemErrorEvent",
    "VenueDegradedEvent",
    "VenueRestoredEvent",
]
