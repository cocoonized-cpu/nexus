"""
Funding rates API endpoints.

Provides funding rate data across all exchanges for the funding rates overview page.
"""

import httpx
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

router = APIRouter()

# Funding aggregator service URL (internal Docker network)
FUNDING_AGGREGATOR_URL = "http://nexus-funding-aggregator:8002"


class FundingRateItem(BaseModel):
    """Single funding rate entry."""
    exchange: str
    symbol: str
    ticker: str
    rate: Decimal
    rate_annualized: Decimal
    next_funding_time: datetime
    funding_interval_hours: int


@router.get("/rates")
async def get_funding_rates(
    exchange: Optional[str] = None,
    symbol: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get latest funding rates across all exchanges.

    Returns funding rates optionally filtered by exchange or symbol.
    """
    # Get latest funding rate for each exchange/symbol pair
    query = """
        WITH latest_rates AS (
            SELECT DISTINCT ON (exchange, symbol)
                exchange, symbol, ticker, rate,
                next_funding_time, funding_interval_hours, timestamp
            FROM funding.rates
            ORDER BY exchange, symbol, timestamp DESC
        )
        SELECT
            exchange, symbol, ticker, rate,
            next_funding_time, funding_interval_hours
        FROM latest_rates
        WHERE 1=1
    """
    params: dict[str, Any] = {}

    if exchange:
        query += " AND exchange = :exchange"
        params["exchange"] = exchange

    if symbol:
        query += " AND symbol ILIKE :symbol"
        params["symbol"] = f"%{symbol}%"

    query += " ORDER BY symbol, exchange"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    rates = []
    for row in rows:
        rate_decimal = Decimal(str(row[3])) if row[3] else Decimal("0")
        funding_interval = row[5] or 8
        # Annualize: rate * (365 * 24 / funding_interval_hours) * 100
        annualized = rate_decimal * Decimal(str(365 * 24 / funding_interval)) * 100

        rates.append({
            "exchange": row[0],
            "symbol": row[1],
            "ticker": row[2],
            "rate": float(rate_decimal),
            "rate_pct": float(rate_decimal * 100),
            "rate_annualized": float(annualized),
            "next_funding_time": row[4].isoformat() if row[4] else None,
            "funding_interval_hours": funding_interval,
        })

    return {
        "success": True,
        "data": rates,
        "meta": {
            "total": len(rates),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/matrix")
async def get_funding_rates_matrix(
    source: str = Query("both", description="Data source: exchanges, arbitrage-scanner, both"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get funding rates in a matrix format (coins x exchanges).

    Returns data structured for the funding rates overview table:
    - Rows are unique symbols/tickers
    - Columns are exchanges
    - Values are funding rates

    Filter by data source:
    - "exchanges": Only rates from direct exchange APIs
    - "arbitrage-scanner": Only rates from ArbitrageScanner API
    - "both": All rates (default)
    """
    # Get all unique exchanges from config
    exchanges_query = """
        SELECT slug, display_name FROM config.exchanges
        WHERE enabled = true
        ORDER BY
            CASE tier
                WHEN 'tier_1' THEN 1
                WHEN 'tier_2' THEN 2
                ELSE 3
            END,
            display_name
    """
    exchanges_result = await db.execute(text(exchanges_query))
    exchanges = [{"slug": row[0], "name": row[1]} for row in exchanges_result.fetchall()]
    exchange_slugs = [e["slug"] for e in exchanges]

    # Build source filter
    source_filter = ""
    if source == "exchanges":
        source_filter = "AND (source = 'exchange' OR source IS NULL)"
    elif source == "arbitrage-scanner":
        source_filter = "AND source = 'arbitrage_scanner'"
    # "both" = no filter

    # Get latest funding rates
    rates_query = f"""
        WITH latest_rates AS (
            SELECT DISTINCT ON (exchange, symbol)
                exchange, symbol, ticker, rate, funding_interval_hours
            FROM funding.rates
            WHERE 1=1 {source_filter}
            ORDER BY exchange, symbol, timestamp DESC
        )
        SELECT exchange, symbol, ticker, rate, funding_interval_hours
        FROM latest_rates
        ORDER BY symbol
    """
    rates_result = await db.execute(text(rates_query))
    rates_rows = rates_result.fetchall()

    # Build matrix: group by ticker
    tickers_data: dict[str, dict[str, Any]] = {}

    for row in rates_rows:
        exchange = row[0]
        symbol = row[1]
        ticker = row[2]
        rate = Decimal(str(row[3])) if row[3] else None
        interval = row[4] or 8

        if ticker not in tickers_data:
            tickers_data[ticker] = {
                "ticker": ticker,
                "symbol": symbol,
                "rates": {},
                "max_spread": Decimal("0"),
            }

        if rate is not None:
            rate_pct = float(rate * 100)
            tickers_data[ticker]["rates"][exchange] = rate_pct

    # Calculate max spread for each ticker
    rows_list = []
    for ticker, data in tickers_data.items():
        rates = list(data["rates"].values())
        if len(rates) >= 2:
            max_spread = max(rates) - min(rates)
        else:
            max_spread = 0

        rows_list.append({
            "ticker": data["ticker"],
            "symbol": data["symbol"],
            "rates": data["rates"],
            "max_spread": abs(max_spread),
        })

    # Sort by max_spread descending (best opportunities first)
    rows_list.sort(key=lambda x: x["max_spread"], reverse=True)

    return {
        "success": True,
        "data": {
            "exchanges": exchanges,
            "rows": rows_list,
        },
        "meta": {
            "total_coins": len(rows_list),
            "total_exchanges": len(exchanges),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/history/{symbol}")
async def get_funding_rate_history(
    symbol: str,
    exchange: Optional[str] = None,
    hours: int = Query(default=168, le=720),  # Default 7 days, max 30 days
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get historical funding rates for a symbol.

    Useful for analyzing funding rate trends over time.
    """
    query = """
        SELECT exchange, symbol, ticker, rate, timestamp
        FROM funding.rates
        WHERE symbol ILIKE :symbol
          AND timestamp > NOW() - INTERVAL ':hours hours'
    """
    params: dict[str, Any] = {"symbol": f"%{symbol}%", "hours": hours}

    if exchange:
        query += " AND exchange = :exchange"
        params["exchange"] = exchange

    query += " ORDER BY timestamp DESC"

    result = await db.execute(text(query.replace(":hours", str(hours))),
                              {k: v for k, v in params.items() if k != "hours"})
    rows = result.fetchall()

    history = [
        {
            "exchange": row[0],
            "symbol": row[1],
            "ticker": row[2],
            "rate": float(row[3]) if row[3] else 0,
            "rate_pct": float(row[3] * 100) if row[3] else 0,
            "timestamp": row[4].isoformat() if row[4] else None,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": history,
        "meta": {
            "symbol": symbol,
            "exchange": exchange,
            "hours": hours,
            "total": len(history),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/exchanges/{exchange}")
async def get_exchange_funding_rates(
    exchange: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get all funding rates for a specific exchange.
    """
    query = """
        WITH latest_rates AS (
            SELECT DISTINCT ON (symbol)
                exchange, symbol, ticker, rate,
                next_funding_time, funding_interval_hours, timestamp
            FROM funding.rates
            WHERE exchange = :exchange
            ORDER BY symbol, timestamp DESC
        )
        SELECT
            symbol, ticker, rate,
            next_funding_time, funding_interval_hours
        FROM latest_rates
        ORDER BY ABS(rate) DESC
    """

    result = await db.execute(text(query), {"exchange": exchange})
    rows = result.fetchall()

    rates = []
    for row in rows:
        rate_decimal = Decimal(str(row[2])) if row[2] else Decimal("0")
        funding_interval = row[4] or 8
        annualized = rate_decimal * Decimal(str(365 * 24 / funding_interval)) * 100

        rates.append({
            "symbol": row[0],
            "ticker": row[1],
            "rate": float(rate_decimal),
            "rate_pct": float(rate_decimal * 100),
            "rate_annualized": float(annualized),
            "next_funding_time": row[3].isoformat() if row[3] else None,
            "funding_interval_hours": funding_interval,
        })

    return {
        "success": True,
        "data": rates,
        "meta": {
            "exchange": exchange,
            "total": len(rates),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


# ============================================================================
# LIVE ENDPOINTS - Fetch directly from funding-aggregator service
# ============================================================================


@router.get("/live/rates")
async def get_live_funding_rates(
    exchange: Optional[str] = None,
    symbol: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get live funding rates from the funding-aggregator service.
    Returns real-time in-memory data, not persisted data.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {}
            if exchange:
                params["exchange"] = exchange
            if symbol:
                params["symbol"] = symbol

            response = await client.get(
                f"{FUNDING_AGGREGATOR_URL}/funding/rates",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Failed to connect to funding aggregator: {str(e)}",
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


@router.get("/live/spreads")
async def get_live_funding_spreads(
    min_spread: float = 0.0,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get live funding rate spreads between exchanges.
    This is the key input for opportunity detection.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{FUNDING_AGGREGATOR_URL}/funding/spreads",
                params={"min_spread": min_spread, "limit": limit},
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Failed to connect to funding aggregator: {str(e)}",
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


@router.get("/live/matrix")
async def get_live_funding_matrix() -> dict[str, Any]:
    """
    Get live funding rates in matrix format (coins x exchanges).
    Built from real-time data in the funding-aggregator.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get all unified rates
            response = await client.get(f"{FUNDING_AGGREGATOR_URL}/funding/rates")
            response.raise_for_status()
            rates_data = response.json()

            if not rates_data.get("success") or not rates_data.get("data"):
                return {
                    "success": True,
                    "data": {"exchanges": [], "rows": []},
                    "meta": {"timestamp": datetime.utcnow().isoformat()},
                }

            # Build matrix from rates
            rates = rates_data["data"]
            exchanges_set = set()
            tickers_data: dict[str, dict[str, Any]] = {}

            for rate in rates:
                exchange = rate.get("exchange", "unknown")
                symbol = rate.get("symbol", "unknown")
                # Extract ticker from symbol (e.g., "BTC/USDT:USDT" -> "BTC")
                ticker = symbol.split("/")[0] if "/" in symbol else symbol
                funding_rate = rate.get("funding_rate") or rate.get("rate") or 0

                exchanges_set.add(exchange)

                if ticker not in tickers_data:
                    tickers_data[ticker] = {
                        "ticker": ticker,
                        "symbol": symbol,
                        "rates": {},
                    }

                # Convert to percentage
                rate_pct = float(funding_rate) * 100
                tickers_data[ticker]["rates"][exchange] = rate_pct

            # Build rows with max_spread calculation
            rows_list = []
            for ticker, data in tickers_data.items():
                rates_values = list(data["rates"].values())
                if len(rates_values) >= 2:
                    max_spread = max(rates_values) - min(rates_values)
                else:
                    max_spread = 0

                rows_list.append({
                    "ticker": data["ticker"],
                    "symbol": data["symbol"],
                    "rates": data["rates"],
                    "max_spread": abs(max_spread),
                })

            # Sort by max_spread descending
            rows_list.sort(key=lambda x: x["max_spread"], reverse=True)

            # Build exchanges list
            exchanges = [{"slug": e, "name": e.replace("_", " ").title()}
                        for e in sorted(exchanges_set)]

            return {
                "success": True,
                "data": {
                    "exchanges": exchanges,
                    "rows": rows_list,
                },
                "meta": {
                    "total_coins": len(rows_list),
                    "total_exchanges": len(exchanges),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Failed to connect to funding aggregator: {str(e)}",
            "data": {"exchanges": [], "rows": []},
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {"exchanges": [], "rows": []},
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }
