"""
Opportunities API endpoints.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/")
async def list_opportunities(
    request: Request,
    min_score: int = Query(0, ge=0, le=100, description="Minimum UOS score"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    include_bot_action: bool = Query(True, description="Include bot action status"),
) -> dict[str, Any]:
    """Get list of current opportunities with bot action status."""
    detector = request.app.state.detector

    if include_bot_action:
        # Use the new method that includes bot_action
        opportunities = detector.get_opportunities_with_bot_action(
            min_score=min_score,
            symbol=symbol,
            limit=limit,
        )
    else:
        # Legacy method without bot_action
        opps = detector.get_opportunities(
            min_score=min_score,
            symbol=symbol,
            limit=limit,
        )
        opportunities = [opp.model_dump() for opp in opps]

    return {
        "success": True,
        "data": opportunities,
        "meta": {
            "count": len(opportunities),
            "min_score_filter": min_score,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/top")
async def get_top_opportunities(
    request: Request,
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
) -> dict[str, Any]:
    """Get top opportunities by UOS score."""
    detector = request.app.state.detector

    opportunities = detector.get_top_opportunities(limit=limit)

    return {
        "success": True,
        "data": [opp.model_dump() for opp in opportunities],
        "meta": {
            "count": len(opportunities),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/{opportunity_id}")
async def get_opportunity(
    request: Request,
    opportunity_id: str,
) -> dict[str, Any]:
    """Get a specific opportunity by ID."""
    detector = request.app.state.detector

    opportunity = detector.get_opportunity_by_id(opportunity_id)

    if not opportunity:
        return {
            "success": False,
            "error": "Opportunity not found",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "data": opportunity.model_dump(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/{opportunity_id}/score-breakdown")
async def get_score_breakdown(
    request: Request,
    opportunity_id: str,
) -> dict[str, Any]:
    """Get detailed UOS score breakdown for an opportunity."""
    detector = request.app.state.detector

    breakdown = detector.get_score_breakdown(opportunity_id)

    if not breakdown:
        return {
            "success": False,
            "error": "Opportunity not found",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "data": breakdown,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/symbol/{symbol}")
async def get_opportunities_by_symbol(
    request: Request,
    symbol: str,
) -> dict[str, Any]:
    """Get all opportunities for a specific symbol."""
    detector = request.app.state.detector

    opportunities = detector.get_opportunities_for_symbol(symbol)

    return {
        "success": True,
        "data": [opp.model_dump() for opp in opportunities],
        "meta": {
            "symbol": symbol,
            "count": len(opportunities),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.post("/refresh")
async def trigger_refresh(request: Request) -> dict[str, Any]:
    """Manually trigger opportunity detection cycle."""
    detector = request.app.state.detector

    await detector.run_detection_cycle()

    return {
        "success": True,
        "message": "Detection cycle completed",
        "opportunities_found": detector.active_opportunity_count,
        "timestamp": datetime.utcnow().isoformat(),
    }
