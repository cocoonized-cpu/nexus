"""
Blacklist API endpoints.
Manages symbols that should never be traded by the bot.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

router = APIRouter()


class BlacklistEntry(BaseModel):
    """Response model for a blacklist entry."""

    id: UUID
    symbol: str
    reason: Optional[str]
    blacklisted_by: str
    created_at: datetime
    updated_at: datetime


class AddToBlacklistRequest(BaseModel):
    """Request model for adding a symbol to the blacklist."""

    reason: Optional[str] = None


class BlacklistResponse(BaseModel):
    """Response model for blacklist operations."""

    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    meta: Optional[dict] = None


@router.get("")
async def list_blacklist(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List all blacklisted symbols.
    """
    query = """
        SELECT id, symbol, reason, blacklisted_by, created_at, updated_at
        FROM config.symbol_blacklist
        ORDER BY created_at DESC
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    entries = [
        {
            "id": str(row[0]),
            "symbol": row[1],
            "reason": row[2],
            "blacklisted_by": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "updated_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": entries,
        "meta": {
            "timestamp": datetime.utcnow().isoformat(),
            "count": len(entries),
        },
    }


@router.delete("")
async def clear_blacklist(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Clear all entries from the symbol blacklist.

    WARNING: This removes all blacklisted symbols. The bot will be able to
    open positions on all symbols again.
    """
    # Count entries first
    count_query = "SELECT COUNT(*) FROM config.symbol_blacklist"
    count_result = await db.execute(text(count_query))
    entry_count = count_result.scalar() or 0

    if entry_count == 0:
        return {
            "success": True,
            "message": "Blacklist is already empty",
            "entries_removed": 0,
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    # Get symbols before deleting (for logging)
    symbols_query = "SELECT symbol FROM config.symbol_blacklist"
    symbols_result = await db.execute(text(symbols_query))
    symbols = [row[0] for row in symbols_result.fetchall()]

    # Delete all entries
    delete_query = "DELETE FROM config.symbol_blacklist"
    await db.execute(text(delete_query))
    await db.commit()

    # Log the clear event
    await _log_blacklist_event(
        db,
        "ALL",
        "blacklist_cleared",
        f"Blacklist cleared ({entry_count} symbols removed)",
        f"Symbols: {', '.join(symbols)}",
    )

    # Publish event to Redis
    try:
        from src.redis_client import get_redis_client
        import json

        redis = await get_redis_client()
        await redis.publish(
            "nexus:config:blacklist_changed",
            json.dumps(
                {
                    "action": "cleared",
                    "symbols_removed": symbols,
                    "count": entry_count,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Cleared {entry_count} symbols from blacklist",
        "entries_removed": entry_count,
        "symbols_removed": symbols,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/{symbol}")
async def get_blacklist_entry(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Check if a symbol is blacklisted and get its details.
    """
    query = """
        SELECT id, symbol, reason, blacklisted_by, created_at, updated_at
        FROM config.symbol_blacklist
        WHERE symbol = :symbol
    """

    result = await db.execute(text(query), {"symbol": symbol.upper()})
    row = result.fetchone()

    if not row:
        return {
            "success": True,
            "data": None,
            "message": f"Symbol {symbol.upper()} is not blacklisted",
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    entry = {
        "id": str(row[0]),
        "symbol": row[1],
        "reason": row[2],
        "blacklisted_by": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
        "updated_at": row[5].isoformat() if row[5] else None,
    }

    return {
        "success": True,
        "data": entry,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.post("/{symbol}")
async def add_to_blacklist(
    symbol: str,
    request: AddToBlacklistRequest = AddToBlacklistRequest(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Add a symbol to the blacklist.
    The bot will never open positions on blacklisted symbols.
    """
    symbol_upper = symbol.upper()

    # Check if already blacklisted
    check_query = """
        SELECT id FROM config.symbol_blacklist WHERE symbol = :symbol
    """
    result = await db.execute(text(check_query), {"symbol": symbol_upper})
    existing = result.fetchone()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Symbol {symbol_upper} is already blacklisted",
        )

    # Insert into blacklist
    insert_query = """
        INSERT INTO config.symbol_blacklist (symbol, reason, blacklisted_by)
        VALUES (:symbol, :reason, 'user')
        RETURNING id, symbol, reason, blacklisted_by, created_at, updated_at
    """

    result = await db.execute(
        text(insert_query),
        {"symbol": symbol_upper, "reason": request.reason},
    )
    row = result.fetchone()
    await db.commit()

    # Log the blacklist action
    await _log_blacklist_event(
        db,
        symbol_upper,
        "symbol_blacklisted",
        f"Symbol {symbol_upper} added to blacklist",
        request.reason,
    )

    # Publish event to Redis for real-time updates
    try:
        from src.redis_client import get_redis_client

        redis = await get_redis_client()
        import json

        await redis.publish(
            "nexus:config:blacklist_changed",
            json.dumps(
                {
                    "action": "added",
                    "symbol": symbol_upper,
                    "reason": request.reason,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
        )
    except Exception:
        pass  # Don't fail if Redis is unavailable

    entry = {
        "id": str(row[0]),
        "symbol": row[1],
        "reason": row[2],
        "blacklisted_by": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
        "updated_at": row[5].isoformat() if row[5] else None,
    }

    return {
        "success": True,
        "data": entry,
        "message": f"Symbol {symbol_upper} added to blacklist",
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.delete("/{symbol}")
async def remove_from_blacklist(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Remove a symbol from the blacklist.
    """
    symbol_upper = symbol.upper()

    # Check if blacklisted
    check_query = """
        SELECT id, reason FROM config.symbol_blacklist WHERE symbol = :symbol
    """
    result = await db.execute(text(check_query), {"symbol": symbol_upper})
    existing = result.fetchone()

    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol {symbol_upper} is not blacklisted",
        )

    # Delete from blacklist
    delete_query = """
        DELETE FROM config.symbol_blacklist WHERE symbol = :symbol
    """
    await db.execute(text(delete_query), {"symbol": symbol_upper})
    await db.commit()

    # Log the removal
    await _log_blacklist_event(
        db,
        symbol_upper,
        "symbol_unblacklisted",
        f"Symbol {symbol_upper} removed from blacklist",
        None,
    )

    # Publish event to Redis
    try:
        from src.redis_client import get_redis_client

        redis = await get_redis_client()
        import json

        await redis.publish(
            "nexus:config:blacklist_changed",
            json.dumps(
                {
                    "action": "removed",
                    "symbol": symbol_upper,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Symbol {symbol_upper} removed from blacklist",
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.patch("/{symbol}")
async def update_blacklist_reason(
    symbol: str,
    request: AddToBlacklistRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update the reason for a blacklisted symbol.
    """
    symbol_upper = symbol.upper()

    # Check if blacklisted
    check_query = """
        SELECT id FROM config.symbol_blacklist WHERE symbol = :symbol
    """
    result = await db.execute(text(check_query), {"symbol": symbol_upper})
    existing = result.fetchone()

    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol {symbol_upper} is not blacklisted",
        )

    # Update reason
    update_query = """
        UPDATE config.symbol_blacklist
        SET reason = :reason, updated_at = NOW()
        WHERE symbol = :symbol
        RETURNING id, symbol, reason, blacklisted_by, created_at, updated_at
    """

    result = await db.execute(
        text(update_query),
        {"symbol": symbol_upper, "reason": request.reason},
    )
    row = result.fetchone()
    await db.commit()

    entry = {
        "id": str(row[0]),
        "symbol": row[1],
        "reason": row[2],
        "blacklisted_by": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
        "updated_at": row[5].isoformat() if row[5] else None,
    }

    return {
        "success": True,
        "data": entry,
        "message": f"Blacklist reason updated for {symbol_upper}",
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


async def _log_blacklist_event(
    db: AsyncSession,
    symbol: str,
    event_type: str,
    message: str,
    reason: Optional[str],
) -> None:
    """Log blacklist change to activity_events."""
    try:
        insert_query = """
            INSERT INTO audit.activity_events (
                service, category, event_type, severity, symbol, message, details
            ) VALUES (
                'gateway', 'config', :event_type, 'info', :symbol, :message,
                :details::jsonb
            )
        """
        import json

        await db.execute(
            text(insert_query),
            {
                "event_type": event_type,
                "symbol": symbol,
                "message": message,
                "details": json.dumps({"reason": reason}),
            },
        )
    except Exception:
        pass  # Don't fail the main operation if logging fails
