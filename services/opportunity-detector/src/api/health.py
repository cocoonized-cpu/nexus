"""
Health check endpoints for Opportunity Detector service.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    """Basic health check."""
    detector = request.app.state.detector

    return {
        "status": "healthy",
        "service": "opportunity-detector",
        "timestamp": datetime.utcnow().isoformat(),
        "opportunities_active": detector.active_opportunity_count,
        "detection_running": detector.is_running,
    }


@router.get("/stats")
async def detection_stats(request: Request) -> dict[str, Any]:
    """Get detection statistics."""
    detector = request.app.state.detector

    stats = detector.get_stats()

    return {
        "success": True,
        "data": stats,
        "timestamp": datetime.utcnow().isoformat(),
    }
