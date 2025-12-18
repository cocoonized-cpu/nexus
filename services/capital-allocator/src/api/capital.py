"""Capital management endpoints."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class AllocateRequest(BaseModel):
    opportunity_id: str
    amount_usd: Optional[float] = None  # None = auto-size


@router.get("/state")
async def get_capital_state(request: Request) -> dict[str, Any]:
    allocator = request.app.state.allocator
    return {
        "success": True,
        "data": allocator.get_state(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/allocations")
async def get_allocations(request: Request) -> dict[str, Any]:
    allocator = request.app.state.allocator
    return {
        "success": True,
        "data": allocator.get_allocations(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/allocate")
async def allocate_capital(request: Request, body: AllocateRequest) -> dict[str, Any]:
    allocator = request.app.state.allocator
    result = await allocator.allocate(body.opportunity_id, body.amount_usd)
    return {"success": True, "data": result, "timestamp": datetime.utcnow().isoformat()}


@router.get("/exchanges")
async def get_exchange_balances(request: Request) -> dict[str, Any]:
    allocator = request.app.state.allocator
    return {
        "success": True,
        "data": allocator.get_exchange_balances(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/balances")
async def get_detailed_balances(request: Request) -> dict[str, Any]:
    """Get detailed balances from all exchanges."""
    balance_monitor = request.app.state.balance_monitor
    if not balance_monitor:
        return {
            "success": False,
            "error": "Balance monitor not available",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "data": balance_monitor.get_balances(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/balances/sync")
async def sync_balances(request: Request) -> dict[str, Any]:
    """Trigger a manual balance sync from all exchanges."""
    balance_monitor = request.app.state.balance_monitor
    if not balance_monitor:
        return {
            "success": False,
            "error": "Balance monitor not available",
            "timestamp": datetime.utcnow().isoformat(),
        }

    result = await balance_monitor.sync_all_balances()
    return {
        "success": result.get("success", False),
        "data": result,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/balances/{exchange}")
async def get_exchange_balance_detail(request: Request, exchange: str) -> dict[str, Any]:
    """Get detailed balance for a specific exchange."""
    balance_monitor = request.app.state.balance_monitor
    if not balance_monitor:
        return {
            "success": False,
            "error": "Balance monitor not available",
            "timestamp": datetime.utcnow().isoformat(),
        }

    balance = balance_monitor.get_exchange_balance(exchange)
    if not balance:
        return {
            "success": False,
            "error": f"No balance data for exchange: {exchange}",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "data": balance,
        "timestamp": datetime.utcnow().isoformat(),
    }
