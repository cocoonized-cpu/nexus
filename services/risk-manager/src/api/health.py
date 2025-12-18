"""Health check endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    return {
        "status": "healthy",
        "service": "risk-manager",
        "timestamp": datetime.utcnow().isoformat(),
        "circuit_breaker_active": manager.circuit_breaker_active,
        "active_alerts": manager.active_alert_count,
    }
