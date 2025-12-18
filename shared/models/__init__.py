"""
NEXUS Shared Data Models

Core data models used across all microservices.
"""

from shared.models.base import BaseModel, TimestampMixin
from shared.models.capital import CapitalPool, CapitalPoolType, CapitalState
from shared.models.exchange import ExchangeConfig, ExchangeStatus, MarketType
from shared.models.funding import (FundingRateData, FundingRateDiscrepancy,
                                   FundingRateSource, UnifiedFundingSnapshot)
from shared.models.opportunity import (Opportunity, OpportunityLeg,
                                       OpportunityStatus, OpportunityType)
from shared.models.position import (Position, PositionHealthStatus,
                                    PositionLeg, PositionStatus)
from shared.models.risk import (RiskAlert, RiskAlertSeverity, RiskLimits,
                                RiskState)

__all__ = [
    # Base
    "BaseModel",
    "TimestampMixin",
    # Funding
    "FundingRateData",
    "FundingRateSource",
    "UnifiedFundingSnapshot",
    "FundingRateDiscrepancy",
    # Opportunity
    "OpportunityType",
    "OpportunityLeg",
    "Opportunity",
    "OpportunityStatus",
    # Position
    "PositionStatus",
    "PositionHealthStatus",
    "PositionLeg",
    "Position",
    # Risk
    "RiskLimits",
    "RiskState",
    "RiskAlert",
    "RiskAlertSeverity",
    # Capital
    "CapitalPoolType",
    "CapitalPool",
    "CapitalState",
    # Exchange
    "ExchangeConfig",
    "ExchangeStatus",
    "MarketType",
]
