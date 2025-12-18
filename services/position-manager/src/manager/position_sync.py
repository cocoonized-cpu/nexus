"""
Position Sync Worker - Synchronizes positions and orders from all exchanges.

Responsibilities:
- Fetch open positions from all configured exchanges
- Fetch open orders from all configured exchanges
- Store position and order history in the database
- Track order fills and position changes
- Reconcile exchange data with local state
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from shared.utils.exchange_client import (
    ExchangeClient,
    get_enabled_exchanges,
    get_exchange_credentials,
)
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class PositionSyncWorker:
    """Synchronizes positions and orders from all configured exchanges."""

    def __init__(
        self,
        redis: RedisClient,
        db_url: str,
        sync_interval: int = 30,
        encryption_key: str = "nexus_secret",
    ):
        self.redis = redis
        self.db_url = db_url
        self.sync_interval = sync_interval
        self.encryption_key = encryption_key

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._db_session_factory: Optional[sessionmaker] = None

        # In-memory cache
        self._positions: dict[str, list[dict[str, Any]]] = {}
        self._orders: dict[str, list[dict[str, Any]]] = {}
        self._last_sync: Optional[datetime] = None

    async def start(self) -> None:
        """Start the position sync loop."""
        logger.info("Starting Position Sync Worker")

        # Setup database connection
        engine = create_async_engine(self.db_url, echo=False)
        self._db_session_factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info("Position Sync Worker started")

    async def stop(self) -> None:
        """Stop the position sync loop."""
        logger.info("Stopping Position Sync Worker")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Position Sync Worker stopped")

    async def _sync_loop(self) -> None:
        """Main synchronization loop."""
        # Initial sync after a short delay
        await asyncio.sleep(10)

        while self._running:
            try:
                await self.sync_all()
            except Exception as e:
                logger.error("Error in position sync loop", error=str(e))

            await asyncio.sleep(self.sync_interval)

    async def sync_all(self) -> dict[str, Any]:
        """Sync positions and orders from all enabled exchanges."""
        if not self._db_session_factory:
            return {"success": False, "error": "Database not initialized"}

        async with self._db_session_factory() as db:
            # Get all enabled exchanges
            exchanges = await get_enabled_exchanges(db)
            logger.info(f"Syncing positions for {len(exchanges)} exchanges")

            results: dict[str, Any] = {
                "positions": {},
                "orders": {},
            }
            total_positions = 0
            total_orders = 0

            for exchange in exchanges:
                slug = exchange["slug"]
                if not exchange["has_credentials"]:
                    continue

                try:
                    pos_result = await self._sync_exchange_positions(
                        db, slug, exchange["api_type"]
                    )
                    results["positions"][slug] = pos_result
                    total_positions += len(pos_result.get("positions", []))

                    order_result = await self._sync_exchange_orders(
                        db, slug, exchange["api_type"]
                    )
                    results["orders"][slug] = order_result
                    total_orders += len(order_result.get("orders", []))
                except Exception as e:
                    logger.error(f"Failed to sync {slug}", error=str(e))
                    results["positions"][slug] = {"error": str(e)}
                    results["orders"][slug] = {"error": str(e)}

            self._last_sync = datetime.utcnow()

            # Publish sync complete event
            await self.redis.publish(
                "nexus:positions:sync_complete",
                json.dumps({
                    "total_positions": total_positions,
                    "total_orders": total_orders,
                    "exchanges": list(results["positions"].keys()),
                    "timestamp": self._last_sync.isoformat(),
                }),
            )

            logger.info(
                "Position sync complete",
                positions=total_positions,
                orders=total_orders,
            )

            # After syncing exchange positions, adopt any untracked positions
            adoption_result = await self.adopt_untracked_positions()
            if adoption_result.get("adopted", 0) > 0 or adoption_result.get("unpaired", 0) > 0:
                logger.info(
                    "Position adoption complete",
                    adopted=adoption_result.get("adopted", 0),
                    unpaired=adoption_result.get("unpaired", 0),
                )

            return {
                "success": True,
                "total_positions": total_positions,
                "total_orders": total_orders,
                "results": results,
                "adoption": adoption_result,
                "synced_at": self._last_sync.isoformat(),
            }

    async def _sync_exchange_positions(
        self, db: AsyncSession, slug: str, api_type: str
    ) -> dict[str, Any]:
        """Sync positions for a single exchange."""
        # Get credentials
        credentials = await get_exchange_credentials(db, slug, self.encryption_key)
        if not credentials:
            return {"error": "No credentials found", "positions": []}

        # Create client and fetch positions
        client = ExchangeClient(slug, credentials, api_type)
        connected = await client.connect()

        if not connected:
            return {"error": "Failed to connect", "positions": []}

        try:
            positions = await client.get_positions()

            # Store in database
            for position in positions:
                await self._store_exchange_position(db, slug, position)

            # Update cache
            self._positions[slug] = positions

            return {"positions": positions, "count": len(positions)}
        finally:
            await client.disconnect()

    async def _store_exchange_position(
        self, db: AsyncSession, exchange: str, position: dict[str, Any]
    ) -> None:
        """Store or update an exchange position in the database."""
        # Create a unique ID based on exchange + symbol
        position_key = f"{exchange}:{position['symbol']}"

        query = text("""
            INSERT INTO positions.exchange_positions (
                id, exchange, symbol, side, size, notional_usd,
                entry_price, mark_price, unrealized_pnl, leverage,
                liquidation_price, margin_mode, updated_at
            )
            VALUES (
                :id, :exchange, :symbol, :side, :size, :notional_usd,
                :entry_price, :mark_price, :unrealized_pnl, :leverage,
                :liquidation_price, :margin_mode, NOW()
            )
            ON CONFLICT (exchange, symbol) DO UPDATE SET
                side = :side,
                size = :size,
                notional_usd = :notional_usd,
                entry_price = :entry_price,
                mark_price = :mark_price,
                unrealized_pnl = :unrealized_pnl,
                leverage = :leverage,
                liquidation_price = :liquidation_price,
                margin_mode = :margin_mode,
                updated_at = NOW()
        """)

        try:
            await db.execute(
                query,
                {
                    "id": str(uuid4()),
                    "exchange": exchange,
                    "symbol": position["symbol"],
                    "side": position["side"],
                    "size": position["size"],
                    "notional_usd": position["notional"],
                    "entry_price": position["entry_price"],
                    "mark_price": position["mark_price"],
                    "unrealized_pnl": position["unrealized_pnl"],
                    "leverage": position["leverage"],
                    "liquidation_price": position.get("liquidation_price"),
                    "margin_mode": position.get("margin_mode", "cross"),
                },
            )
            await db.commit()
        except Exception as e:
            # Table might not exist yet, log and continue
            logger.debug(f"Could not store position: {e}")
            await db.rollback()

    async def _sync_exchange_orders(
        self, db: AsyncSession, slug: str, api_type: str
    ) -> dict[str, Any]:
        """Sync orders for a single exchange."""
        # Get credentials
        credentials = await get_exchange_credentials(db, slug, self.encryption_key)
        if not credentials:
            return {"error": "No credentials found", "orders": []}

        # Create client and fetch orders
        client = ExchangeClient(slug, credentials, api_type)
        connected = await client.connect()

        if not connected:
            return {"error": "Failed to connect", "orders": []}

        try:
            orders = await client.get_orders()

            # Store in database
            for order in orders:
                await self._store_exchange_order(db, slug, order)

            # Update cache
            self._orders[slug] = orders

            return {"orders": orders, "count": len(orders)}
        finally:
            await client.disconnect()

    async def _store_exchange_order(
        self, db: AsyncSession, exchange: str, order: dict[str, Any]
    ) -> None:
        """Store or update an exchange order in the database."""
        query = text("""
            INSERT INTO positions.exchange_orders (
                id, exchange_order_id, exchange, symbol, side, order_type,
                price, amount, filled, remaining, status, created_at, updated_at
            )
            VALUES (
                :id, :exchange_order_id, :exchange, :symbol, :side, :order_type,
                :price, :amount, :filled, :remaining, :status, :created_at, NOW()
            )
            ON CONFLICT (exchange, exchange_order_id) DO UPDATE SET
                filled = :filled,
                remaining = :remaining,
                status = :status,
                updated_at = NOW()
        """)

        try:
            await db.execute(
                query,
                {
                    "id": str(uuid4()),
                    "exchange_order_id": order["id"],
                    "exchange": exchange,
                    "symbol": order["symbol"],
                    "side": order["side"],
                    "order_type": order["type"],
                    "price": order["price"],
                    "amount": order["amount"],
                    "filled": order["filled"],
                    "remaining": order["remaining"],
                    "status": order["status"],
                    "created_at": order.get("created_at"),
                },
            )
            await db.commit()
        except Exception as e:
            # Table might not exist yet, log and continue
            logger.debug(f"Could not store order: {e}")
            await db.rollback()

    def get_positions(self, exchange: Optional[str] = None) -> dict[str, Any]:
        """Get cached positions."""
        if exchange:
            return {
                "exchange": exchange,
                "positions": self._positions.get(exchange, []),
                "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            }

        all_positions = []
        for slug, positions in self._positions.items():
            for pos in positions:
                pos["exchange"] = slug
                all_positions.append(pos)

        return {
            "positions": all_positions,
            "exchanges": list(self._positions.keys()),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
        }

    def get_orders(self, exchange: Optional[str] = None) -> dict[str, Any]:
        """Get cached orders."""
        if exchange:
            return {
                "exchange": exchange,
                "orders": self._orders.get(exchange, []),
                "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            }

        all_orders = []
        for slug, orders in self._orders.items():
            for order in orders:
                order["exchange"] = slug
                all_orders.append(order)

        return {
            "orders": all_orders,
            "exchanges": list(self._orders.keys()),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    async def adopt_untracked_positions(self) -> dict[str, Any]:
        """
        Adopt exchange positions that are not tracked in positions.active.

        This method:
        1. Finds positions in exchange_positions not linked to positions.active
        2. Groups them by symbol to identify pairs (long/short on different exchanges)
        3. Creates positions.active entries for each pair
        4. Marks unpaired positions for attention

        Returns:
            Summary of adopted positions
        """
        if not self._db_session_factory:
            return {"success": False, "error": "Database not initialized"}

        async with self._db_session_factory() as db:
            # Find all exchange positions that are NOT linked to any active position leg
            query = text("""
                SELECT
                    ep.exchange,
                    ep.symbol,
                    ep.side,
                    ep.size,
                    ep.notional_usd,
                    ep.entry_price,
                    ep.mark_price,
                    ep.unrealized_pnl,
                    ep.leverage,
                    ep.margin_mode,
                    ep.updated_at
                FROM positions.exchange_positions ep
                LEFT JOIN positions.legs pl
                    ON ep.exchange = pl.exchange AND ep.symbol = pl.symbol
                WHERE pl.id IS NULL
                    AND ep.size > 0
                ORDER BY ep.symbol, ep.exchange
            """)

            result = await db.execute(query)
            untracked = result.mappings().all()

            if not untracked:
                logger.info("No untracked exchange positions found")
                return {
                    "success": True,
                    "adopted": 0,
                    "unpaired": 0,
                    "message": "No untracked positions to adopt"
                }

            logger.info(f"Found {len(untracked)} untracked exchange positions")

            # Group positions by symbol
            by_symbol: dict[str, list[dict]] = {}
            for pos in untracked:
                symbol = pos["symbol"]
                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append(dict(pos))

            adopted_count = 0
            unpaired_count = 0
            adopted_positions = []

            for symbol, positions in by_symbol.items():
                # Find long and short legs
                long_legs = [p for p in positions if p["side"] == "long"]
                short_legs = [p for p in positions if p["side"] == "short"]

                # Create pairs from available legs
                while long_legs and short_legs:
                    long_leg = long_legs.pop(0)
                    short_leg = short_legs.pop(0)

                    # Create a new position.active entry for this pair
                    position_id = str(uuid4())
                    base_asset = symbol.split("/")[0] if "/" in symbol else symbol.split("-")[0]
                    total_notional = float(long_leg["notional_usd"] or 0) + float(short_leg["notional_usd"] or 0)

                    try:
                        # Insert into positions.active
                        await db.execute(
                            text("""
                                INSERT INTO positions.active (
                                    id, opportunity_id, opportunity_type, symbol, base_asset,
                                    status, health_status, total_capital_deployed,
                                    entry_costs_paid, funding_received, funding_paid,
                                    opened_at, created_at, updated_at
                                ) VALUES (
                                    :id, NULL, 'cross_exchange_perp', :symbol, :base_asset,
                                    'active', 'attention', :capital,
                                    0, 0, 0,
                                    :opened_at, NOW(), NOW()
                                )
                            """),
                            {
                                "id": position_id,
                                "symbol": symbol,
                                "base_asset": base_asset,
                                "capital": total_notional,
                                "opened_at": long_leg["updated_at"],
                            },
                        )

                        # Insert long leg
                        await db.execute(
                            text("""
                                INSERT INTO positions.legs (
                                    position_id, leg_type, exchange, symbol, market_type, side,
                                    quantity, entry_price, current_price, notional_value_usd
                                ) VALUES (
                                    :position_id, 'primary', :exchange, :symbol, 'perpetual', 'long',
                                    :quantity, :entry_price, :current_price, :notional
                                )
                            """),
                            {
                                "position_id": position_id,
                                "exchange": long_leg["exchange"],
                                "symbol": symbol,
                                "quantity": float(long_leg["size"]),
                                "entry_price": float(long_leg["entry_price"]),
                                "current_price": float(long_leg["mark_price"]),
                                "notional": float(long_leg["notional_usd"] or 0),
                            },
                        )

                        # Insert short leg
                        await db.execute(
                            text("""
                                INSERT INTO positions.legs (
                                    position_id, leg_type, exchange, symbol, market_type, side,
                                    quantity, entry_price, current_price, notional_value_usd
                                ) VALUES (
                                    :position_id, 'hedge', :exchange, :symbol, 'perpetual', 'short',
                                    :quantity, :entry_price, :current_price, :notional
                                )
                            """),
                            {
                                "position_id": position_id,
                                "exchange": short_leg["exchange"],
                                "symbol": symbol,
                                "quantity": float(short_leg["size"]),
                                "entry_price": float(short_leg["entry_price"]),
                                "current_price": float(short_leg["mark_price"]),
                                "notional": float(short_leg["notional_usd"] or 0),
                            },
                        )

                        await db.commit()
                        adopted_count += 1
                        adopted_positions.append({
                            "id": position_id,
                            "symbol": symbol,
                            "long_exchange": long_leg["exchange"],
                            "short_exchange": short_leg["exchange"],
                            "notional": total_notional,
                        })

                        logger.info(
                            f"Adopted position pair",
                            symbol=symbol,
                            long_exchange=long_leg["exchange"],
                            short_exchange=short_leg["exchange"],
                            notional=total_notional,
                        )

                    except Exception as e:
                        logger.error(f"Failed to adopt position pair for {symbol}: {e}")
                        await db.rollback()

                # Handle remaining unpaired legs
                remaining_legs = long_legs + short_legs
                for leg in remaining_legs:
                    # Create single-leg position marked for attention
                    position_id = str(uuid4())
                    base_asset = symbol.split("/")[0] if "/" in symbol else symbol.split("-")[0]

                    try:
                        await db.execute(
                            text("""
                                INSERT INTO positions.active (
                                    id, opportunity_id, opportunity_type, symbol, base_asset,
                                    status, health_status, total_capital_deployed,
                                    entry_costs_paid, funding_received, funding_paid,
                                    opened_at, created_at, updated_at
                                ) VALUES (
                                    :id, NULL, 'single_leg', :symbol, :base_asset,
                                    'active', 'warning', :capital,
                                    0, 0, 0,
                                    :opened_at, NOW(), NOW()
                                )
                            """),
                            {
                                "id": position_id,
                                "symbol": symbol,
                                "base_asset": base_asset,
                                "capital": float(leg["notional_usd"] or 0),
                                "opened_at": leg["updated_at"],
                            },
                        )

                        # Insert the single leg
                        leg_type = "primary" if leg["side"] == "long" else "hedge"
                        await db.execute(
                            text("""
                                INSERT INTO positions.legs (
                                    position_id, leg_type, exchange, symbol, market_type, side,
                                    quantity, entry_price, current_price, notional_value_usd
                                ) VALUES (
                                    :position_id, :leg_type, :exchange, :symbol, 'perpetual', :side,
                                    :quantity, :entry_price, :current_price, :notional
                                )
                            """),
                            {
                                "position_id": position_id,
                                "leg_type": leg_type,
                                "exchange": leg["exchange"],
                                "symbol": symbol,
                                "side": leg["side"],
                                "quantity": float(leg["size"]),
                                "entry_price": float(leg["entry_price"]),
                                "current_price": float(leg["mark_price"]),
                                "notional": float(leg["notional_usd"] or 0),
                            },
                        )

                        await db.commit()
                        unpaired_count += 1

                        logger.warning(
                            f"Adopted unpaired position",
                            symbol=symbol,
                            exchange=leg["exchange"],
                            side=leg["side"],
                            notional=leg["notional_usd"],
                        )

                    except Exception as e:
                        logger.error(f"Failed to adopt unpaired position for {symbol}: {e}")
                        await db.rollback()

            # Publish activity event
            await self.redis.publish(
                "nexus:activity",
                json.dumps({
                    "type": "positions_adopted",
                    "service": "position-manager",
                    "level": "info",
                    "message": f"Adopted {adopted_count} paired and {unpaired_count} unpaired positions into tracking",
                    "details": {
                        "adopted_pairs": adopted_count,
                        "unpaired_positions": unpaired_count,
                        "positions": adopted_positions[:10],  # Limit to first 10 for event
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }),
            )

            return {
                "success": True,
                "adopted": adopted_count,
                "unpaired": unpaired_count,
                "positions": adopted_positions,
                "message": f"Adopted {adopted_count} position pairs, {unpaired_count} unpaired positions",
            }
