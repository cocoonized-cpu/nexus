"""Health check endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    engine = request.app.state.engine
    return {
        "status": "healthy",
        "service": "execution-engine",
        "timestamp": datetime.utcnow().isoformat(),
        "pending_orders": engine.pending_order_count,
        "connected_exchanges": engine.connected_exchange_count,
    }


@router.get("/stats")
async def get_stats(request: Request) -> dict[str, Any]:
    engine = request.app.state.engine
    return {
        "success": True,
        "data": engine.get_stats(),
        "timestamp": datetime.utcnow().isoformat(),
    }
