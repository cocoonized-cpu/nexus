"""
API routers for NEXUS Gateway.
"""

from src.api.analytics import router as analytics_router
from src.api.capital import router as capital_router
from src.api.config import router as config_router
from src.api.funding import router as funding_router
from src.api.health import router as health_router
from src.api.opportunities import router as opportunities_router
from src.api.positions import router as positions_router
from src.api.risk import router as risk_router
from src.api.system import router as system_router

__all__ = [
    "health_router",
    "opportunities_router",
    "positions_router",
    "risk_router",
    "capital_router",
    "config_router",
    "analytics_router",
    "system_router",
    "funding_router",
]
