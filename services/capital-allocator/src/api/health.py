"""Health check endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> dict[str, Any]:
    allocator = request.app.state.allocator
    return {
        "status": "healthy",
        "service": "capital-allocator",
        "timestamp": datetime.utcnow().isoformat(),
        "total_capital_usd": allocator.total_capital,
        "allocated_capital_usd": allocator.allocated_capital,
    }
