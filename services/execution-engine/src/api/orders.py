"""Order management endpoints."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class ExecuteOrderRequest(BaseModel):
    opportunity_id: str
    position_size_usd: float
    max_slippage_pct: Optional[float] = 0.5


class CancelOrderRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/execute")
async def execute_opportunity(
    request: Request, body: ExecuteOrderRequest
) -> dict[str, Any]:
    """Execute an arbitrage opportunity."""
    engine = request.app.state.engine
    result = await engine.execute_opportunity(
        opportunity_id=body.opportunity_id,
        position_size_usd=body.position_size_usd,
        max_slippage_pct=body.max_slippage_pct,
    )
    return {"success": True, "data": result, "timestamp": datetime.utcnow().isoformat()}


@router.get("/")
async def list_orders(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List orders with optional status filter."""
    engine = request.app.state.engine
    orders = engine.get_orders(status=status, limit=limit)
    return {
        "success": True,
        "data": [o.model_dump() for o in orders],
        "meta": {"count": len(orders), "timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/{order_id}")
async def get_order(request: Request, order_id: str) -> dict[str, Any]:
    """Get order by ID."""
    engine = request.app.state.engine
    order = engine.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "success": True,
        "data": order.model_dump(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/{order_id}/cancel")
async def cancel_order(
    request: Request, order_id: str, body: CancelOrderRequest
) -> dict[str, Any]:
    """Cancel an order."""
    engine = request.app.state.engine
    result = await engine.cancel_order(order_id, reason=body.reason)
    return {
        "success": result,
        "message": "Order cancelled" if result else "Cancel failed",
        "timestamp": datetime.utcnow().isoformat(),
    }
