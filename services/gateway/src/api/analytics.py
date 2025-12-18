"""
Analytics API endpoints.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

router = APIRouter()


class DailyPnLResponse(BaseModel):
    """Response model for daily P&L."""

    date: date
    funding_pnl: Decimal
    price_pnl: Decimal
    fee_costs: Decimal
    net_pnl: Decimal
    return_pct: Decimal
    cumulative_return_pct: Decimal
    positions_opened: int
    positions_closed: int
    capital_utilization_pct: Decimal


class PerformanceSummaryResponse(BaseModel):
    """Response model for performance summary."""

    period: str
    total_return_pct: Decimal
    funding_return_pct: Decimal
    total_pnl: Decimal
    win_rate: Decimal
    avg_return_pct: Decimal
    max_drawdown_pct: Decimal
    sharpe_ratio: Optional[Decimal]
    trades_count: int
    avg_hold_hours: Decimal


@router.get("/daily")
async def get_daily_pnl(
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    days: int = Query(
        30, ge=1, le=365, description="Number of days if no dates provided"
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get daily P&L history.
    Aggregates data directly from closed positions in positions.active.
    """
    if not start_date:
        start_date = date.today() - timedelta(days=days)
    if not end_date:
        end_date = date.today()

    # Query closed positions and aggregate by date
    query = """
        SELECT
            DATE(closed_at) as trade_date,
            COALESCE(SUM(realized_pnl_funding), 0) as funding_pnl,
            COALESCE(SUM(realized_pnl_price), 0) as price_pnl,
            COALESCE(SUM(COALESCE(entry_costs_paid, 0) + COALESCE(exit_costs_paid, 0)), 0) as fee_costs,
            COALESCE(SUM(
                COALESCE(realized_pnl_funding, 0) +
                COALESCE(realized_pnl_price, 0) -
                COALESCE(entry_costs_paid, 0) -
                COALESCE(exit_costs_paid, 0)
            ), 0) as net_pnl,
            COUNT(*) as positions_closed,
            COALESCE(SUM(total_capital_deployed), 0) as capital_deployed
        FROM positions.active
        WHERE status = 'closed'
          AND closed_at IS NOT NULL
          AND DATE(closed_at) >= :start_date
          AND DATE(closed_at) <= :end_date
        GROUP BY DATE(closed_at)
        ORDER BY trade_date
    """

    result = await db.execute(
        text(query), {"start_date": start_date, "end_date": end_date}
    )
    rows = result.fetchall()

    # Build daily data with cumulative P&L
    daily_pnl = []
    cumulative_pnl = Decimal("0")

    for row in rows:
        net_pnl = row[4] or Decimal("0")
        cumulative_pnl += net_pnl
        capital = row[6] or Decimal("1")
        return_pct = (net_pnl / capital * 100) if capital > 0 else Decimal("0")

        daily_pnl.append(
            DailyPnLResponse(
                date=row[0],
                funding_pnl=row[1] or Decimal("0"),
                price_pnl=row[2] or Decimal("0"),
                fee_costs=row[3] or Decimal("0"),
                net_pnl=net_pnl,
                return_pct=return_pct,
                cumulative_return_pct=cumulative_pnl,
                positions_opened=0,  # Not tracked in this query
                positions_closed=row[5] or 0,
                capital_utilization_pct=Decimal("0"),  # Not tracked in this query
            ).model_dump()
        )

    # Calculate summary stats
    total_pnl = sum(d["net_pnl"] for d in daily_pnl)
    avg_return = (
        sum(d["return_pct"] for d in daily_pnl) / len(daily_pnl)
        if daily_pnl
        else Decimal("0")
    )

    return {
        "success": True,
        "data": daily_pnl,
        "meta": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": len(daily_pnl),
            "total_pnl": float(total_pnl),
            "avg_daily_return_pct": float(avg_return),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/summary")
async def get_performance_summary(
    period: str = Query("30d", description="Period: 7d, 30d, 90d, ytd, all"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get performance summary for a period.
    Aggregates data directly from closed positions in positions.active.
    """
    # Calculate date range
    today = date.today()
    if period == "7d":
        start_date = today - timedelta(days=7)
    elif period == "30d":
        start_date = today - timedelta(days=30)
    elif period == "90d":
        start_date = today - timedelta(days=90)
    elif period == "ytd":
        start_date = date(today.year, 1, 1)
    else:
        start_date = date(2020, 1, 1)  # All time

    # Get aggregated stats directly from closed positions
    query = """
        SELECT
            COALESCE(SUM(
                COALESCE(realized_pnl_funding, 0) +
                COALESCE(realized_pnl_price, 0) -
                COALESCE(entry_costs_paid, 0) -
                COALESCE(exit_costs_paid, 0)
            ), 0) as total_pnl,
            COALESCE(SUM(realized_pnl_funding), 0) as funding_pnl,
            COALESCE(SUM(realized_pnl_price), 0) as price_pnl,
            COUNT(*) as trades_count,
            COUNT(CASE WHEN
                COALESCE(realized_pnl_funding, 0) +
                COALESCE(realized_pnl_price, 0) -
                COALESCE(entry_costs_paid, 0) -
                COALESCE(exit_costs_paid, 0) > 0
            THEN 1 END) as winning_trades,
            COALESCE(AVG(EXTRACT(EPOCH FROM (closed_at - opened_at)) / 3600), 0) as avg_hold_hours,
            COALESCE(SUM(total_capital_deployed), 0) as total_capital
        FROM positions.active
        WHERE status = 'closed'
          AND closed_at >= :start_date
    """

    result = await db.execute(text(query), {"start_date": start_date})
    row = result.fetchone()

    total_pnl = Decimal(str(row[0])) if row[0] else Decimal("0")
    funding_pnl = Decimal(str(row[1])) if row[1] else Decimal("0")
    price_pnl = Decimal(str(row[2])) if row[2] else Decimal("0")
    trades_count = int(row[3]) if row[3] else 0
    winning_trades = int(row[4]) if row[4] else 0
    avg_hold = Decimal(str(row[5])) if row[5] else Decimal("0")
    total_capital = Decimal(str(row[6])) if row[6] else Decimal("0")

    # Calculate derived metrics
    win_rate = Decimal(str(winning_trades / trades_count * 100)) if trades_count > 0 else Decimal("0")
    total_return = (total_pnl / total_capital * 100) if total_capital > 0 else Decimal("0")
    avg_return = (total_return / trades_count) if trades_count > 0 else Decimal("0")
    funding_return = (funding_pnl / total_capital * 100) if total_capital > 0 else Decimal("0")

    summary = PerformanceSummaryResponse(
        period=period,
        total_return_pct=total_return,
        funding_return_pct=funding_return,
        total_pnl=total_pnl,
        win_rate=win_rate,
        avg_return_pct=avg_return,
        max_drawdown_pct=Decimal("0"),  # Would need time-series data to calculate
        sharpe_ratio=None,  # Would need daily returns to calculate
        trades_count=trades_count,
        avg_hold_hours=avg_hold,
    )

    return {
        "success": True,
        "data": summary.model_dump(),
        "meta": {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "funding_pnl": float(funding_pnl),
            "price_pnl": float(price_pnl),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/funding")
async def get_funding_history(
    symbol: Optional[str] = None,
    exchange: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get funding payment history.
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    query = """
        SELECT
            fp.position_id, fp.exchange, fp.symbol,
            fp.funding_rate, fp.payment_amount, fp.position_size,
            fp.timestamp
        FROM positions.funding_payments fp
        WHERE fp.timestamp >= :start_date
    """
    params: dict[str, Any] = {"start_date": start_date}

    if symbol:
        query += " AND fp.symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    if exchange:
        query += " AND fp.exchange = :exchange"
        params["exchange"] = exchange

    query += " ORDER BY fp.timestamp DESC LIMIT 500"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    payments = [
        {
            "position_id": str(row[0]),
            "exchange": row[1],
            "symbol": row[2],
            "funding_rate": float(row[3]),
            "payment_amount": float(row[4]),
            "position_size": float(row[5]),
            "timestamp": row[6].isoformat(),
        }
        for row in rows
    ]

    # Calculate totals
    total_received = sum(
        p["payment_amount"] for p in payments if p["payment_amount"] > 0
    )
    total_paid = sum(
        abs(p["payment_amount"]) for p in payments if p["payment_amount"] < 0
    )

    return {
        "success": True,
        "data": payments,
        "meta": {
            "total_payments": len(payments),
            "total_received": total_received,
            "total_paid": total_paid,
            "net_funding": total_received - total_paid,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/trades")
async def get_trade_history(
    symbol: Optional[str] = None,
    exchange: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get closed position (trade) history.
    """
    query = """
        SELECT
            p.id, p.symbol, p.opportunity_type,
            l1.exchange as primary_exchange, l2.exchange as hedge_exchange,
            p.total_capital_deployed,
            (p.funding_received - p.funding_paid) as net_funding,
            p.entry_costs_paid, p.exit_costs_paid,
            p.opened_at, p.closed_at, p.exit_reason,
            p.funding_periods_collected,
            COALESCE(p.realized_pnl_price, 0) as realized_pnl_price,
            COALESCE(p.realized_pnl_funding, 0) as realized_pnl_funding
        FROM positions.active p
        LEFT JOIN positions.legs l1 ON l1.position_id = p.id AND l1.leg_type = 'primary'
        LEFT JOIN positions.legs l2 ON l2.position_id = p.id AND l2.leg_type = 'hedge'
        WHERE p.status = 'closed'
    """
    params: dict[str, Any] = {}

    if symbol:
        query += " AND p.symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    if exchange:
        query += " AND (l1.exchange = :exchange OR l2.exchange = :exchange)"
        params["exchange"] = exchange

    query += " ORDER BY p.closed_at DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    trades = []
    for row in rows:
        capital = row[5] or Decimal("1")
        net_funding = row[6] or Decimal("0")
        costs = (row[7] or Decimal("0")) + (row[8] or Decimal("0"))
        price_pnl = row[13] or Decimal("0")  # realized_pnl_price
        funding_pnl = row[14] or Decimal("0")  # realized_pnl_funding
        # Total P&L = price movement + funding payments - costs
        net_pnl = price_pnl + funding_pnl - costs
        return_pct = (net_pnl / capital * 100) if capital > 0 else Decimal("0")

        hold_hours = None
        if row[9] and row[10]:
            delta = row[10] - row[9]
            hold_hours = delta.total_seconds() / 3600

        trades.append(
            {
                "id": str(row[0]),
                "symbol": row[1],
                "opportunity_type": row[2],
                "primary_exchange": row[3],
                "hedge_exchange": row[4],
                "capital_deployed": float(capital),
                "net_funding": float(funding_pnl),
                "price_pnl": float(price_pnl),
                "costs": float(costs),
                "net_pnl": float(net_pnl),
                "return_pct": float(return_pct),
                "opened_at": row[9].isoformat() if row[9] else None,
                "closed_at": row[10].isoformat() if row[10] else None,
                "exit_reason": row[11],
                "funding_periods": row[12] or 0,
                "hold_hours": hold_hours,
            }
        )

    # Calculate summary stats
    winning = [t for t in trades if t["net_pnl"] > 0]
    losing = [t for t in trades if t["net_pnl"] < 0]

    return {
        "success": True,
        "data": trades,
        "meta": {
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": len(winning) / len(trades) * 100 if trades else 0,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/attribution")
async def get_performance_attribution(
    period: str = Query("30d", description="Period: 7d, 30d, 90d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get detailed performance attribution analysis.
    Breaks down P&L by exchange, symbol, and UOS score cohorts.
    """
    # Calculate date range
    today = date.today()
    if period == "7d":
        start_date = today - timedelta(days=7)
    elif period == "90d":
        start_date = today - timedelta(days=90)
    else:
        start_date = today - timedelta(days=30)

    # Get P&L breakdown (funding vs price)
    pnl_query = """
        SELECT
            COALESCE(SUM(realized_pnl_funding), 0) as funding_pnl,
            COALESCE(SUM(realized_pnl_price), 0) as price_pnl,
            COALESCE(SUM(realized_pnl_funding + realized_pnl_price), 0) as total_pnl,
            COUNT(*) as trade_count
        FROM positions.active
        WHERE status = 'closed'
          AND closed_at >= :start_date
    """
    pnl_result = await db.execute(text(pnl_query), {"start_date": start_date})
    pnl_row = pnl_result.fetchone()

    funding_pnl = float(pnl_row[0] or 0)
    price_pnl = float(pnl_row[1] or 0)
    total_pnl = float(pnl_row[2] or 0)
    trade_count = int(pnl_row[3] or 0)

    # Get exchange attribution (using legs table)
    exchange_query = """
        SELECT
            l.exchange,
            COUNT(DISTINCT p.id) as trade_count,
            COALESCE(SUM(p.realized_pnl_funding + p.realized_pnl_price), 0) as total_pnl,
            SUM(CASE WHEN (p.realized_pnl_funding + p.realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins
        FROM positions.active p
        JOIN positions.legs l ON l.position_id = p.id
        WHERE p.status = 'closed'
          AND p.closed_at >= :start_date
        GROUP BY l.exchange
        ORDER BY total_pnl DESC
    """
    exchange_result = await db.execute(text(exchange_query), {"start_date": start_date})
    exchange_rows = exchange_result.fetchall()

    exchange_breakdown = [
        {
            "exchange": row[0],
            "trade_count": int(row[1] or 0),
            "total_pnl": float(row[2] or 0),
            "win_rate": float((row[3] or 0) / (row[1] or 1) * 100),
        }
        for row in exchange_rows
    ]

    # Get symbol attribution (top 10)
    symbol_query = """
        SELECT
            symbol,
            COUNT(*) as trade_count,
            SUM(realized_pnl_funding + realized_pnl_price) as total_pnl,
            SUM(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins
        FROM positions.active
        WHERE status = 'closed'
          AND closed_at >= :start_date
        GROUP BY symbol
        ORDER BY total_pnl DESC
        LIMIT 10
    """
    symbol_result = await db.execute(text(symbol_query), {"start_date": start_date})
    symbol_rows = symbol_result.fetchall()

    symbol_breakdown = [
        {
            "symbol": row[0],
            "trade_count": int(row[1] or 0),
            "total_pnl": float(row[2] or 0),
            "win_rate": float((row[3] or 0) / (row[1] or 1) * 100),
        }
        for row in symbol_rows
    ]

    # Get UOS score cohorts from opportunities table if linked
    # Note: UOS scores are stored in opportunities.detected, linked via opportunity_id
    cohort_boundaries = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
    cohort_names = ["Low (0-60)", "Medium-Low (60-70)", "Medium (70-80)", "Medium-High (80-90)", "High (90-100)"]
    uos_cohorts = []

    for (min_score, max_score), name in zip(cohort_boundaries, cohort_names):
        cohort_query = """
            SELECT
                COUNT(*) as trade_count,
                COALESCE(SUM(p.realized_pnl_funding + p.realized_pnl_price), 0) as total_pnl,
                COALESCE(AVG(p.realized_pnl_funding + p.realized_pnl_price), 0) as avg_pnl,
                SUM(CASE WHEN (p.realized_pnl_funding + p.realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins
            FROM positions.active p
            LEFT JOIN opportunities.detected o ON p.opportunity_id = o.id
            WHERE p.status = 'closed'
              AND p.closed_at >= :start_date
              AND o.uos_score >= :min_score
              AND o.uos_score < :max_score
        """
        cohort_result = await db.execute(text(cohort_query), {
            "start_date": start_date,
            "min_score": min_score,
            "max_score": max_score,
        })
        cohort_row = cohort_result.fetchone()

        trades = int(cohort_row[0] or 0)
        uos_cohorts.append({
            "cohort": name,
            "trade_count": trades,
            "total_pnl": float(cohort_row[1] or 0),
            "avg_pnl": float(cohort_row[2] or 0),
            "win_rate": float((cohort_row[3] or 0) / trades * 100) if trades > 0 else 0,
        })

    # Calculate percentages
    funding_pct = (funding_pnl / abs(total_pnl) * 100) if total_pnl != 0 else 0
    price_pct = (price_pnl / abs(total_pnl) * 100) if total_pnl != 0 else 0

    return {
        "success": True,
        "data": {
            "pnl_breakdown": {
                "funding_pnl": funding_pnl,
                "price_pnl": price_pnl,
                "total_pnl": total_pnl,
                "funding_pct": funding_pct,
                "price_pct": price_pct,
                "trade_count": trade_count,
            },
            "exchange_attribution": exchange_breakdown,
            "symbol_attribution": symbol_breakdown,
            "uos_score_cohorts": uos_cohorts,
        },
        "meta": {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/realtime")
async def get_realtime_pnl(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get real-time P&L from current positions and today's closed trades.
    This provides KPI values even when analytics tables aren't populated.
    """
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    # Get unrealized P&L from open positions
    open_positions_query = """
        SELECT
            COUNT(*) as position_count,
            COALESCE(SUM(funding_received - funding_paid), 0) as unrealized_funding,
            COALESCE(SUM(total_capital_deployed), 0) as capital_deployed
        FROM positions.active
        WHERE status = 'open'
    """
    open_result = await db.execute(text(open_positions_query))
    open_row = open_result.fetchone()

    # Get today's realized P&L from closed positions
    today_closed_query = """
        SELECT
            COUNT(*) as closed_count,
            COALESCE(SUM(realized_pnl_funding + realized_pnl_price - entry_costs_paid - exit_costs_paid), 0) as today_realized
        FROM positions.active
        WHERE status = 'closed'
        AND closed_at >= :today_start
    """
    today_result = await db.execute(text(today_closed_query), {"today_start": today_start})
    today_row = today_result.fetchone()

    # Get total realized P&L from all closed positions
    total_realized_query = """
        SELECT
            COALESCE(SUM(realized_pnl_funding + realized_pnl_price - entry_costs_paid - exit_costs_paid), 0) as total_realized
        FROM positions.active
        WHERE status = 'closed'
    """
    total_result = await db.execute(text(total_realized_query))
    total_row = total_result.fetchone()

    # Parse results
    active_positions = open_row[0] if open_row else 0
    unrealized_pnl = float(open_row[1]) if open_row else 0.0
    capital_deployed = float(open_row[2]) if open_row else 0.0

    today_closed = today_row[0] if today_row else 0
    today_pnl = float(today_row[1]) if today_row else 0.0

    total_pnl = float(total_row[0]) if total_row else 0.0

    # ROI calculation (return on deployed capital)
    roi = (total_pnl / capital_deployed * 100) if capital_deployed > 0 else 0.0

    return {
        "success": True,
        "data": {
            "total_pnl": total_pnl,
            "today_pnl": today_pnl,
            "unrealized_pnl": unrealized_pnl,
            "roi": roi,
            "active_positions": active_positions,
            "today_closed_trades": today_closed,
            "capital_deployed": capital_deployed,
        },
        "meta": {
            "timestamp": datetime.utcnow().isoformat(),
        },
    }
