"""
Health check endpoints for Data Collector service.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    """Basic health check."""
    collector_manager = request.app.state.collector_manager

    return {
        "status": "healthy",
        "service": "data-collector",
        "timestamp": datetime.utcnow().isoformat(),
        "exchanges_active": collector_manager.active_exchange_count,
    }


@router.get("/exchanges")
async def exchange_health(request: Request) -> dict[str, Any]:
    """Get health status for all exchanges."""
    collector_manager = request.app.state.collector_manager

    exchange_status = await collector_manager.get_exchange_health()

    return {
        "success": True,
        "data": exchange_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/stats")
async def collection_stats(request: Request) -> dict[str, Any]:
    """Get data collection statistics."""
    collector_manager = request.app.state.collector_manager

    stats = collector_manager.get_stats()

    return {
        "success": True,
        "data": stats,
        "timestamp": datetime.utcnow().isoformat(),
    }
