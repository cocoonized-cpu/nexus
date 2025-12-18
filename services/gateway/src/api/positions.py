"""
Positions API endpoints.
"""

import httpx
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

# Funding aggregator service URL (internal Docker network)
FUNDING_AGGREGATOR_URL = "http://nexus-funding-aggregator:8002"

router = APIRouter()


class PositionLegResponse(BaseModel):
    """Response model for position leg."""

    id: UUID
    leg_type: str
    exchange: str
    symbol: str
    market_type: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    notional_value_usd: Decimal
    unrealized_pnl: Decimal
    funding_pnl: Decimal


class PositionResponse(BaseModel):
    """Response model for position data."""

    id: UUID
    opportunity_id: Optional[UUID]
    opportunity_type: str
    symbol: str
    base_asset: str
    status: str
    health_status: str
    total_capital_deployed: Decimal
    funding_received: Decimal
    funding_paid: Decimal
    net_funding_pnl: Decimal
    unrealized_pnl: Decimal
    return_pct: Decimal
    delta_exposure_pct: Decimal
    max_margin_utilization: Decimal
    opened_at: Optional[datetime]
    funding_periods_collected: int
    legs: list[PositionLegResponse] = Field(default_factory=list)


class PositionListResponse(BaseModel):
    """Response model for position list."""

    success: bool = True
    data: list[PositionResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class PositionDetailResponse(BaseModel):
    """Response model for position detail."""

    success: bool = True
    data: PositionResponse
    meta: dict[str, Any] = Field(default_factory=dict)


class ClosePositionRequest(BaseModel):
    """Request model for closing a position."""

    reason: str = "manual"


@router.get("", response_model=PositionListResponse)
async def list_positions(
    status: Optional[str] = Query(None, description="Filter by status"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    health: Optional[str] = Query(None, description="Filter by health status"),
    db: AsyncSession = Depends(get_db),
) -> PositionListResponse:
    """
    List all positions with optional filtering, including leg data.
    """
    from sqlalchemy import text

    query = """
        SELECT
            p.id, p.opportunity_id, p.opportunity_type, p.symbol, p.base_asset,
            p.status, p.health_status, p.total_capital_deployed,
            p.funding_received, p.funding_paid,
            p.net_delta, p.delta_exposure_pct, p.max_margin_utilization,
            p.opened_at, p.funding_periods_collected
        FROM positions.active p
        WHERE 1=1
    """
    params: dict[str, Any] = {}

    if status:
        query += " AND p.status = :status"
        params["status"] = status
    else:
        query += " AND p.status NOT IN ('closed', 'cancelled')"

    if symbol:
        query += " AND p.symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    if health:
        query += " AND p.health_status = :health"
        params["health"] = health

    query += " ORDER BY p.opened_at DESC"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    # Collect all position IDs for batch leg query
    position_ids = [str(row[0]) for row in rows]

    # Fetch all legs for these positions in a single query
    legs_by_position: dict[str, list[PositionLegResponse]] = {}
    if position_ids:
        legs_query = """
            SELECT
                l.id, l.position_id, l.leg_type, l.exchange, l.symbol,
                l.market_type, l.side, l.quantity, l.entry_price,
                l.current_price, l.notional_value_usd, l.unrealized_pnl,
                COALESCE(l.funding_pnl, 0) as funding_pnl
            FROM positions.legs l
            WHERE l.position_id = ANY(CAST(:position_ids AS uuid[]))
            ORDER BY l.position_id, l.leg_type
        """
        legs_result = await db.execute(
            text(legs_query),
            {"position_ids": position_ids},
        )
        legs_rows = legs_result.fetchall()

        for leg_row in legs_rows:
            pos_id = str(leg_row[1])
            if pos_id not in legs_by_position:
                legs_by_position[pos_id] = []

            legs_by_position[pos_id].append(
                PositionLegResponse(
                    id=leg_row[0],
                    leg_type=leg_row[2] or "unknown",
                    exchange=leg_row[3] or "",
                    symbol=leg_row[4] or "",
                    market_type=leg_row[5] or "perpetual",
                    side=leg_row[6] or "",
                    quantity=Decimal(str(leg_row[7] or 0)),
                    entry_price=Decimal(str(leg_row[8] or 0)),
                    current_price=Decimal(str(leg_row[9] or leg_row[8] or 0)),
                    notional_value_usd=Decimal(str(leg_row[10] or 0)),
                    unrealized_pnl=Decimal(str(leg_row[11] or 0)),
                    funding_pnl=Decimal(str(leg_row[12] or 0)),
                )
            )

    positions = []
    for row in rows:
        # Calculate derived fields
        funding_received = row[8] or Decimal("0")
        funding_paid = row[9] or Decimal("0")
        net_funding_pnl = funding_received - funding_paid
        capital = row[7] or Decimal("1")
        return_pct = (net_funding_pnl / capital * 100) if capital > 0 else Decimal("0")

        # Get legs for this position
        pos_id = str(row[0])
        position_legs = legs_by_position.get(pos_id, [])

        position = PositionResponse(
            id=row[0],
            opportunity_id=row[1],
            opportunity_type=row[2],
            symbol=row[3],
            base_asset=row[4],
            status=row[5],
            health_status=row[6],
            total_capital_deployed=row[7],
            funding_received=funding_received,
            funding_paid=funding_paid,
            net_funding_pnl=net_funding_pnl,
            unrealized_pnl=net_funding_pnl,  # Simplified for now
            return_pct=return_pct,
            delta_exposure_pct=row[11] or Decimal("0"),
            max_margin_utilization=row[12] or Decimal("0"),
            opened_at=row[13],
            funding_periods_collected=row[14] or 0,
            legs=position_legs,
        )
        positions.append(position)

    return PositionListResponse(
        data=positions,
        meta={
            "total": len(positions),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@router.get("/active", response_model=PositionListResponse)
async def list_active_positions(
    db: AsyncSession = Depends(get_db),
) -> PositionListResponse:
    """
    List only active positions.
    """
    return await list_positions(status="active", db=db)


# ============================================================================
# Exchange Positions API (synced from exchanges)
# Must be before /{position_id} to avoid route conflicts
# ============================================================================


class ExchangePositionResponse(BaseModel):
    """Response model for exchange position data."""

    id: UUID
    exchange: str
    symbol: str
    side: str
    size: Decimal
    notional_usd: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    leverage: Decimal
    liquidation_price: Optional[Decimal]
    margin_mode: str
    updated_at: Optional[datetime]


class ExchangePositionListResponse(BaseModel):
    """Response model for exchange position list."""

    success: bool = True
    data: list[ExchangePositionResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("/exchange", response_model=ExchangePositionListResponse)
async def list_exchange_positions(
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    db: AsyncSession = Depends(get_db),
) -> ExchangePositionListResponse:
    """
    List all positions synced from connected exchanges.

    These are the raw positions from each exchange, updated every 30 seconds.
    """
    from sqlalchemy import text

    query = """
        SELECT
            id, exchange, symbol, side, size, notional_usd, entry_price,
            mark_price, unrealized_pnl, leverage, liquidation_price,
            margin_mode, updated_at
        FROM positions.exchange_positions
        WHERE 1=1
    """
    params: dict[str, Any] = {}

    if exchange:
        query += " AND exchange = :exchange"
        params["exchange"] = exchange

    if symbol:
        query += " AND symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    query += " ORDER BY notional_usd DESC"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    positions = [
        ExchangePositionResponse(
            id=row[0],
            exchange=row[1],
            symbol=row[2],
            side=row[3],
            size=row[4],
            notional_usd=row[5],
            entry_price=row[6],
            mark_price=row[7],
            unrealized_pnl=row[8] or Decimal("0"),
            leverage=row[9] or Decimal("1"),
            liquidation_price=row[10],
            margin_mode=row[11] or "cross",
            updated_at=row[12],
        )
        for row in rows
    ]

    # Calculate totals
    total_notional = sum(p.notional_usd for p in positions)
    total_pnl = sum(p.unrealized_pnl for p in positions)

    return ExchangePositionListResponse(
        data=positions,
        meta={
            "total": len(positions),
            "total_notional_usd": float(total_notional),
            "total_unrealized_pnl": float(total_pnl),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@router.post("/exchange/sync")
async def sync_exchange_positions(
    request: Request,
) -> dict[str, Any]:
    """
    Trigger an immediate sync of positions from all exchanges.
    """
    # Get the sync service from app state
    sync_service = getattr(request.app.state, "position_sync", None)
    if not sync_service:
        raise HTTPException(
            status_code=503,
            detail="Position sync service not available",
        )

    results = await sync_service.sync_now()

    return {
        "success": True,
        "message": "Position sync completed",
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Trade/Order History API
# ============================================================================


class TradeHistoryResponse(BaseModel):
    """Response model for trade/order history."""

    id: UUID
    exchange_order_id: str
    exchange: str
    symbol: str
    side: str
    order_type: str
    price: Decimal
    amount: Decimal
    filled: Decimal
    fee: Optional[Decimal]
    fee_currency: Optional[str]
    status: str
    executed_at: Optional[datetime]
    created_at: Optional[datetime]


class TradeHistoryListResponse(BaseModel):
    """Response model for trade history list."""

    success: bool = True
    data: list[TradeHistoryResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("/trades", response_model=TradeHistoryListResponse)
async def list_trade_history(
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    side: Optional[str] = Query(None, description="Filter by side (buy/sell)"),
    limit: int = Query(100, description="Number of trades to return", le=500),
    db: AsyncSession = Depends(get_db),
) -> TradeHistoryListResponse:
    """
    List trade/order history synced from connected exchanges.

    Returns recent trades and filled orders, updated every 30 seconds.
    """
    from sqlalchemy import text

    query = """
        SELECT
            id, exchange_order_id, exchange, symbol, side, order_type,
            price, amount, filled, fee, fee_currency, status,
            executed_at, created_at
        FROM positions.order_history
        WHERE 1=1
    """
    params: dict[str, Any] = {"limit": limit}

    if exchange:
        query += " AND exchange = :exchange"
        params["exchange"] = exchange

    if symbol:
        query += " AND symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    if side:
        query += " AND side = :side"
        params["side"] = side

    query += " ORDER BY executed_at DESC NULLS LAST, created_at DESC LIMIT :limit"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    trades = [
        TradeHistoryResponse(
            id=row[0],
            exchange_order_id=row[1] or "",
            exchange=row[2],
            symbol=row[3],
            side=row[4],
            order_type=row[5] or "market",
            price=row[6] or Decimal("0"),
            amount=row[7] or Decimal("0"),
            filled=row[8] or Decimal("0"),
            fee=row[9],
            fee_currency=row[10],
            status=row[11] or "closed",
            executed_at=row[12],
            created_at=row[13],
        )
        for row in rows
    ]

    # Calculate totals
    total_volume = sum(float(t.filled * t.price) for t in trades)
    total_fees = sum(float(t.fee or 0) for t in trades)

    return TradeHistoryListResponse(
        data=trades,
        meta={
            "total": len(trades),
            "total_volume_usd": total_volume,
            "total_fees": total_fees,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# ============================================================================
# Spread History API for TradingView-like charting
# ============================================================================


class SpreadSnapshotResponse(BaseModel):
    """Response model for spread snapshot."""

    timestamp: datetime
    spread: float
    long_rate: Optional[float]
    short_rate: Optional[float]
    price: Optional[float]


class SpreadHistoryResponse(BaseModel):
    """Response model for position spread history."""

    success: bool = True
    position_id: str
    symbol: str
    initial_spread: Optional[float]
    current_spread: Optional[float]
    spread_drawdown_pct: Optional[float]
    spread_trend: str
    snapshots: list[SpreadSnapshotResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("/{position_id}/spread-history", response_model=SpreadHistoryResponse)
async def get_position_spread_history(
    position_id: UUID,
    hours: int = Query(24, le=168, description="Hours of history (max 7 days)"),
    db: AsyncSession = Depends(get_db),
) -> SpreadHistoryResponse:
    """
    Get spread history for TradingView-style charting.

    Returns time-series spread data with individual funding rates for visualization.
    If no spread snapshots exist, generates data from funding rate history.
    """
    from sqlalchemy import text

    # Get position info with leg exchanges
    pos_query = """
        SELECT
            p.symbol, p.initial_spread, p.current_spread,
            p.spread_drawdown_pct, p.spread_trend,
            (SELECT exchange FROM positions.legs WHERE position_id = p.id AND side = 'long' LIMIT 1) as long_exchange,
            (SELECT exchange FROM positions.legs WHERE position_id = p.id AND side = 'short' LIMIT 1) as short_exchange
        FROM positions.active p WHERE p.id = :id
    """
    pos_result = await db.execute(text(pos_query), {"id": str(position_id)})
    pos_row = pos_result.fetchone()

    if not pos_row:
        raise HTTPException(status_code=404, detail="Position not found")

    symbol = pos_row[0]
    initial_spread = pos_row[1]
    current_spread = pos_row[2]
    spread_drawdown_pct = pos_row[3]
    spread_trend = pos_row[4] or "stable"
    long_exchange = pos_row[5]
    short_exchange = pos_row[6]

    # Get snapshots within time range
    snap_query = f"""
        SELECT timestamp, spread, long_rate, short_rate, price
        FROM positions.spread_snapshots
        WHERE position_id = :pos_id
          AND timestamp >= NOW() - INTERVAL '{hours} hours'
        ORDER BY timestamp ASC
    """
    snap_result = await db.execute(text(snap_query), {"pos_id": str(position_id)})
    snap_rows = snap_result.fetchall()

    snapshots = [
        SpreadSnapshotResponse(
            timestamp=row[0],
            spread=float(row[1]),
            long_rate=float(row[2]) if row[2] else None,
            short_rate=float(row[3]) if row[3] else None,
            price=float(row[4]) if row[4] else None,
        )
        for row in snap_rows
    ]

    # Track data source
    data_source = "spread_snapshots" if snap_rows else None

    # If no snapshots exist, generate from spread history or funding rate history
    if not snapshots and long_exchange and short_exchange:
        # Extract base asset for querying (e.g., "DEEP/USDT:USDT" -> "DEEP")
        base_asset = symbol.split("/")[0] if "/" in symbol else symbol

        # Normalize exchange names (positions.legs uses "bybit_futures", funding.rates may use "bybit" or "bybit_futures")
        # Try multiple formats to maximize match chances
        def get_exchange_variants(exchange: str) -> list[str]:
            """Generate possible exchange name variants for matching."""
            variants = [exchange]
            # Add lowercase version
            variants.append(exchange.lower())
            # Remove _futures suffix
            if "_futures" in exchange.lower():
                base = exchange.lower().replace("_futures", "")
                variants.append(base)
            # Add without underscore
            variants.append(exchange.replace("_", ""))
            return list(set(variants))

        long_variants = get_exchange_variants(long_exchange)
        short_variants = get_exchange_variants(short_exchange)

        # FIRST: Try to get data from funding.spread_history (ML training data)
        # This table is continuously populated with spread snapshots for all coins
        # Note: spread_history stores exchanges based on which has lower/higher rate at recording time,
        # not based on position legs. So we need to match either direction.
        all_exchange_variants = [v.lower() for v in long_variants + short_variants]

        spread_history_query = f"""
            SELECT timestamp, long_exchange, short_exchange, long_rate, short_rate, spread
            FROM funding.spread_history
            WHERE symbol = :base_asset
              AND (
                  (LOWER(long_exchange) = ANY(:all_variants) AND LOWER(short_exchange) = ANY(:all_variants))
              )
              AND timestamp >= NOW() - INTERVAL '{hours} hours'
            ORDER BY timestamp ASC
        """

        spread_history_result = await db.execute(
            text(spread_history_query),
            {
                "base_asset": base_asset,
                "all_variants": all_exchange_variants,
            },
        )
        spread_history_rows = spread_history_result.fetchall()

        if spread_history_rows:
            # Use spread history data
            data_source = "spread_history"
            # Map rates to position's long/short based on exchange matching
            for row in spread_history_rows:
                ts, hist_long_ex, hist_short_ex, hist_long_rate, hist_short_rate, spread_val = row

                # Determine which rate corresponds to position's long/short leg
                hist_long_ex_lower = hist_long_ex.lower()
                hist_short_ex_lower = hist_short_ex.lower()

                # Check if spread_history's long matches position's long
                pos_long_rate = None
                pos_short_rate = None

                if hist_long_ex_lower in [v.lower() for v in long_variants]:
                    # spread_history long = position long
                    pos_long_rate = float(hist_long_rate) if hist_long_rate else None
                    pos_short_rate = float(hist_short_rate) if hist_short_rate else None
                    # Spread from position's perspective: short_rate - long_rate
                    pos_spread = float(hist_short_rate) - float(hist_long_rate) if hist_short_rate and hist_long_rate else float(spread_val)
                elif hist_short_ex_lower in [v.lower() for v in long_variants]:
                    # spread_history short = position long (reversed)
                    pos_long_rate = float(hist_short_rate) if hist_short_rate else None
                    pos_short_rate = float(hist_long_rate) if hist_long_rate else None
                    # Spread from position's perspective (reversed)
                    pos_spread = float(hist_long_rate) - float(hist_short_rate) if hist_short_rate and hist_long_rate else -float(spread_val)
                else:
                    # Fallback - use as-is
                    pos_long_rate = float(hist_long_rate) if hist_long_rate else None
                    pos_short_rate = float(hist_short_rate) if hist_short_rate else None
                    pos_spread = float(spread_val)

                snapshots.append(
                    SpreadSnapshotResponse(
                        timestamp=ts,
                        spread=pos_spread,
                        long_rate=pos_long_rate,
                        short_rate=pos_short_rate,
                        price=None,
                    )
                )

        # SECOND: If no spread history, try funding.rates table
        if not snapshots:
            # Query funding rate history for both exchanges (using ANY for multiple exchange name variants)
            funding_query = f"""
                WITH long_rates AS (
                    SELECT timestamp, rate, exchange
                    FROM funding.rates
                    WHERE LOWER(exchange) = ANY(:long_variants)
                      AND (symbol ILIKE :symbol_pattern OR ticker = :base_asset)
                      AND timestamp >= NOW() - INTERVAL '{hours} hours'
                ),
                short_rates AS (
                    SELECT timestamp, rate, exchange
                    FROM funding.rates
                    WHERE LOWER(exchange) = ANY(:short_variants)
                      AND (symbol ILIKE :symbol_pattern OR ticker = :base_asset)
                      AND timestamp >= NOW() - INTERVAL '{hours} hours'
                ),
                combined AS (
                    SELECT
                        COALESCE(l.timestamp, s.timestamp) as timestamp,
                        l.rate as long_rate,
                        s.rate as short_rate
                    FROM long_rates l
                    FULL OUTER JOIN short_rates s ON
                        date_trunc('hour', l.timestamp) = date_trunc('hour', s.timestamp)
                    WHERE l.rate IS NOT NULL OR s.rate IS NOT NULL
                )
                SELECT timestamp, long_rate, short_rate
                FROM combined
                ORDER BY timestamp ASC
            """

            funding_result = await db.execute(
                text(funding_query),
                {
                    "long_variants": [v.lower() for v in long_variants],
                    "short_variants": [v.lower() for v in short_variants],
                    "symbol_pattern": f"%{base_asset}%",
                    "base_asset": base_asset,
                },
            )
            funding_rows = funding_result.fetchall()

            # Generate spread snapshots from funding rate data
            for row in funding_rows:
                ts, long_rate, short_rate = row
                if long_rate is not None and short_rate is not None:
                    spread = float(short_rate) - float(long_rate)
                    snapshots.append(
                        SpreadSnapshotResponse(
                            timestamp=ts,
                            spread=spread,
                            long_rate=float(long_rate) if long_rate else None,
                            short_rate=float(short_rate) if short_rate else None,
                            price=None,  # Price not available from funding rates
                        )
                    )

        # THIRD: If still no data, try to get current funding rates and create a single point
        if not snapshots:
            current_rates_query = """
                WITH latest_rates AS (
                    SELECT DISTINCT ON (exchange)
                        exchange, rate, timestamp
                    FROM funding.rates
                    WHERE LOWER(exchange) = ANY(:all_variants)
                      AND (symbol ILIKE :symbol_pattern OR ticker = :base_asset)
                    ORDER BY exchange, timestamp DESC
                )
                SELECT exchange, rate, timestamp FROM latest_rates
            """
            all_variants = [v.lower() for v in long_variants + short_variants]
            current_result = await db.execute(
                text(current_rates_query),
                {
                    "all_variants": all_variants,
                    "symbol_pattern": f"%{base_asset}%",
                    "base_asset": base_asset,
                },
            )
            current_rows = current_result.fetchall()

            # Map results back to exchange variants
            rates_by_exchange = {}
            for row in current_rows:
                ex_name = row[0].lower()
                rates_by_exchange[ex_name] = (float(row[1]), row[2])

            # Find matching long and short rates
            long_rate_data = None
            short_rate_data = None
            for variant in long_variants:
                if variant.lower() in rates_by_exchange:
                    long_rate_data = rates_by_exchange[variant.lower()]
                    break
            for variant in short_variants:
                if variant.lower() in rates_by_exchange:
                    short_rate_data = rates_by_exchange[variant.lower()]
                    break

            if long_rate_data and short_rate_data:
                long_rate, long_ts = long_rate_data
                short_rate, short_ts = short_rate_data
                spread = short_rate - long_rate

                # Update position spread values if not set
                if current_spread is None:
                    current_spread = Decimal(str(spread))
                if initial_spread is None:
                    initial_spread = Decimal(str(spread))

                snapshots.append(
                    SpreadSnapshotResponse(
                        timestamp=max(long_ts, short_ts),
                        spread=spread,
                        long_rate=long_rate,
                        short_rate=short_rate,
                        price=None,
                    )
                )

        # If still no data, try to fetch live data from funding-aggregator
        if not snapshots:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{FUNDING_AGGREGATOR_URL}/funding/rates")
                    if response.status_code == 200:
                        rates_data = response.json()
                        rates_list = rates_data.get("data", [])

                        # Find rates for this symbol on both exchanges
                        long_rate_live = None
                        short_rate_live = None

                        for rate in rates_list:
                            rate_symbol = rate.get("symbol", "")
                            rate_exchange = rate.get("exchange", "").lower()

                            # Check if this rate matches our symbol
                            if base_asset.upper() not in rate_symbol.upper():
                                continue

                            # Check if exchange matches
                            if rate_exchange in [v.lower() for v in long_variants]:
                                long_rate_live = rate.get("funding_rate", 0)
                            elif rate_exchange in [v.lower() for v in short_variants]:
                                short_rate_live = rate.get("funding_rate", 0)

                        if long_rate_live is not None and short_rate_live is not None:
                            spread = float(short_rate_live) - float(long_rate_live)

                            if current_spread is None:
                                current_spread = Decimal(str(spread))
                            if initial_spread is None:
                                initial_spread = Decimal(str(spread))

                            snapshots.append(
                                SpreadSnapshotResponse(
                                    timestamp=datetime.utcnow(),
                                    spread=spread,
                                    long_rate=float(long_rate_live),
                                    short_rate=float(short_rate_live),
                                    price=None,
                                )
                            )
            except Exception as e:
                # Log but don't fail - live data is optional
                pass

    # Calculate spread drawdown if we have data
    if snapshots and initial_spread is not None and float(initial_spread) > 0:
        current = snapshots[-1].spread if snapshots else 0
        spread_drawdown_pct = (float(initial_spread) - current) / float(initial_spread) * 100

    # Set fallback data source if not already set
    if data_source is None:
        data_source = "live_aggregator"

    return SpreadHistoryResponse(
        position_id=str(position_id),
        symbol=symbol,
        initial_spread=float(initial_spread) if initial_spread else None,
        current_spread=float(current_spread) if current_spread else None,
        spread_drawdown_pct=float(spread_drawdown_pct) if spread_drawdown_pct else None,
        spread_trend=spread_trend,
        snapshots=snapshots,
        meta={
            "hours_requested": hours,
            "snapshot_count": len(snapshots),
            "data_source": data_source,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# ============================================================================
# Position Interactions API (bot decision timeline)
# ============================================================================


class PositionInteractionResponse(BaseModel):
    """Response model for position interaction."""

    id: UUID
    position_id: UUID
    opportunity_id: Optional[UUID]
    symbol: str
    timestamp: datetime
    interaction_type: str
    worker_service: str
    decision: Optional[str]
    narrative: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[UUID]


class PositionInteractionListResponse(BaseModel):
    """Response model for position interaction list."""

    success: bool = True
    data: list[PositionInteractionResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("/{position_id}/interactions", response_model=PositionInteractionListResponse)
async def get_position_interactions(
    position_id: UUID,
    interaction_type: Optional[str] = Query(None, description="Filter by interaction type"),
    decision: Optional[str] = Query(None, description="Filter by decision"),
    limit: int = Query(100, description="Number of interactions to return", le=500),
    offset: int = Query(0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
) -> PositionInteractionListResponse:
    """
    Get the interaction timeline for a position.

    This shows every decision the bot made about this position, including:
    - Position opened/closed events
    - Health checks and health changes
    - Funding collection events
    - Rebalancing decisions
    - Exit triggers

    Each interaction includes a human-readable narrative explaining what happened.
    """
    from sqlalchemy import text

    # First verify the position exists
    pos_check = await db.execute(
        text("SELECT id, symbol FROM positions.active WHERE id = :id"),
        {"id": str(position_id)},
    )
    pos_row = pos_check.fetchone()

    if not pos_row:
        raise HTTPException(status_code=404, detail="Position not found")

    # Build query for interactions
    query = """
        SELECT
            id, position_id, opportunity_id, symbol, timestamp,
            interaction_type, worker_service, decision, narrative,
            metrics, correlation_id
        FROM positions.interactions
        WHERE position_id = :position_id
    """
    params: dict[str, Any] = {
        "position_id": str(position_id),
        "limit": limit,
        "offset": offset,
    }

    if interaction_type:
        query += " AND interaction_type = :interaction_type"
        params["interaction_type"] = interaction_type

    if decision:
        query += " AND decision = :decision"
        params["decision"] = decision

    query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    interactions = []
    for row in rows:
        # Parse metrics JSONB
        metrics_data = row[9] if row[9] else {}
        if isinstance(metrics_data, str):
            try:
                import json
                metrics_data = json.loads(metrics_data)
            except Exception:
                metrics_data = {}

        interactions.append(
            PositionInteractionResponse(
                id=row[0],
                position_id=row[1],
                opportunity_id=row[2],
                symbol=row[3],
                timestamp=row[4],
                interaction_type=row[5],
                worker_service=row[6],
                decision=row[7],
                narrative=row[8],
                metrics=metrics_data,
                correlation_id=row[10],
            )
        )

    # Get total count for pagination
    count_query = """
        SELECT COUNT(*) FROM positions.interactions WHERE position_id = :position_id
    """
    if interaction_type:
        count_query += " AND interaction_type = :interaction_type"
    if decision:
        count_query += " AND decision = :decision"

    count_result = await db.execute(text(count_query), params)
    total_count = count_result.scalar() or 0

    return PositionInteractionListResponse(
        data=interactions,
        meta={
            "position_id": str(position_id),
            "symbol": pos_row[1],
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(interactions)) < total_count,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@router.get("/{position_id}", response_model=PositionDetailResponse)
async def get_position(
    position_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PositionDetailResponse:
    """
    Get detailed information about a specific position including legs.
    """
    from sqlalchemy import text

    # Get position
    query = """
        SELECT
            p.id, p.opportunity_id, p.opportunity_type, p.symbol, p.base_asset,
            p.status, p.health_status, p.total_capital_deployed,
            p.funding_received, p.funding_paid,
            p.net_delta, p.delta_exposure_pct, p.max_margin_utilization,
            p.opened_at, p.funding_periods_collected
        FROM positions.active p
        WHERE p.id = :id
    """

    result = await db.execute(text(query), {"id": str(position_id)})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Position not found")

    # Get legs
    legs_query = """
        SELECT
            id, leg_type, exchange, symbol, market_type, side,
            quantity, entry_price, current_price, notional_value_usd,
            unrealized_pnl, funding_pnl
        FROM positions.legs
        WHERE position_id = :position_id
    """

    legs_result = await db.execute(text(legs_query), {"position_id": str(position_id)})
    legs_rows = legs_result.fetchall()

    legs = [
        PositionLegResponse(
            id=leg[0],
            leg_type=leg[1],
            exchange=leg[2],
            symbol=leg[3],
            market_type=leg[4],
            side=leg[5],
            quantity=leg[6],
            entry_price=leg[7],
            current_price=leg[8],
            notional_value_usd=leg[9],
            unrealized_pnl=leg[10] or Decimal("0"),
            funding_pnl=leg[11] or Decimal("0"),
        )
        for leg in legs_rows
    ]

    # Calculate derived fields
    funding_received = row[8] or Decimal("0")
    funding_paid = row[9] or Decimal("0")
    net_funding_pnl = funding_received - funding_paid
    capital = row[7] or Decimal("1")
    return_pct = (net_funding_pnl / capital * 100) if capital > 0 else Decimal("0")

    position = PositionResponse(
        id=row[0],
        opportunity_id=row[1],
        opportunity_type=row[2],
        symbol=row[3],
        base_asset=row[4],
        status=row[5],
        health_status=row[6],
        total_capital_deployed=row[7],
        funding_received=funding_received,
        funding_paid=funding_paid,
        net_funding_pnl=net_funding_pnl,
        unrealized_pnl=net_funding_pnl,
        return_pct=return_pct,
        delta_exposure_pct=row[11] or Decimal("0"),
        max_margin_utilization=row[12] or Decimal("0"),
        opened_at=row[13],
        funding_periods_collected=row[14] or 0,
        legs=legs,
    )

    return PositionDetailResponse(
        data=position,
        meta={"timestamp": datetime.utcnow().isoformat()},
    )


@router.post("/{position_id}/close")
async def close_position(
    position_id: UUID,
    request: ClosePositionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Close a position by closing both legs on their respective exchanges.

    This places market orders to close both the primary and hedge positions.
    """
    from sqlalchemy import text
    from uuid import uuid4
    from shared.utils.exchange_client import ExchangeClient, get_exchange_credentials

    # Exchange name to slug mapping
    EXCHANGE_SLUG_MAP = {
        "binance": "binance_futures",
        "bybit": "bybit_futures",
        "okx": "okex_futures",
        "gate": "gate_futures",
        "kucoin": "kucoin_futures",
        "bitget": "bitget_futures",
        "mexc": "mexc_futures",
        "bingx": "bingx_futures",
        "hyperliquid": "hyperliquid_futures",
    }

    # Get position with legs
    query = """
        SELECT
            p.id, p.symbol, p.status, p.total_capital_deployed,
            p.funding_received, p.funding_paid
        FROM positions.active p
        WHERE p.id = :id
    """
    result = await db.execute(text(query), {"id": str(position_id)})
    pos_row = result.fetchone()

    if not pos_row:
        raise HTTPException(status_code=404, detail="Position not found")

    if pos_row[2] not in ("active", "opening"):
        raise HTTPException(
            status_code=400, detail=f"Cannot close position in {pos_row[2]} status"
        )

    symbol = pos_row[1]
    capital = pos_row[3]
    funding_received = pos_row[4] or Decimal("0")
    funding_paid = pos_row[5] or Decimal("0")

    # Get legs
    legs_query = """
        SELECT id, leg_type, exchange, side, quantity, entry_price
        FROM positions.legs
        WHERE position_id = :position_id
    """
    legs_result = await db.execute(text(legs_query), {"position_id": str(position_id)})
    legs = legs_result.fetchall()

    if not legs:
        raise HTTPException(status_code=400, detail="Position has no legs to close")

    # Update status to closing
    await db.execute(
        text("UPDATE positions.active SET status = 'closing', exit_reason = :reason, updated_at = NOW() WHERE id = :id"),
        {"id": str(position_id), "reason": request.reason}
    )
    await db.commit()

    close_results = {"legs": [], "errors": []}
    total_exit_value = Decimal("0")
    total_pnl = Decimal("0")

    # Close each leg
    for leg in legs:
        leg_id, leg_type, exchange, side, quantity, entry_price = leg
        exchange_slug = EXCHANGE_SLUG_MAP.get(exchange.lower(), f"{exchange.lower()}_futures")

        try:
            # Get exchange config
            ex_query = "SELECT slug, api_type FROM config.exchanges WHERE slug = :slug"
            ex_result = await db.execute(text(ex_query), {"slug": exchange_slug})
            ex_row = ex_result.fetchone()

            if not ex_row:
                close_results["errors"].append(f"Exchange {exchange} not configured")
                continue

            # Get credentials
            creds = await get_exchange_credentials(db, exchange_slug)
            if not creds:
                close_results["errors"].append(f"No credentials for {exchange}")
                continue

            # Create client and connect
            client = ExchangeClient(
                slug=exchange_slug,
                credentials=creds,
                api_type=ex_row[1],
                sandbox=False,
            )

            if not await client.connect():
                close_results["errors"].append(f"Failed to connect to {exchange}")
                continue

            try:
                # Format symbol for exchange
                formatted_symbol = f"{symbol}/USDT:USDT" if ex_row[1] == "ccxt" else symbol

                # Close order - opposite side of the current position
                close_side = "sell" if side == "long" else "buy"

                close_order = await client.place_order(
                    symbol=formatted_symbol,
                    side=close_side,
                    size=float(quantity),
                    order_type="market",
                    reduce_only=True,
                )

                # Check if order was successful
                if not close_order.get("success", False):
                    error_msg = close_order.get("error", "Order failed")
                    close_results["errors"].append(f"Failed to close {leg_type} on {exchange}: {error_msg}")
                    continue

                # Get exit price (from order or fetch ticker)
                exit_price = close_order.get("price")
                if not exit_price:
                    try:
                        ticker = await client._client.fetch_ticker(formatted_symbol)
                        exit_price = float(ticker.get("last", 0))
                    except Exception:
                        exit_price = float(entry_price)  # Fallback to entry price

                exit_value = Decimal(str(float(quantity) * exit_price))
                leg_pnl = exit_value - (Decimal(str(quantity)) * entry_price)
                if side == "short":
                    leg_pnl = -leg_pnl  # Short profit is inverse

                total_exit_value += exit_value
                total_pnl += leg_pnl

                close_results["legs"].append({
                    "leg_type": leg_type,
                    "exchange": exchange,
                    "side": side,
                    "quantity": float(quantity),
                    "entry_price": float(entry_price),
                    "exit_price": exit_price,
                    "pnl": float(leg_pnl),
                    "order_id": close_order.get("order_id"),
                    "success": True,
                })

                # Update leg with exit info - use separate try to prevent transaction issues
                try:
                    order_ids_json = json.dumps([close_order.get("order_id", "")])
                    await db.execute(
                        text("""
                            UPDATE positions.legs
                            SET avg_exit_price = :exit_price, exit_timestamp = NOW(),
                                exit_order_ids = CAST(:order_ids AS jsonb), realized_pnl = :pnl
                            WHERE id = :id
                        """),
                        {
                            "id": str(leg_id),
                            "exit_price": exit_price,
                            "order_ids": order_ids_json,
                            "pnl": float(leg_pnl),
                        }
                    )
                    await db.commit()
                except Exception as db_err:
                    await db.rollback()
                    close_results["errors"].append(f"DB update failed for {leg_type}: {str(db_err)}")

            finally:
                await client.disconnect()

        except Exception as e:
            await db.rollback()  # Rollback any failed transaction
            close_results["errors"].append(f"Error closing {leg_type} leg on {exchange}: {str(e)}")

    # Calculate final P&L including funding
    net_funding = funding_received - funding_paid
    realized_pnl = total_pnl + net_funding

    # Determine final status based on results
    legs_closed = len(close_results["legs"])
    total_legs = len(legs)
    final_status = "closed" if legs_closed == total_legs else "partially_closed" if legs_closed > 0 else "close_failed"

    # Update position status
    try:
        await db.execute(
            text("""
                UPDATE positions.active
                SET status = :status,
                    closed_at = NOW(),
                    realized_pnl_funding = :funding_pnl,
                    realized_pnl_price = :trade_pnl,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": str(position_id),
                "funding_pnl": float(net_funding),
                "trade_pnl": float(total_pnl),
                "status": final_status
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        close_results["errors"].append(f"Failed to update position status: {str(e)}")

    # Log the close event
    try:
        audit_query = """
            INSERT INTO audit.actions (actor, action_type, resource_type, resource_id, details)
            VALUES ('user', 'position_closed', 'position', :id, :details)
        """
        await db.execute(text(audit_query), {
            "id": str(position_id),
            "details": f'{{"symbol": "{symbol}", "realized_pnl": {float(realized_pnl)}, "reason": "{request.reason}", "legs_closed": {legs_closed}, "status": "{final_status}"}}'
        })
        await db.commit()
    except Exception:
        await db.rollback()  # Non-critical, continue

    return {
        "success": len(close_results["errors"]) == 0,
        "message": "Position closed" if not close_results["errors"] else "Position partially closed",
        "position_id": str(position_id),
        "symbol": symbol,
        "realized_pnl": float(realized_pnl),
        "funding_pnl": float(net_funding),
        "trade_pnl": float(total_pnl),
        "legs": close_results["legs"],
        "errors": close_results["errors"],
        "timestamp": datetime.utcnow().isoformat(),
    }
