"""
Health check endpoints for Funding Aggregator service.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    """Basic health check."""
    aggregator = request.app.state.aggregator

    return {
        "status": "healthy",
        "service": "funding-aggregator",
        "timestamp": datetime.utcnow().isoformat(),
        "symbols_tracked": aggregator.symbol_count,
        "sources_active": aggregator.active_source_count,
    }


@router.get("/sources")
async def source_health(request: Request) -> dict[str, Any]:
    """Get health status for data sources."""
    aggregator = request.app.state.aggregator

    source_status = aggregator.get_source_status()

    return {
        "success": True,
        "data": source_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/stats")
async def aggregation_stats(request: Request) -> dict[str, Any]:
    """Get aggregation statistics."""
    aggregator = request.app.state.aggregator

    stats = aggregator.get_stats()

    return {
        "success": True,
        "data": stats,
        "timestamp": datetime.utcnow().isoformat(),
    }
