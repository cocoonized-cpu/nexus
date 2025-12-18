"""
Execution Engine Manager - Handles order execution across exchanges.

Execution flow:
1. Receive opportunity from Capital Allocator
2. Validate system state and pre-trade checks
3. Calculate optimal order parameters (size, timing)
4. Execute both legs simultaneously on real exchanges
5. Monitor fill status and handle partial fills
6. Publish execution events and activity updates
"""

import asyncio
import json
import os
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from shared.events.position import PositionOpenedEvent
from shared.utils.exchange_client import (
    ExchangeClient,
    ExchangeCredentials,
    get_enabled_exchanges,
    get_exchange_credentials,
)
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.system_state import SystemStateManager

logger = get_logger(__name__)


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Order(BaseModel):
    id: str
    opportunity_id: str
    exchange: str
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "limit" or "market"
    size: float
    price: Optional[float] = None
    filled_size: float = 0
    avg_fill_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    exchange_order_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    # Enhanced tracking fields
    trading_fees: Optional[float] = None  # Total fees paid
    fee_currency: Optional[str] = None  # Fee currency (usually quote currency)
    actual_slippage_pct: Optional[float] = None  # Actual slippage vs expected price
    fill_time_ms: Optional[int] = None  # Time to fill in milliseconds
    partial_fill_count: int = 0  # Number of partial fills
    expected_price: Optional[float] = None  # Price at submission time for slippage calc
    paired_order_id: Optional[str] = None  # ID of the paired hedge order


class ExecutionEngine:
    """Manages order execution across exchanges."""

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.state_manager = SystemStateManager(redis, "execution-engine")
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._orders: dict[str, Order] = {}
        self._exchange_clients: dict[str, ExchangeClient] = {}
        self._db_session_factory: Optional[sessionmaker] = None
        self._encryption_key = os.getenv("NEXUS_ENCRYPTION_KEY", "nexus_secret")
        self._stats = {
            "orders_submitted": 0,
            "orders_filled": 0,
            "orders_failed": 0,
            "total_volume_usd": Decimal("0"),
            "start_time": None,
        }

        # Risk limits (loaded from database)
        self._risk_limits = {
            "max_position_size_usd": 5000,  # Default max $5000 per position
        }

        # Partial fill handling configuration
        self._partial_fill_config = {
            "min_fill_ratio_for_complete": 0.95,  # 95% filled = consider complete
            "min_fill_ratio_for_hedge_adjust": 0.50,  # 50% filled and stale = adjust hedge
            "stale_order_age_seconds": 30,  # Order considered stale after 30s
            "max_order_age_seconds": 60,  # Force close orders older than 60s
            "leg_sync_tolerance": 0.05,  # 5% tolerance for leg synchronization
        }

        # Order pairs for tracking synchronized legs
        self._order_pairs: dict[str, tuple[str, str]] = {}  # {pair_id: (long_order_id, short_order_id)}

    async def start(self) -> None:
        """Start the execution engine."""
        logger.info("Starting Execution Engine")
        self._running = True
        self._stats["start_time"] = datetime.utcnow()

        # Initialize database connection
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            engine = create_async_engine(db_url, echo=False)
            self._db_session_factory = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

        # Start system state manager
        await self.state_manager.start()

        # Load risk limits from database
        await self._load_risk_limits()

        # Initialize exchange clients from database
        await self._init_exchange_clients()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._listen_execution_requests()),
            asyncio.create_task(self._listen_close_requests()),
            asyncio.create_task(self._monitor_orders()),
            asyncio.create_task(self._run_redis_listener()),
            asyncio.create_task(self._listen_config_updates()),
            asyncio.create_task(self._monitor_partial_fills()),
        ]

        logger.info(
            "Execution Engine started",
            exchanges=list(self._exchange_clients.keys()),
        )

    async def stop(self) -> None:
        """Stop the execution engine."""
        logger.info("Stopping Execution Engine")
        self._running = False

        # Stop state manager
        await self.state_manager.stop()

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close exchange clients
        for slug, client in self._exchange_clients.items():
            try:
                await client.disconnect()
                logger.debug(f"Disconnected from {slug}")
            except Exception as e:
                logger.warning(f"Error disconnecting from {slug}", error=str(e))

        logger.info("Execution Engine stopped")

    async def _load_risk_limits(self) -> None:
        """Load risk limits from database."""
        if not self._db_session_factory:
            logger.warning("No database connection - using default risk limits")
            return

        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT max_position_size_usd
                    FROM config.risk_limits
                    WHERE is_active = true
                    LIMIT 1
                """))
                row = result.fetchone()

                if row and row[0]:
                    self._risk_limits["max_position_size_usd"] = float(row[0])
                    logger.info(
                        "Loaded risk limits from database",
                        max_position_size_usd=self._risk_limits["max_position_size_usd"],
                    )
                else:
                    logger.warning("No risk limits found in database, using defaults")

        except Exception as e:
            logger.warning("Failed to load risk limits from database", error=str(e))

    async def _listen_config_updates(self) -> None:
        """Listen for config updates via Redis pub/sub."""
        try:
            await self.redis.subscribe(
                "nexus:config:risk_limits_updated",
                self._handle_config_update,
            )
            logger.info("Subscribed to config updates")
        except Exception as e:
            logger.error("Failed to subscribe to config updates", error=str(e))

    async def _handle_config_update(self, channel: str, message: str) -> None:
        """Handle config update notifications."""
        try:
            logger.info("Received config update notification", channel=channel)
            # Reload risk limits from database
            await self._load_risk_limits()
            logger.info(
                "Risk limits reloaded after config update",
                max_position_size_usd=self._risk_limits.get("max_position_size_usd"),
            )
        except Exception as e:
            logger.error("Failed to handle config update", error=str(e))

    async def _init_exchange_clients(self) -> None:
        """Initialize real exchange API clients from database."""
        if not self._db_session_factory:
            logger.warning("No database connection - using mock clients")
            return

        try:
            async with self._db_session_factory() as db:
                # Get all enabled exchanges with credentials
                exchanges = await get_enabled_exchanges(db)
                logger.info(f"Found {len(exchanges)} enabled exchanges")

                for exchange in exchanges:
                    slug = exchange["slug"]

                    if not exchange["has_credentials"]:
                        logger.debug(f"Skipping {slug} - no credentials configured")
                        continue

                    try:
                        # Get decrypted credentials
                        credentials = await get_exchange_credentials(
                            db, slug, self._encryption_key
                        )

                        if not credentials:
                            logger.warning(f"Could not load credentials for {slug}")
                            continue

                        # Create and connect client
                        client = ExchangeClient(
                            slug=slug,
                            credentials=credentials,
                            api_type=exchange["api_type"],
                            sandbox=False,  # Production mode
                        )

                        if await client.connect():
                            self._exchange_clients[slug] = client
                            logger.info(f"Connected to {slug}")

                            # Publish activity
                            try:
                                await self._publish_activity(
                                    "exchange_connected",
                                    {"exchange": slug, "api_type": exchange["api_type"]},
                                )
                            except Exception as pub_err:
                                import traceback
                                logger.error(
                                    f"Failed to publish activity for {slug}",
                                    error=str(pub_err),
                                    traceback=traceback.format_exc()
                                )
                        else:
                            logger.error(f"Failed to connect to {slug}")

                    except Exception as e:
                        logger.error(f"Error initializing {slug}", error=str(e))

            logger.info(
                f"Initialized {len(self._exchange_clients)} exchange clients",
                exchanges=list(self._exchange_clients.keys()),
            )

        except Exception as e:
            logger.error("Failed to initialize exchange clients", error=str(e))

    async def _listen_execution_requests(self) -> None:
        """Listen for execution requests from Capital Allocator."""

        async def handle_request(channel: str, message: str):
            try:
                data = json.loads(message)
                logger.info("Received execution request", data=data)

                result = await self.execute_opportunity(
                    opportunity_id=data["opportunity_id"],
                    position_size_usd=data["position_size_usd"],
                    long_exchange=data.get("long_exchange"),
                    short_exchange=data.get("short_exchange"),
                    symbol=data.get("symbol"),
                    max_slippage_pct=data.get("max_slippage_pct", 0.5),
                )

                # Publish result
                await self.redis.publish(
                    "nexus:execution:result",
                    json.dumps({
                        "opportunity_id": data["opportunity_id"],
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat(),
                    }),
                )

            except Exception as e:
                logger.error("Failed to process execution request", error=str(e))
                await self._publish_activity(
                    "execution_failed",
                    {"error": str(e)},
                    level="error",
                )

        await self.redis.subscribe("nexus:execution:request", handle_request)

        while self._running:
            await asyncio.sleep(1)

    async def _listen_close_requests(self) -> None:
        """Listen for position close requests."""

        async def handle_close(channel: str, message: str):
            try:
                data = json.loads(message)
                logger.info("Received close request", data=data)

                await self.close_position(
                    position_id=data["position_id"],
                    symbol=data["symbol"],
                    long_exchange=data["long_exchange"],
                    short_exchange=data["short_exchange"],
                    size_usd=data.get("size_usd", 0),
                    reason=data.get("reason", "manual"),
                )

            except Exception as e:
                logger.error("Failed to process close request", error=str(e))

        await self.redis.subscribe("nexus:execution:close_request", handle_close)

        while self._running:
            await asyncio.sleep(1)

    async def _run_redis_listener(self) -> None:
        """Run the Redis pub/sub listener to dispatch messages to handlers."""
        try:
            logger.info("Starting Redis listener for execution requests")
            await self.redis.listen()
        except asyncio.CancelledError:
            logger.debug("Redis listener cancelled")
        except Exception as e:
            logger.error("Redis listener error", error=str(e))

    async def _monitor_orders(self) -> None:
        """Monitor pending orders for fills."""
        while self._running:
            try:
                pending = [
                    o
                    for o in self._orders.values()
                    if o.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
                ]

                for order in pending:
                    await self._check_order_status(order)

            except Exception as e:
                logger.error("Error monitoring orders", error=str(e))

            await asyncio.sleep(2)  # Check every 2 seconds

    async def _check_order_status(self, order: Order) -> None:
        """Check and update order status from exchange."""
        client = self._exchange_clients.get(order.exchange)
        if not client:
            return

        try:
            # Get open orders from exchange
            open_orders = await client.get_orders(order.symbol)

            # Find our order
            found = False
            for exchange_order in open_orders:
                if str(exchange_order.get("id")) == str(order.exchange_order_id):
                    found = True
                    filled = float(exchange_order.get("filled", 0))

                    if filled > order.filled_size:
                        order.filled_size = filled
                        order.avg_fill_price = exchange_order.get("price")
                        order.updated_at = datetime.utcnow()

                        if filled >= order.size * 0.99:  # 99% filled = complete
                            order.status = OrderStatus.FILLED
                            self._stats["orders_filled"] += 1
                            await self._publish_activity(
                                "order_filled",
                                {
                                    "order_id": order.id,
                                    "exchange": order.exchange,
                                    "symbol": order.symbol,
                                    "side": order.side,
                                    "filled_size": order.filled_size,
                                    "avg_price": order.avg_fill_price,
                                },
                            )
                        elif filled > 0:
                            order.status = OrderStatus.PARTIAL

                    break

            # If not found in open orders, assume filled
            if not found and order.status == OrderStatus.SUBMITTED:
                # Check if it was recently submitted (give it time)
                age = (datetime.utcnow() - order.created_at).total_seconds()
                if age > 10:  # More than 10 seconds old
                    order.status = OrderStatus.FILLED
                    order.filled_size = order.size
                    self._stats["orders_filled"] += 1
                    logger.info(
                        "Order assumed filled (not in open orders)",
                        order_id=order.id,
                    )
                    await self._publish_activity(
                        "order_filled",
                        {
                            "order_id": order.id,
                            "exchange": order.exchange,
                            "symbol": order.symbol,
                            "side": order.side,
                            "filled_size": order.size,
                        },
                    )

        except Exception as e:
            logger.warning(
                f"Failed to check order status",
                order_id=order.id,
                error=str(e),
            )

    async def _monitor_partial_fills(self) -> None:
        """Monitor and handle partial fills with leg synchronization."""
        while self._running:
            try:
                # Get all partially filled orders
                partial_orders = [
                    o for o in self._orders.values()
                    if o.status == OrderStatus.PARTIAL
                ]

                for order in partial_orders:
                    await self._handle_partial_fill(order)

                # Check leg synchronization for order pairs
                for pair_id, (long_id, short_id) in list(self._order_pairs.items()):
                    long_order = self._orders.get(long_id)
                    short_order = self._orders.get(short_id)

                    if long_order and short_order:
                        if not await self._check_leg_sync(long_order, short_order):
                            await self._handle_leg_desync(long_order, short_order, pair_id)

            except Exception as e:
                logger.error("Error in partial fill monitor", error=str(e))

            await asyncio.sleep(5)  # Check every 5 seconds

    async def _handle_partial_fill(self, order: Order) -> None:
        """
        Handle partial fills - decide to wait, cancel, or adjust hedge.

        Strategy:
        - If nearly complete (>95%), mark as filled
        - If half filled and stale (>30s), adjust the paired hedge leg
        - If too old (>60s) with low fill, cancel and close filled portion
        """
        fill_ratio = order.filled_size / order.size if order.size > 0 else 0
        age_seconds = (datetime.utcnow() - order.created_at).total_seconds()

        config = self._partial_fill_config

        # Track partial fill count
        if order.partial_fill_count == 0 and order.filled_size > 0:
            order.partial_fill_count = 1

        # Nearly complete - mark as filled
        if fill_ratio >= config["min_fill_ratio_for_complete"]:
            order.status = OrderStatus.FILLED
            order.fill_time_ms = int(age_seconds * 1000)
            order.updated_at = datetime.utcnow()
            self._stats["orders_filled"] += 1

            logger.info(
                "Partial order considered complete",
                order_id=order.id,
                fill_ratio=fill_ratio,
                filled_size=order.filled_size,
            )

            await self._publish_activity(
                "order_filled",
                {
                    "order_id": order.id,
                    "exchange": order.exchange,
                    "symbol": order.symbol,
                    "side": order.side,
                    "filled_size": order.filled_size,
                    "fill_ratio": fill_ratio,
                    "partial": True,
                },
            )
            return

        # Half filled and stale - adjust hedge
        if (fill_ratio >= config["min_fill_ratio_for_hedge_adjust"] and
            age_seconds > config["stale_order_age_seconds"]):

            logger.warning(
                "Partial fill stale - adjusting hedge",
                order_id=order.id,
                fill_ratio=fill_ratio,
                age_seconds=age_seconds,
            )

            await self._adjust_hedge_size(order, order.filled_size)
            return

        # Too old with low fill - cancel and close
        if age_seconds > config["max_order_age_seconds"]:
            logger.warning(
                "Order too old - cancelling and closing",
                order_id=order.id,
                fill_ratio=fill_ratio,
                age_seconds=age_seconds,
            )

            await self._cancel_and_close_partial(order)

    async def _adjust_hedge_size(self, filled_order: Order, actual_filled_size: float) -> None:
        """
        Adjust the paired hedge order to match the filled size.

        If we partially filled one leg, we need to reduce the other leg
        to maintain hedge balance.
        """
        paired_id = filled_order.paired_order_id
        if not paired_id:
            logger.warning(
                "Cannot adjust hedge - no paired order",
                order_id=filled_order.id,
            )
            return

        paired_order = self._orders.get(paired_id)
        if not paired_order:
            logger.warning(
                "Cannot adjust hedge - paired order not found",
                order_id=filled_order.id,
                paired_id=paired_id,
            )
            return

        client = self._exchange_clients.get(paired_order.exchange)
        if not client:
            return

        try:
            # Cancel existing paired order
            if paired_order.exchange_order_id:
                await client.cancel_order(paired_order.symbol, paired_order.exchange_order_id)

            # Determine adjusted size
            adjusted_size = actual_filled_size

            # Submit new order with adjusted size
            result = await client.place_order(
                symbol=paired_order.symbol,
                side=paired_order.side,
                size=adjusted_size,
                order_type=paired_order.order_type,
            )

            if result.get("success"):
                # Update paired order with new details
                paired_order.size = adjusted_size
                paired_order.exchange_order_id = str(result.get("order_id", ""))
                paired_order.status = OrderStatus.SUBMITTED
                paired_order.updated_at = datetime.utcnow()

                logger.info(
                    "Hedge order adjusted",
                    original_order_id=filled_order.id,
                    paired_order_id=paired_id,
                    adjusted_size=adjusted_size,
                )

                await self._publish_activity(
                    "hedge_adjusted",
                    {
                        "original_order_id": filled_order.id,
                        "paired_order_id": paired_id,
                        "original_size": paired_order.size,
                        "adjusted_size": adjusted_size,
                        "reason": "partial_fill",
                    },
                )
            else:
                logger.error(
                    "Failed to submit adjusted hedge order",
                    error=result.get("error"),
                )

        except Exception as e:
            logger.error("Error adjusting hedge size", error=str(e))

    async def _cancel_and_close_partial(self, order: Order) -> None:
        """Cancel a partially filled order and close the filled portion."""
        client = self._exchange_clients.get(order.exchange)
        if not client:
            return

        try:
            # Cancel remaining unfilled portion
            if order.exchange_order_id:
                await client.cancel_order(order.symbol, order.exchange_order_id)

            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.utcnow()

            # Close the filled portion if any
            if order.filled_size > 0:
                close_side = "sell" if order.side == "buy" else "buy"

                result = await client.place_order(
                    symbol=order.symbol,
                    side=close_side,
                    size=order.filled_size,
                    order_type="market",
                    reduce_only=True,
                )

                if result.get("success"):
                    logger.info(
                        "Closed partial fill",
                        order_id=order.id,
                        closed_size=order.filled_size,
                    )

                    await self._publish_activity(
                        "partial_fill_closed",
                        {
                            "order_id": order.id,
                            "exchange": order.exchange,
                            "symbol": order.symbol,
                            "closed_size": order.filled_size,
                            "reason": "order_timeout",
                        },
                    )

            # Also close the paired order if exists
            if order.paired_order_id:
                paired_order = self._orders.get(order.paired_order_id)
                if paired_order and paired_order.filled_size > 0:
                    paired_client = self._exchange_clients.get(paired_order.exchange)
                    if paired_client:
                        close_side = "sell" if paired_order.side == "buy" else "buy"
                        await paired_client.place_order(
                            symbol=paired_order.symbol,
                            side=close_side,
                            size=paired_order.filled_size,
                            order_type="market",
                            reduce_only=True,
                        )

        except Exception as e:
            logger.error("Error cancelling and closing partial fill", error=str(e))

    async def _check_leg_sync(self, long_order: Order, short_order: Order) -> bool:
        """
        Check if both legs are synchronized within tolerance.

        Returns True if legs are in sync, False if they need adjustment.
        """
        # If either order is not in a terminal or partial state, they might still sync naturally
        non_final_states = [OrderStatus.PENDING, OrderStatus.SUBMITTED]
        if long_order.status in non_final_states or short_order.status in non_final_states:
            return True  # Still in progress, let them complete

        # Both orders should have some fill
        if not (long_order.filled_size and short_order.filled_size):
            return False

        # Calculate fill ratio between legs
        min_filled = min(long_order.filled_size, short_order.filled_size)
        max_filled = max(long_order.filled_size, short_order.filled_size)

        if max_filled == 0:
            return True

        sync_ratio = min_filled / max_filled
        tolerance = self._partial_fill_config["leg_sync_tolerance"]

        # Synchronized if within tolerance (e.g., 95% sync for 5% tolerance)
        return sync_ratio >= (1 - tolerance)

    async def _handle_leg_desync(
        self,
        long_order: Order,
        short_order: Order,
        pair_id: str,
    ) -> None:
        """
        Handle desynchronized legs by closing the excess on the larger leg.
        """
        long_filled = long_order.filled_size or 0
        short_filled = short_order.filled_size or 0

        logger.warning(
            "Leg desynchronization detected",
            pair_id=pair_id,
            long_filled=long_filled,
            short_filled=short_filled,
        )

        # Determine which leg has excess
        if long_filled > short_filled:
            excess_order = long_order
            excess_amount = long_filled - short_filled
            close_side = "sell"
        else:
            excess_order = short_order
            excess_amount = short_filled - long_filled
            close_side = "buy"

        if excess_amount <= 0:
            return

        client = self._exchange_clients.get(excess_order.exchange)
        if not client:
            return

        try:
            # Close excess amount
            result = await client.place_order(
                symbol=excess_order.symbol,
                side=close_side,
                size=excess_amount,
                order_type="market",
                reduce_only=True,
            )

            if result.get("success"):
                logger.info(
                    "Closed excess from desync",
                    pair_id=pair_id,
                    exchange=excess_order.exchange,
                    excess_amount=excess_amount,
                )

                await self._publish_activity(
                    "leg_desync_corrected",
                    {
                        "pair_id": pair_id,
                        "long_order_id": long_order.id,
                        "short_order_id": short_order.id,
                        "excess_exchange": excess_order.exchange,
                        "excess_closed": excess_amount,
                    },
                )

        except Exception as e:
            logger.error("Failed to correct leg desync", error=str(e))

    def _normalize_exchange_name(self, exchange: str) -> str:
        """Normalize exchange name to match client keys (e.g., 'binance' -> 'binance_futures')."""
        # Map short names to full client names
        exchange_map = {
            "binance": "binance_futures",
            "bybit": "bybit_futures",
            "okx": "okex_futures",
            "okex": "okex_futures",
            "hyperliquid": "hyperliquid_futures",
            "dydx": "dydx_futures",
            "bingx": "bingx_futures",
            "bitget": "bitget_futures",
            "gate": "gate_futures",
            "kucoin": "kucoin_futures",
            "mexc": "mexc_futures",
        }
        # If already a full name or not in map, return as-is
        return exchange_map.get(exchange.lower(), exchange)

    async def execute_opportunity(
        self,
        opportunity_id: str,
        position_size_usd: float,
        long_exchange: Optional[str] = None,
        short_exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        max_slippage_pct: float = 0.5,
    ) -> dict[str, Any]:
        """
        Execute an arbitrage opportunity with real orders.

        Creates and submits orders for both legs simultaneously.
        """
        # Check system state
        if not self.state_manager.should_open_positions():
            reason = "System not accepting new positions"
            if not self.state_manager.is_running:
                reason = "System is not running"
            elif self.state_manager.mode == "discovery":
                reason = "System is in discovery mode (no trading)"
            elif self.state_manager.circuit_breaker_active:
                reason = "Circuit breaker is active"

            logger.warning(
                "Execution blocked by system state",
                reason=reason,
                opportunity_id=opportunity_id,
            )
            return {"success": False, "error": reason}

        # Enforce max position size from risk limits
        max_position_size = self._risk_limits.get("max_position_size_usd", 5000)
        if position_size_usd > max_position_size:
            original_size = position_size_usd
            position_size_usd = max_position_size
            logger.warning(
                "Position size capped to max allowed",
                original_size=original_size,
                capped_size=position_size_usd,
                max_allowed=max_position_size,
                opportunity_id=opportunity_id,
            )

        # Get opportunity details from Redis cache
        opp_data = await self._get_opportunity(opportunity_id)

        if not opp_data:
            # Use provided parameters if opportunity not in cache
            if not all([long_exchange, short_exchange, symbol]):
                return {"success": False, "error": "Opportunity not found and missing parameters"}
            opp_data = {
                "long_exchange": long_exchange,
                "short_exchange": short_exchange,
                "symbol": symbol,
                "current_price": None,
            }

        # Extract opportunity details
        long_ex = opp_data.get("long_exchange") or opp_data.get("hedge_exchange") or long_exchange
        short_ex = opp_data.get("short_exchange") or opp_data.get("primary_exchange") or short_exchange
        sym = opp_data.get("symbol") or symbol

        if not all([long_ex, short_ex, sym]):
            logger.warning("Missing exchange or symbol information", opp_data=opp_data)
            return {"success": False, "error": "Missing exchange or symbol information"}

        # Normalize exchange names (e.g., 'binance' -> 'binance_futures')
        long_ex = self._normalize_exchange_name(long_ex)
        short_ex = self._normalize_exchange_name(short_ex)

        # Get exchange clients
        long_client = self._exchange_clients.get(long_ex)
        short_client = self._exchange_clients.get(short_ex)

        if not long_client:
            logger.warning(
                "Long exchange not connected",
                exchange=long_ex,
                available=list(self._exchange_clients.keys()),
            )
            return {"success": False, "error": f"Long exchange {long_ex} not connected"}
        if not short_client:
            logger.warning(
                "Short exchange not connected",
                exchange=short_ex,
                available=list(self._exchange_clients.keys()),
            )
            return {"success": False, "error": f"Short exchange {short_ex} not connected"}

        logger.info(
            "Executing opportunity",
            opportunity_id=opportunity_id,
            size_usd=position_size_usd,
            symbol=sym,
            long_exchange=long_ex,
            short_exchange=short_ex,
        )

        # Get current price for sizing - MUST fetch real price
        current_price = opp_data.get("current_price")
        if not current_price:
            # Fetch actual price from exchange ticker
            try:
                ticker = await long_client.get_ticker(sym)
                if ticker and ticker.get("last"):
                    current_price = float(ticker["last"])
                    logger.debug(
                        "Fetched current price from exchange",
                        symbol=sym,
                        exchange=long_ex,
                        price=current_price,
                    )
                else:
                    # Try short exchange
                    ticker = await short_client.get_ticker(sym)
                    if ticker and ticker.get("last"):
                        current_price = float(ticker["last"])
                        logger.debug(
                            "Fetched current price from short exchange",
                            symbol=sym,
                            exchange=short_ex,
                            price=current_price,
                        )
            except Exception as e:
                logger.warning("Failed to fetch ticker price", error=str(e))

        if not current_price or current_price <= 0:
            logger.error(
                "Could not determine current price for symbol",
                symbol=sym,
                opportunity_id=opportunity_id,
            )
            return {"success": False, "error": f"Could not determine current price for {sym}"}

        # Calculate position size in base currency
        raw_position_size = position_size_usd / current_price
        logger.debug(
            "Calculated raw position size",
            position_size_usd=position_size_usd,
            current_price=current_price,
            raw_size=raw_position_size,
        )

        # Fetch minimum order sizes and adjust
        try:
            long_min_size = await long_client.get_min_order_size(sym)
            short_min_size = await short_client.get_min_order_size(sym)
            min_size = max(long_min_size or 0, short_min_size or 0)

            if min_size > 0 and raw_position_size < min_size:
                # Check if min size is affordable
                min_size_usd = min_size * current_price
                if min_size_usd > position_size_usd * 2:  # Allow up to 2x overshoot
                    logger.warning(
                        "Minimum order size exceeds position allocation",
                        symbol=sym,
                        min_size=min_size,
                        min_size_usd=min_size_usd,
                        position_size_usd=position_size_usd,
                    )
                    return {
                        "success": False,
                        "error": f"Min order size (${min_size_usd:.2f}) exceeds allocation (${position_size_usd:.2f})",
                    }
                logger.info(
                    "Adjusting position size to meet minimum",
                    original_size=raw_position_size,
                    min_size=min_size,
                    symbol=sym,
                )
                raw_position_size = min_size
        except Exception as e:
            logger.warning("Could not check minimum order sizes", error=str(e))

        position_size = raw_position_size

        execution_id = str(uuid4())
        now = datetime.utcnow()

        # Generate order IDs first so we can link them
        long_order_id = str(uuid4())
        short_order_id = str(uuid4())

        # Create orders with paired order tracking and expected price
        long_order = Order(
            id=long_order_id,
            opportunity_id=opportunity_id,
            exchange=long_ex,
            symbol=sym,
            side="buy",
            order_type="market",  # Use market for execution certainty
            size=position_size,
            created_at=now,
            updated_at=now,
            expected_price=current_price,  # For slippage calculation
            paired_order_id=short_order_id,  # Link to paired hedge order
        )

        short_order = Order(
            id=short_order_id,
            opportunity_id=opportunity_id,
            exchange=short_ex,
            symbol=sym,
            side="sell",
            order_type="market",
            size=position_size,
            created_at=now,
            updated_at=now,
            expected_price=current_price,  # For slippage calculation
            paired_order_id=long_order_id,  # Link to paired hedge order
        )

        # Store orders
        self._orders[long_order.id] = long_order
        self._orders[short_order.id] = short_order

        # Track order pair for leg sync monitoring
        self._order_pairs[execution_id] = (long_order_id, short_order_id)

        # Publish activity - executing
        await self._publish_activity(
            "execution_started",
            {
                "opportunity_id": opportunity_id,
                "execution_id": execution_id,
                "symbol": sym,
                "long_exchange": long_ex,
                "short_exchange": short_ex,
                "position_size_usd": position_size_usd,
                "position_size": position_size,
            },
        )

        # Submit both legs concurrently
        try:
            results = await asyncio.gather(
                self._submit_order(long_order, long_client),
                self._submit_order(short_order, short_client),
                return_exceptions=True,
            )

            # Check results
            long_result = results[0]
            short_result = results[1]

            long_success = isinstance(long_result, dict) and long_result.get("success")
            short_success = isinstance(short_result, dict) and short_result.get("success")

            if long_success and short_success:
                # Both legs submitted successfully
                self._stats["orders_submitted"] += 2
                self._stats["total_volume_usd"] += Decimal(str(position_size_usd * 2))

                # Publish position opened event
                event = PositionOpenedEvent(
                    position_id=execution_id,
                    opportunity_id=opportunity_id,
                    symbol=sym,
                    long_exchange=long_ex,
                    short_exchange=short_ex,
                    size_usd=position_size_usd,
                    timestamp=now,
                )
                await self.redis.publish("nexus:position:opened", event.model_dump_json())

                await self._publish_activity(
                    "position_opened",
                    {
                        "position_id": execution_id,
                        "opportunity_id": opportunity_id,
                        "symbol": sym,
                        "long_exchange": long_ex,
                        "short_exchange": short_ex,
                        "size_usd": position_size_usd,
                        "long_order_id": long_order.exchange_order_id,
                        "short_order_id": short_order.exchange_order_id,
                    },
                )

                return {
                    "success": True,
                    "execution_id": execution_id,
                    "long_order_id": long_order.id,
                    "short_order_id": short_order.id,
                    "long_exchange_order_id": long_order.exchange_order_id,
                    "short_exchange_order_id": short_order.exchange_order_id,
                    "status": "submitted",
                }

            else:
                # One or both legs failed - handle cleanup
                errors = []
                if not long_success:
                    error = long_result.get("error") if isinstance(long_result, dict) else str(long_result)
                    errors.append(f"Long leg failed: {error}")
                    self._stats["orders_failed"] += 1
                if not short_success:
                    error = short_result.get("error") if isinstance(short_result, dict) else str(short_result)
                    errors.append(f"Short leg failed: {error}")
                    self._stats["orders_failed"] += 1

                # If one leg succeeded, we need to close it
                if long_success and not short_success:
                    logger.warning("Long leg filled but short failed - closing long")
                    await self._emergency_close_order(long_order, long_client)
                elif short_success and not long_success:
                    logger.warning("Short leg filled but long failed - closing short")
                    await self._emergency_close_order(short_order, short_client)

                error_msg = "; ".join(errors)
                await self._publish_activity(
                    "execution_failed",
                    {
                        "opportunity_id": opportunity_id,
                        "error": error_msg,
                    },
                    level="error",
                )

                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error("Execution failed with exception", error=str(e))
            self._stats["orders_failed"] += 2
            return {"success": False, "error": str(e)}

    async def _get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        """Fetch opportunity details from Redis cache or database."""
        try:
            # Try Redis cache first
            opp_json = await self.redis.get(f"nexus:opportunity:{opportunity_id}")
            if opp_json:
                return json.loads(opp_json)

            # Try opportunities cache
            opps_json = await self.redis.get("nexus:cache:opportunities")
            if opps_json:
                opps = json.loads(opps_json)
                for opp in opps:
                    if opp.get("id") == opportunity_id:
                        return opp

            return None

        except Exception as e:
            logger.warning(f"Failed to fetch opportunity", error=str(e))
            return None

    async def _submit_order(self, order: Order, client: ExchangeClient) -> dict[str, Any]:
        """Submit order to exchange via client with fee and slippage tracking."""
        submission_time = datetime.utcnow()
        try:
            logger.info(
                "Submitting order",
                order_id=order.id,
                exchange=order.exchange,
                symbol=order.symbol,
                side=order.side,
                size=order.size,
                order_type=order.order_type,
            )

            result = await client.place_order(
                symbol=order.symbol,
                side=order.side,
                size=order.size,
                price=order.price,
                order_type=order.order_type,
            )

            if result.get("success"):
                order.status = OrderStatus.SUBMITTED
                order.exchange_order_id = str(result.get("order_id", ""))
                order.updated_at = datetime.utcnow()

                # Extract fee information from result if available
                if result.get("fee"):
                    order.trading_fees = float(result.get("fee", 0))
                    order.fee_currency = result.get("fee_currency", "USDT")
                elif result.get("fees"):
                    # Some exchanges return fees as a list
                    fees = result.get("fees", [])
                    if isinstance(fees, list) and len(fees) > 0:
                        order.trading_fees = sum(float(f.get("cost", 0)) for f in fees)
                        order.fee_currency = fees[0].get("currency", "USDT") if fees else "USDT"

                # Extract fill price for slippage calculation
                fill_price = result.get("average") or result.get("price") or result.get("fill_price")
                if fill_price and order.expected_price:
                    order.avg_fill_price = float(fill_price)
                    # Calculate slippage as percentage
                    if order.side == "buy":
                        # For buys, slippage is positive if we paid more than expected
                        order.actual_slippage_pct = (
                            (order.avg_fill_price - order.expected_price) / order.expected_price * 100
                        )
                    else:
                        # For sells, slippage is positive if we received less than expected
                        order.actual_slippage_pct = (
                            (order.expected_price - order.avg_fill_price) / order.expected_price * 100
                        )

                # Track fill time if order is immediately filled
                if result.get("status") in ["closed", "filled"]:
                    order.fill_time_ms = int((datetime.utcnow() - submission_time).total_seconds() * 1000)
                    order.filled_size = result.get("filled", order.size)

                logger.info(
                    "Order submitted successfully",
                    order_id=order.id,
                    exchange_order_id=order.exchange_order_id,
                    trading_fees=order.trading_fees,
                    slippage_pct=order.actual_slippage_pct,
                )

                await self._publish_activity(
                    "order_submitted",
                    {
                        "order_id": order.id,
                        "exchange": order.exchange,
                        "exchange_order_id": order.exchange_order_id,
                        "symbol": order.symbol,
                        "side": order.side,
                        "size": order.size,
                        "order_type": order.order_type,
                        "trading_fees": order.trading_fees,
                        "slippage_pct": order.actual_slippage_pct,
                    },
                )

                return {
                    "success": True,
                    "order_id": order.exchange_order_id,
                    "trading_fees": order.trading_fees,
                    "slippage_pct": order.actual_slippage_pct,
                }

            else:
                order.status = OrderStatus.FAILED
                order.error = result.get("error", "Unknown error")
                order.updated_at = datetime.utcnow()

                logger.error(
                    "Order submission failed",
                    order_id=order.id,
                    error=order.error,
                )

                return {"success": False, "error": order.error}

        except Exception as e:
            order.status = OrderStatus.FAILED
            order.error = str(e)
            order.updated_at = datetime.utcnow()

            logger.error(
                "Order submission exception",
                order_id=order.id,
                error=str(e),
            )

            return {"success": False, "error": str(e)}

    async def _emergency_close_order(self, order: Order, client: ExchangeClient) -> None:
        """Emergency close a filled order when the other leg fails."""
        try:
            close_side = "sell" if order.side == "buy" else "buy"

            result = await client.place_order(
                symbol=order.symbol,
                side=close_side,
                size=order.size,
                order_type="market",
                reduce_only=True,
            )

            if result.get("success"):
                logger.info(
                    "Emergency close order submitted",
                    original_order_id=order.id,
                    close_order_id=result.get("order_id"),
                )
            else:
                logger.error(
                    "Emergency close failed",
                    original_order_id=order.id,
                    error=result.get("error"),
                )

        except Exception as e:
            logger.error("Emergency close exception", error=str(e))

    async def close_position(
        self,
        position_id: str,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        size_usd: float = 0,
        reason: str = "manual",
    ) -> dict[str, Any]:
        """Close an existing position."""
        logger.info(
            "Closing position",
            position_id=position_id,
            symbol=symbol,
            reason=reason,
        )

        long_client = self._exchange_clients.get(long_exchange) if long_exchange else None
        short_client = self._exchange_clients.get(short_exchange) if short_exchange else None

        # Allow partial closes - only require at least one exchange
        if not long_client and not short_client:
            logger.warning(
                "Cannot close position - no exchange clients available",
                position_id=position_id,
                symbol=symbol,
                long_exchange=long_exchange,
                short_exchange=short_exchange,
            )
            return {"success": False, "error": "No exchange clients available"}

        try:
            close_results = []
            long_pos = None
            short_pos = None

            # Get and close long position if we have the client
            if long_client:
                long_positions = await long_client.get_positions()
                for pos in long_positions:
                    if pos.get("symbol") == symbol and pos.get("side") == "long":
                        long_pos = pos
                        break

                if long_pos and float(long_pos.get("size", 0)) > 0:
                    result = await long_client.place_order(
                        symbol=symbol,
                        side="sell",
                        size=float(long_pos["size"]),
                        order_type="market",
                        reduce_only=True,
                    )
                    close_results.append(("long", result))
                    logger.info(
                        "Closed long leg",
                        position_id=position_id,
                        symbol=symbol,
                        exchange=long_exchange,
                        size=long_pos.get("size"),
                    )

            # Get and close short position if we have the client
            if short_client:
                short_positions = await short_client.get_positions()
                for pos in short_positions:
                    if pos.get("symbol") == symbol and pos.get("side") == "short":
                        short_pos = pos
                        break

                if short_pos and float(short_pos.get("size", 0)) > 0:
                    result = await short_client.place_order(
                        symbol=symbol,
                        side="buy",
                        size=float(short_pos["size"]),
                        order_type="market",
                        reduce_only=True,
                    )
                    close_results.append(("short", result))
                    logger.info(
                        "Closed short leg",
                        position_id=position_id,
                        symbol=symbol,
                        exchange=short_exchange,
                        size=short_pos.get("size"),
                    )

            # Publish position closed event
            await self.redis.publish(
                "nexus:position:closed",
                json.dumps({
                    "position_id": position_id,
                    "symbol": symbol,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat(),
                }),
            )

            await self._publish_activity(
                "position_closed",
                {
                    "position_id": position_id,
                    "symbol": symbol,
                    "reason": reason,
                    "long_exchange": long_exchange,
                    "short_exchange": short_exchange,
                },
            )

            return {"success": True, "close_results": close_results}

        except Exception as e:
            logger.error("Failed to close position", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_order(self, order_id: str, reason: Optional[str] = None) -> bool:
        """Cancel an order."""
        order = self._orders.get(order_id)
        if not order:
            return False

        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False

        client = self._exchange_clients.get(order.exchange)
        if client and order.exchange_order_id:
            try:
                result = await client.cancel_order(order.symbol, order.exchange_order_id)
                if not result.get("success"):
                    logger.warning(f"Exchange cancel failed", error=result.get("error"))
            except Exception as e:
                logger.warning(f"Cancel order exception", error=str(e))

        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()

        logger.info(f"Order cancelled", order_id=order_id, reason=reason)

        await self._publish_activity(
            "order_cancelled",
            {"order_id": order_id, "reason": reason},
        )

        return True

    async def _publish_activity(
        self,
        activity_type: str,
        details: dict[str, Any],
        level: str = "info",
    ) -> None:
        """Publish activity event for real-time monitoring and persist to database."""
        message = self._format_activity_message(activity_type, details)
        activity = {
            "type": activity_type,
            "service": "execution-engine",
            "level": level,
            "message": message,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Publish to Redis for real-time updates
        try:
            await self.redis.publish("nexus:activity", json.dumps(activity))
        except Exception as e:
            logger.warning(f"Failed to publish activity to Redis", error=str(e))

        # Persist to database for activity log history
        if self._db_session_factory:
            try:
                async with self._db_session_factory() as db:
                    await db.execute(
                        text("""
                            INSERT INTO audit.execution_events
                            (event_type, service, opportunity_id, position_id, allocation_id,
                             exchange, symbol, order_id, side, quantity, price, details, level, message)
                            VALUES (:type, 'execution-engine', :opp_id, :pos_id, :alloc_id,
                                    :exchange, :symbol, :order_id, :side, :quantity, :price,
                                    CAST(:details AS jsonb), :level, :message)
                        """),
                        {
                            "type": activity_type,
                            "opp_id": details.get("opportunity_id"),
                            "pos_id": details.get("position_id"),
                            "alloc_id": details.get("allocation_id"),
                            "exchange": details.get("exchange") or details.get("long_exchange"),
                            "symbol": details.get("symbol"),
                            "order_id": details.get("order_id") or details.get("exchange_order_id"),
                            "side": details.get("side"),
                            "quantity": details.get("size") or details.get("filled_size"),
                            "price": details.get("price") or details.get("avg_price"),
                            "details": json.dumps(details),
                            "level": level,
                            "message": message,
                        },
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to persist activity to database", error=str(e))

    def _format_activity_message(self, activity_type: str, details: dict) -> str:
        """Format a human-readable activity message."""
        # Use if/elif to avoid evaluating all f-strings upfront
        if activity_type == "exchange_connected":
            return f"Connected to {details.get('exchange')}"
        elif activity_type == "execution_started":
            return f"Executing {details.get('symbol')} - ${details.get('position_size_usd', 0):.2f}"
        elif activity_type == "order_submitted":
            side = (details.get('side') or 'unknown').upper()
            size = details.get('size', 0) or 0
            return f"Order submitted to {details.get('exchange')}: {side} {size:.6f} {details.get('symbol')}"
        elif activity_type == "order_filled":
            side = (details.get('side') or 'unknown').upper()
            filled_size = details.get('filled_size', 0) or 0
            return f"Order filled on {details.get('exchange')}: {side} {filled_size:.6f}"
        elif activity_type == "order_cancelled":
            return f"Order cancelled: {details.get('order_id')}"
        elif activity_type == "position_opened":
            return f"Position opened: {details.get('symbol')} (Long: {details.get('long_exchange')}, Short: {details.get('short_exchange')})"
        elif activity_type == "position_closed":
            return f"Position closed: {details.get('symbol')} - {details.get('reason')}"
        elif activity_type == "execution_failed":
            return f"Execution failed: {details.get('error')}"
        else:
            return f"{activity_type}: {details}"

    @property
    def pending_order_count(self) -> int:
        return sum(
            1
            for o in self._orders.values()
            if o.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]
        )

    @property
    def connected_exchange_count(self) -> int:
        return len(self._exchange_clients)

    def get_stats(self) -> dict[str, Any]:
        uptime = None
        if self._stats["start_time"]:
            uptime = (datetime.utcnow() - self._stats["start_time"]).total_seconds()
        return {
            "uptime_seconds": uptime,
            "orders_submitted": self._stats["orders_submitted"],
            "orders_filled": self._stats["orders_filled"],
            "orders_failed": self._stats["orders_failed"],
            "total_volume_usd": float(self._stats["total_volume_usd"]),
            "pending_orders": self.pending_order_count,
            "connected_exchanges": self.connected_exchange_count,
            "exchanges": list(self._exchange_clients.keys()),
            "system_running": self.state_manager.is_running,
            "system_mode": self.state_manager.mode,
        }

    def get_orders(self, status: Optional[str] = None, limit: int = 50) -> list[Order]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status.value == status]
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders[:limit]

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)
