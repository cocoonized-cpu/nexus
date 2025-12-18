"""Position management endpoints."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class ClosePositionRequest(BaseModel):
    reason: Optional[str] = "manual"


@router.get("/")
async def list_positions(
    request: Request, status: Optional[str] = None, limit: int = 50
) -> dict[str, Any]:
    manager = request.app.state.manager
    positions = manager.get_positions(status=status, limit=limit)
    return {
        "success": True,
        "data": [p.model_dump() for p in positions],
        "meta": {"count": len(positions), "timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/{position_id}")
async def get_position(request: Request, position_id: str) -> dict[str, Any]:
    manager = request.app.state.manager
    position = manager.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return {
        "success": True,
        "data": position.model_dump(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/{position_id}/pnl")
async def get_position_pnl(request: Request, position_id: str) -> dict[str, Any]:
    manager = request.app.state.manager
    pnl = manager.get_position_pnl(position_id)
    if not pnl:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"success": True, "data": pnl, "timestamp": datetime.utcnow().isoformat()}


@router.post("/{position_id}/close")
async def close_position(
    request: Request, position_id: str, body: ClosePositionRequest
) -> dict[str, Any]:
    manager = request.app.state.manager
    result = await manager.close_position(position_id, reason=body.reason)
    return {"success": result, "timestamp": datetime.utcnow().isoformat()}


@router.get("/summary/total")
async def get_total_pnl(request: Request) -> dict[str, Any]:
    manager = request.app.state.manager
    summary = manager.get_total_pnl_summary()
    return {
        "success": True,
        "data": summary,
        "timestamp": datetime.utcnow().isoformat(),
    }


# Exchange position/order sync endpoints
@router.get("/exchange/positions")
async def get_exchange_positions(
    request: Request, exchange: Optional[str] = None
) -> dict[str, Any]:
    """Get positions synced from exchanges."""
    sync_worker = request.app.state.sync_worker
    if not sync_worker:
        return {
            "success": False,
            "error": "Sync worker not available",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "data": sync_worker.get_positions(exchange),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/exchange/orders")
async def get_exchange_orders(
    request: Request, exchange: Optional[str] = None
) -> dict[str, Any]:
    """Get open orders synced from exchanges."""
    sync_worker = request.app.state.sync_worker
    if not sync_worker:
        return {
            "success": False,
            "error": "Sync worker not available",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "data": sync_worker.get_orders(exchange),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/exchange/sync")
async def trigger_sync(request: Request) -> dict[str, Any]:
    """Trigger a manual sync of positions and orders from all exchanges."""
    sync_worker = request.app.state.sync_worker
    if not sync_worker:
        return {
            "success": False,
            "error": "Sync worker not available",
            "timestamp": datetime.utcnow().isoformat(),
        }

    result = await sync_worker.sync_all()
    return {
        "success": result.get("success", False),
        "data": result,
        "timestamp": datetime.utcnow().isoformat(),
    }
