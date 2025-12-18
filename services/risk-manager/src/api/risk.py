"""Risk management endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ValidateTradeRequest(BaseModel):
    opportunity_id: str
    position_size_usd: float
    long_exchange: str
    short_exchange: str


@router.get("/state")
async def get_risk_state(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    return {
        "success": True,
        "data": manager.get_risk_state(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/limits")
async def get_risk_limits(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    return {
        "success": True,
        "data": manager.get_limits(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/validate")
async def validate_trade(
    request: Request, body: ValidateTradeRequest
) -> dict[str, Any]:
    manager = request.app.state.manager
    result = await manager.validate_trade(
        opportunity_id=body.opportunity_id,
        position_size_usd=body.position_size_usd,
        long_exchange=body.long_exchange,
        short_exchange=body.short_exchange,
    )
    return {"success": True, "data": result, "timestamp": datetime.utcnow().isoformat()}


@router.get("/alerts")
async def get_alerts(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    return {
        "success": True,
        "data": manager.get_alerts(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/circuit-breaker/activate")
async def activate_circuit_breaker(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    await manager.activate_circuit_breaker("manual")
    return {
        "success": True,
        "message": "Circuit breaker activated",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/circuit-breaker/deactivate")
async def deactivate_circuit_breaker(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    await manager.deactivate_circuit_breaker()
    return {
        "success": True,
        "message": "Circuit breaker deactivated",
        "timestamp": datetime.utcnow().isoformat(),
    }
