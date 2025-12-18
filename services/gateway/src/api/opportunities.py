"""
Opportunities API endpoints.
"""

import httpx
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

from shared.models.opportunity import (OpportunityConfidence,
                                       OpportunityStatus, OpportunityType)

router = APIRouter()

# Opportunity detector service URL (internal Docker network)
OPPORTUNITY_DETECTOR_URL = "http://nexus-opportunity-detector:8003"


class OpportunityResponse(BaseModel):
    """Response model for opportunity data."""

    id: UUID
    opportunity_type: str
    symbol: str
    base_asset: str
    status: str
    primary_exchange: str
    primary_side: str
    primary_rate: Decimal
    hedge_exchange: str
    hedge_side: str
    hedge_rate: Decimal
    gross_funding_rate: Decimal
    net_apr: Decimal
    uos_score: int
    confidence: str
    recommended_size_usd: Decimal
    detected_at: datetime
    expires_at: datetime


class OpportunityListResponse(BaseModel):
    """Response model for opportunity list."""

    success: bool = True
    data: list[OpportunityResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class OpportunityDetailResponse(BaseModel):
    """Response model for opportunity detail."""

    success: bool = True
    data: OpportunityResponse
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    status: Optional[str] = Query(None, description="Filter by status"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    min_score: Optional[int] = Query(
        None, ge=0, le=100, description="Minimum UOS score"
    ),
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
    sort_by: str = Query("uos_score", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
) -> OpportunityListResponse:
    """
    List detected opportunities with filtering and sorting.
    """
    # Build query
    query = """
        SELECT
            id, opportunity_type, symbol, base_asset, status,
            primary_exchange, primary_side, primary_rate,
            hedge_exchange, hedge_side, hedge_rate,
            gross_funding_rate, net_apr, uos_score, confidence,
            recommended_size_usd, detected_at, expires_at
        FROM opportunities.detected
        WHERE expires_at > NOW()
    """
    params: dict[str, Any] = {}

    if status:
        query += " AND status = :status"
        params["status"] = status

    if symbol:
        query += " AND symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    if min_score is not None:
        query += " AND uos_score >= :min_score"
        params["min_score"] = min_score

    if exchange:
        query += " AND (primary_exchange = :exchange OR hedge_exchange = :exchange)"
        params["exchange"] = exchange

    # Add sorting
    sort_column = (
        sort_by
        if sort_by in ["uos_score", "net_apr", "detected_at", "gross_funding_rate"]
        else "uos_score"
    )
    sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
    query += f" ORDER BY {sort_column} {sort_dir}"

    # Add pagination
    query += " LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    from sqlalchemy import text

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    # Get total count
    count_query = """
        SELECT COUNT(*) FROM opportunities.detected WHERE expires_at > NOW()
    """
    count_result = await db.execute(text(count_query))
    total = count_result.scalar()

    opportunities = [
        OpportunityResponse(
            id=row[0],
            opportunity_type=row[1],
            symbol=row[2],
            base_asset=row[3],
            status=row[4],
            primary_exchange=row[5],
            primary_side=row[6],
            primary_rate=row[7],
            hedge_exchange=row[8],
            hedge_side=row[9],
            hedge_rate=row[10],
            gross_funding_rate=row[11],
            net_apr=row[12],
            uos_score=row[13],
            confidence=row[14],
            recommended_size_usd=row[15],
            detected_at=row[16],
            expires_at=row[17],
        )
        for row in rows
    ]

    return OpportunityListResponse(
        data=opportunities,
        meta={
            "total": total,
            "limit": limit,
            "offset": offset,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@router.get("/live", response_model=dict)
async def get_live_opportunities(
    min_score: int = Query(0, ge=0, le=100, description="Minimum UOS score"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
) -> dict[str, Any]:
    """
    Get live opportunities directly from the opportunity-detector service.
    This returns real-time in-memory opportunities, not persisted data.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"min_score": min_score, "limit": limit}
            if symbol:
                params["symbol"] = symbol

            response = await client.get(
                f"{OPPORTUNITY_DETECTOR_URL}/opportunities/",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Failed to connect to opportunity detector: {str(e)}",
            "data": [],
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(
    opportunity_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> OpportunityDetailResponse:
    """
    Get detailed information about a specific opportunity.
    """
    from sqlalchemy import text

    query = """
        SELECT
            id, opportunity_type, symbol, base_asset, status,
            primary_exchange, primary_side, primary_rate,
            hedge_exchange, hedge_side, hedge_rate,
            gross_funding_rate, net_apr, uos_score, confidence,
            recommended_size_usd, detected_at, expires_at
        FROM opportunities.detected
        WHERE id = :id
    """

    result = await db.execute(text(query), {"id": str(opportunity_id)})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opportunity = OpportunityResponse(
        id=row[0],
        opportunity_type=row[1],
        symbol=row[2],
        base_asset=row[3],
        status=row[4],
        primary_exchange=row[5],
        primary_side=row[6],
        primary_rate=row[7],
        hedge_exchange=row[8],
        hedge_side=row[9],
        hedge_rate=row[10],
        gross_funding_rate=row[11],
        net_apr=row[12],
        uos_score=row[13],
        confidence=row[14],
        recommended_size_usd=row[15],
        detected_at=row[16],
        expires_at=row[17],
    )

    return OpportunityDetailResponse(
        data=opportunity,
        meta={"timestamp": datetime.utcnow().isoformat()},
    )


@router.get("/top/{count}")
async def get_top_opportunities(
    count: int = 10,
    db: AsyncSession = Depends(get_db),
) -> OpportunityListResponse:
    """
    Get the top N opportunities by UOS score.
    """
    from sqlalchemy import text

    query = """
        SELECT
            id, opportunity_type, symbol, base_asset, status,
            primary_exchange, primary_side, primary_rate,
            hedge_exchange, hedge_side, hedge_rate,
            gross_funding_rate, net_apr, uos_score, confidence,
            recommended_size_usd, detected_at, expires_at
        FROM opportunities.detected
        WHERE expires_at > NOW()
          AND status IN ('validated', 'scored')
        ORDER BY uos_score DESC
        LIMIT :count
    """

    result = await db.execute(text(query), {"count": min(count, 50)})
    rows = result.fetchall()

    opportunities = [
        OpportunityResponse(
            id=row[0],
            opportunity_type=row[1],
            symbol=row[2],
            base_asset=row[3],
            status=row[4],
            primary_exchange=row[5],
            primary_side=row[6],
            primary_rate=row[7],
            hedge_exchange=row[8],
            hedge_side=row[9],
            hedge_rate=row[10],
            gross_funding_rate=row[11],
            net_apr=row[12],
            uos_score=row[13],
            confidence=row[14],
            recommended_size_usd=row[15],
            detected_at=row[16],
            expires_at=row[17],
        )
        for row in rows
    ]

    return OpportunityListResponse(
        data=opportunities,
        meta={"timestamp": datetime.utcnow().isoformat()},
    )


class ExecuteOpportunityRequest(BaseModel):
    """Request model for executing an opportunity."""

    capital_usd: Optional[Decimal] = Field(
        None, description="Capital to allocate (uses recommended if not specified)"
    )
    leverage: Optional[int] = Field(
        default=3, ge=1, le=20, description="Leverage to use (default: 3x)"
    )


@router.post("/{opportunity_id}/execute")
async def execute_opportunity(
    opportunity_id: UUID,
    request: Optional[ExecuteOpportunityRequest] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Execute an opportunity - place orders on both exchanges.

    This endpoint:
    1. Validates the opportunity is still valid
    2. Connects to both exchanges
    3. Places long order on primary exchange
    4. Places short order on hedge exchange
    5. Creates position and leg records
    6. Logs all execution details for analysis
    7. Returns execution details
    """
    from sqlalchemy import text
    from datetime import timezone
    from uuid import uuid4
    import json
    from shared.utils.exchange_client import ExchangeClient, get_exchange_credentials

    execution_log_id = uuid4()  # Unique ID for this execution attempt

    # Common exchange error codes and user-friendly messages
    EXCHANGE_ERROR_MESSAGES = {
        # Bybit errors
        "110007": "Insufficient balance on {exchange}. Please deposit more funds or reduce position size.",
        "ab not enough": "Insufficient balance on {exchange}. Please deposit more funds or reduce position size.",
        "110003": "Order price is invalid on {exchange}. Market may be too volatile.",
        "110004": "Insufficient wallet balance on {exchange}.",
        "110017": "Position size exceeds maximum allowed on {exchange}.",
        "110018": "Position value is too low. Minimum notional not met on {exchange}.",
        # Binance errors
        "-4164": "Order notional too small on {exchange}. Minimum is $5 USDT.",
        "-2019": "Insufficient margin on {exchange}. Please deposit more funds.",
        "-1121": "Invalid symbol on {exchange}. The trading pair may not be available.",
        "-4003": "Quantity precision error on {exchange}.",
        "-4131": "Insufficient balance to cover fees on {exchange}.",
        # Generic
        "insufficient": "Insufficient balance on {exchange}. Please check your account balance.",
        "not enough": "Insufficient balance on {exchange}. Please check your account balance.",
    }

    def parse_exchange_error(error_str: str, exchange: str) -> str:
        """Parse exchange error and return user-friendly message."""
        error_lower = error_str.lower()
        for key, message in EXCHANGE_ERROR_MESSAGES.items():
            if key.lower() in error_lower:
                return message.format(exchange=exchange)
        # Return a cleaner version of the original error
        return f"Order failed on {exchange}: {error_str[:200]}"

    # Map short exchange names to full slugs (for config/credentials lookup)
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
        "dydx": "dydx_futures",
        # Also support full slug names
        "binance_futures": "binance_futures",
        "bybit_futures": "bybit_futures",
        "okex_futures": "okex_futures",
        "gate_futures": "gate_futures",
        "kucoin_futures": "kucoin_futures",
        "bitget_futures": "bitget_futures",
        "mexc_futures": "mexc_futures",
        "bingx_futures": "bingx_futures",
        "hyperliquid_futures": "hyperliquid_futures",
        "dydx_futures": "dydx_futures",
    }

    # Helper function to log execution events
    async def log_execution_event(
        event_type: str,
        status: str,
        details: dict,
        error: str = None
    ):
        """Log execution event to database for analysis."""
        try:
            log_query = """
                INSERT INTO audit.execution_logs (
                    id, opportunity_id, event_type, status, details, error_message, created_at
                ) VALUES (
                    :id, :opp_id, :event_type, :status, :details, :error, NOW()
                )
            """
            await db.execute(text(log_query), {
                "id": str(uuid4()),
                "opp_id": str(opportunity_id),
                "event_type": event_type,
                "status": status,
                "details": json.dumps(details),
                "error": error,
            })
        except Exception as log_error:
            # Don't fail execution if logging fails, but print error
            print(f"Failed to log execution event: {log_error}")

    # Get the full opportunity details
    query = """
        SELECT
            id, opportunity_type, symbol, base_asset, status,
            primary_exchange, primary_side, primary_rate,
            hedge_exchange, hedge_side, hedge_rate,
            gross_funding_rate, net_apr, uos_score,
            recommended_size_usd, expires_at
        FROM opportunities.detected
        WHERE id = :id
    """
    result = await db.execute(text(query), {"id": str(opportunity_id)})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    (opp_id, opp_type, symbol, base_asset, status,
     primary_ex, primary_side, primary_rate,
     hedge_ex, hedge_side, hedge_rate,
     gross_rate, net_apr, uos_score,
     recommended_size, expires_at) = row

    # Map exchange names to slugs early for validation
    primary_slug_check = EXCHANGE_SLUG_MAP.get(primary_ex.lower(), f"{primary_ex.lower()}_futures")
    hedge_slug_check = EXCHANGE_SLUG_MAP.get(hedge_ex.lower(), f"{hedge_ex.lower()}_futures")

    # Pre-validate: Check if exchanges have credentials before proceeding
    creds_check_query = """
        SELECT slug, api_key_encrypted IS NOT NULL OR wallet_address_encrypted IS NOT NULL as has_creds
        FROM config.exchanges
        WHERE slug IN (:primary, :hedge)
    """
    creds_result = await db.execute(text(creds_check_query), {"primary": primary_slug_check, "hedge": hedge_slug_check})
    creds_map = {row[0]: row[1] for row in creds_result.fetchall()}

    missing_creds = []
    if not creds_map.get(primary_slug_check):
        missing_creds.append(f"{primary_ex} ({primary_slug_check})")
    if not creds_map.get(hedge_slug_check):
        missing_creds.append(f"{hedge_ex} ({hedge_slug_check})")

    if missing_creds:
        error_msg = f"Missing API credentials for: {', '.join(missing_creds)}. Please configure exchange credentials in Settings."
        await log_execution_event("validation_failed", "rejected", {
            "reason": "missing_credentials",
            "exchanges_missing": missing_creds,
        }, error=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # Log execution start
    await log_execution_event("execution_started", "pending", {
        "opportunity_id": str(opportunity_id),
        "symbol": symbol,
        "primary_exchange": primary_ex,
        "hedge_exchange": hedge_ex,
        "current_status": status,
        "recommended_size_usd": float(recommended_size) if recommended_size else 0,
    })

    # Validate status - allow re-execution of 'executing' status (for retries)
    valid_statuses = ['detected', 'validated', 'scored', 'allocated', 'executing']
    if status not in valid_statuses:
        await log_execution_event("validation_failed", "rejected", {
            "reason": "invalid_status",
            "current_status": status,
            "valid_statuses": valid_statuses,
        }, error=f"Invalid status: {status}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot execute opportunity with status '{status}'. Must be one of: {valid_statuses}"
        )

    # Check if expired
    if expires_at and expires_at < datetime.now(timezone.utc):
        await log_execution_event("validation_failed", "rejected", {
            "reason": "expired",
            "expires_at": expires_at.isoformat() if expires_at else None,
        }, error="Opportunity expired")
        raise HTTPException(status_code=400, detail="Opportunity has expired")

    # Determine capital and leverage - ensure we have a valid size
    if recommended_size and float(recommended_size) > 0:
        capital = float(request.capital_usd if request and request.capital_usd else recommended_size)
    else:
        # Default to $100 if no recommended size
        capital = float(request.capital_usd if request and request.capital_usd else 100)
    leverage = request.leverage if request and request.leverage else 3

    await log_execution_event("capital_determined", "pending", {
        "capital_usd": capital,
        "leverage": leverage,
        "recommended_size_usd": float(recommended_size) if recommended_size else 0,
        "user_override": bool(request and request.capital_usd),
    })

    # Update status to 'executing'
    await db.execute(
        text("UPDATE opportunities.detected SET status = 'executing' WHERE id = :id"),
        {"id": str(opportunity_id)}
    )
    await db.commit()

    # Map exchange names to slugs
    primary_slug = EXCHANGE_SLUG_MAP.get(primary_ex.lower(), f"{primary_ex.lower()}_futures")
    hedge_slug = EXCHANGE_SLUG_MAP.get(hedge_ex.lower(), f"{hedge_ex.lower()}_futures")

    # Get exchange info
    ex_query = """
        SELECT slug, api_type FROM config.exchanges
        WHERE slug IN (:primary, :hedge)
    """
    ex_result = await db.execute(text(ex_query), {"primary": primary_slug, "hedge": hedge_slug})
    exchanges = {row[0]: row[1] for row in ex_result.fetchall()}

    if primary_slug not in exchanges or hedge_slug not in exchanges:
        await log_execution_event("exchange_config_failed", "error", {
            "primary_exchange": primary_ex,
            "primary_slug": primary_slug,
            "hedge_exchange": hedge_ex,
            "hedge_slug": hedge_slug,
            "configured_exchanges": list(exchanges.keys()),
        }, error="Exchange configuration not found")
        raise HTTPException(status_code=400, detail=f"Exchange configuration not found for {primary_slug} or {hedge_slug}")

    # Get credentials for both exchanges
    primary_creds = await get_exchange_credentials(db, primary_slug)
    hedge_creds = await get_exchange_credentials(db, hedge_slug)

    if not primary_creds or not hedge_creds:
        await log_execution_event("credentials_failed", "error", {
            "primary_has_creds": bool(primary_creds),
            "hedge_has_creds": bool(hedge_creds),
            "primary_slug": primary_slug,
            "hedge_slug": hedge_slug,
        }, error="Exchange credentials not configured")
        raise HTTPException(status_code=400, detail=f"Exchange credentials not configured for {primary_slug} or {hedge_slug}")

    await log_execution_event("credentials_loaded", "pending", {
        "primary_exchange": primary_ex,
        "primary_slug": primary_slug,
        "hedge_exchange": hedge_ex,
        "hedge_slug": hedge_slug,
    })

    # Create exchange clients using the mapped slugs
    primary_client = ExchangeClient(
        slug=primary_slug,
        credentials=primary_creds,
        api_type=exchanges[primary_slug],
        sandbox=False,
    )
    hedge_client = ExchangeClient(
        slug=hedge_slug,
        credentials=hedge_creds,
        api_type=exchanges[hedge_slug],
        sandbox=False,
    )

    # Track execution results
    execution_results = {
        "primary": None,
        "hedge": None,
        "errors": [],
    }

    try:
        # Connect to both exchanges
        await log_execution_event("connecting_exchanges", "pending", {
            "primary_exchange": primary_ex,
            "primary_slug": primary_slug,
            "hedge_exchange": hedge_ex,
            "hedge_slug": hedge_slug,
        })

        if not await primary_client.connect():
            await log_execution_event("connection_failed", "error", {
                "exchange": primary_ex,
                "slug": primary_slug,
                "type": "primary",
            }, error=f"Failed to connect to {primary_slug}")
            raise HTTPException(status_code=500, detail=f"Failed to connect to {primary_slug}")

        if not await hedge_client.connect():
            await primary_client.disconnect()
            await log_execution_event("connection_failed", "error", {
                "exchange": hedge_ex,
                "slug": hedge_slug,
                "type": "hedge",
            }, error=f"Failed to connect to {hedge_slug}")
            raise HTTPException(status_code=500, detail=f"Failed to connect to {hedge_slug}")

        await log_execution_event("exchanges_connected", "pending", {
            "primary_exchange": primary_ex,
            "primary_slug": primary_slug,
            "hedge_exchange": hedge_ex,
            "hedge_slug": hedge_slug,
        })

        # Calculate notional size based on capital and leverage
        notional_size = capital * leverage

        # Format symbol for exchanges (add /USDT:USDT for CCXT perpetuals)
        primary_symbol = f"{symbol}/USDT:USDT" if "ccxt" in exchanges.get(primary_slug, "ccxt") else symbol
        hedge_symbol = f"{symbol}/USDT:USDT" if "ccxt" in exchanges.get(hedge_slug, "ccxt") else symbol

        # Fetch current price to calculate proper quantity
        try:
            # Use primary client to fetch ticker price
            ticker = await primary_client._client.fetch_ticker(primary_symbol)
            current_price = float(ticker.get("last") or ticker.get("close") or 0)

            if current_price <= 0:
                raise ValueError(f"Invalid price: {current_price}")

            await log_execution_event("price_fetched", "pending", {
                "symbol": primary_symbol,
                "price": current_price,
            })

        except Exception as price_err:
            await log_execution_event("price_fetch_failed", "error", {
                "symbol": primary_symbol,
                "error": str(price_err),
            }, error=str(price_err))
            raise HTTPException(status_code=500, detail=f"Failed to fetch price for {symbol}: {price_err}")

        # Calculate quantity based on notional size and current price
        # Add a small buffer for slippage
        quantity = notional_size / current_price

        # Ensure minimum notional of $6 (above Binance's $5 minimum)
        min_notional = 6.0
        if quantity * current_price < min_notional:
            quantity = min_notional / current_price

        await log_execution_event("order_params_calculated", "pending", {
            "capital_usd": capital,
            "leverage": leverage,
            "notional_size": notional_size,
            "current_price": current_price,
            "quantity": quantity,
            "estimated_notional": quantity * current_price,
            "primary_symbol": primary_symbol,
            "hedge_symbol": hedge_symbol,
        })

        # Place primary leg order (the side that receives funding)
        primary_order_side = primary_side.lower()  # 'long' -> buy, 'short' -> sell

        await log_execution_event("placing_primary_order", "pending", {
            "exchange": primary_ex,
            "symbol": primary_symbol,
            "side": "buy" if primary_order_side == "long" else "sell",
            "quantity": quantity,
            "order_type": "market",
        })

        primary_order = await primary_client.place_order(
            symbol=primary_symbol,
            side="buy" if primary_order_side == "long" else "sell",
            size=quantity,
            order_type="market",
        )
        execution_results["primary"] = primary_order

        await log_execution_event("primary_order_result", "pending" if primary_order.get("success") else "error", {
            "exchange": primary_ex,
            "order_id": primary_order.get("order_id"),
            "success": primary_order.get("success"),
            "filled_quantity": primary_order.get("filled"),
            "price": primary_order.get("price"),
            "response": primary_order,
        }, error=primary_order.get("error") if not primary_order.get("success") else None)

        if not primary_order.get("success"):
            error_msg = parse_exchange_error(primary_order.get('error', 'Unknown error'), primary_ex)
            raise Exception(f"Primary order failed: {error_msg}")

        # Place hedge leg order (opposite side)
        hedge_order_side = hedge_side.lower()

        await log_execution_event("placing_hedge_order", "pending", {
            "exchange": hedge_ex,
            "symbol": hedge_symbol,
            "side": "buy" if hedge_order_side == "long" else "sell",
            "quantity": quantity,
            "order_type": "market",
        })

        hedge_order = await hedge_client.place_order(
            symbol=hedge_symbol,
            side="buy" if hedge_order_side == "long" else "sell",
            size=quantity,
            order_type="market",
        )
        execution_results["hedge"] = hedge_order

        await log_execution_event("hedge_order_result", "pending" if hedge_order.get("success") else "error", {
            "exchange": hedge_ex,
            "order_id": hedge_order.get("order_id"),
            "success": hedge_order.get("success"),
            "filled_quantity": hedge_order.get("filled"),
            "price": hedge_order.get("price"),
            "response": hedge_order,
        }, error=hedge_order.get("error") if not hedge_order.get("success") else None)

        if not hedge_order.get("success"):
            # Parse the error for user-friendly message
            hedge_error_msg = parse_exchange_error(hedge_order.get('error', 'Unknown error'), hedge_ex)
            execution_results["errors"].append(hedge_error_msg)

            await log_execution_event("rollback_started", "pending", {
                "reason": "hedge_order_failed",
                "hedge_error": hedge_order.get("error"),
                "hedge_error_parsed": hedge_error_msg,
                "primary_order_id": primary_order.get("order_id"),
            })

            # Try to close primary position (rollback)
            rollback_order = await primary_client.place_order(
                symbol=primary_symbol,
                side="sell" if primary_order_side == "long" else "buy",
                size=quantity,
                order_type="market",
                reduce_only=True,
            )

            rollback_success = rollback_order.get("success", False)
            await log_execution_event("rollback_result", "completed" if rollback_success else "error", {
                "rollback_order": rollback_order,
                "rollback_success": rollback_success,
            }, error=rollback_order.get("error") if not rollback_success else None)

            # Construct user-friendly error message
            if rollback_success:
                final_error = f"{hedge_error_msg} The primary position on {primary_ex} has been automatically closed."
            else:
                rollback_error = parse_exchange_error(rollback_order.get('error', ''), primary_ex)
                final_error = f"{hedge_error_msg} WARNING: Failed to close primary position on {primary_ex}: {rollback_error}. Manual intervention may be required."

            raise Exception(final_error)

        # Both orders successful - create position record
        position_id = uuid4()
        now = datetime.now(timezone.utc)

        # Insert position
        position_query = """
            INSERT INTO positions.active (
                id, opportunity_id, opportunity_type, symbol, base_asset,
                status, health_status, total_capital_deployed,
                opened_at, created_at
            ) VALUES (
                :id, :opp_id, :opp_type, :symbol, :base_asset,
                'active', 'healthy', :capital,
                :now, :now
            )
        """
        await db.execute(text(position_query), {
            "id": str(position_id),
            "opp_id": str(opportunity_id),
            "opp_type": opp_type,
            "symbol": symbol,
            "base_asset": base_asset,
            "capital": capital,
            "now": now,
        })

        # Insert primary leg
        primary_leg_query = """
            INSERT INTO positions.legs (
                id, position_id, leg_type, exchange, symbol, market_type,
                side, quantity, entry_price, current_price, notional_value_usd,
                leverage, entry_timestamp, entry_order_ids
            ) VALUES (
                :id, :position_id, 'primary', :exchange, :symbol, 'perpetual',
                :side, :quantity, :price, :price, :notional,
                :leverage, :now, :order_ids
            )
        """
        await db.execute(text(primary_leg_query), {
            "id": str(uuid4()),
            "position_id": str(position_id),
            "exchange": primary_ex,
            "symbol": symbol,
            "side": primary_side.lower(),
            "quantity": quantity,
            "price": primary_order.get("price", 0) or current_price,
            "notional": notional_size / 2,
            "leverage": leverage,
            "now": now,
            "order_ids": f'["{primary_order.get("order_id", "")}"]',
        })

        # Insert hedge leg
        hedge_leg_query = """
            INSERT INTO positions.legs (
                id, position_id, leg_type, exchange, symbol, market_type,
                side, quantity, entry_price, current_price, notional_value_usd,
                leverage, entry_timestamp, entry_order_ids
            ) VALUES (
                :id, :position_id, 'hedge', :exchange, :symbol, 'perpetual',
                :side, :quantity, :price, :price, :notional,
                :leverage, :now, :order_ids
            )
        """
        await db.execute(text(hedge_leg_query), {
            "id": str(uuid4()),
            "position_id": str(position_id),
            "exchange": hedge_ex,
            "symbol": symbol,
            "side": hedge_side.lower(),
            "quantity": quantity,
            "price": hedge_order.get("price", 0) or current_price,
            "notional": notional_size / 2,
            "leverage": leverage,
            "now": now,
            "order_ids": f'["{hedge_order.get("order_id", "")}"]',
        })

        # Update opportunity status to 'executed'
        await db.execute(
            text("UPDATE opportunities.detected SET status = 'executed' WHERE id = :id"),
            {"id": str(opportunity_id)}
        )

        # Log the execution
        audit_query = """
            INSERT INTO audit.actions (actor, action_type, resource_type, resource_id, details)
            VALUES ('user', 'position_opened', 'position', :id, :details)
        """
        await db.execute(text(audit_query), {
            "id": str(position_id),
            "details": f'{{"symbol": "{symbol}", "capital_usd": {capital}, "primary_exchange": "{primary_ex}", "hedge_exchange": "{hedge_ex}", "leverage": {leverage}}}'
        })

        await db.commit()

        # Log position created successfully
        await log_execution_event("position_created", "completed", {
            "position_id": str(position_id),
            "opportunity_id": str(opportunity_id),
            "symbol": symbol,
            "capital_usd": capital,
            "leverage": leverage,
            "primary_leg": {
                "exchange": primary_ex,
                "side": primary_side,
                "order_id": primary_order.get("order_id"),
                "price": primary_order.get("price"),
            },
            "hedge_leg": {
                "exchange": hedge_ex,
                "side": hedge_side,
                "order_id": hedge_order.get("order_id"),
                "price": hedge_order.get("price"),
            },
        })

        # Log final execution completed
        await log_execution_event("execution_completed", "success", {
            "position_id": str(position_id),
            "total_execution_time_ms": None,  # Could add timing if needed
            "final_status": "active",
        })

        return {
            "success": True,
            "message": f"Position opened for {symbol}",
            "data": {
                "position_id": str(position_id),
                "opportunity_id": str(opportunity_id),
                "symbol": symbol,
                "capital_usd": capital,
                "leverage": leverage,
                "primary": {
                    "exchange": primary_ex,
                    "side": primary_side,
                    "order_id": primary_order.get("order_id"),
                },
                "hedge": {
                    "exchange": hedge_ex,
                    "side": hedge_side,
                    "order_id": hedge_order.get("order_id"),
                },
                "status": "active",
            },
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log execution failure with full details
        await log_execution_event("execution_failed", "error", {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "execution_results": execution_results,
            "primary_order": execution_results.get("primary"),
            "hedge_order": execution_results.get("hedge"),
            "accumulated_errors": execution_results.get("errors", []),
        }, error=str(e))

        # Update status to failed
        await db.execute(
            text("UPDATE opportunities.detected SET status = 'rejected' WHERE id = :id"),
            {"id": str(opportunity_id)}
        )
        await db.commit()

        # Provide user-friendly error message (the exception message is already parsed)
        error_message = str(e)

        # Add context about what happened with each leg
        primary_result = execution_results.get("primary")
        hedge_result = execution_results.get("hedge")

        status_details = []
        if primary_result:
            if primary_result.get("success"):
                status_details.append(f"Primary order on {primary_ex}: SUCCESS (Order ID: {primary_result.get('order_id', 'N/A')})")
            else:
                status_details.append(f"Primary order on {primary_ex}: FAILED")
        if hedge_result:
            if hedge_result.get("success"):
                status_details.append(f"Hedge order on {hedge_ex}: SUCCESS (Order ID: {hedge_result.get('order_id', 'N/A')})")
            else:
                status_details.append(f"Hedge order on {hedge_ex}: FAILED")

        detail_msg = error_message
        if status_details:
            detail_msg += " | Order Status: " + "; ".join(status_details)

        raise HTTPException(
            status_code=500,
            detail=detail_msg
        )

    finally:
        # Always disconnect
        await primary_client.disconnect()
        await hedge_client.disconnect()
