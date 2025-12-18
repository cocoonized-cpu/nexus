"""
Position Manager Core - Tracks positions, P&L, and manages exits.

This module provides comprehensive position lifecycle management:
- Tracks all active positions and their legs
- Monitors position health based on funding rate spreads
- Tracks funding payments from exchanges
- Triggers exits when conditions are met
- Broadcasts activity for real-time UI updates

Position Health Status:
- HEALTHY: Funding rate spread favorable, within risk limits
- DEGRADED: Spread declining or approaching thresholds
- CRITICAL: Stop-loss triggered or spread flipped
- EXITING: Close in progress
"""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.events.position import (
    FundingCollectedEvent,
    PositionClosedEvent,
    PositionHealthChangedEvent,
    PositionExitTriggeredEvent,
    PositionUpdatedEvent,
)
from shared.models.position import PositionHealthStatus
from shared.utils.config import get_settings
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.system_state import SystemStateManager

logger = get_logger(__name__)


# Interaction types for position timeline
class InteractionType:
    POSITION_OPENED = "position_opened"
    HEALTH_CHECK = "health_check"
    HEALTH_CHANGED = "health_changed"
    FUNDING_CHECK = "funding_check"
    FUNDING_COLLECTED = "funding_collected"
    SPREAD_UPDATE = "spread_update"
    REBALANCE_CHECK = "rebalance_check"
    REBALANCE_TRIGGERED = "rebalance_triggered"
    EXIT_EVALUATION = "exit_evaluation"
    EXIT_TRIGGERED = "exit_triggered"
    POSITION_CLOSED = "position_closed"


# Decision types for interactions
class InteractionDecision:
    KEPT_OPEN = "kept_open"
    TRIGGERED_EXIT = "triggered_exit"
    REBALANCED = "rebalanced"
    SKIPPED = "skipped"
    ESCALATED = "escalated"
    DEGRADED = "degraded"
    RECOVERED = "recovered"


class PositionStatus(str, Enum):
    OPENING = "opening"
    ACTIVE = "active"
    CLOSING = "closing"  # Position is being closed
    EXITING = "exiting"
    CLOSED = "closed"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class Position(BaseModel):
    """Tracked position with full lifecycle data."""

    id: str
    opportunity_id: str
    symbol: str
    long_exchange: str
    short_exchange: str
    size_usd: Decimal
    status: PositionStatus = PositionStatus.ACTIVE
    health: HealthStatus = HealthStatus.HEALTHY

    # Funding tracking
    funding_received: Decimal = Decimal("0")
    funding_paid: Decimal = Decimal("0")
    funding_periods_collected: int = 0
    last_funding_check: Optional[datetime] = None

    # P&L tracking
    entry_costs: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    entry_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None

    # Funding rate tracking
    initial_spread: Optional[Decimal] = None  # Spread at entry
    current_spread: Optional[Decimal] = None  # Current spread
    long_funding_rate: Optional[Decimal] = None
    short_funding_rate: Optional[Decimal] = None

    # Spread monitoring (for trend analysis and TradingView-like UI)
    spread_history: list[dict] = Field(default_factory=list)  # Last 60 snapshots (30 min at 30s cadence)
    spread_drawdown_pct: Decimal = Decimal("0")  # Current drawdown from entry spread
    spread_trend: str = "stable"  # rising, falling, stable
    time_to_next_funding: Optional[int] = None  # Seconds until next funding payment

    # Delta exposure tracking
    delta_exposure_pct: Decimal = Decimal("0")  # Current delta exposure percentage
    max_delta_threshold: Decimal = Decimal("10")  # 10% max delta before warning

    # Correlation and rebalancing tracking
    price_correlation: Optional[Decimal] = None  # Rolling correlation between legs (-1 to 1)
    leg_drift_pct: Decimal = Decimal("0")  # Percentage drift between leg notionals
    max_leg_drift_threshold: Decimal = Decimal("5")  # 5% max drift before rebalancing
    last_rebalance_check: Optional[datetime] = None
    rebalance_count: int = 0  # Number of times rebalanced

    # Price history for correlation calculation
    long_price_history: list[float] = Field(default_factory=list)
    short_price_history: list[float] = Field(default_factory=list)
    max_price_history: int = 60  # Last 60 price points for correlation

    # Timing
    opened_at: datetime
    closed_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    degraded_since: Optional[datetime] = None  # Track when position entered DEGRADED state

    # Configuration (loaded from DB config.strategy_parameters)
    min_spread_threshold: Decimal = Decimal("0.005")  # 0.5% minimum spread
    stop_loss_pct: Decimal = Decimal("2")  # 2% stop loss
    max_hold_periods: int = 72  # 24 hours worth of 8h funding periods
    degraded_timeout_seconds: int = 1800  # 30 minutes in DEGRADED before auto-escalation
    spread_drawdown_exit_pct: Decimal = Decimal("50")  # Exit if spread drops 50% from entry
    min_time_to_funding_exit: int = 1800  # Don't exit if funding < 30 min away (configurable)

    class Config:
        arbitrary_types_allowed = True


class PositionManager:
    """
    Manages position lifecycle, health monitoring, and P&L tracking.

    Listens to:
    - Position opened/closed events from execution engine
    - Funding rate updates from aggregator
    - Balance updates for unrealized P&L

    Publishes:
    - Health status changes
    - Funding collected events
    - Exit triggered events
    - Position updates
    """

    def __init__(
        self,
        redis: RedisClient,
        db_session_factory: Optional[Callable] = None,
    ):
        self.redis = redis
        self._db_session_factory = db_session_factory or self._create_db_session_factory()
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._positions: dict[str, Position] = {}

        # System state manager
        self.state_manager: Optional[SystemStateManager] = None

        # Funding rate cache
        self._funding_rates: dict[tuple[str, str], dict[str, Any]] = {}

        # Statistics
        self._stats = {
            "positions_opened": 0,
            "positions_closed": 0,
            "total_funding_collected": Decimal("0"),
            "total_pnl": Decimal("0"),
            "start_time": None,
        }

        # Configuration
        self._health_check_interval = 30  # seconds
        self._funding_check_interval = 60  # seconds - check hourly accumulation
        self._price_update_interval = 10  # seconds

    def _create_db_session_factory(self) -> Callable:
        """Create database session factory."""
        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
        )
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def start(self) -> None:
        """Start the position manager."""
        logger.info("Starting Position Manager")
        self._running = True
        self._stats["start_time"] = datetime.utcnow()

        # Initialize system state manager
        self.state_manager = SystemStateManager(self.redis, "position-manager")
        await self.state_manager.start()

        # Recover existing positions
        await self._recover_positions()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._listen_position_events()),
            asyncio.create_task(self._listen_funding_updates()),
            asyncio.create_task(self._monitor_health()),
            asyncio.create_task(self._track_funding_payments()),
            asyncio.create_task(self._update_prices()),
            asyncio.create_task(self._publish_positions_periodic()),
            asyncio.create_task(self._monitor_correlation_and_rebalancing()),
        ]

        logger.info(
            "Position Manager started",
            active_positions=len(self._positions),
        )

    async def stop(self) -> None:
        """Stop the position manager."""
        logger.info("Stopping Position Manager")
        self._running = False

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.state_manager:
            await self.state_manager.stop()

        logger.info("Position Manager stopped")

    # ==================== Initialization ====================

    async def _recover_positions(self) -> None:
        """Recover positions from Redis cache and database."""
        # First try Redis cache for in-flight positions
        try:
            positions_json = await self.redis.get("nexus:positions:active")
            if positions_json:
                positions_data = json.loads(positions_json)
                for pos_data in positions_data:
                    position = Position(
                        id=pos_data.get("position_id", pos_data.get("id", str(uuid4()))),
                        opportunity_id=pos_data.get("opportunity_id", ""),
                        symbol=pos_data.get("symbol", ""),
                        long_exchange=pos_data.get("long_exchange", pos_data.get("primary_exchange", "")),
                        short_exchange=pos_data.get("short_exchange", pos_data.get("hedge_exchange", "")),
                        size_usd=Decimal(str(pos_data.get("size_usd", 0))),
                        funding_received=Decimal(str(pos_data.get("funding_received", 0))),
                        funding_paid=Decimal(str(pos_data.get("funding_paid", 0))),
                        funding_periods_collected=pos_data.get("funding_periods_collected", 0),
                        opened_at=datetime.fromisoformat(
                            pos_data.get("opened_at", datetime.utcnow().isoformat())
                        ),
                    )
                    self._positions[position.id] = position
                    self._stats["positions_opened"] += 1

                logger.info(f"Recovered {len(self._positions)} positions from cache")

        except Exception as e:
            logger.warning(f"Failed to recover positions from cache", error=str(e))

        # Then load from database to ensure we have all positions including adopted ones
        try:
            await self._load_positions_from_db()
        except Exception as e:
            logger.warning(f"Failed to load positions from database", error=str(e))

    async def _load_positions_from_db(self) -> None:
        """Load active positions from database."""
        async with self._db_session_factory() as db:
            # Get all active positions with their legs
            query = text("""
                SELECT
                    p.id,
                    p.opportunity_id,
                    p.symbol,
                    p.base_asset,
                    p.status,
                    p.health_status,
                    p.total_capital_deployed,
                    p.funding_received,
                    p.funding_paid,
                    p.opened_at,
                    p.created_at,
                    COALESCE(
                        (SELECT exchange FROM positions.legs WHERE position_id = p.id AND side = 'long' LIMIT 1),
                        ''
                    ) as long_exchange,
                    COALESCE(
                        (SELECT exchange FROM positions.legs WHERE position_id = p.id AND side = 'short' LIMIT 1),
                        ''
                    ) as short_exchange
                FROM positions.active p
                WHERE p.status = 'active'
            """)

            result = await db.execute(query)
            rows = result.mappings().all()

            loaded_count = 0
            for row in rows:
                position_id = str(row["id"])

                # Skip if already loaded from Redis
                if position_id in self._positions:
                    continue

                # Map database health_status to HealthStatus enum
                health_map = {
                    "healthy": HealthStatus.HEALTHY,
                    "attention": HealthStatus.DEGRADED,
                    "warning": HealthStatus.DEGRADED,
                    "critical": HealthStatus.CRITICAL,
                }

                position = Position(
                    id=position_id,
                    opportunity_id=str(row["opportunity_id"]) if row["opportunity_id"] else "",
                    symbol=row["symbol"],
                    long_exchange=row["long_exchange"] or "",
                    short_exchange=row["short_exchange"] or "",
                    size_usd=Decimal(str(row["total_capital_deployed"] or 0)),
                    funding_received=Decimal(str(row["funding_received"] or 0)),
                    funding_paid=Decimal(str(row["funding_paid"] or 0)),
                    funding_periods_collected=0,
                    opened_at=row["opened_at"] or row["created_at"] or datetime.utcnow(),
                )
                position.health = health_map.get(row["health_status"], HealthStatus.HEALTHY)

                self._positions[position.id] = position
                loaded_count += 1

            if loaded_count > 0:
                logger.info(f"Loaded {loaded_count} positions from database")

    # ==================== Event Listeners ====================

    async def _listen_position_events(self) -> None:
        """Listen for position lifecycle events."""
        channels = [
            "nexus:position:opened",
            "nexus:position:closing",
            "nexus:position:closed",
        ]

        async def handle_event(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message
                event_type = channel.split(":")[-1]

                if event_type == "opened":
                    await self._on_position_opened(data)
                elif event_type == "closing":
                    await self._on_position_closing(data)
                elif event_type == "closed":
                    await self._on_position_closed(data)

            except Exception as e:
                logger.error(f"Failed to process position event", error=str(e))

        try:
            for channel in channels:
                await self.redis.subscribe(channel, handle_event)

            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in position event listener", error=str(e))

    async def _on_position_opened(self, data: dict[str, Any]) -> None:
        """Handle position opened event."""
        position_id = str(data.get("position_id", str(uuid4())))

        # Don't duplicate if already tracking
        if position_id in self._positions:
            return

        position = Position(
            id=position_id,
            opportunity_id=str(data.get("opportunity_id", "")),
            symbol=data.get("symbol", ""),
            long_exchange=data.get("long_exchange", data.get("primary_exchange", "")),
            short_exchange=data.get("short_exchange", data.get("hedge_exchange", "")),
            size_usd=Decimal(str(data.get("size_usd", 0))),
            entry_costs=Decimal(str(data.get("entry_costs", 0))),
            entry_price=Decimal(str(data.get("entry_price"))) if data.get("entry_price") else None,
            opened_at=datetime.utcnow(),
        )

        # Get initial funding spread
        await self._update_position_funding_rates(position)
        if position.long_funding_rate and position.short_funding_rate:
            position.initial_spread = position.short_funding_rate - position.long_funding_rate

        self._positions[position_id] = position
        self._stats["positions_opened"] += 1

        # Persist to database
        await self._persist_position_to_db(position)

        # Cache active positions
        await self._cache_active_positions()

        # Log interaction for timeline
        initial_spread_str = f"{float(position.initial_spread)*100:.4f}%" if position.initial_spread else "unknown"
        await self._log_interaction(
            position,
            InteractionType.POSITION_OPENED,
            None,
            f"Position opened with ${float(position.size_usd):,.0f} capital. "
            f"Long on {position.long_exchange}, short on {position.short_exchange}. "
            f"Initial funding spread: {initial_spread_str}.",
            {
                "size_usd": float(position.size_usd),
                "long_exchange": position.long_exchange,
                "short_exchange": position.short_exchange,
                "initial_spread": float(position.initial_spread) if position.initial_spread else None,
                "entry_costs": float(position.entry_costs),
            },
        )

        # Publish activity
        await self._publish_activity(
            "position_opened",
            f"Position opened: {position.symbol} on {position.long_exchange}/{position.short_exchange}",
            {
                "position_id": position_id,
                "symbol": position.symbol,
                "size_usd": float(position.size_usd),
                "long_exchange": position.long_exchange,
                "short_exchange": position.short_exchange,
            },
        )

        logger.info(
            f"Position opened",
            position_id=position_id,
            symbol=position.symbol,
            size_usd=float(position.size_usd),
        )

    async def _on_position_closing(self, data: dict[str, Any]) -> None:
        """Handle position closing event."""
        position_id = str(data.get("position_id", ""))
        position = self._positions.get(position_id)

        if position:
            position.status = PositionStatus.EXITING
            logger.info(f"Position closing", position_id=position_id)

    async def _on_position_closed(self, data: dict[str, Any]) -> None:
        """Handle position closed event."""
        position_id = str(data.get("position_id", ""))
        position = self._positions.get(position_id)

        if not position:
            return

        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.utcnow()
        position.exit_reason = data.get("reason", "unknown")

        # Calculate final P&L
        net_funding = position.funding_received - position.funding_paid
        total_pnl = net_funding - position.entry_costs + position.unrealized_pnl

        self._stats["positions_closed"] += 1
        self._stats["total_pnl"] += total_pnl
        self._stats["total_funding_collected"] += max(Decimal("0"), net_funding)

        # Log interaction before removing position
        hold_duration = (position.closed_at - position.opened_at).total_seconds() / 3600 if position.closed_at else 0
        pnl_emoji = "✅" if total_pnl >= 0 else "❌"
        await self._log_interaction(
            position,
            InteractionType.POSITION_CLOSED,
            InteractionDecision.TRIGGERED_EXIT if position.exit_reason else None,
            f"Position closed after {hold_duration:.1f} hours. "
            f"Exit reason: {position.exit_reason or 'unknown'}. "
            f"Final P&L: ${float(total_pnl):+.2f} ({pnl_emoji}). "
            f"Net funding collected: ${float(net_funding):+.2f} over {position.funding_periods_collected} periods.",
            {
                "exit_reason": position.exit_reason,
                "total_pnl": float(total_pnl),
                "net_funding": float(net_funding),
                "funding_received": float(position.funding_received),
                "funding_paid": float(position.funding_paid),
                "funding_periods": position.funding_periods_collected,
                "hold_duration_hours": hold_duration,
                "entry_costs": float(position.entry_costs),
                "unrealized_pnl": float(position.unrealized_pnl),
            },
        )

        # Update position in database with closed status
        await self._close_position_in_db(position, total_pnl)

        # Remove from active tracking
        del self._positions[position_id]

        # Update cache
        await self._cache_active_positions()

        # Publish activity
        await self._publish_activity(
            "position_closed",
            f"Position closed: {position.symbol} - P&L: ${float(total_pnl):.2f}",
            {
                "position_id": position_id,
                "symbol": position.symbol,
                "pnl": float(total_pnl),
                "funding_collected": float(net_funding),
                "exit_reason": position.exit_reason,
            },
            level="info" if total_pnl >= 0 else "warning",
        )

        logger.info(
            f"Position closed",
            position_id=position_id,
            pnl=float(total_pnl),
            funding=float(net_funding),
        )

    async def _listen_funding_updates(self) -> None:
        """Listen for funding rate updates."""
        async def handle_update(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message

                # Handle individual rate update
                if "exchange" in data and "symbol" in data:
                    key = (data["exchange"], data["symbol"])
                    self._funding_rates[key] = {
                        "rate": Decimal(str(data.get("funding_rate", 0))),
                        "timestamp": datetime.utcnow(),
                    }

                # Handle snapshot update
                if "snapshot" in data:
                    snapshot = data["snapshot"]
                    for symbol, exchanges in snapshot.get("rates", {}).items():
                        for exchange, rate_data in exchanges.items():
                            key = (exchange, f"{symbol}/USDT:USDT")
                            self._funding_rates[key] = {
                                "rate": Decimal(str(rate_data.get("funding_rate", 0))),
                                "timestamp": datetime.utcnow(),
                            }

            except Exception as e:
                logger.error(f"Failed to process funding update", error=str(e))

        try:
            await self.redis.subscribe("nexus:market_data:funding_rate", handle_update)
            await self.redis.subscribe("nexus:market_data:unified_snapshot", handle_update)

            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in funding update listener", error=str(e))

    # ==================== Health Monitoring ====================

    async def _monitor_health(self) -> None:
        """Monitor position health status."""
        health_check_count = 0
        while self._running:
            try:
                # Include OPENING and CLOSING positions for spread data collection
                # This ensures charts have data from position open to close
                active_positions = [
                    p for p in self._positions.values()
                    if p.status in [PositionStatus.OPENING, PositionStatus.ACTIVE, PositionStatus.CLOSING]
                ]

                # Check health for each active position
                for position in active_positions:
                    await self._update_position_health(position)

                health_check_count += 1

                # Persist spread snapshots to DB on EVERY health check (every 30s)
                # This is critical for position detail charts to have sufficient data
                for position in active_positions:
                    await self._persist_spread_snapshot(position)

                # Publish heartbeat activity every 6 checks (every 3 minutes with 30s interval)
                if health_check_count % 6 == 0 and active_positions:
                    # Summarize position health (handles both enum and string values)
                    health_summary = {"healthy": 0, "degraded": 0, "critical": 0}
                    for p in active_positions:
                        health_val = p.health.value if isinstance(p.health, HealthStatus) else p.health
                        if health_val == "healthy":
                            health_summary["healthy"] += 1
                        elif health_val == "degraded":
                            health_summary["degraded"] += 1
                        elif health_val == "critical":
                            health_summary["critical"] += 1

                    await self._publish_activity(
                        "health_check_complete",
                        f"Health check: {len(active_positions)} positions monitored ({health_summary['healthy']} healthy, {health_summary['degraded']} degraded, {health_summary['critical']} critical)",
                        {
                            "total_positions": len(active_positions),
                            "health_summary": health_summary,
                            "check_number": health_check_count,
                        },
                        level="info",
                    )

            except Exception as e:
                import traceback
                logger.error("Error monitoring health", error=str(e), traceback=traceback.format_exc())

            await asyncio.sleep(self._health_check_interval)

    async def _update_position_health(self, position: Position) -> None:
        """Update position health based on funding rate trends."""
        old_health = position.health

        # Update funding rates
        await self._update_position_funding_rates(position)

        # Calculate current spread
        if position.long_funding_rate is not None and position.short_funding_rate is not None:
            position.current_spread = position.short_funding_rate - position.long_funding_rate

            # Record spread snapshot for trend analysis and charting
            self._record_spread_snapshot(position)

            # Calculate spread drawdown from entry
            if position.initial_spread and position.initial_spread > 0:
                position.spread_drawdown_pct = (
                    (position.initial_spread - position.current_spread) / position.initial_spread * Decimal("100")
                )

            # Detect spread trend
            position.spread_trend = self._calculate_spread_trend(position)

            # Assess health based on spread
            spread = position.current_spread
            initial = position.initial_spread or spread

            if spread <= Decimal("0"):
                # Spread flipped - critical
                position.health = HealthStatus.CRITICAL
            elif spread < position.min_spread_threshold:
                # Below minimum threshold - degraded
                position.health = HealthStatus.DEGRADED
            elif initial > 0 and spread < initial * Decimal("0.5"):
                # Spread dropped by more than 50% - degraded
                position.health = HealthStatus.DEGRADED
            else:
                position.health = HealthStatus.HEALTHY

        # Check stop loss
        if position.unrealized_pnl < 0:
            loss_pct = abs(position.unrealized_pnl) / position.size_usd * 100
            if loss_pct >= position.stop_loss_pct:
                position.health = HealthStatus.CRITICAL

        # Check max hold time
        if position.funding_periods_collected >= position.max_hold_periods:
            if position.health == HealthStatus.HEALTHY:
                position.health = HealthStatus.DEGRADED

        # Calculate and check delta exposure
        position.delta_exposure_pct = await self._calculate_delta_exposure(position)
        if position.delta_exposure_pct > position.max_delta_threshold:
            if position.health == HealthStatus.HEALTHY:
                position.health = HealthStatus.DEGRADED
                logger.warning(
                    f"High delta exposure detected",
                    position_id=position.id,
                    symbol=position.symbol,
                    delta_pct=float(position.delta_exposure_pct),
                    threshold=float(position.max_delta_threshold),
                )
            # If delta is extremely high (>25%), mark as critical
            if position.delta_exposure_pct > Decimal("25"):
                position.health = HealthStatus.CRITICAL
                logger.error(
                    f"Critical delta exposure - hedges severely unbalanced",
                    position_id=position.id,
                    symbol=position.symbol,
                    delta_pct=float(position.delta_exposure_pct),
                )

        # Check liquidation distance
        liquidation_distance = await self._check_liquidation_distance(position)
        if liquidation_distance is not None:
            if liquidation_distance < 5:  # Less than 5% from liquidation
                position.health = HealthStatus.CRITICAL
                logger.error(
                    f"Position near liquidation",
                    position_id=position.id,
                    symbol=position.symbol,
                    liquidation_distance_pct=liquidation_distance,
                )
            elif liquidation_distance < 10:  # Less than 10% from liquidation
                if position.health == HealthStatus.HEALTHY:
                    position.health = HealthStatus.DEGRADED
                logger.warning(
                    f"Position approaching liquidation",
                    position_id=position.id,
                    symbol=position.symbol,
                    liquidation_distance_pct=liquidation_distance,
                )

        # Check spread deterioration exit condition
        if self._should_exit_on_spread_deterioration(position):
            position.health = HealthStatus.CRITICAL
            logger.warning(
                f"Spread deterioration threshold exceeded",
                position_id=position.id,
                symbol=position.symbol,
                spread_drawdown_pct=float(position.spread_drawdown_pct),
                exit_threshold_pct=float(position.spread_drawdown_exit_pct),
            )

        # Track DEGRADED state timing for timeout mechanism
        if position.health == HealthStatus.DEGRADED:
            if position.degraded_since is None:
                position.degraded_since = datetime.utcnow()
                logger.info(
                    f"Position entered DEGRADED state",
                    position_id=position.id,
                    symbol=position.symbol,
                    timeout_seconds=position.degraded_timeout_seconds,
                )
            else:
                # Check if DEGRADED timeout exceeded
                degraded_duration = (datetime.utcnow() - position.degraded_since).total_seconds()
                if degraded_duration >= position.degraded_timeout_seconds:
                    logger.warning(
                        f"Position DEGRADED timeout exceeded, escalating to CRITICAL",
                        position_id=position.id,
                        symbol=position.symbol,
                        degraded_duration_seconds=degraded_duration,
                    )
                    position.health = HealthStatus.CRITICAL
        elif position.health == HealthStatus.HEALTHY:
            # Reset degraded tracking when healthy again
            if position.degraded_since is not None:
                logger.info(
                    f"Position recovered to HEALTHY state",
                    position_id=position.id,
                    symbol=position.symbol,
                )
            position.degraded_since = None

        # Publish health change if different
        if old_health != position.health:
            await self._on_health_changed(position, old_health)

        # Publish spread update for real-time UI (every health check)
        await self._publish_spread_update(position)

        # Check if should exit
        if position.health == HealthStatus.CRITICAL:
            exit_reason = await self._get_exit_reason(position)
            await self._trigger_exit(position, exit_reason)
        else:
            # Log health check interaction when keeping position open
            # Only log periodically (every 10th check) to avoid flooding, unless health changed
            health_val = position.health.value if isinstance(position.health, HealthStatus) else position.health
            old_health_val = old_health.value if isinstance(old_health, HealthStatus) else old_health

            # Always log when health changes, otherwise log every ~5 minutes (10 checks at 30s interval)
            should_log = old_health_val != health_val

            if should_log:
                spread_str = f"{float(position.current_spread)*100:.4f}%" if position.current_spread else "unknown"
                trend_desc = {
                    "rising": "improving",
                    "falling": "declining",
                    "stable": "stable",
                }.get(position.spread_trend, "unknown")

                if health_val == "healthy":
                    narrative = (
                        f"Health check: Position is healthy. "
                        f"Funding spread at {spread_str} ({trend_desc}). "
                        f"Keeping position open."
                    )
                elif health_val == "degraded":
                    narrative = (
                        f"Health check: Position is DEGRADED. "
                        f"Funding spread at {spread_str} ({trend_desc}). "
                        f"Monitoring closely for recovery or further deterioration."
                    )
                    if position.degraded_since:
                        degraded_duration = (datetime.utcnow() - position.degraded_since).total_seconds()
                        remaining = position.degraded_timeout_seconds - degraded_duration
                        if remaining > 0:
                            narrative += f" Will escalate to CRITICAL in {remaining/60:.0f} minutes if not recovered."
                else:
                    narrative = f"Health check: Position health is {health_val}."

                await self._log_interaction(
                    position,
                    InteractionType.HEALTH_CHECK,
                    InteractionDecision.KEPT_OPEN,
                    narrative,
                    {
                        "health": health_val,
                        "previous_health": old_health_val,
                        "current_spread": float(position.current_spread) if position.current_spread else None,
                        "initial_spread": float(position.initial_spread) if position.initial_spread else None,
                        "spread_drawdown_pct": float(position.spread_drawdown_pct),
                        "spread_trend": position.spread_trend,
                        "long_funding_rate": float(position.long_funding_rate) if position.long_funding_rate else None,
                        "short_funding_rate": float(position.short_funding_rate) if position.short_funding_rate else None,
                        "delta_exposure_pct": float(position.delta_exposure_pct),
                        "funding_periods": position.funding_periods_collected,
                    },
                )

    async def _update_position_funding_rates(self, position: Position) -> None:
        """Fetch current funding rates for position's exchanges."""
        # Get long exchange rate
        long_key = (position.long_exchange, position.symbol)
        if long_key in self._funding_rates:
            position.long_funding_rate = self._funding_rates[long_key]["rate"]

        # Get short exchange rate
        short_key = (position.short_exchange, position.symbol)
        if short_key in self._funding_rates:
            position.short_funding_rate = self._funding_rates[short_key]["rate"]

    async def _calculate_delta_exposure(self, position: Position) -> Decimal:
        """
        Calculate the delta exposure percentage for a position.

        Delta exposure = |long_notional - short_notional| / (long_notional + short_notional) * 100

        Returns 0 if no data available, or the delta percentage if calculable.
        """
        try:
            async with self._db_session_factory() as db:
                query = text("""
                    SELECT exchange, side, size, notional_usd
                    FROM positions.exchange_positions
                    WHERE symbol = :symbol
                      AND exchange IN (:long_ex, :short_ex)
                      AND size > 0
                """)
                result = await db.execute(
                    query,
                    {
                        "symbol": position.symbol,
                        "long_ex": position.long_exchange,
                        "short_ex": position.short_exchange,
                    },
                )
                rows = result.fetchall()

                if not rows:
                    return Decimal("0")

                long_notional = Decimal("0")
                short_notional = Decimal("0")

                for row in rows:
                    exchange, side, size, notional = row
                    notional_dec = Decimal(str(notional or 0))
                    if side == "long":
                        long_notional = notional_dec
                    elif side == "short":
                        short_notional = notional_dec

                total_notional = long_notional + short_notional
                if total_notional == 0:
                    return Decimal("0")

                delta = abs(long_notional - short_notional) / total_notional * 100
                return delta.quantize(Decimal("0.01"))

        except Exception as e:
            logger.warning(
                f"Failed to calculate delta exposure",
                position_id=position.id,
                error=str(e),
            )
            return Decimal("0")

    async def _monitor_correlation_and_rebalancing(self) -> None:
        """Monitor price correlation between legs and check for rebalancing needs."""
        while self._running:
            try:
                active_positions = [
                    p for p in self._positions.values()
                    if p.status == PositionStatus.ACTIVE
                ]

                for position in active_positions:
                    # Calculate price correlation
                    await self._update_price_correlation(position)

                    # Check for leg drift and potential rebalancing
                    await self._check_rebalancing_need(position)

            except Exception as e:
                logger.error("Error in correlation/rebalancing monitor", error=str(e))

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _update_price_correlation(self, position: Position) -> None:
        """
        Calculate rolling correlation between leg prices.

        High correlation (>0.95) is expected for arbitrage.
        Correlation breakdown may indicate execution issues or market dislocations.
        """
        try:
            async with self._db_session_factory() as db:
                # Fetch recent price snapshots for both legs
                query = text("""
                    SELECT exchange, mark_price, updated_at
                    FROM positions.exchange_positions
                    WHERE symbol = :symbol
                      AND exchange IN (:long_ex, :short_ex)
                      AND size > 0
                    ORDER BY updated_at DESC
                    LIMIT 2
                """)
                result = await db.execute(
                    query,
                    {
                        "symbol": position.symbol,
                        "long_ex": position.long_exchange,
                        "short_ex": position.short_exchange,
                    },
                )
                rows = result.fetchall()

                if len(rows) < 2:
                    return

                # Extract prices
                long_price = None
                short_price = None
                for row in rows:
                    exchange, mark_price, _ = row
                    if exchange == position.long_exchange and mark_price:
                        long_price = float(mark_price)
                    elif exchange == position.short_exchange and mark_price:
                        short_price = float(mark_price)

                if long_price and short_price:
                    # Add to price history
                    position.long_price_history.append(long_price)
                    position.short_price_history.append(short_price)

                    # Trim to max size
                    if len(position.long_price_history) > position.max_price_history:
                        position.long_price_history = position.long_price_history[-position.max_price_history:]
                        position.short_price_history = position.short_price_history[-position.max_price_history:]

                    # Calculate correlation if enough data
                    if len(position.long_price_history) >= 10:
                        correlation = self._calculate_pearson_correlation(
                            position.long_price_history,
                            position.short_price_history,
                        )
                        position.price_correlation = Decimal(str(round(correlation, 4)))

                        # Log warning if correlation is breaking down
                        if correlation < 0.9:
                            logger.warning(
                                "Price correlation breakdown detected",
                                position_id=position.id,
                                symbol=position.symbol,
                                correlation=correlation,
                            )

        except Exception as e:
            logger.warning(
                "Failed to update price correlation",
                position_id=position.id,
                error=str(e),
            )

    def _calculate_pearson_correlation(self, x: list[float], y: list[float]) -> float:
        """Calculate Pearson correlation coefficient between two series."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # Calculate covariance and standard deviations
        covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = (sum((xi - mean_x) ** 2 for xi in x) / n) ** 0.5
        std_y = (sum((yi - mean_y) ** 2 for yi in y) / n) ** 0.5

        if std_x == 0 or std_y == 0:
            return 1.0  # Constant values = perfect correlation

        return covariance / (std_x * std_y)

    async def _check_rebalancing_need(self, position: Position) -> None:
        """
        Check if position legs have drifted and need rebalancing.

        Drift can occur from:
        - Partial fills during entry
        - Price movement with different leverage
        - Different margin requirements
        """
        try:
            position.leg_drift_pct = await self._calculate_leg_drift(position)

            if position.leg_drift_pct > position.max_leg_drift_threshold:
                should_rebalance = await self._should_rebalance(position)

                if should_rebalance:
                    await self._trigger_rebalance(position)

        except Exception as e:
            logger.warning(
                "Failed to check rebalancing need",
                position_id=position.id,
                error=str(e),
            )

    async def _calculate_leg_drift(self, position: Position) -> Decimal:
        """Calculate percentage drift between leg notionals."""
        try:
            async with self._db_session_factory() as db:
                query = text("""
                    SELECT exchange, side, notional_usd
                    FROM positions.exchange_positions
                    WHERE symbol = :symbol
                      AND exchange IN (:long_ex, :short_ex)
                      AND size > 0
                """)
                result = await db.execute(
                    query,
                    {
                        "symbol": position.symbol,
                        "long_ex": position.long_exchange,
                        "short_ex": position.short_exchange,
                    },
                )
                rows = result.fetchall()

                if len(rows) < 2:
                    return Decimal("0")

                long_notional = Decimal("0")
                short_notional = Decimal("0")

                for row in rows:
                    exchange, side, notional = row
                    notional_dec = Decimal(str(notional or 0))
                    if side == "long":
                        long_notional = notional_dec
                    elif side == "short":
                        short_notional = notional_dec

                if long_notional == 0 and short_notional == 0:
                    return Decimal("0")

                avg_notional = (long_notional + short_notional) / 2
                if avg_notional == 0:
                    return Decimal("0")

                drift = abs(long_notional - short_notional) / avg_notional * 100
                return drift.quantize(Decimal("0.01"))

        except Exception as e:
            logger.warning(
                "Failed to calculate leg drift",
                position_id=position.id,
                error=str(e),
            )
            return Decimal("0")

    async def _should_rebalance(self, position: Position) -> bool:
        """
        Determine if position should be rebalanced based on multiple factors.

        Considers:
        - Drift magnitude
        - Time since last rebalance
        - Time to next funding
        - Rebalancing cost vs expected benefit
        """
        # Don't rebalance too frequently (min 5 minutes between rebalances)
        if position.last_rebalance_check:
            time_since_last = (datetime.utcnow() - position.last_rebalance_check).total_seconds()
            if time_since_last < 300:  # 5 minutes
                return False

        # Don't rebalance if close to funding time (within 30 min)
        if position.time_to_next_funding and position.time_to_next_funding < 1800:
            return False

        # Only rebalance if drift is significant
        if position.leg_drift_pct < position.max_leg_drift_threshold:
            return False

        # Estimate rebalancing cost (fees + slippage)
        estimated_rebalance_cost = float(position.size_usd) * 0.001  # ~0.1% cost

        # Estimate drift cost if not rebalanced (imperfect hedge)
        drift_risk_cost = float(position.size_usd) * float(position.leg_drift_pct) / 100 * 0.1

        # Rebalance only if benefit exceeds cost
        return drift_risk_cost > estimated_rebalance_cost * 2

    async def _trigger_rebalance(self, position: Position) -> None:
        """Trigger a rebalancing operation for the position."""
        position.last_rebalance_check = datetime.utcnow()
        position.rebalance_count += 1

        # Log interaction for rebalancing
        await self._log_interaction(
            position,
            InteractionType.REBALANCE_TRIGGERED,
            InteractionDecision.REBALANCED,
            f"⚖️ Rebalancing triggered (#{position.rebalance_count}). "
            f"Leg drift of {float(position.leg_drift_pct):.2f}% exceeded {float(position.max_leg_drift_threshold):.1f}% threshold. "
            f"Long and short legs will be adjusted to restore delta neutrality.",
            {
                "leg_drift_pct": float(position.leg_drift_pct),
                "max_drift_threshold": float(position.max_leg_drift_threshold),
                "rebalance_count": position.rebalance_count,
                "delta_exposure_pct": float(position.delta_exposure_pct),
                "price_correlation": float(position.price_correlation) if position.price_correlation else None,
            },
        )

        # Publish rebalancing request to execution engine
        rebalance_request = {
            "position_id": position.id,
            "symbol": position.symbol,
            "long_exchange": position.long_exchange,
            "short_exchange": position.short_exchange,
            "current_drift_pct": float(position.leg_drift_pct),
            "action": "rebalance",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.redis.publish("nexus:execution:rebalance_request", json.dumps(rebalance_request))

        # Publish activity
        await self._publish_activity(
            "rebalance_triggered",
            f"Rebalancing triggered for {position.symbol} - drift: {position.leg_drift_pct}%",
            {
                "position_id": position.id,
                "symbol": position.symbol,
                "drift_pct": float(position.leg_drift_pct),
                "rebalance_count": position.rebalance_count,
            },
            level="warning",
        )

        logger.info(
            "Rebalancing triggered",
            position_id=position.id,
            symbol=position.symbol,
            drift_pct=float(position.leg_drift_pct),
        )

    def get_optimal_exit_window(self, position: Position) -> dict:
        """
        Calculate optimal exit window based on funding schedule and spread trend.

        Returns window with earliest and latest recommended exit times.
        """
        now = datetime.utcnow()

        # Default window: anytime in the next 24 hours
        earliest_exit = now
        latest_exit = now + timedelta(hours=24)

        # Factor 1: Time to next funding
        if position.time_to_next_funding:
            seconds_to_funding = position.time_to_next_funding

            if seconds_to_funding < 1800:  # Within 30 minutes of funding
                # Wait for funding payment unless urgent
                if position.health != HealthStatus.CRITICAL:
                    earliest_exit = now + timedelta(seconds=seconds_to_funding + 300)

            elif seconds_to_funding > 25200:  # More than 7 hours to funding
                # Good time to exit - won't miss funding
                pass

        # Factor 2: Spread trend
        if position.spread_trend == "falling":
            # Exit sooner if spread is declining
            latest_exit = now + timedelta(hours=4)
        elif position.spread_trend == "rising":
            # Can wait longer if spread is improving
            latest_exit = now + timedelta(hours=12)

        # Factor 3: Position health
        if position.health == HealthStatus.CRITICAL:
            earliest_exit = now  # Exit immediately
            latest_exit = now + timedelta(minutes=30)
        elif position.health == HealthStatus.DEGRADED:
            latest_exit = min(latest_exit, now + timedelta(hours=2))

        # Factor 4: Max hold time
        position_age = (now - position.opened_at).total_seconds()
        max_hold_seconds = position.max_hold_periods * 8 * 3600  # 8 hours per period
        remaining_hold_time = max_hold_seconds - position_age

        if remaining_hold_time < 0:
            latest_exit = now  # Should have exited already
        else:
            latest_exit = min(latest_exit, now + timedelta(seconds=remaining_hold_time))

        return {
            "position_id": position.id,
            "earliest_exit": earliest_exit.isoformat(),
            "latest_exit": latest_exit.isoformat(),
            "time_to_funding_seconds": position.time_to_next_funding,
            "spread_trend": position.spread_trend,
            "health": position.health.value if isinstance(position.health, HealthStatus) else position.health,
            "recommendation": self._get_exit_recommendation(position, earliest_exit, latest_exit),
        }

    def _get_exit_recommendation(
        self,
        position: Position,
        earliest: datetime,
        latest: datetime,
    ) -> str:
        """Generate human-readable exit recommendation."""
        now = datetime.utcnow()

        if position.health == HealthStatus.CRITICAL:
            return "Exit immediately - position is critical"

        if latest <= now:
            return "Exit now - max hold time reached"

        hours_until_earliest = (earliest - now).total_seconds() / 3600
        hours_until_latest = (latest - now).total_seconds() / 3600

        if position.spread_trend == "falling":
            return f"Consider exit within {hours_until_latest:.1f}h - spread declining"

        if position.time_to_next_funding and position.time_to_next_funding < 3600:
            return f"Wait {position.time_to_next_funding // 60}min for funding, then evaluate"

        if position.health == HealthStatus.DEGRADED:
            return f"Exit within {hours_until_latest:.1f}h - position degraded"

        return f"Optimal exit window: {hours_until_earliest:.1f}h to {hours_until_latest:.1f}h"

    def _record_spread_snapshot(self, position: Position, max_snapshots: int = 60) -> None:
        """
        Record spread snapshot for trend analysis.

        Stores last 60 snapshots (30 min at 30s health check cadence).
        Used for TradingView-like charting and spread trend detection.
        """
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "spread": float(position.current_spread) if position.current_spread else None,
            "long_rate": float(position.long_funding_rate) if position.long_funding_rate else None,
            "short_rate": float(position.short_funding_rate) if position.short_funding_rate else None,
        }
        position.spread_history.append(snapshot)
        if len(position.spread_history) > max_snapshots:
            position.spread_history = position.spread_history[-max_snapshots:]

    def _calculate_spread_trend(self, position: Position) -> str:
        """
        Calculate spread trend from recent history.

        Compares average of last 2 snapshots vs previous 2 snapshots (2 min window).
        Returns: 'rising', 'falling', or 'stable'
        """
        if len(position.spread_history) < 4:
            return "stable"

        recent = [s["spread"] for s in position.spread_history[-4:] if s["spread"] is not None]
        if len(recent) < 4:
            return "stable"

        avg_first = sum(recent[:2]) / 2
        avg_second = sum(recent[2:]) / 2
        diff = avg_second - avg_first

        # Threshold: 0.05% change indicates trend
        if diff > 0.0005:
            return "rising"
        elif diff < -0.0005:
            return "falling"
        return "stable"

    def _should_exit_on_spread_deterioration(self, position: Position) -> bool:
        """
        Check if position should exit due to spread deterioration.

        Considers:
        1. Don't exit if close to funding time (capture payment first)
        2. Exit if spread drawdown exceeds configured threshold
        """
        # Don't exit if close to funding time (configurable protection window)
        if position.time_to_next_funding is not None and position.time_to_next_funding < position.min_time_to_funding_exit:
            return False

        # Exit if spread drawdown exceeds threshold
        if position.spread_drawdown_pct >= position.spread_drawdown_exit_pct:
            return True

        return False

    async def _check_liquidation_distance(self, position: Position) -> Optional[float]:
        """
        Check liquidation distance for position's exchange positions.

        Returns the minimum distance to liquidation as a percentage,
        or None if no liquidation data is available.
        """
        try:
            async with self._db_session_factory() as db:
                query = text("""
                    SELECT exchange, side, mark_price, liquidation_price
                    FROM positions.exchange_positions
                    WHERE symbol = :symbol
                      AND exchange IN (:long_ex, :short_ex)
                      AND size > 0
                      AND liquidation_price IS NOT NULL
                      AND liquidation_price > 0
                """)
                result = await db.execute(
                    query,
                    {
                        "symbol": position.symbol,
                        "long_ex": position.long_exchange,
                        "short_ex": position.short_exchange,
                    }
                )
                rows = result.fetchall()

                if not rows:
                    return None

                min_distance = float("inf")
                for row in rows:
                    exchange, side, mark_price, liq_price = row
                    if mark_price is None or liq_price is None:
                        continue

                    mark_dec = Decimal(str(mark_price))
                    liq_dec = Decimal(str(liq_price))

                    if mark_dec <= 0:
                        continue

                    # Calculate distance to liquidation as percentage
                    # For long: (mark - liq) / mark * 100
                    # For short: (liq - mark) / mark * 100
                    if side == "long":
                        distance = float((mark_dec - liq_dec) / mark_dec * 100)
                    else:  # short
                        distance = float((liq_dec - mark_dec) / mark_dec * 100)

                    # Take the minimum (closest to liquidation)
                    if distance < min_distance:
                        min_distance = distance

                return min_distance if min_distance != float("inf") else None

        except Exception as e:
            logger.warning(
                f"Failed to check liquidation distance",
                position_id=position.id,
                error=str(e),
            )
            return None

    async def _get_exit_reason(self, position: Position) -> str:
        """Determine the exit reason based on position state."""
        if position.current_spread is not None and position.current_spread <= 0:
            return "spread_flipped"

        if position.unrealized_pnl < 0:
            loss_pct = abs(position.unrealized_pnl) / position.size_usd * 100
            if loss_pct >= position.stop_loss_pct:
                return "stop_loss"

        if position.funding_periods_collected >= position.max_hold_periods:
            return "max_hold_time"

        if position.current_spread is not None and position.current_spread < position.min_spread_threshold:
            return "spread_below_threshold"

        # Check if delta exposure is critical
        if position.delta_exposure_pct > Decimal("25"):
            return "delta_critical"

        # Check if near liquidation
        liq_distance = await self._check_liquidation_distance(position)
        if liq_distance is not None and liq_distance < 5:
            return "liquidation_imminent"

        # Check if spread deterioration threshold exceeded
        if position.spread_drawdown_pct >= position.spread_drawdown_exit_pct:
            return "spread_deterioration"

        # Check if escalated due to DEGRADED timeout
        if position.degraded_since is not None:
            degraded_duration = (datetime.utcnow() - position.degraded_since).total_seconds()
            if degraded_duration >= position.degraded_timeout_seconds:
                return "degraded_timeout"

        return "health_critical"

    async def _on_health_changed(self, position: Position, old_health) -> None:
        """Handle health status change."""
        # Map to shared model health status (handles both enum and string)
        health_map = {
            HealthStatus.HEALTHY: PositionHealthStatus.HEALTHY,
            HealthStatus.DEGRADED: PositionHealthStatus.WARNING,
            HealthStatus.CRITICAL: PositionHealthStatus.CRITICAL,
            "healthy": PositionHealthStatus.HEALTHY,
            "degraded": PositionHealthStatus.WARNING,
            "critical": PositionHealthStatus.CRITICAL,
        }

        event = PositionHealthChangedEvent(
            position_id=position.id,
            symbol=position.symbol,
            previous_health=health_map.get(old_health, PositionHealthStatus.HEALTHY),
            current_health=health_map.get(position.health, PositionHealthStatus.HEALTHY),
            trigger_metric="funding_spread",
            trigger_value=position.current_spread or Decimal("0"),
        )
        await self.redis.publish("nexus:position:health_changed", event.model_dump_json())

        # Helper to safely get health value (handles both enum and string)
        def get_health_value(health):
            return health.value if isinstance(health, HealthStatus) else health

        old_health_value = get_health_value(old_health)
        new_health_value = get_health_value(position.health)

        # Publish activity
        level = "info"
        if new_health_value == "degraded":
            level = "warning"
        elif new_health_value == "critical":
            level = "error"

        await self._publish_activity(
            "position_health_changed",
            f"Position health: {position.symbol} {old_health_value} → {new_health_value}",
            {
                "position_id": position.id,
                "symbol": position.symbol,
                "old_health": old_health_value,
                "new_health": new_health_value,
                "spread": float(position.current_spread) if position.current_spread else None,
            },
            level=level,
        )

        logger.info(
            f"Position health changed",
            position_id=position.id,
            old=old_health_value,
            new=new_health_value,
        )

    async def _publish_spread_update(self, position: Position) -> None:
        """Publish spread update event for real-time UI."""
        # Handle health as either enum or string
        health_value = position.health.value if isinstance(position.health, HealthStatus) else position.health
        spread_event = {
            "position_id": position.id,
            "symbol": position.symbol,
            "current_spread": float(position.current_spread) if position.current_spread else None,
            "initial_spread": float(position.initial_spread) if position.initial_spread else None,
            "spread_drawdown_pct": float(position.spread_drawdown_pct),
            "spread_trend": position.spread_trend,
            "long_rate": float(position.long_funding_rate) if position.long_funding_rate else None,
            "short_rate": float(position.short_funding_rate) if position.short_funding_rate else None,
            "long_exchange": position.long_exchange,
            "short_exchange": position.short_exchange,
            "health": health_value,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.redis.publish("nexus:position:spread_update", json.dumps(spread_event))

    async def _persist_spread_snapshot(self, position: Position) -> None:
        """
        Persist spread snapshot to database for charting.

        Called periodically to store time-series data for TradingView-like charts.
        """
        if position.current_spread is None:
            return

        try:
            async with self._db_session_factory() as db:
                await db.execute(
                    text("""
                        INSERT INTO positions.spread_snapshots
                        (position_id, spread, long_rate, short_rate, price, timestamp)
                        VALUES (:pos_id, :spread, :long_rate, :short_rate, :price, NOW())
                    """),
                    {
                        "pos_id": position.id,
                        "spread": float(position.current_spread),
                        "long_rate": float(position.long_funding_rate) if position.long_funding_rate else None,
                        "short_rate": float(position.short_funding_rate) if position.short_funding_rate else None,
                        "price": float(position.current_price) if position.current_price else None,
                    },
                )
                await db.commit()
        except Exception as e:
            logger.warning(
                "Failed to persist spread snapshot",
                position_id=position.id,
                error=str(e),
            )

    async def _trigger_exit(self, position: Position, reason: str) -> None:
        """Trigger position exit."""
        if position.status == PositionStatus.EXITING:
            return  # Already exiting

        position.status = PositionStatus.EXITING

        # Map exit reasons to human-readable narratives
        reason_narratives = {
            "spread_flipped": "Funding spread has flipped negative - arbitrage is now costing money instead of earning.",
            "stop_loss": f"Stop loss triggered - unrealized loss exceeded {float(position.stop_loss_pct)}% threshold.",
            "max_hold_time": f"Maximum hold time reached - position has collected {position.funding_periods_collected} funding periods.",
            "spread_below_threshold": f"Funding spread dropped below minimum threshold of {float(position.min_spread_threshold)*100:.2f}%.",
            "delta_critical": f"Critical delta exposure of {float(position.delta_exposure_pct):.1f}% - hedges severely unbalanced.",
            "liquidation_imminent": "Position is dangerously close to liquidation price.",
            "spread_deterioration": f"Spread has deteriorated {float(position.spread_drawdown_pct):.1f}% from entry, exceeding {float(position.spread_drawdown_exit_pct):.0f}% threshold.",
            "degraded_timeout": f"Position remained in DEGRADED state for over {position.degraded_timeout_seconds/60:.0f} minutes without recovery.",
            "health_critical": "Position health is critical - immediate exit required.",
            "manual": "Manual exit requested by user.",
        }

        detailed_narrative = reason_narratives.get(reason, f"Exit triggered: {reason}")
        spread_str = f"{float(position.current_spread)*100:.4f}%" if position.current_spread else "unknown"

        await self._log_interaction(
            position,
            InteractionType.EXIT_TRIGGERED,
            InteractionDecision.TRIGGERED_EXIT,
            f"🚨 EXIT TRIGGERED: {detailed_narrative} Current spread: {spread_str}.",
            {
                "exit_reason": reason,
                "urgency": "immediate" if reason in ["stop_loss", "spread_flipped", "liquidation_imminent"] else "normal",
                "current_spread": float(position.current_spread) if position.current_spread else None,
                "initial_spread": float(position.initial_spread) if position.initial_spread else None,
                "spread_drawdown_pct": float(position.spread_drawdown_pct),
                "unrealized_pnl": float(position.unrealized_pnl),
                "funding_collected": float(position.funding_received - position.funding_paid),
                "delta_exposure_pct": float(position.delta_exposure_pct),
            },
        )

        # Publish exit triggered event
        event = PositionExitTriggeredEvent(
            position_id=position.id,
            symbol=position.symbol,
            trigger_reason=reason,
            urgency="immediate" if reason in ["stop_loss", "spread_flipped"] else "normal",
        )
        await self.redis.publish("nexus:position:exit_triggered", event.model_dump_json())

        # CRITICAL: Also publish close request to execution engine
        # The execution engine listens to nexus:execution:close_request, not exit_triggered
        close_request = {
            "position_id": position.id,
            "symbol": position.symbol,
            "long_exchange": position.long_exchange,
            "short_exchange": position.short_exchange,
            "reason": reason,
            "urgency": "immediate" if reason in ["stop_loss", "spread_flipped"] else "normal",
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.redis.publish("nexus:execution:close_request", json.dumps(close_request))

        # Publish activity
        await self._publish_activity(
            "exit_triggered",
            f"Exit triggered for {position.symbol}: {reason}",
            {
                "position_id": position.id,
                "symbol": position.symbol,
                "reason": reason,
                "close_request_sent": True,
            },
            level="warning",
        )

        logger.warning(
            f"Exit triggered and close request sent",
            position_id=position.id,
            reason=reason,
            long_exchange=position.long_exchange,
            short_exchange=position.short_exchange,
        )

    # ==================== Funding Tracking ====================

    async def _track_funding_payments(self) -> None:
        """Track funding payments for positions."""
        while self._running:
            try:
                now = datetime.utcnow()

                for position in list(self._positions.values()):
                    if position.status != PositionStatus.ACTIVE:
                        continue

                    # Check if it's time to check for funding
                    if position.last_funding_check:
                        time_since_check = (now - position.last_funding_check).total_seconds()
                        if time_since_check < self._funding_check_interval:
                            continue

                    await self._check_funding_payment(position)
                    position.last_funding_check = now

            except Exception as e:
                logger.error("Error tracking funding", error=str(e))

            await asyncio.sleep(self._funding_check_interval)

    async def _check_funding_payment(self, position: Position) -> None:
        """Check and record funding payment for a position."""
        # For now, estimate funding based on rates
        # In production, would fetch actual payments from exchange APIs

        if position.long_funding_rate is None or position.short_funding_rate is None:
            return

        # Calculate funding for this period (assuming 8h funding interval)
        # Long position pays if rate is positive, receives if negative
        # Short position receives if rate is positive, pays if negative
        leg_size = position.size_usd / 2

        long_payment = leg_size * position.long_funding_rate / 100
        short_payment = leg_size * position.short_funding_rate / 100

        # For long position: negative rate = receive, positive rate = pay
        # For short position: positive rate = receive, negative rate = pay
        long_funding = -long_payment  # Long pays positive rates
        short_funding = short_payment  # Short receives positive rates

        total_funding = long_funding + short_funding

        if total_funding > 0:
            position.funding_received += abs(total_funding)
        else:
            position.funding_paid += abs(total_funding)

        position.funding_periods_collected += 1

        # Publish funding collected event if significant
        if abs(total_funding) > Decimal("0.01"):
            event = FundingCollectedEvent(
                position_id=position.id,
                symbol=position.symbol,
                exchange=f"{position.long_exchange}/{position.short_exchange}",
                funding_rate=position.current_spread or Decimal("0"),
                payment_amount=total_funding,
                total_funding_collected=position.funding_received - position.funding_paid,
                funding_periods=position.funding_periods_collected,
            )
            await self.redis.publish("nexus:funding:collected", event.model_dump_json())

            # Persist funding payment to database
            await self._persist_funding_payment(position, total_funding)

            # Log interaction for significant funding events
            net_funding = position.funding_received - position.funding_paid
            funding_emoji = "💰" if total_funding > 0 else "💸"
            await self._log_interaction(
                position,
                InteractionType.FUNDING_COLLECTED,
                InteractionDecision.KEPT_OPEN,
                f"{funding_emoji} Funding payment: ${float(total_funding):+.2f}. "
                f"Total funding collected: ${float(net_funding):+.2f} over {position.funding_periods_collected} periods. "
                f"Long rate: {float(position.long_funding_rate)*100:.4f}%, Short rate: {float(position.short_funding_rate)*100:.4f}%.",
                {
                    "payment_amount": float(total_funding),
                    "total_funding_received": float(position.funding_received),
                    "total_funding_paid": float(position.funding_paid),
                    "net_funding": float(net_funding),
                    "funding_periods": position.funding_periods_collected,
                    "long_funding_rate": float(position.long_funding_rate) if position.long_funding_rate else None,
                    "short_funding_rate": float(position.short_funding_rate) if position.short_funding_rate else None,
                    "current_spread": float(position.current_spread) if position.current_spread else None,
                },
            )

        # Update position P&L in database periodically
        await self._update_position_pnl_in_db(position)

        logger.debug(
            f"Funding checked",
            position_id=position.id,
            funding=float(total_funding),
            periods=position.funding_periods_collected,
        )

    # ==================== Price Updates ====================

    async def _update_prices(self) -> None:
        """Update position prices and unrealized P&L."""
        while self._running:
            try:
                # Get latest prices from Redis cache
                prices_json = await self.redis.get("nexus:cache:prices")
                if prices_json:
                    prices = json.loads(prices_json)

                    for position in self._positions.values():
                        if position.status != PositionStatus.ACTIVE:
                            continue

                        # Get price for symbol
                        symbol_prices = prices.get(position.symbol, {})
                        if symbol_prices:
                            # Use mid price or average
                            price = Decimal(str(symbol_prices.get("price", 0)))
                            if price > 0:
                                position.current_price = price

                                # Calculate unrealized P&L
                                # For delta-neutral, P&L comes mainly from funding
                                # Price P&L should be minimal if properly hedged

                                # Sync leg data to database
                                await self._sync_leg_prices(position, price)

            except Exception as e:
                logger.error("Error updating prices", error=str(e))

            await asyncio.sleep(self._price_update_interval)

    async def _sync_leg_prices(self, position: Position, current_price: Decimal) -> None:
        """Sync current prices and P&L to position legs in database."""
        try:
            async with self._db_session_factory() as db:
                # Get legs for this position
                result = await db.execute(
                    text("""
                        SELECT id, leg_type, side, quantity, entry_price
                        FROM positions.legs
                        WHERE position_id = :position_id
                    """),
                    {"position_id": position.id}
                )
                legs = result.fetchall()

                for leg in legs:
                    leg_id, leg_type, side, quantity, entry_price = leg
                    if entry_price is None or quantity is None:
                        continue

                    entry_dec = Decimal(str(entry_price))
                    qty_dec = Decimal(str(quantity))

                    # Calculate unrealized P&L for this leg
                    # Long: (current - entry) * qty
                    # Short: (entry - current) * qty
                    if side == "long":
                        unrealized_pnl = (current_price - entry_dec) * qty_dec
                    else:  # short
                        unrealized_pnl = (entry_dec - current_price) * qty_dec

                    # Calculate notional value
                    notional_usd = current_price * qty_dec

                    # Update leg in database
                    await db.execute(
                        text("""
                            UPDATE positions.legs
                            SET current_price = :current_price,
                                notional_value_usd = :notional_usd,
                                unrealized_pnl = :unrealized_pnl,
                                updated_at = NOW()
                            WHERE id = :leg_id
                        """),
                        {
                            "leg_id": leg_id,
                            "current_price": float(current_price),
                            "notional_usd": float(notional_usd),
                            "unrealized_pnl": float(unrealized_pnl),
                        }
                    )

                await db.commit()

        except Exception as e:
            logger.warning(
                "Failed to sync leg prices",
                position_id=position.id,
                error=str(e),
            )

    # ==================== State Publishing ====================

    async def _publish_positions_periodic(self) -> None:
        """Periodically publish position state to Redis."""
        while self._running:
            try:
                await self._cache_active_positions()

                # Publish position updates
                for position in self._positions.values():
                    event = PositionUpdatedEvent(
                        position_id=position.id,
                        symbol=position.symbol,
                        unrealized_pnl=position.unrealized_pnl,
                        return_pct=(
                            (position.funding_received - position.funding_paid - position.entry_costs)
                            / position.size_usd * 100
                            if position.size_usd > 0 else Decimal("0")
                        ),
                        delta_exposure_pct=Decimal("0"),  # Delta-neutral
                        margin_utilization=Decimal("0"),
                    )
                    await self.redis.publish("nexus:position:updated", event.model_dump_json())

            except Exception as e:
                logger.error("Error publishing positions", error=str(e))

            await asyncio.sleep(30)  # Every 30 seconds

    async def _cache_active_positions(self) -> None:
        """Cache active positions to Redis."""
        positions_data = [
            {
                "position_id": p.id,
                "opportunity_id": p.opportunity_id,
                "symbol": p.symbol,
                "long_exchange": p.long_exchange,
                "short_exchange": p.short_exchange,
                "size_usd": str(p.size_usd),
                "status": p.status.value,
                "health": p.health.value,
                "funding_received": str(p.funding_received),
                "funding_paid": str(p.funding_paid),
                "funding_periods_collected": p.funding_periods_collected,
                "unrealized_pnl": str(p.unrealized_pnl),
                "current_spread": str(p.current_spread) if p.current_spread else None,
                "opened_at": p.opened_at.isoformat(),
            }
            for p in self._positions.values()
        ]
        await self.redis.set("nexus:positions:active", json.dumps(positions_data))

    # ==================== Database Persistence ====================

    async def _persist_position_to_db(self, position: Position) -> None:
        """Persist position to PostgreSQL database."""
        try:
            async with self._db_session_factory() as db:
                # Extract base asset from symbol (e.g., BTC from BTC/USDT:USDT)
                base_asset = position.symbol.split("/")[0] if "/" in position.symbol else position.symbol

                # Insert position into positions.active
                await db.execute(
                    text("""
                        INSERT INTO positions.active (
                            id, opportunity_id, opportunity_type, symbol, base_asset,
                            status, health_status, total_capital_deployed,
                            entry_costs_paid, funding_received, funding_paid,
                            opened_at, created_at, updated_at
                        ) VALUES (
                            :id, :opportunity_id, 'cross_exchange_perp', :symbol, :base_asset,
                            'active', :health_status, :capital,
                            :entry_costs, :funding_received, :funding_paid,
                            :opened_at, NOW(), NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            status = 'active',
                            health_status = EXCLUDED.health_status,
                            funding_received = EXCLUDED.funding_received,
                            funding_paid = EXCLUDED.funding_paid,
                            updated_at = NOW()
                    """),
                    {
                        "id": position.id,
                        "opportunity_id": position.opportunity_id or None,
                        "symbol": position.symbol,
                        "base_asset": base_asset,
                        "health_status": position.health.value,
                        "capital": float(position.size_usd),
                        "entry_costs": float(position.entry_costs),
                        "funding_received": float(position.funding_received),
                        "funding_paid": float(position.funding_paid),
                        "opened_at": position.opened_at,
                    },
                )

                # Insert position legs
                # Long leg
                await db.execute(
                    text("""
                        INSERT INTO positions.legs (
                            position_id, leg_type, exchange, symbol, market_type, side,
                            quantity, entry_price, current_price, notional_value_usd
                        ) VALUES (
                            :position_id, 'primary', :exchange, :symbol, 'perpetual', 'long',
                            :quantity, :entry_price, :entry_price, :notional
                        )
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "position_id": position.id,
                        "exchange": position.long_exchange,
                        "symbol": position.symbol,
                        "quantity": float(position.size_usd / 2) / float(position.entry_price or 1),
                        "entry_price": float(position.entry_price or 0),
                        "notional": float(position.size_usd / 2),
                    },
                )

                # Short leg
                await db.execute(
                    text("""
                        INSERT INTO positions.legs (
                            position_id, leg_type, exchange, symbol, market_type, side,
                            quantity, entry_price, current_price, notional_value_usd
                        ) VALUES (
                            :position_id, 'hedge', :exchange, :symbol, 'perpetual', 'short',
                            :quantity, :entry_price, :entry_price, :notional
                        )
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "position_id": position.id,
                        "exchange": position.short_exchange,
                        "symbol": position.symbol,
                        "quantity": float(position.size_usd / 2) / float(position.entry_price or 1),
                        "entry_price": float(position.entry_price or 0),
                        "notional": float(position.size_usd / 2),
                    },
                )

                await db.commit()
                logger.info(f"Position persisted to database", position_id=position.id)

        except Exception as e:
            logger.error(f"Failed to persist position to database", position_id=position.id, error=str(e))

    async def _close_position_in_db(self, position: Position, total_pnl: Decimal) -> None:
        """Update position in database with closed status and final P&L."""
        try:
            net_funding = position.funding_received - position.funding_paid

            async with self._db_session_factory() as db:
                await db.execute(
                    text("""
                        UPDATE positions.active SET
                            status = 'closed',
                            health_status = 'healthy',
                            funding_received = :funding_received,
                            funding_paid = :funding_paid,
                            funding_periods_collected = :funding_periods,
                            realized_pnl_funding = :funding_pnl,
                            realized_pnl_price = :price_pnl,
                            exit_costs_paid = 0,
                            exit_reason = :exit_reason,
                            closed_at = :closed_at,
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {
                        "id": position.id,
                        "funding_received": float(position.funding_received),
                        "funding_paid": float(position.funding_paid),
                        "funding_periods": position.funding_periods_collected,
                        "funding_pnl": float(net_funding),
                        "price_pnl": float(position.unrealized_pnl),
                        "exit_reason": position.exit_reason,
                        "closed_at": position.closed_at,
                    },
                )
                await db.commit()
                logger.info(f"Position closed in database", position_id=position.id, pnl=float(total_pnl))

        except Exception as e:
            logger.error(f"Failed to close position in database", position_id=position.id, error=str(e))

    async def _update_position_pnl_in_db(self, position: Position) -> None:
        """Update position P&L in database."""
        try:
            async with self._db_session_factory() as db:
                await db.execute(
                    text("""
                        UPDATE positions.active SET
                            funding_received = :funding_received,
                            funding_paid = :funding_paid,
                            funding_periods_collected = :funding_periods,
                            unrealized_pnl = :unrealized_pnl,
                            health_status = :health_status,
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {
                        "id": position.id,
                        "funding_received": float(position.funding_received),
                        "funding_paid": float(position.funding_paid),
                        "funding_periods": position.funding_periods_collected,
                        "unrealized_pnl": float(position.unrealized_pnl),
                        "health_status": position.health.value,
                    },
                )
                await db.commit()

        except Exception as e:
            logger.error(f"Failed to update position P&L in database", position_id=position.id, error=str(e))

    async def _persist_funding_payment(self, position: Position, payment_amount: Decimal) -> None:
        """Persist funding payment record to database."""
        try:
            async with self._db_session_factory() as db:
                # Get leg IDs for the position
                result = await db.execute(
                    text("""
                        SELECT id, exchange, side FROM positions.legs
                        WHERE position_id = :position_id
                    """),
                    {"position_id": position.id},
                )
                legs = result.fetchall()

                for leg in legs:
                    leg_id, exchange, side = leg
                    # Calculate per-leg funding
                    if side == "long":
                        leg_funding = float(payment_amount) / 2 * -1  # Long pays
                        funding_rate = float(position.long_funding_rate or 0)
                    else:
                        leg_funding = float(payment_amount) / 2  # Short receives
                        funding_rate = float(position.short_funding_rate or 0)

                    await db.execute(
                        text("""
                            INSERT INTO positions.funding_payments (
                                position_id, leg_id, exchange, symbol,
                                funding_rate, payment_amount, position_size, timestamp
                            ) VALUES (
                                :position_id, :leg_id, :exchange, :symbol,
                                :funding_rate, :payment_amount, :position_size, NOW()
                            )
                        """),
                        {
                            "position_id": position.id,
                            "leg_id": leg_id,
                            "exchange": exchange,
                            "symbol": position.symbol,
                            "funding_rate": funding_rate,
                            "payment_amount": leg_funding,
                            "position_size": float(position.size_usd / 2),
                        },
                    )

                await db.commit()

        except Exception as e:
            logger.error(f"Failed to persist funding payment", position_id=position.id, error=str(e))

    # ==================== Activity Broadcasting ====================

    async def _publish_activity(
        self,
        activity_type: str,
        message: str,
        details: dict[str, Any],
        level: str = "info",
    ) -> None:
        """Publish activity event for real-time UI updates."""
        activity = {
            "type": activity_type,
            "service": "position-manager",
            "level": level,
            "message": message,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.redis.publish("nexus:activity", json.dumps(activity))

    # ==================== Position Interaction Logging ====================

    async def _log_interaction(
        self,
        position: Position,
        interaction_type: str,
        decision: Optional[str],
        narrative: str,
        metrics: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Log an interaction with a position to the database for timeline tracking.

        This creates a permanent record of every decision made about the position,
        enabling users to understand why the bot took (or didn't take) actions.

        Args:
            position: The position being interacted with
            interaction_type: Type of interaction (from InteractionType)
            decision: Decision made (from InteractionDecision), or None if informational
            narrative: Human-readable explanation of what happened and why
            metrics: Optional dict of relevant metrics at the time of interaction
            correlation_id: Optional UUID to correlate related interactions
        """
        try:
            # Prepare parameters
            params = {
                "position_id": str(position.id),
                "opportunity_id": str(position.opportunity_id) if position.opportunity_id else None,
                "symbol": position.symbol,
                "interaction_type": interaction_type,
                "decision": decision,
                "narrative": narrative,
                "metrics": json.dumps(metrics or {}),
                "correlation_id": str(correlation_id) if correlation_id else None,
            }

            logger.debug(
                "Logging position interaction",
                position_id=position.id,
                interaction_type=interaction_type,
                decision=decision,
            )

            async with self._db_session_factory() as db:
                await db.execute(
                    text("""
                        INSERT INTO positions.interactions (
                            position_id,
                            opportunity_id,
                            symbol,
                            timestamp,
                            interaction_type,
                            worker_service,
                            decision,
                            narrative,
                            metrics,
                            correlation_id
                        ) VALUES (
                            CAST(:position_id AS UUID),
                            CAST(:opportunity_id AS UUID),
                            :symbol,
                            NOW(),
                            :interaction_type,
                            'position-manager',
                            :decision,
                            :narrative,
                            :metrics::jsonb,
                            CAST(:correlation_id AS UUID)
                        )
                    """),
                    params,
                )
                await db.commit()

            logger.debug(
                "Successfully logged position interaction",
                position_id=position.id,
                interaction_type=interaction_type,
            )

        except Exception as e:
            # Log with full traceback for debugging
            import traceback
            logger.error(
                "Failed to log position interaction",
                position_id=position.id,
                interaction_type=interaction_type,
                error=str(e),
                traceback=traceback.format_exc(),
            )

    # ==================== Public Methods ====================

    async def close_position(self, position_id: str, reason: str = "manual") -> bool:
        """Manually close a position."""
        position = self._positions.get(position_id)
        if not position:
            return False

        await self._trigger_exit(position, reason)
        return True

    @property
    def active_position_count(self) -> int:
        return sum(
            1 for p in self._positions.values() if p.status == PositionStatus.ACTIVE
        )

    def get_stats(self) -> dict[str, Any]:
        """Get position manager statistics."""
        uptime = None
        if self._stats["start_time"]:
            uptime = (datetime.utcnow() - self._stats["start_time"]).total_seconds()

        return {
            "uptime_seconds": uptime,
            "positions_opened": self._stats["positions_opened"],
            "positions_closed": self._stats["positions_closed"],
            "active_positions": self.active_position_count,
            "total_funding_collected": float(self._stats["total_funding_collected"]),
            "total_pnl": float(self._stats["total_pnl"]),
        }

    def get_positions(
        self, status: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get positions list."""
        positions = list(self._positions.values())
        if status:
            positions = [p for p in positions if p.status.value == status]
        positions.sort(key=lambda p: p.opened_at, reverse=True)

        return [
            {
                "id": p.id,
                "opportunity_id": p.opportunity_id,
                "symbol": p.symbol,
                "long_exchange": p.long_exchange,
                "short_exchange": p.short_exchange,
                "size_usd": float(p.size_usd),
                "status": p.status.value,
                "health": p.health.value,
                "funding_received": float(p.funding_received),
                "funding_paid": float(p.funding_paid),
                "net_funding": float(p.funding_received - p.funding_paid),
                "funding_periods": p.funding_periods_collected,
                "unrealized_pnl": float(p.unrealized_pnl),
                "current_spread": float(p.current_spread) if p.current_spread else None,
                "opened_at": p.opened_at.isoformat(),
            }
            for p in positions[:limit]
        ]

    def get_position(self, position_id: str) -> Optional[dict[str, Any]]:
        """Get single position details."""
        position = self._positions.get(position_id)
        if not position:
            return None

        return {
            "id": position.id,
            "opportunity_id": position.opportunity_id,
            "symbol": position.symbol,
            "long_exchange": position.long_exchange,
            "short_exchange": position.short_exchange,
            "size_usd": float(position.size_usd),
            "status": position.status.value,
            "health": position.health.value,
            "funding_received": float(position.funding_received),
            "funding_paid": float(position.funding_paid),
            "net_funding": float(position.funding_received - position.funding_paid),
            "funding_periods": position.funding_periods_collected,
            "entry_costs": float(position.entry_costs),
            "unrealized_pnl": float(position.unrealized_pnl),
            "current_spread": float(position.current_spread) if position.current_spread else None,
            "initial_spread": float(position.initial_spread) if position.initial_spread else None,
            "long_funding_rate": float(position.long_funding_rate) if position.long_funding_rate else None,
            "short_funding_rate": float(position.short_funding_rate) if position.short_funding_rate else None,
            "opened_at": position.opened_at.isoformat(),
            "closed_at": position.closed_at.isoformat() if position.closed_at else None,
            "exit_reason": position.exit_reason,
        }

    def get_position_pnl(self, position_id: str) -> Optional[dict[str, Any]]:
        """Get position P&L breakdown."""
        position = self._positions.get(position_id)
        if not position:
            return None

        net_funding = position.funding_received - position.funding_paid
        total_pnl = net_funding - position.entry_costs + position.unrealized_pnl

        return {
            "position_id": position_id,
            "funding_received": float(position.funding_received),
            "funding_paid": float(position.funding_paid),
            "net_funding": float(net_funding),
            "entry_costs": float(position.entry_costs),
            "unrealized_pnl": float(position.unrealized_pnl),
            "total_pnl": float(total_pnl),
            "return_pct": float(total_pnl / position.size_usd * 100) if position.size_usd > 0 else 0,
        }

    def get_total_pnl_summary(self) -> dict[str, Any]:
        """Get total P&L summary across all positions."""
        active = [
            p for p in self._positions.values() if p.status == PositionStatus.ACTIVE
        ]
        total_funding = sum(p.funding_received - p.funding_paid for p in active)
        total_unrealized = sum(p.unrealized_pnl for p in active)

        return {
            "active_positions": len(active),
            "total_capital_deployed": float(sum(p.size_usd for p in active)),
            "total_funding_pnl": float(total_funding),
            "total_unrealized_pnl": float(total_unrealized),
            "realized_pnl": float(self._stats["total_pnl"]),
            "positions_opened": self._stats["positions_opened"],
            "positions_closed": self._stats["positions_closed"],
        }
