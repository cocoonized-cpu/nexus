"""
Funding rate API endpoints.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/rates")
async def get_funding_rates(
    request: Request,
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
) -> dict[str, Any]:
    """Get current unified funding rates."""
    aggregator = request.app.state.aggregator

    rates = aggregator.get_unified_rates(exchange=exchange, symbol=symbol)

    return {
        "success": True,
        "data": [rate.model_dump() for rate in rates],
        "meta": {
            "count": len(rates),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/rates/{symbol}")
async def get_funding_rate_by_symbol(
    request: Request,
    symbol: str,
) -> dict[str, Any]:
    """Get funding rates for a specific symbol across all exchanges."""
    aggregator = request.app.state.aggregator

    rates = aggregator.get_rates_for_symbol(symbol)

    return {
        "success": True,
        "data": [rate.model_dump() for rate in rates],
        "meta": {
            "symbol": symbol,
            "exchanges": len(rates),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/snapshot")
async def get_unified_snapshot(
    request: Request,
) -> dict[str, Any]:
    """Get unified funding snapshot (latest aggregated view)."""
    aggregator = request.app.state.aggregator

    snapshot = aggregator.get_latest_snapshot()

    return {
        "success": True,
        "data": snapshot.model_dump() if snapshot else None,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/spreads")
async def get_funding_spreads(
    request: Request,
    min_spread: float = Query(0.0, description="Minimum spread percentage"),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
) -> dict[str, Any]:
    """
    Get funding rate spreads between exchanges.

    Returns pairs of (exchange_a, exchange_b, symbol) with their spread.
    This is the key input for opportunity detection.
    """
    aggregator = request.app.state.aggregator

    spreads = aggregator.calculate_spreads(min_spread=min_spread, limit=limit)

    return {
        "success": True,
        "data": spreads,
        "meta": {
            "count": len(spreads),
            "min_spread_filter": min_spread,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/arb-scanner/status")
async def get_arb_scanner_status(
    request: Request,
) -> dict[str, Any]:
    """Get ArbitrageScanner API status."""
    aggregator = request.app.state.aggregator

    status = await aggregator.get_arb_scanner_status()

    return {
        "success": True,
        "data": status,
        "timestamp": datetime.utcnow().isoformat(),
    }
