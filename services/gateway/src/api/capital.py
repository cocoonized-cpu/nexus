"""
Capital API endpoints.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from shared.utils.redis_client import get_redis_client

router = APIRouter()


class VenueBalanceResponse(BaseModel):
    """Response model for venue balance."""

    venue: str
    total_usd: Decimal
    margin_used: Decimal
    margin_available: Decimal
    margin_utilization_pct: Decimal
    unrealized_pnl: Decimal


class CapitalSummaryResponse(BaseModel):
    """Response model for capital summary."""

    total_capital_usd: Decimal
    available_capital_usd: Decimal
    deployed_capital_usd: Decimal
    pending_capital_usd: Decimal
    reserve_capital_usd: Decimal
    utilization_pct: Decimal


@router.get("/summary")
async def get_capital_summary(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get capital summary across all venues.
    """
    # Get total from venue balances
    query = """
        SELECT
            COALESCE(SUM(total_usd), 0) as total,
            COALESCE(SUM(margin_used), 0) as margin_used,
            COALESCE(SUM(margin_available), 0) as margin_available
        FROM capital.venue_balances
    """

    result = await db.execute(text(query))
    row = result.fetchone()

    total = row[0] if row else Decimal("0")
    margin_used = row[1] if row else Decimal("0")
    margin_available = row[2] if row else Decimal("0")

    # Get deployed capital from positions
    positions_query = """
        SELECT COALESCE(SUM(total_capital_deployed), 0)
        FROM positions.active
        WHERE status IN ('active', 'opening')
    """
    positions_result = await db.execute(text(positions_query))
    deployed = positions_result.scalar() or Decimal("0")

    # Get pending allocations
    pending_query = """
        SELECT COALESCE(SUM(amount_usd), 0)
        FROM capital.allocations
        WHERE status = 'reserved'
    """
    pending_result = await db.execute(text(pending_query))
    pending = pending_result.scalar() or Decimal("0")

    # Calculate reserve (20% target)
    reserve = total * Decimal("0.20")
    available = total - deployed - pending - reserve
    utilization = (deployed / total * 100) if total > 0 else Decimal("0")

    summary = CapitalSummaryResponse(
        total_capital_usd=total,
        available_capital_usd=max(Decimal("0"), available),
        deployed_capital_usd=deployed,
        pending_capital_usd=pending,
        reserve_capital_usd=reserve,
        utilization_pct=utilization,
    )

    return {
        "success": True,
        "data": summary.model_dump(),
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/venues")
async def get_venue_balances(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get capital breakdown by venue.
    """
    query = """
        SELECT
            venue, total_usd, margin_used, margin_available, unrealized_pnl
        FROM capital.venue_balances
        ORDER BY total_usd DESC
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    balances = []
    for row in rows:
        total_margin = row[2] + row[3]
        utilization = (
            (row[2] / total_margin * 100) if total_margin > 0 else Decimal("0")
        )

        balance = VenueBalanceResponse(
            venue=row[0],
            total_usd=row[1],
            margin_used=row[2],
            margin_available=row[3],
            margin_utilization_pct=utilization,
            unrealized_pnl=row[4] or Decimal("0"),
        )
        balances.append(balance)

    return {
        "success": True,
        "data": [b.model_dump() for b in balances],
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/allocations")
async def get_allocations(
    status: Optional[str] = None,
    venue: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get capital allocations with optional filtering.
    """
    query = """
        SELECT
            id, opportunity_id, position_id, amount_usd, venue,
            status, allocated_at, deployed_at, released_at
        FROM capital.allocations
        WHERE 1=1
    """
    params: dict[str, Any] = {}

    if status:
        query += " AND status = :status"
        params["status"] = status

    if venue:
        query += " AND venue = :venue"
        params["venue"] = venue

    query += " ORDER BY allocated_at DESC LIMIT 100"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    allocations = [
        {
            "id": str(row[0]),
            "opportunity_id": str(row[1]) if row[1] else None,
            "position_id": str(row[2]) if row[2] else None,
            "amount_usd": float(row[3]),
            "venue": row[4],
            "status": row[5],
            "allocated_at": row[6].isoformat() if row[6] else None,
            "deployed_at": row[7].isoformat() if row[7] else None,
            "released_at": row[8].isoformat() if row[8] else None,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": allocations,
        "meta": {
            "total": len(allocations),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/transfers")
async def get_transfers(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get capital transfers between venues.
    """
    query = """
        SELECT
            id, from_venue, to_venue, asset, amount,
            status, tx_hash, fee, initiated_at, completed_at
        FROM capital.transfers
        WHERE 1=1
    """
    params: dict[str, Any] = {}

    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY initiated_at DESC LIMIT 100"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    transfers = [
        {
            "id": str(row[0]),
            "from_venue": row[1],
            "to_venue": row[2],
            "asset": row[3],
            "amount": float(row[4]),
            "status": row[5],
            "tx_hash": row[6],
            "fee": float(row[7]) if row[7] else 0,
            "initiated_at": row[8].isoformat() if row[8] else None,
            "completed_at": row[9].isoformat() if row[9] else None,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": transfers,
        "meta": {
            "total": len(transfers),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/portfolio")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get comprehensive portfolio overview with balances across all exchanges.

    Returns:
    - Total portfolio value
    - Per-exchange breakdown with balances by currency
    - P&L summary (realized, unrealized)
    - Historical balance snapshots
    """
    # Get exchange info
    exchanges_query = """
        SELECT slug, display_name, enabled
        FROM config.exchanges
        ORDER BY
            CASE tier
                WHEN 'tier_1' THEN 1
                WHEN 'tier_2' THEN 2
                ELSE 3
            END
    """
    exchanges_result = await db.execute(text(exchanges_query))
    exchanges_map = {
        row[0]: {"name": row[1], "enabled": row[2]}
        for row in exchanges_result.fetchall()
    }

    # Get venue balances with detailed breakdown
    balances_query = """
        SELECT
            venue, balances, total_usd, margin_used,
            margin_available, unrealized_pnl, last_updated
        FROM capital.venue_balances
        ORDER BY total_usd DESC
    """
    balances_result = await db.execute(text(balances_query))
    balances_rows = balances_result.fetchall()

    exchange_balances = []
    total_usd = Decimal("0")
    total_unrealized_pnl = Decimal("0")

    for row in balances_rows:
        venue = row[0]
        balances_json = row[1] or {}
        venue_total = Decimal(str(row[2])) if row[2] else Decimal("0")
        margin_used = Decimal(str(row[3])) if row[3] else Decimal("0")
        margin_available = Decimal(str(row[4])) if row[4] else Decimal("0")
        unrealized = Decimal(str(row[5])) if row[5] else Decimal("0")
        last_updated = row[6]

        total_usd += venue_total
        total_unrealized_pnl += unrealized

        exchange_info = exchanges_map.get(venue, {"name": venue, "enabled": True})

        # Parse balances JSON into currency breakdown
        currencies = []
        if isinstance(balances_json, dict):
            for currency, balance_data in balances_json.items():
                # Handle nested structure: {"USDT": {"free": X, "used": Y, "total": Z}}
                if isinstance(balance_data, dict):
                    currencies.append({
                        "currency": currency,
                        "free": float(balance_data.get("free", 0) or 0),
                        "used": float(balance_data.get("used", 0) or 0),
                        "total": float(balance_data.get("total", 0) or 0),
                    })
                else:
                    # Simple format: {"USDT": 123.45}
                    currencies.append({
                        "currency": currency,
                        "free": float(balance_data) if balance_data else 0,
                        "used": 0,
                        "total": float(balance_data) if balance_data else 0,
                    })

        exchange_balances.append({
            "exchange": venue,
            "exchange_name": exchange_info["name"],
            "enabled": exchange_info["enabled"],
            "total_usd": float(venue_total),
            "margin_used": float(margin_used),
            "margin_available": float(margin_available),
            "margin_utilization": float(margin_used / (margin_used + margin_available) * 100) if (margin_used + margin_available) > 0 else 0,
            "unrealized_pnl": float(unrealized),
            "currencies": currencies,
            "last_updated": last_updated.isoformat() if last_updated else None,
        })

    # Get realized P&L - these values may not be available depending on schema
    realized_funding_pnl = 0.0
    realized_price_pnl = 0.0
    total_fees = 0.0
    closed_positions = 0

    # Get current active positions value
    active_positions = 0
    deployed_capital = 0.0
    positions_unrealized = 0.0

    try:
        positions_query = """
            SELECT
                COUNT(*) as active_count,
                COALESCE(SUM(total_capital_deployed), 0) as deployed,
                COALESCE(SUM(unrealized_pnl), 0) as unrealized
            FROM positions.active
            WHERE status IN ('active', 'opening')
        """
        positions_result = await db.execute(text(positions_query))
        positions_row = positions_result.fetchone()

        if positions_row:
            active_positions = positions_row[0] or 0
            deployed_capital = float(positions_row[1]) if positions_row[1] else 0
            positions_unrealized = float(positions_row[2]) if positions_row[2] else 0
    except Exception:
        await db.rollback()  # Reset transaction state

    return {
        "success": True,
        "data": {
            "summary": {
                "total_value_usd": float(total_usd),
                "total_unrealized_pnl": float(total_unrealized_pnl),
                "deployed_capital": deployed_capital,
                "active_positions": active_positions,
            },
            "pnl": {
                "realized_funding": realized_funding_pnl,
                "realized_price": realized_price_pnl,
                "total_realized": realized_funding_pnl + realized_price_pnl - total_fees,
                "total_fees": total_fees,
                "unrealized": positions_unrealized,
                "closed_positions_30d": closed_positions,
            },
            "exchanges": exchange_balances,
        },
        "meta": {
            "total_exchanges": len(exchange_balances),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/portfolio/history")
async def get_portfolio_history(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get historical portfolio values for charting.

    Returns daily snapshots of total portfolio value.
    """
    history = []

    try:
        # Try to get from closed positions in active table
        query = """
            SELECT
                DATE(updated_at) as date,
                SUM(COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0) - COALESCE(total_fees, 0)) as daily_pnl,
                COUNT(*) as positions_closed
            FROM positions.active
            WHERE status = 'closed'
              AND updated_at > NOW() - INTERVAL ':days days'
            GROUP BY DATE(updated_at)
            ORDER BY date
        """

        result = await db.execute(text(query.replace(":days", str(days))))
        rows = result.fetchall()

        history = [
            {
                "date": row[0].isoformat() if row[0] else None,
                "daily_pnl": float(row[1]) if row[1] else 0,
                "positions_closed": row[2],
            }
            for row in rows
        ]
    except Exception:
        pass  # Table structure may vary

    # Calculate cumulative P&L
    cumulative = 0
    for entry in history:
        cumulative += entry["daily_pnl"]
        entry["cumulative_pnl"] = cumulative

    return {
        "success": True,
        "data": history,
        "meta": {
            "days": days,
            "total_entries": len(history),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


class AutoExecuteRequest(BaseModel):
    """Request model for setting auto-execute mode."""
    enabled: bool


@router.post("/auto-execute")
async def set_auto_execute(
    request: AutoExecuteRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Enable or disable auto-execution of high quality opportunities.

    When enabled, opportunities meeting the UOS threshold will be
    automatically executed without manual approval.
    """
    try:
        # Update database setting
        update_query = text("""
            INSERT INTO config.system_settings (key, value, data_type, category, description)
            VALUES ('auto_execute', :value, 'boolean', 'capital', 'Auto-execute high quality opportunities')
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW()
        """)
        await db.execute(update_query, {"value": json.dumps(request.enabled)})
        await db.commit()

        # Publish state change event via Redis
        redis = await get_redis_client()
        await redis.publish(
            "nexus:system:state_changed",
            json.dumps({
                "auto_execute": request.enabled,
                "source": "gateway-api",
                "timestamp": datetime.utcnow().isoformat(),
            }),
        )

        return {
            "success": True,
            "data": {"auto_execute": request.enabled},
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update auto-execute setting: {str(e)}")


@router.get("/auto-execute")
async def get_auto_execute(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get current auto-execute setting.
    """
    try:
        query = text("""
            SELECT value FROM config.system_settings WHERE key = 'auto_execute'
        """)
        result = await db.execute(query)
        row = result.fetchone()

        enabled = True  # Default to true
        if row and row[0]:
            try:
                enabled = json.loads(row[0]) if isinstance(row[0], str) else bool(row[0])
            except (json.JSONDecodeError, ValueError):
                enabled = str(row[0]).lower() == "true"

        return {
            "success": True,
            "data": {"auto_execute": enabled},
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auto-execute setting: {str(e)}")
