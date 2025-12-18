"""
Position Sync Service - Synchronizes positions from connected exchanges.

Periodically fetches positions from all enabled exchanges with credentials
and stores them in the positions.exchange_positions table.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from shared.utils.config import get_settings
from shared.utils.exchange_client import (
    ExchangeClient,
    ExchangeCredentials,
    get_enabled_exchanges,
    get_exchange_credentials,
)
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)
settings = get_settings()


class PositionSyncService:
    """
    Service that periodically syncs positions from all connected exchanges.

    This runs as a background task and updates the positions.exchange_positions
    table with the latest position data from each exchange.
    """

    def __init__(
        self,
        redis_client: RedisClient,
        sync_interval: int = 30,  # seconds
    ):
        self.redis = redis_client
        self.sync_interval = sync_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._engine = None
        self._session_factory = None

    async def start(self) -> None:
        """Start the position sync service."""
        if self._running:
            return

        # Create database engine
        self._engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info("Position sync service started", interval=self.sync_interval)

    async def stop(self) -> None:
        """Stop the position sync service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._engine:
            await self._engine.dispose()
        logger.info("Position sync service stopped")

    async def _sync_loop(self) -> None:
        """Main sync loop."""
        while self._running:
            try:
                await self._sync_all_exchanges()
            except Exception as e:
                logger.error("Position sync failed", error=str(e))

            # Wait for next sync interval
            await asyncio.sleep(self.sync_interval)

    async def _sync_all_exchanges(self) -> None:
        """Sync positions from all enabled exchanges."""
        async with self._session_factory() as db:
            # Get enabled exchanges
            exchanges = await get_enabled_exchanges(db)

            for exchange in exchanges:
                if not exchange.get("has_credentials"):
                    continue

                slug = exchange["slug"]
                api_type = exchange.get("api_type", "ccxt")

                try:
                    await self._sync_exchange_positions(db, slug, api_type)
                except Exception as e:
                    logger.error(
                        f"Failed to sync positions from {slug}",
                        error=str(e),
                    )

    async def _sync_exchange_positions(
        self, db: AsyncSession, slug: str, api_type: str
    ) -> None:
        """Sync positions and trades from a single exchange."""
        # Get credentials
        credentials = await get_exchange_credentials(db, slug)
        if not credentials:
            return

        # Create exchange client
        client = ExchangeClient(
            slug=slug,
            credentials=credentials,
            api_type=api_type,
            sandbox=False,
        )

        try:
            # Connect to exchange
            connected = await client.connect()
            if not connected:
                logger.warning(f"Could not connect to {slug}")
                return

            # Fetch positions
            positions = await client.get_positions()

            # Get current positions in DB for this exchange
            current_query = text("""
                SELECT symbol FROM positions.exchange_positions WHERE exchange = :exchange
            """)
            result = await db.execute(current_query, {"exchange": slug})
            current_symbols = {row[0] for row in result.fetchall()}

            # Upsert each position
            synced_symbols = set()
            for pos in positions:
                symbol = pos["symbol"]
                synced_symbols.add(symbol)

                await self._upsert_position(db, slug, pos)

            # Remove positions that no longer exist on exchange
            removed_symbols = current_symbols - synced_symbols
            if removed_symbols:
                delete_query = text("""
                    DELETE FROM positions.exchange_positions
                    WHERE exchange = :exchange AND symbol = ANY(:symbols)
                """)
                await db.execute(
                    delete_query,
                    {"exchange": slug, "symbols": list(removed_symbols)},
                )

            # Sync trades/fills
            await self._sync_exchange_trades(db, client, slug)

            await db.commit()

            # Publish sync event
            await self.redis.publish(
                "nexus:positions:synced",
                {
                    "exchange": slug,
                    "count": len(positions),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            logger.debug(
                f"Synced {len(positions)} positions from {slug}",
                removed=len(removed_symbols),
            )

        finally:
            await client.disconnect()

    async def _sync_exchange_trades(
        self, db: AsyncSession, client: ExchangeClient, exchange: str
    ) -> None:
        """Sync recent trades from an exchange."""
        try:
            # Get the most recent trade timestamp to avoid duplicates
            last_trade_query = text("""
                SELECT MAX(executed_at) FROM positions.order_history WHERE exchange = :exchange
            """)
            result = await db.execute(last_trade_query, {"exchange": exchange})
            last_trade_time = result.scalar()

            # Convert to timestamp if available (fetch trades since last sync)
            since = int(last_trade_time.timestamp() * 1000) if last_trade_time else None

            # Fetch recent trades
            trades = await client.get_trades(since=since, limit=100)

            for trade in trades:
                await self._upsert_trade(db, exchange, trade)

            logger.debug(f"Synced {len(trades)} trades from {exchange}")

        except Exception as e:
            logger.error(f"Failed to sync trades from {exchange}", error=str(e))

    async def _upsert_trade(
        self, db: AsyncSession, exchange: str, trade: dict[str, Any]
    ) -> None:
        """Insert or update a trade in the database."""
        upsert_query = text("""
            INSERT INTO positions.order_history (
                exchange_order_id, exchange, symbol, side, order_type,
                price, amount, filled, fee, fee_currency, status, executed_at
            )
            VALUES (
                :order_id, :exchange, :symbol, :side, 'market',
                :price, :amount, :filled, :fee, :fee_currency, 'closed', :executed_at
            )
            ON CONFLICT (exchange, exchange_order_id) DO UPDATE SET
                price = EXCLUDED.price,
                amount = EXCLUDED.amount,
                filled = EXCLUDED.filled,
                fee = EXCLUDED.fee,
                fee_currency = EXCLUDED.fee_currency,
                executed_at = EXCLUDED.executed_at
        """)

        executed_at = None
        if trade.get("datetime"):
            try:
                executed_at = datetime.fromisoformat(trade["datetime"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if not executed_at and trade.get("timestamp"):
            executed_at = datetime.utcfromtimestamp(trade["timestamp"] / 1000)

        await db.execute(
            upsert_query,
            {
                "order_id": str(trade.get("id") or trade.get("order_id", "")),
                "exchange": exchange,
                "symbol": trade["symbol"],
                "side": trade["side"],
                "price": Decimal(str(trade.get("price", 0))),
                "amount": Decimal(str(trade.get("amount", 0))),
                "filled": Decimal(str(trade.get("amount", 0))),  # For trades, filled = amount
                "fee": Decimal(str(trade.get("fee", 0))),
                "fee_currency": trade.get("fee_currency"),
                "executed_at": executed_at,
            },
        )

    async def _upsert_position(
        self, db: AsyncSession, exchange: str, position: dict[str, Any]
    ) -> None:
        """Insert or update a position in the database."""
        upsert_query = text("""
            INSERT INTO positions.exchange_positions (
                exchange, symbol, side, size, notional_usd, entry_price,
                mark_price, unrealized_pnl, leverage, liquidation_price,
                margin_mode, updated_at
            )
            VALUES (
                :exchange, :symbol, :side, :size, :notional_usd, :entry_price,
                :mark_price, :unrealized_pnl, :leverage, :liquidation_price,
                :margin_mode, NOW()
            )
            ON CONFLICT (exchange, symbol) DO UPDATE SET
                side = EXCLUDED.side,
                size = EXCLUDED.size,
                notional_usd = EXCLUDED.notional_usd,
                entry_price = EXCLUDED.entry_price,
                mark_price = EXCLUDED.mark_price,
                unrealized_pnl = EXCLUDED.unrealized_pnl,
                leverage = EXCLUDED.leverage,
                liquidation_price = EXCLUDED.liquidation_price,
                margin_mode = EXCLUDED.margin_mode,
                updated_at = NOW()
        """)

        await db.execute(
            upsert_query,
            {
                "exchange": exchange,
                "symbol": position["symbol"],
                "side": position["side"],
                "size": Decimal(str(position["size"])),
                "notional_usd": Decimal(str(position.get("notional", 0))),
                "entry_price": Decimal(str(position["entry_price"])),
                "mark_price": Decimal(str(position["mark_price"])),
                "unrealized_pnl": Decimal(str(position.get("unrealized_pnl", 0))),
                "leverage": Decimal(str(position.get("leverage", 1))),
                "liquidation_price": (
                    Decimal(str(position["liquidation_price"]))
                    if position.get("liquidation_price")
                    else None
                ),
                "margin_mode": position.get("margin_mode", "cross"),
            },
        )

    async def sync_now(self) -> dict[str, Any]:
        """Trigger an immediate sync and return results."""
        results = {"exchanges": [], "total_positions": 0, "errors": []}

        async with self._session_factory() as db:
            exchanges = await get_enabled_exchanges(db)

            for exchange in exchanges:
                if not exchange.get("has_credentials"):
                    continue

                slug = exchange["slug"]
                api_type = exchange.get("api_type", "ccxt")

                try:
                    await self._sync_exchange_positions(db, slug, api_type)

                    # Count positions for this exchange
                    count_query = text("""
                        SELECT COUNT(*) FROM positions.exchange_positions
                        WHERE exchange = :exchange
                    """)
                    result = await db.execute(count_query, {"exchange": slug})
                    count = result.scalar() or 0

                    results["exchanges"].append({
                        "exchange": slug,
                        "positions": count,
                        "status": "success",
                    })
                    results["total_positions"] += count

                except Exception as e:
                    results["exchanges"].append({
                        "exchange": slug,
                        "status": "error",
                        "error": str(e),
                    })
                    results["errors"].append(f"{slug}: {str(e)}")

        return results
