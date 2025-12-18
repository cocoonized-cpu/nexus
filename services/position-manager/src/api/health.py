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
        "service": "position-manager",
        "timestamp": datetime.utcnow().isoformat(),
        "active_positions": manager.active_position_count,
    }


@router.get("/stats")
async def get_stats(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    return {
        "success": True,
        "data": manager.get_stats(),
        "timestamp": datetime.utcnow().isoformat(),
    }
