"""Metrics and analytics endpoints."""

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/performance")
async def get_performance(
    request: Request, period: str = Query("30d")
) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "success": True,
        "data": service.get_performance(period),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/daily")
async def get_daily_pnl(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "success": True,
        "data": service.get_daily_pnl(start_date, end_date),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/attribution")
async def get_attribution(
    request: Request, by: str = Query("exchange")
) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "success": True,
        "data": service.get_attribution(by),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/trades")
async def get_trade_stats(request: Request) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "success": True,
        "data": service.get_trade_stats(),
        "timestamp": datetime.utcnow().isoformat(),
    }
