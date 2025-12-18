"""
Balance Monitor - Periodically fetches balances from all configured exchanges.

Responsibilities:
- Fetch balances from all enabled exchanges with credentials
- Store balances in capital.venue_balances table
- Publish balance updates via Redis
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

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


class BalanceMonitor:
    """Monitors and syncs balances from all configured exchanges."""

    def __init__(
        self,
        redis: RedisClient,
        db_url: str,
        sync_interval: int = 60,
        encryption_key: str = "nexus_secret",
    ):
        self.redis = redis
        self.db_url = db_url
        self.sync_interval = sync_interval
        self.encryption_key = encryption_key

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._db_session_factory: Optional[sessionmaker] = None

        # In-memory balance cache
        self._balances: dict[str, dict[str, Any]] = {}
        self._last_sync: Optional[datetime] = None

    async def start(self) -> None:
        """Start the balance monitoring loop."""
        logger.info("Starting Balance Monitor")

        # Setup database connection
        engine = create_async_engine(self.db_url, echo=False)
        self._db_session_factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info("Balance Monitor started")

    async def stop(self) -> None:
        """Stop the balance monitoring loop."""
        logger.info("Stopping Balance Monitor")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Balance Monitor stopped")

    async def _sync_loop(self) -> None:
        """Main synchronization loop."""
        # Initial sync after a short delay
        await asyncio.sleep(5)

        while self._running:
            try:
                await self.sync_all_balances()
            except Exception as e:
                logger.error("Error in balance sync loop", error=str(e))

            await asyncio.sleep(self.sync_interval)

    async def sync_all_balances(self) -> dict[str, Any]:
        """Sync balances from all enabled exchanges."""
        if not self._db_session_factory:
            return {"success": False, "error": "Database not initialized"}

        async with self._db_session_factory() as db:
            # Get all enabled exchanges
            exchanges = await get_enabled_exchanges(db)
            logger.info(f"Syncing balances for {len(exchanges)} exchanges")

            results: dict[str, Any] = {}
            total_usd = Decimal("0")

            for exchange in exchanges:
                slug = exchange["slug"]
                if not exchange["has_credentials"]:
                    logger.debug(f"Skipping {slug} - no credentials")
                    continue

                try:
                    balance = await self._sync_exchange_balance(db, slug, exchange["api_type"])
                    results[slug] = balance
                    if balance.get("total_usd"):
                        total_usd += Decimal(str(balance["total_usd"]))
                except Exception as e:
                    logger.error(f"Failed to sync balance for {slug}", error=str(e))
                    results[slug] = {"error": str(e)}

            self._last_sync = datetime.utcnow()

            # Publish aggregate balance update
            await self.redis.publish(
                "nexus:capital:balance_update",
                json.dumps({
                    "total_usd": float(total_usd),
                    "exchanges": {k: v.get("total_usd", 0) for k, v in results.items()},
                    "timestamp": self._last_sync.isoformat(),
                }),
            )

            logger.info(
                f"Balance sync complete",
                total_usd=float(total_usd),
                exchanges=len(results),
            )

            return {
                "success": True,
                "total_usd": float(total_usd),
                "exchanges": results,
                "synced_at": self._last_sync.isoformat(),
            }

    async def _sync_exchange_balance(
        self, db: AsyncSession, slug: str, api_type: str
    ) -> dict[str, Any]:
        """Sync balance for a single exchange."""
        # Get credentials
        credentials = await get_exchange_credentials(db, slug, self.encryption_key)
        if not credentials:
            return {"error": "No credentials found"}

        # Create client and fetch balance
        client = ExchangeClient(slug, credentials, api_type)
        connected = await client.connect()

        if not connected:
            return {"error": "Failed to connect"}

        try:
            balance = await client.get_balance()

            # Store in database
            await self._store_balance(db, slug, balance)

            # Update cache
            self._balances[slug] = balance
            self._balances[slug]["updated_at"] = datetime.utcnow().isoformat()

            return balance
        finally:
            await client.disconnect()

    async def _store_balance(
        self, db: AsyncSession, slug: str, balance: dict[str, Any]
    ) -> None:
        """Store balance in the database."""
        query = text("""
            INSERT INTO capital.venue_balances (venue, balances, total_usd, margin_used, margin_available, last_updated)
            VALUES (:venue, :balances, :total_usd, :margin_used, :margin_available, NOW())
            ON CONFLICT (venue) DO UPDATE SET
                balances = :balances,
                total_usd = :total_usd,
                margin_used = :margin_used,
                margin_available = :margin_available,
                last_updated = NOW()
        """)

        await db.execute(
            query,
            {
                "venue": slug,
                "balances": json.dumps(balance.get("balances", {})),
                "total_usd": balance.get("total_usd", 0),
                "margin_used": balance.get("margin_used", 0),
                "margin_available": balance.get("margin_available", 0),
            },
        )
        await db.commit()

    def get_balances(self) -> dict[str, Any]:
        """Get cached balances."""
        total = sum(
            Decimal(str(b.get("total_usd", 0)))
            for b in self._balances.values()
            if isinstance(b.get("total_usd"), (int, float))
        )

        return {
            "total_usd": float(total),
            "exchanges": self._balances.copy(),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
        }

    def get_exchange_balance(self, slug: str) -> Optional[dict[str, Any]]:
        """Get cached balance for a specific exchange."""
        return self._balances.get(slug)

    @property
    def is_running(self) -> bool:
        return self._running
