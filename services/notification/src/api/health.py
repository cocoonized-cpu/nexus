"""Health check endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "status": "healthy",
        "service": "notification",
        "timestamp": datetime.utcnow().isoformat(),
        "channels_configured": service.configured_channel_count,
    }
