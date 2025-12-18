"""
Capital Allocator Core - Distributes capital across opportunities.

This module manages capital allocation for the trading bot:
- Allocates capital to high-scoring opportunities
- Respects system state (start/stop, auto/manual mode)
- Validates allocations with Risk Manager
- Tracks allocation lifecycle (pending → executing → active → closed)
- Broadcasts activity for real-time UI updates

Allocation Strategy:
- Score-weighted allocation to opportunities above UOS threshold
- Reserve percentage for new opportunities
- Per-exchange exposure limits
- Automatic position sizing based on score and available capital
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.events.capital import CapitalAllocatedEvent
from shared.utils.config import get_settings
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.system_state import SystemStateManager

if TYPE_CHECKING:
    from src.allocator.balance_monitor import BalanceMonitor

logger = get_logger(__name__)


class AllocationStatus:
    PENDING = "pending"  # Capital reserved, awaiting execution
    EXECUTING = "executing"  # Orders being placed
    ACTIVE = "active"  # Position open
    CLOSING = "closing"  # Position being closed
    CLOSED = "closed"  # Position closed
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Allocation cancelled


class Allocation:
    """Tracks a capital allocation to an opportunity."""

    def __init__(
        self,
        opportunity_id: str,
        amount_usd: float,
        uos_score: float = 0,
        symbol: str = "",
        long_exchange: str = "",
        short_exchange: str = "",
    ):
        self.id = str(uuid4())
        self.opportunity_id = opportunity_id
        self.amount_usd = amount_usd
        self.uos_score = uos_score
        self.symbol = symbol
        self.long_exchange = long_exchange
        self.short_exchange = short_exchange
        self.status = AllocationStatus.PENDING
        self.position_id: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.executed_at: Optional[datetime] = None
        self.closed_at: Optional[datetime] = None
        self.realized_pnl: Optional[float] = None
        # For weakness scoring during auto-unwind
        self.realized_funding_pnl: Optional[Decimal] = None
        self.unrealized_pnl: Optional[Decimal] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "amount_usd": self.amount_usd,
            "uos_score": self.uos_score,
            "symbol": self.symbol,
            "long_exchange": self.long_exchange,
            "short_exchange": self.short_exchange,
            "status": self.status,
            "position_id": self.position_id,
            "created_at": self.created_at.isoformat(),
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "realized_pnl": self.realized_pnl,
            "realized_funding_pnl": float(self.realized_funding_pnl) if self.realized_funding_pnl else None,
            "unrealized_pnl": float(self.unrealized_pnl) if self.unrealized_pnl else None,
        }


class CapitalAllocator:
    """
    Manages capital allocation across opportunities.

    Listens to:
    - Opportunity detected events
    - Position opened/closed events (to update allocation status)
    - System state changes

    Publishes:
    - Execution requests (for Execution Engine)
    - Capital allocated events
    - Activity events for UI
    """

    def __init__(
        self,
        redis: RedisClient,
        balance_monitor: Optional["BalanceMonitor"] = None,
        db_session_factory: Optional[Callable] = None,
    ):
        self.redis = redis
        self.balance_monitor = balance_monitor
        self._db_session_factory = db_session_factory or self._create_db_session_factory()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # System state manager
        self.state_manager: Optional[SystemStateManager] = None

        # Capital tracking
        self._total_capital = Decimal("0")
        self._allocated_capital = Decimal("0")
        self._reserve_pct = Decimal("0.2")  # 20% reserve

        # Active allocations
        self._allocations: dict[str, Allocation] = {}  # allocation_id -> Allocation
        self._opportunity_allocations: dict[str, str] = {}  # opportunity_id -> allocation_id

        # Pending manual approvals (for manual mode)
        self._pending_approvals: dict[str, dict[str, Any]] = {}  # opportunity_id -> opportunity data

        # Configuration (loaded from DB, defaults set to enable trading)
        self._config = {
            "min_allocation_usd": Decimal("100"),
            "max_allocation_usd": Decimal("10000"),
            "auto_execute": True,  # True = auto-execute high quality opportunities
            "min_uos_score": 65,  # Minimum score to consider
            "high_quality_threshold": 75,  # Score for auto-allocation
            "allocation_interval": 30,  # Seconds between rebalance checks
            "max_concurrent_coins": 5,  # Max coins (1 coin = 2 positions: long + short)
            "score_weight_factor": Decimal("0.5"),  # How much score affects size
            # Kelly criterion settings
            "use_kelly_criterion": True,  # Enable Kelly-based position sizing
            "kelly_fraction": Decimal("0.5"),  # Half-Kelly for safety
            "min_kelly_edge": Decimal("0.01"),  # Minimum edge to use Kelly
            # Correlation settings
            "max_portfolio_correlation": Decimal("0.7"),  # Max correlation with existing positions
            "correlation_size_penalty": Decimal("0.5"),  # Reduce size if correlated
        }

        # Historical performance tracking for Kelly calculation
        self._performance_history: dict[str, list[dict]] = {}  # symbol -> [{pnl, entry_score, ...}]
        self._strategy_edge_cache: dict[str, dict] = {}  # symbol -> {win_rate, avg_win, avg_loss}
        self._edge_cache_ttl_seconds = 3600  # 1 hour cache

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
        """Start the capital allocator."""
        logger.info("Starting Capital Allocator")
        self._running = True

        # Initialize system state manager
        self.state_manager = SystemStateManager(self.redis, "capital-allocator")
        await self.state_manager.start()

        # Load configuration from database
        await self._load_config()

        # Load existing allocations from cache
        await self._recover_allocations()

        # CRITICAL: Sync with database to catch orphaned positions
        # The database is the source of truth for positions
        await self._sync_positions_from_db()

        # Immediately enforce coin limit on startup
        # This will auto-close excess positions if we're over the limit
        db_coin_count = await self._count_active_coins_from_db()
        max_coins = self._config.get("max_concurrent_coins", 5)
        logger.info(
            "Checking coin limit on startup",
            current_coins=db_coin_count,
            max_coins=max_coins,
            over_limit=db_coin_count > max_coins,
        )
        await self._check_and_enforce_coin_limit()

        # Load performance history for Kelly calculations
        await self._load_performance_history()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._listen_opportunities()),
            asyncio.create_task(self._listen_position_events()),
            asyncio.create_task(self._listen_execution_results()),
            asyncio.create_task(self._auto_allocate_loop()),
            asyncio.create_task(self._update_capital_periodic()),
            asyncio.create_task(self._periodic_limit_enforcement()),  # New: periodic enforcement
            asyncio.create_task(self._listen_config_changes()),  # New: listen for config changes
            asyncio.create_task(self._update_edge_estimates()),  # Update Kelly edge estimates
        ]

        logger.info(
            "Capital Allocator started",
            auto_execute=self._config["auto_execute"],
            total_capital=float(self._total_capital),
            active_coins=db_coin_count,
            max_coins=max_coins,
        )

    async def stop(self) -> None:
        """Stop the capital allocator."""
        logger.info("Stopping Capital Allocator")
        self._running = False

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.state_manager:
            await self.state_manager.stop()

        logger.info("Capital Allocator stopped")

    # ==================== Initialization ====================

    async def _load_config(self) -> None:
        """Load configuration from database."""
        try:
            async with self._db_session_factory() as db:
                query = text("""
                    SELECT key, value, data_type
                    FROM config.system_settings
                    WHERE category = 'capital'
                """)
                result = await db.execute(query)
                rows = result.fetchall()

                for key, value, data_type in rows:
                    if key in self._config:
                        if data_type == "decimal":
                            self._config[key] = Decimal(value)
                        elif data_type == "integer":
                            self._config[key] = int(value)
                        elif data_type == "boolean":
                            self._config[key] = value.lower() == "true"
                        elif data_type == "float":
                            self._config[key] = float(value)

                logger.info("Loaded capital config from database")

        except Exception as e:
            logger.warning(f"Failed to load config from DB, using defaults", error=str(e))

    async def _recover_allocations(self) -> None:
        """Recover allocations from Redis cache."""
        try:
            allocations_json = await self.redis.get("nexus:capital:allocations")
            if allocations_json:
                allocations_data = json.loads(allocations_json)
                for alloc_data in allocations_data:
                    if alloc_data.get("status") in [AllocationStatus.ACTIVE, AllocationStatus.EXECUTING]:
                        allocation = Allocation(
                            opportunity_id=alloc_data["opportunity_id"],
                            amount_usd=alloc_data["amount_usd"],
                            uos_score=alloc_data.get("uos_score", 0),
                            symbol=alloc_data.get("symbol", ""),
                            long_exchange=alloc_data.get("long_exchange", ""),
                            short_exchange=alloc_data.get("short_exchange", ""),
                        )
                        allocation.id = alloc_data.get("id", allocation.id)
                        allocation.status = alloc_data["status"]
                        allocation.position_id = alloc_data.get("position_id")
                        self._allocations[allocation.id] = allocation
                        self._opportunity_allocations[allocation.opportunity_id] = allocation.id
                        self._allocated_capital += Decimal(str(allocation.amount_usd))

                logger.info(f"Recovered {len(self._allocations)} allocations from cache")

        except Exception as e:
            logger.warning(f"Failed to recover allocations", error=str(e))

    async def _sync_positions_from_db(self) -> None:
        """
        Sync allocations with actual positions in database.

        This is CRITICAL for enforcing max_concurrent_coins limit.
        The database is the source of truth - positions may exist that
        weren't tracked in Redis cache (e.g., after service restart).
        """
        try:
            async with self._db_session_factory() as db:
                # Get all active positions from database
                # Note: Using columns that exist in positions.active table
                result = await db.execute(text("""
                    SELECT id, symbol, opportunity_id, status,
                           total_capital_deployed, opened_at,
                           COALESCE(realized_pnl_funding, 0) as net_funding_pnl,
                           COALESCE(unrealized_pnl, 0) as unrealized_pnl
                    FROM positions.active
                    WHERE status IN ('pending', 'opening', 'active', 'closing')
                """))
                rows = result.fetchall()

                synced_count = 0
                already_tracked = 0

                for row in rows:
                    position_id = str(row[0])
                    symbol = row[1]
                    opportunity_id = str(row[2]) if row[2] else None
                    status = row[3]
                    capital = Decimal(str(row[4])) if row[4] else Decimal("0")
                    net_funding_pnl = Decimal(str(row[6])) if row[6] else None
                    unrealized_pnl = Decimal(str(row[7])) if row[7] else None

                    # Check if we already track this position
                    existing = None
                    for alloc in self._allocations.values():
                        if alloc.position_id == position_id:
                            existing = alloc
                            break

                    if existing:
                        # Update existing allocation with latest P&L from DB
                        existing.realized_funding_pnl = net_funding_pnl
                        existing.unrealized_pnl = unrealized_pnl
                        already_tracked += 1
                    else:
                        # Create synthetic allocation for orphaned position
                        alloc = Allocation(
                            opportunity_id=opportunity_id or f"sync_{position_id}",
                            amount_usd=float(capital),
                            symbol=symbol,
                        )
                        alloc.position_id = position_id
                        alloc.status = self._map_position_status(status)
                        alloc.realized_funding_pnl = net_funding_pnl
                        alloc.unrealized_pnl = unrealized_pnl

                        self._allocations[alloc.id] = alloc
                        if opportunity_id:
                            self._opportunity_allocations[opportunity_id] = alloc.id
                        self._allocated_capital += capital
                        synced_count += 1

                logger.info(
                    "Synced positions from database",
                    synced=synced_count,
                    already_tracked=already_tracked,
                    total_in_memory=len(self._allocations),
                )

                if synced_count > 0:
                    await self._publish_activity(
                        "positions_synced",
                        f"Synced {synced_count} orphaned positions from database",
                        {
                            "synced_count": synced_count,
                            "already_tracked": already_tracked,
                            "total_positions": len(self._allocations),
                        },
                        level="warning",
                    )

        except Exception as e:
            logger.error(f"Failed to sync positions from DB: {e}")

    def _map_position_status(self, db_status: str) -> str:
        """Map database position status to allocation status."""
        mapping = {
            'pending': AllocationStatus.PENDING,
            'opening': AllocationStatus.EXECUTING,
            'active': AllocationStatus.ACTIVE,
            'closing': AllocationStatus.CLOSING,
            'closed': AllocationStatus.CLOSED,
        }
        return mapping.get(db_status, AllocationStatus.ACTIVE)

    async def _count_active_coins_from_db(self) -> int:
        """
        Count unique coins from database positions (source of truth).

        This queries the database directly to ensure accurate count,
        even if in-memory state has drifted.
        """
        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT COUNT(DISTINCT symbol)
                    FROM positions.active
                    WHERE status IN ('pending', 'opening', 'active')
                """))
                count = result.scalar() or 0
                return count
        except Exception as e:
            logger.error(f"Failed to count coins from DB: {e}")
            # Fallback to in-memory count
            return self._count_active_coins()

    # ==================== Event Listeners ====================

    async def _listen_opportunities(self) -> None:
        """Listen for new opportunity events."""
        async def handle_opportunity(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message
                opp = data.get("opportunity", data)  # Handle both wrapped and direct

                uos_score = opp.get("uos_score", 0)
                opportunity_id = opp.get("id", "")
                symbol = opp.get("symbol", "unknown")

                # Check if we should process this opportunity
                if not self.state_manager:
                    logger.warning(
                        "Cannot process opportunity - no state manager",
                        opportunity_id=opportunity_id,
                        symbol=symbol,
                    )
                    return

                if not self.state_manager.should_open_positions():
                    logger.info(
                        "Opportunity ignored - system not accepting new positions",
                        opportunity_id=opportunity_id,
                        symbol=symbol,
                        uos_score=uos_score,
                        system_running=self.state_manager.is_running,
                        new_positions_enabled=self.state_manager.new_positions_enabled,
                        circuit_breaker=self.state_manager.circuit_breaker_active,
                        mode=self.state_manager.mode,
                    )
                    return

                # Skip if below minimum threshold
                if uos_score < self._config["min_uos_score"]:
                    logger.debug(
                        "Opportunity below minimum UOS threshold",
                        opportunity_id=opportunity_id,
                        symbol=symbol,
                        uos_score=uos_score,
                        min_uos_score=self._config["min_uos_score"],
                    )
                    return

                # Skip if already allocated
                if opportunity_id in self._opportunity_allocations:
                    return

                # Check execution mode using consolidated check
                auto_execute = await self._is_auto_execute_enabled()

                logger.info(
                    "Processing opportunity",
                    opportunity_id=opportunity_id,
                    symbol=symbol,
                    uos_score=uos_score,
                    auto_execute=auto_execute,
                    threshold=self._config["high_quality_threshold"],
                )

                if auto_execute and uos_score >= self._config["high_quality_threshold"]:
                    # Auto-allocate high quality opportunities
                    logger.info(
                        "Auto-executing high quality opportunity",
                        opportunity_id=opportunity_id,
                        symbol=symbol,
                        uos_score=uos_score,
                    )
                    await self.allocate_to_opportunity(opp)
                else:
                    # Queue for manual approval
                    logger.info(
                        "Queuing opportunity for manual approval",
                        opportunity_id=opportunity_id,
                        symbol=symbol,
                        uos_score=uos_score,
                        auto_execute=auto_execute,
                        reason="below_threshold" if uos_score < self._config["high_quality_threshold"] else "manual_mode",
                    )
                    await self._queue_for_approval(opp)

            except Exception as e:
                logger.error("Failed to process opportunity", error=str(e))

        try:
            await self.redis.subscribe("nexus:opportunity:detected", handle_opportunity)
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in opportunity listener", error=str(e))

    async def _listen_position_events(self) -> None:
        """Listen for position lifecycle events to update allocation status."""
        channels = [
            "nexus:position:opened",
            "nexus:position:closed",
            "nexus:position:updated",  # For P&L updates used in weakness scoring
        ]

        async def handle_event(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message
                event_type = channel.split(":")[-1]

                opportunity_id = data.get("opportunity_id", "")
                allocation_id = self._opportunity_allocations.get(opportunity_id)

                if not allocation_id:
                    # Try lookup by position_id
                    position_id = data.get("position_id")
                    if position_id:
                        for alloc in self._allocations.values():
                            if alloc.position_id == position_id:
                                allocation_id = alloc.id
                                break
                    if not allocation_id:
                        return

                allocation = self._allocations.get(allocation_id)
                if not allocation:
                    return

                if event_type == "opened":
                    allocation.status = AllocationStatus.ACTIVE
                    allocation.position_id = data.get("position_id")
                    allocation.executed_at = datetime.utcnow()

                    await self._publish_activity(
                        "allocation_active",
                        f"Position opened for {allocation.symbol}: ${allocation.amount_usd:.0f}",
                        allocation.to_dict(),
                    )

                elif event_type == "updated":
                    # Update P&L for weakness scoring
                    if "net_funding_pnl" in data:
                        allocation.realized_funding_pnl = Decimal(str(data["net_funding_pnl"]))
                    if "unrealized_pnl" in data:
                        allocation.unrealized_pnl = Decimal(str(data["unrealized_pnl"]))

                elif event_type == "closed":
                    allocation.status = AllocationStatus.CLOSED
                    allocation.closed_at = datetime.utcnow()
                    allocation.realized_pnl = data.get("realized_pnl", data.get("net_pnl", 0))

                    # Release capital
                    self._allocated_capital -= Decimal(str(allocation.amount_usd))

                    # Record outcome for Kelly learning
                    await self._record_allocation_outcome(allocation, {
                        "realized_pnl": allocation.realized_pnl,
                    })

                    await self._publish_activity(
                        "allocation_closed",
                        f"Position closed for {allocation.symbol}: P&L ${allocation.realized_pnl:.2f}",
                        allocation.to_dict(),
                        level="info" if (allocation.realized_pnl or 0) >= 0 else "warning",
                    )

                # Update cache
                await self._cache_allocations()

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

    async def _listen_execution_results(self) -> None:
        """Listen for execution results."""
        async def handle_result(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message

                opportunity_id = data.get("opportunity_id", "")
                allocation_id = self._opportunity_allocations.get(opportunity_id)

                if not allocation_id:
                    return

                allocation = self._allocations.get(allocation_id)
                if not allocation:
                    return

                if data.get("success"):
                    allocation.status = AllocationStatus.EXECUTING
                    allocation.position_id = data.get("position_id")
                else:
                    # Execution failed - release capital
                    allocation.status = AllocationStatus.FAILED
                    self._allocated_capital -= Decimal(str(allocation.amount_usd))

                    await self._publish_activity(
                        "allocation_failed",
                        f"Execution failed for {allocation.symbol}: {data.get('error', 'Unknown error')}",
                        {**allocation.to_dict(), "error": data.get("error")},
                        level="error",
                    )

                await self._cache_allocations()

            except Exception as e:
                logger.error(f"Failed to process execution result", error=str(e))

        try:
            await self.redis.subscribe("nexus:execution:result", handle_result)
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in execution result listener", error=str(e))

    # ==================== Allocation Logic ====================

    def _count_active_coins(self) -> int:
        """
        Count unique coins (symbols) with active allocations.
        1 coin = 1 arbitrage position = 2 exchange positions (long + short).
        """
        active_symbols = set()
        for alloc in self._allocations.values():
            if alloc.status in [AllocationStatus.PENDING, AllocationStatus.EXECUTING, AllocationStatus.ACTIVE]:
                active_symbols.add(alloc.symbol)
        return len(active_symbols)

    def _is_coin_already_active(self, symbol: str) -> bool:
        """Check if a coin (symbol) already has an active allocation."""
        for alloc in self._allocations.values():
            if alloc.symbol == symbol and alloc.status in [
                AllocationStatus.PENDING,
                AllocationStatus.EXECUTING,
                AllocationStatus.ACTIVE,
            ]:
                return True
        return False

    def _calculate_weakness_score(self, allocation: Allocation) -> float:
        """
        Calculate weakness score for position ranking during auto-unwind.
        Higher score = weaker position (close first).

        Factors:
        - Net funding P&L (negative = weaker)
        - Unrealized P&L (negative = weaker)
        - Time held with poor performance
        """
        score = 0.0

        # Factor 1: Net funding (negative funding = +50 to score)
        funding_pnl = allocation.realized_funding_pnl or Decimal("0")
        if funding_pnl < 0:
            score += 50 + abs(float(funding_pnl))
        else:
            score -= min(float(funding_pnl), 20)

        # Factor 2: Unrealized P&L (negative = +30 to score)
        unrealized = allocation.unrealized_pnl or Decimal("0")
        if unrealized < 0:
            score += 30 + abs(float(unrealized))
        else:
            score -= min(float(unrealized), 15)

        # Factor 3: Hold time with poor ROI (long hold + negative = weaker)
        if allocation.executed_at:
            hours_held = (datetime.utcnow() - allocation.executed_at).total_seconds() / 3600
            total_pnl = float(funding_pnl) + float(unrealized)
            if total_pnl < 0 and hours_held > 4:
                score += hours_held * 2

        return score

    async def _check_and_enforce_coin_limit(self) -> None:
        """Check coin limit and trigger auto-unwind if exceeded."""
        # Use database count as source of truth
        current_coins = await self._count_active_coins_from_db()
        max_coins = self._config.get("max_concurrent_coins", 5)

        if current_coins <= max_coins:
            return

        excess = current_coins - max_coins
        logger.warning(
            "Coin limit exceeded, initiating auto-unwind",
            current=current_coins,
            max=max_coins,
            excess=excess,
        )

        # Rank positions by weakness (only ACTIVE allocations can be closed)
        active_allocations = [
            a for a in self._allocations.values()
            if a.status == AllocationStatus.ACTIVE
        ]

        # If we have more coins in DB than tracked allocations, we need to fetch
        # the missing positions from DB for proper ranking
        if len(active_allocations) < current_coins:
            logger.warning(
                "In-memory allocations don't match DB count, re-syncing",
                in_memory=len(active_allocations),
                db_count=current_coins,
            )
            await self._sync_positions_from_db()
            active_allocations = [
                a for a in self._allocations.values()
                if a.status == AllocationStatus.ACTIVE
            ]

        ranked = sorted(
            active_allocations,
            key=lambda a: self._calculate_weakness_score(a),
            reverse=True,  # Weakest first (highest score)
        )

        # Close weakest positions until under limit
        closed_count = 0
        for allocation in ranked[:excess]:
            await self._initiate_position_close(
                allocation.id,
                reason="auto_unwind_coin_limit",
            )
            closed_count += 1

            # Log auto-unwind event to database
            await self._log_auto_unwind_event(
                allocation=allocation,
                reason="coin_limit_exceeded",
                weakness_score=self._calculate_weakness_score(allocation),
                coins_before=current_coins,
                max_coins=max_coins,
            )

            # Publish event for activity log
            await self.redis.publish(
                "nexus:capital:auto_unwind_triggered",
                json.dumps({
                    "allocation_id": allocation.id,
                    "symbol": allocation.symbol,
                    "reason": "coin_limit_exceeded",
                    "weakness_score": self._calculate_weakness_score(allocation),
                    "timestamp": datetime.utcnow().isoformat(),
                }),
            )

            await self._publish_activity(
                "auto_unwind",
                f"Auto-unwinding {allocation.symbol}: coin limit exceeded ({current_coins}/{max_coins})",
                {
                    "allocation_id": allocation.id,
                    "symbol": allocation.symbol,
                    "weakness_score": self._calculate_weakness_score(allocation),
                },
                level="warning",
            )

        if closed_count > 0:
            logger.info(
                "Auto-unwind completed",
                closed=closed_count,
                remaining_coins=current_coins - closed_count,
                max_coins=max_coins,
            )

    async def _periodic_limit_enforcement(self) -> None:
        """Background task to enforce coin limits every 60 seconds."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every 60 seconds
                await self._check_and_enforce_coin_limit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Limit enforcement error: {e}")

    async def _listen_config_changes(self) -> None:
        """Listen for configuration changes via Redis."""
        async def handler(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message

                # Handle auto_execute changes
                if "auto_execute" in data:
                    new_value = data["auto_execute"]
                    if isinstance(new_value, str):
                        new_value = new_value.lower() in ('true', '1', 'yes')
                    self._config["auto_execute"] = new_value
                    logger.info(f"Auto-execute updated via config change: {new_value}")

                # Handle max_concurrent_coins changes
                if "max_concurrent_coins" in data:
                    new_value = int(data["max_concurrent_coins"])
                    old_value = self._config.get("max_concurrent_coins", 5)
                    self._config["max_concurrent_coins"] = new_value
                    logger.info(
                        f"Max concurrent coins updated: {old_value} -> {new_value}"
                    )
                    # Immediately enforce new limit if it decreased
                    if new_value < old_value:
                        await self._check_and_enforce_coin_limit()

            except Exception as e:
                logger.error(f"Failed to process config change: {e}")

        try:
            await self.redis.subscribe("nexus:system:state_changed", handler)
            await self.redis.subscribe("nexus:config:updated", handler)
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in config change listener: {e}")

    async def _initiate_position_close(self, allocation_id: str, reason: str) -> None:
        """Initiate close for both legs of a position."""
        allocation = self._allocations.get(allocation_id)
        if not allocation:
            return

        # Get exchange info from allocation or database
        long_exchange = allocation.long_exchange
        short_exchange = allocation.short_exchange

        # If exchanges not set on allocation, fetch from database
        if not long_exchange or not short_exchange:
            try:
                async with self._db_session_factory() as db:
                    result = await db.execute(text("""
                        SELECT leg.exchange
                        FROM positions.legs leg
                        WHERE leg.position_id = :pos_id
                        ORDER BY leg.side
                    """), {"pos_id": allocation.position_id})
                    legs = result.fetchall()

                    # legs should have 2 entries: long and short
                    for leg in legs:
                        # First fetch could be long (buy) or short (sell)
                        if not long_exchange:
                            long_exchange = leg[0]
                        else:
                            short_exchange = leg[0]

            except Exception as e:
                logger.warning(
                    "Could not fetch exchange info from DB, using position manager fallback",
                    error=str(e),
                    position_id=allocation.position_id,
                )

        # If still no exchange info, try to get from position manager via Redis
        if not long_exchange or not short_exchange:
            try:
                position_data = await self.redis.get(f"nexus:position:{allocation.position_id}")
                if position_data:
                    pos = json.loads(position_data)
                    long_exchange = long_exchange or pos.get("long_exchange", "")
                    short_exchange = short_exchange or pos.get("short_exchange", "")
            except Exception:
                pass

        # Publish close request to execution engine
        await self.redis.publish(
            "nexus:execution:close_request",
            json.dumps({
                "allocation_id": allocation_id,
                "position_id": allocation.position_id,
                "symbol": allocation.symbol,
                "long_exchange": long_exchange or "",
                "short_exchange": short_exchange or "",
                "reason": reason,
                "close_both_legs": True,
                "timestamp": datetime.utcnow().isoformat(),
            }),
        )

        allocation.status = AllocationStatus.CLOSING
        logger.info(
            "Position close initiated",
            allocation_id=allocation_id,
            symbol=allocation.symbol,
            long_exchange=long_exchange,
            short_exchange=short_exchange,
            reason=reason,
        )

    async def _log_auto_unwind_event(
        self,
        allocation: Allocation,
        reason: str,
        weakness_score: float,
        coins_before: int,
        max_coins: int,
    ) -> None:
        """Log auto-unwind event to database for audit purposes."""
        try:
            async with self._db_session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO capital.auto_unwind_events
                        (allocation_id, position_id, symbol, reason, weakness_score, coins_before, max_coins)
                        VALUES (:alloc_id, :pos_id, :symbol, :reason, :score, :before, :max)
                    """),
                    {
                        "alloc_id": allocation.id,
                        "pos_id": allocation.position_id,
                        "symbol": allocation.symbol,
                        "reason": reason,
                        "score": weakness_score,
                        "before": coins_before,
                        "max": max_coins,
                    },
                )
                await session.commit()
        except Exception as e:
            logger.error("Failed to log auto-unwind event", error=str(e))

    async def _auto_allocate_loop(self) -> None:
        """Periodic allocation loop for rebalancing."""
        while self._running:
            try:
                # Check if auto-execute is enabled using consolidated check
                auto_execute = await self._is_auto_execute_enabled()

                if auto_execute:
                    await self._rebalance_allocations()

            except Exception as e:
                logger.error("Error in allocation loop", error=str(e))

            await asyncio.sleep(self._config["allocation_interval"])

    async def _is_auto_execute_enabled(self) -> bool:
        """
        Check auto-execute from database (single source of truth).

        This consolidates all auto-execute checks to avoid state divergence
        between database config and Redis state.
        """
        # First check system state - auto-execute can be overridden
        if self.state_manager:
            if not self.state_manager.is_running:
                return False
            if self.state_manager.circuit_breaker_active:
                return False
            if self.state_manager.mode == "maintenance":
                return False

        # Check database for explicit auto_execute setting
        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT value FROM config.system_settings
                    WHERE key = 'auto_execute'
                """))
                row = result.fetchone()
                if row and row[0]:
                    value = str(row[0]).lower()
                    return value in ('true', '1', 'yes')
            return self._config.get("auto_execute", True)  # Default enabled
        except Exception as e:
            logger.warning(f"Failed to check auto_execute from DB: {e}")
            return self._config.get("auto_execute", True)

    async def _rebalance_allocations(self) -> None:
        """Rebalance allocations based on current opportunities."""
        if not self.state_manager or not self.state_manager.should_open_positions():
            return

        # Check and enforce coin limit before any new allocations
        await self._check_and_enforce_coin_limit()

        # Check if we have capacity for more coins (unique symbols)
        # Use DB count as source of truth
        current_coins = await self._count_active_coins_from_db()
        max_coins = self._config["max_concurrent_coins"]
        if current_coins >= max_coins:
            return

        # Get top opportunities from cache
        opportunities = await self._get_top_opportunities()

        for opp in opportunities:
            opportunity_id = opp.get("id", "")
            symbol = opp.get("symbol", "")

            # Skip if already allocated
            if opportunity_id in self._opportunity_allocations:
                continue

            # Skip if this coin is already active (we track unique symbols)
            if self._is_coin_already_active(symbol):
                continue

            # Check UOS score
            uos_score = opp.get("uos_score", 0)
            if uos_score < self._config["high_quality_threshold"]:
                continue

            # Check available capital
            available = self.available_capital
            if available < self._config["min_allocation_usd"]:
                break

            # Allocate
            await self.allocate_to_opportunity(opp)

            # Check if at max coins after allocation (use in-memory for speed here)
            current_coins = self._count_active_coins()
            if current_coins >= max_coins:
                break

    async def _get_top_opportunities(self) -> list[dict[str, Any]]:
        """Get top opportunities from Redis cache."""
        try:
            opps_json = await self.redis.get("nexus:opportunities:top")
            if opps_json:
                return json.loads(opps_json)
        except Exception as e:
            logger.error(f"Failed to get opportunities", error=str(e))
        return []

    async def allocate_to_opportunity(self, opportunity: dict[str, Any]) -> dict[str, Any]:
        """Allocate capital to an opportunity."""
        opportunity_id = opportunity.get("id", "")

        # Check if already allocated
        if opportunity_id in self._opportunity_allocations:
            return {"success": False, "reason": "Already allocated"}

        # Check system state
        if self.state_manager and not self.state_manager.should_open_positions():
            return {"success": False, "reason": "System not accepting positions"}

        # Calculate allocation amount
        uos_score = Decimal(str(opportunity.get("uos_score", 0)))
        available = self.available_capital

        # Choose sizing method
        if self._config.get("use_kelly_criterion", True) and self._strategy_edge_cache:
            # Use Kelly criterion if enabled and we have edge data
            amount = self._calculate_kelly_size(opportunity)
            if amount == Decimal("0"):
                # Kelly says don't trade
                return {"success": False, "reason": "Kelly criterion suggests no position"}
        else:
            # Fallback to score-weighted sizing
            base_allocation = available * Decimal("0.1")  # 10% of available as base
            score_factor = (uos_score / 100) * self._config["score_weight_factor"] + Decimal("0.5")
            amount = base_allocation * score_factor

        # Adjust for correlation with existing positions
        amount = self._adjust_for_correlation(amount, opportunity)

        # Apply limits
        amount = max(amount, self._config["min_allocation_usd"])
        amount = min(amount, self._config["max_allocation_usd"])
        amount = min(amount, available)

        if amount < self._config["min_allocation_usd"]:
            return {"success": False, "reason": "Insufficient capital"}

        # Validate with Risk Manager
        validation = await self._validate_allocation(opportunity, float(amount))
        if not validation.get("approved"):
            return {"success": False, "reason": validation.get("reason", "Risk validation failed")}

        # Adjust amount if needed
        max_allowed = validation.get("max_allowed_size", float(amount))
        amount = min(amount, Decimal(str(max_allowed)))

        # Create allocation
        allocation = Allocation(
            opportunity_id=opportunity_id,
            amount_usd=float(amount),
            uos_score=float(uos_score),
            symbol=opportunity.get("symbol", ""),
            long_exchange=opportunity.get("long_exchange", ""),
            short_exchange=opportunity.get("short_exchange", ""),
        )

        self._allocations[allocation.id] = allocation
        self._opportunity_allocations[opportunity_id] = allocation.id
        self._allocated_capital += amount

        # Request execution
        await self.redis.publish(
            "nexus:execution:request",
            json.dumps({
                "opportunity_id": opportunity_id,
                "allocation_id": allocation.id,
                "position_size_usd": float(amount),
                "symbol": allocation.symbol,
                "long_exchange": allocation.long_exchange,
                "short_exchange": allocation.short_exchange,
            }),
        )

        # Publish allocation event
        event = CapitalAllocatedEvent(
            opportunity_id=opportunity_id,
            amount_usd=float(amount),
            timestamp=datetime.utcnow(),
        )
        await self.redis.publish("nexus:capital:allocated", event.model_dump_json())

        # Remove from pending approvals if present
        self._pending_approvals.pop(opportunity_id, None)

        # Cache state
        await self._cache_allocations()

        # Publish activity
        await self._publish_activity(
            "capital_allocated",
            f"Capital allocated: ${float(amount):.0f} to {allocation.symbol} (UOS: {uos_score:.0f})",
            allocation.to_dict(),
        )

        logger.info(
            f"Capital allocated",
            opportunity_id=opportunity_id,
            amount=float(amount),
            symbol=allocation.symbol,
        )

        return {"success": True, "amount_usd": float(amount), "allocation_id": allocation.id}

    async def _validate_allocation(
        self, opportunity: dict[str, Any], amount_usd: float
    ) -> dict[str, Any]:
        """Validate allocation with Risk Manager via HTTP API."""
        try:
            # Get risk manager URL from settings or use default
            settings = get_settings()
            risk_manager_url = getattr(settings, "risk_manager_url", "http://risk-manager:8006")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{risk_manager_url}/api/risk/validate",
                    json={
                        "opportunity_id": opportunity.get("id", ""),
                        "position_size_usd": amount_usd,
                        "long_exchange": opportunity.get("long_exchange", ""),
                        "short_exchange": opportunity.get("short_exchange", ""),
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    data = result.get("data", {})
                    return {
                        "approved": data.get("approved", False),
                        "reason": data.get("reason", ""),
                        "max_allowed_size": data.get("max_allowed_size", amount_usd),
                        "warnings": data.get("warnings", []),
                    }
                else:
                    logger.warning(
                        "Risk validation returned non-200",
                        status_code=response.status_code,
                        response=response.text[:200],
                    )
                    # Fail closed - reject if risk manager is unavailable
                    return {
                        "approved": False,
                        "reason": f"Risk validation failed: HTTP {response.status_code}",
                        "max_allowed_size": 0,
                    }

        except httpx.ConnectError:
            logger.warning("Risk Manager unavailable, rejecting allocation")
            return {
                "approved": False,
                "reason": "Risk Manager unavailable",
                "max_allowed_size": 0,
            }
        except httpx.TimeoutException:
            logger.warning("Risk validation timed out, rejecting allocation")
            return {
                "approved": False,
                "reason": "Risk validation timed out",
                "max_allowed_size": 0,
            }
        except Exception as e:
            logger.error(f"Risk validation failed", error=str(e))
            # Fail closed - don't allow trades if validation fails
            return {
                "approved": False,
                "reason": f"Risk validation error: {str(e)}",
                "max_allowed_size": 0,
            }

    async def _queue_for_approval(self, opportunity: dict[str, Any]) -> None:
        """Queue opportunity for manual approval."""
        opportunity_id = opportunity.get("id", "")

        if opportunity_id in self._pending_approvals:
            return  # Already queued

        self._pending_approvals[opportunity_id] = {
            **opportunity,
            "queued_at": datetime.utcnow().isoformat(),
        }

        # Publish to UI
        await self.redis.publish(
            "nexus:capital:pending_approval",
            json.dumps({
                "opportunity_id": opportunity_id,
                "symbol": opportunity.get("symbol"),
                "uos_score": opportunity.get("uos_score"),
                "long_exchange": opportunity.get("long_exchange"),
                "short_exchange": opportunity.get("short_exchange"),
                "suggested_size": float(self._calculate_suggested_size(opportunity)),
            }),
        )

        await self._publish_activity(
            "pending_approval",
            f"Opportunity awaiting approval: {opportunity.get('symbol')} (UOS: {opportunity.get('uos_score', 0):.0f})",
            {
                "opportunity_id": opportunity_id,
                "symbol": opportunity.get("symbol"),
                "uos_score": opportunity.get("uos_score"),
            },
        )

    def _calculate_suggested_size(self, opportunity: dict[str, Any]) -> Decimal:
        """Calculate suggested position size for an opportunity."""
        uos_score = Decimal(str(opportunity.get("uos_score", 0)))
        available = self.available_capital

        base_allocation = available * Decimal("0.1")
        score_factor = (uos_score / 100) * self._config["score_weight_factor"] + Decimal("0.5")
        amount = base_allocation * score_factor

        amount = max(amount, self._config["min_allocation_usd"])
        amount = min(amount, self._config["max_allocation_usd"])
        amount = min(amount, available)

        return amount

    # ==================== Kelly Criterion Sizing ====================

    async def _load_performance_history(self) -> None:
        """Load historical performance data for Kelly calculations."""
        try:
            async with self._db_session_factory() as db:
                # Get closed positions with P&L
                result = await db.execute(text("""
                    SELECT
                        symbol,
                        COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0) as total_pnl,
                        total_capital_deployed,
                        opened_at,
                        closed_at
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at IS NOT NULL
                      AND closed_at > NOW() - INTERVAL '30 days'
                    ORDER BY closed_at DESC
                    LIMIT 500
                """))
                rows = result.fetchall()

                for row in rows:
                    symbol = row[0]
                    total_pnl = float(row[1] or 0)
                    capital = float(row[2] or 1)
                    opened_at = row[3]
                    closed_at = row[4]

                    if symbol not in self._performance_history:
                        self._performance_history[symbol] = []

                    self._performance_history[symbol].append({
                        "pnl": total_pnl,
                        "capital": capital,
                        "return_pct": (total_pnl / capital * 100) if capital > 0 else 0,
                        "opened_at": opened_at.isoformat() if opened_at else None,
                        "closed_at": closed_at.isoformat() if closed_at else None,
                    })

                logger.info(
                    "Loaded performance history",
                    symbols=len(self._performance_history),
                    total_trades=sum(len(h) for h in self._performance_history.values()),
                )

        except Exception as e:
            logger.warning("Failed to load performance history", error=str(e))

    async def _update_edge_estimates(self) -> None:
        """Periodically update edge estimates for Kelly calculations."""
        while self._running:
            try:
                await self._calculate_strategy_edge()
            except Exception as e:
                logger.error("Failed to update edge estimates", error=str(e))

            await asyncio.sleep(self._edge_cache_ttl_seconds)

    async def _calculate_strategy_edge(self) -> None:
        """Calculate win rate and average win/loss for Kelly criterion."""
        try:
            async with self._db_session_factory() as db:
                # Get overall strategy statistics
                result = await db.execute(text("""
                    SELECT
                        symbol,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) > 0 THEN 1 ELSE 0 END) as wins,
                        AVG(CASE WHEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) > 0
                            THEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) / NULLIF(total_capital_deployed, 0)
                            ELSE NULL END) as avg_win_pct,
                        AVG(CASE WHEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) <= 0
                            THEN ABS((COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) / NULLIF(total_capital_deployed, 0))
                            ELSE NULL END) as avg_loss_pct
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at > NOW() - INTERVAL '30 days'
                    GROUP BY symbol
                    HAVING COUNT(*) >= 5
                """))
                rows = result.fetchall()

                for row in rows:
                    symbol = row[0]
                    total_trades = row[1]
                    wins = row[2]
                    avg_win = float(row[3] or 0)
                    avg_loss = float(row[4] or 0)

                    win_rate = wins / total_trades if total_trades > 0 else 0.5

                    self._strategy_edge_cache[symbol] = {
                        "win_rate": win_rate,
                        "avg_win": avg_win,
                        "avg_loss": avg_loss,
                        "total_trades": total_trades,
                        "updated_at": datetime.utcnow().isoformat(),
                    }

                # Calculate overall strategy edge
                overall_result = await db.execute(text("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) > 0 THEN 1 ELSE 0 END) as wins,
                        AVG(CASE WHEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) > 0
                            THEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) / NULLIF(total_capital_deployed, 0)
                            ELSE NULL END) as avg_win_pct,
                        AVG(CASE WHEN (COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) <= 0
                            THEN ABS((COALESCE(realized_pnl_funding, 0) + COALESCE(realized_pnl_price, 0)) / NULLIF(total_capital_deployed, 0))
                            ELSE NULL END) as avg_loss_pct
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at > NOW() - INTERVAL '30 days'
                """))
                overall = overall_result.fetchone()

                if overall and overall[0] >= 10:
                    overall_win_rate = overall[1] / overall[0] if overall[0] > 0 else 0.5
                    self._strategy_edge_cache["_overall"] = {
                        "win_rate": overall_win_rate,
                        "avg_win": float(overall[2] or 0.02),  # Default 2% win
                        "avg_loss": float(overall[3] or 0.01),  # Default 1% loss
                        "total_trades": overall[0],
                        "updated_at": datetime.utcnow().isoformat(),
                    }

                logger.info(
                    "Updated strategy edge estimates",
                    symbols_with_data=len(self._strategy_edge_cache),
                )

        except Exception as e:
            logger.warning("Failed to calculate strategy edge", error=str(e))

    def _calculate_kelly_size(self, opportunity: dict[str, Any]) -> Decimal:
        """
        Calculate optimal position size using Kelly criterion.

        Kelly formula: f* = (bp - q) / b
        where:
        - f* = fraction of capital to bet
        - b = odds received on bet (avg_win / avg_loss)
        - p = probability of winning
        - q = probability of losing (1 - p)

        We use half-Kelly for safety.
        """
        symbol = opportunity.get("symbol", "")

        # Get edge data for this symbol or use overall strategy edge
        edge_data = self._strategy_edge_cache.get(
            symbol,
            self._strategy_edge_cache.get("_overall", {})
        )

        if not edge_data:
            # No historical data - use conservative default
            return self._config["min_allocation_usd"]

        win_rate = edge_data.get("win_rate", 0.55)
        avg_win = edge_data.get("avg_win", 0.02)  # 2% average win
        avg_loss = edge_data.get("avg_loss", 0.01)  # 1% average loss

        # Ensure we have minimum edge before using Kelly
        if avg_loss <= 0:
            avg_loss = 0.01  # Prevent division by zero

        # Calculate Kelly fraction
        b = avg_win / avg_loss  # Odds
        p = win_rate
        q = 1 - p

        kelly_fraction = (b * p - q) / b

        # Validate Kelly result
        if kelly_fraction <= 0:
            # Negative Kelly means we shouldn't bet
            logger.info(
                "Kelly suggests no position",
                symbol=symbol,
                kelly_fraction=kelly_fraction,
                win_rate=win_rate,
            )
            return Decimal("0")

        # Apply safety factor (half-Kelly)
        safe_kelly = Decimal(str(kelly_fraction)) * self._config["kelly_fraction"]

        # Cap at reasonable maximum (25% of capital)
        safe_kelly = min(safe_kelly, Decimal("0.25"))

        # Ensure minimum edge threshold
        if safe_kelly < self._config["min_kelly_edge"]:
            return self._config["min_allocation_usd"]

        # Calculate position size
        capital = self.available_capital
        kelly_size = capital * safe_kelly

        logger.info(
            "Kelly position size calculated",
            symbol=symbol,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            raw_kelly=kelly_fraction,
            safe_kelly=float(safe_kelly),
            kelly_size=float(kelly_size),
        )

        return kelly_size

    # ==================== Correlation-Aware Sizing ====================

    def _calculate_portfolio_correlation(self, opportunity: dict[str, Any]) -> Decimal:
        """
        Estimate correlation of new opportunity with existing portfolio.

        Higher correlation = should reduce position size to avoid concentration.
        """
        symbol = opportunity.get("symbol", "")

        # Get active positions
        active_symbols = set()
        for alloc in self._allocations.values():
            if alloc.status in [AllocationStatus.ACTIVE, AllocationStatus.EXECUTING]:
                active_symbols.add(alloc.symbol)

        if not active_symbols:
            return Decimal("0")  # No existing positions

        # Same symbol = perfect correlation
        if symbol in active_symbols:
            return Decimal("1.0")

        # Simple correlation estimation based on symbol similarity
        # In production, this would use actual price correlation data
        correlation_score = Decimal("0")

        # BTC-related pairs tend to be correlated
        btc_symbols = {"BTCUSDT", "BTC-PERP", "BTCUSD"}
        if symbol in btc_symbols or any(s in btc_symbols for s in active_symbols):
            if symbol in btc_symbols and any(s in btc_symbols for s in active_symbols):
                correlation_score = Decimal("0.3")

        # Check for similar base assets (e.g., ETHUSDT and ETHPERP)
        base_asset = symbol.replace("USDT", "").replace("-PERP", "").replace("USD", "")
        for active_symbol in active_symbols:
            active_base = active_symbol.replace("USDT", "").replace("-PERP", "").replace("USD", "")
            if base_asset == active_base:
                correlation_score = max(correlation_score, Decimal("0.8"))

        # General market correlation (crypto assets are moderately correlated)
        base_market_correlation = Decimal("0.3")
        correlation_score = max(correlation_score, base_market_correlation)

        return min(correlation_score, Decimal("1.0"))

    def _adjust_for_correlation(
        self,
        size: Decimal,
        opportunity: dict[str, Any],
    ) -> Decimal:
        """
        Reduce position size if highly correlated with existing positions.

        This helps prevent concentration risk in correlated assets.
        """
        correlation = self._calculate_portfolio_correlation(opportunity)

        max_correlation = self._config["max_portfolio_correlation"]

        if correlation <= max_correlation:
            # Below threshold - no adjustment needed
            return size

        # Apply penalty for high correlation
        penalty = self._config["correlation_size_penalty"]
        excess_correlation = correlation - max_correlation
        adjustment = Decimal("1") - (excess_correlation * penalty)
        adjustment = max(adjustment, Decimal("0.25"))  # Don't reduce below 25%

        adjusted_size = size * adjustment

        logger.info(
            "Position size adjusted for correlation",
            symbol=opportunity.get("symbol"),
            correlation=float(correlation),
            original_size=float(size),
            adjusted_size=float(adjusted_size),
            adjustment_factor=float(adjustment),
        )

        return adjusted_size

    # ==================== Performance Tracking ====================

    async def _record_allocation_outcome(
        self,
        allocation: Allocation,
        outcome: dict[str, Any],
    ) -> None:
        """Record allocation outcome for Kelly criterion learning."""
        symbol = allocation.symbol
        pnl = outcome.get("realized_pnl", 0)
        capital = allocation.amount_usd

        if symbol not in self._performance_history:
            self._performance_history[symbol] = []

        self._performance_history[symbol].append({
            "pnl": pnl,
            "capital": capital,
            "return_pct": (pnl / capital * 100) if capital > 0 else 0,
            "uos_score": allocation.uos_score,
            "opened_at": allocation.executed_at.isoformat() if allocation.executed_at else None,
            "closed_at": datetime.utcnow().isoformat(),
        })

        # Keep only last 100 trades per symbol
        if len(self._performance_history[symbol]) > 100:
            self._performance_history[symbol] = self._performance_history[symbol][-100:]

        # Invalidate edge cache for this symbol
        if symbol in self._strategy_edge_cache:
            del self._strategy_edge_cache[symbol]

        logger.info(
            "Recorded allocation outcome",
            symbol=symbol,
            pnl=pnl,
            return_pct=(pnl / capital * 100) if capital > 0 else 0,
        )

    def get_kelly_analysis(self, symbol: Optional[str] = None) -> dict[str, Any]:
        """Get Kelly criterion analysis for API."""
        if symbol and symbol in self._strategy_edge_cache:
            edge = self._strategy_edge_cache[symbol]
            kelly = self._calculate_kelly_fraction(edge)
            return {
                "symbol": symbol,
                "edge_data": edge,
                "kelly_fraction": kelly,
                "recommended_size_pct": float(kelly * self._config["kelly_fraction"] * 100),
            }

        # Return overall analysis
        overall = self._strategy_edge_cache.get("_overall", {})
        symbols_data = {
            sym: {
                "edge_data": edge,
                "kelly_fraction": self._calculate_kelly_fraction(edge),
            }
            for sym, edge in self._strategy_edge_cache.items()
            if sym != "_overall"
        }

        return {
            "overall_edge": overall,
            "overall_kelly": self._calculate_kelly_fraction(overall) if overall else 0,
            "symbols": symbols_data,
            "total_symbols_analyzed": len(symbols_data),
        }

    def _calculate_kelly_fraction(self, edge_data: dict) -> float:
        """Calculate raw Kelly fraction from edge data."""
        if not edge_data:
            return 0

        win_rate = edge_data.get("win_rate", 0.5)
        avg_win = edge_data.get("avg_win", 0)
        avg_loss = edge_data.get("avg_loss", 0)

        if avg_loss <= 0:
            return 0

        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b if b > 0 else 0
        return max(0, kelly)

    # ==================== Manual Approval ====================

    async def approve_opportunity(
        self, opportunity_id: str, amount_usd: Optional[float] = None
    ) -> dict[str, Any]:
        """Approve a pending opportunity for execution."""
        pending = self._pending_approvals.get(opportunity_id)
        if not pending:
            return {"success": False, "reason": "Opportunity not found in pending queue"}

        if amount_usd:
            pending["override_amount"] = amount_usd

        result = await self.allocate_to_opportunity(pending)
        return result

    async def reject_opportunity(self, opportunity_id: str) -> dict[str, Any]:
        """Reject a pending opportunity."""
        if opportunity_id not in self._pending_approvals:
            return {"success": False, "reason": "Opportunity not found in pending queue"}

        self._pending_approvals.pop(opportunity_id)

        await self._publish_activity(
            "opportunity_rejected",
            f"Opportunity rejected: {opportunity_id}",
            {"opportunity_id": opportunity_id},
        )

        return {"success": True}

    # ==================== State Management ====================

    async def _update_capital_periodic(self) -> None:
        """Periodically update total capital from balance monitor."""
        while self._running:
            try:
                if self.balance_monitor:
                    balances = self.balance_monitor.get_balances()
                    self._total_capital = Decimal(str(balances.get("total_usd", 0)))
                else:
                    # Try to get from Redis cache
                    balance_json = await self.redis.get("nexus:balances:total")
                    if balance_json:
                        data = json.loads(balance_json)
                        self._total_capital = Decimal(str(data.get("total_usd", 0)))

            except Exception as e:
                logger.error(f"Failed to update capital", error=str(e))

            await asyncio.sleep(60)  # Every minute

    async def _cache_allocations(self) -> None:
        """Cache allocations to Redis."""
        allocations_data = [a.to_dict() for a in self._allocations.values()]
        await self.redis.set("nexus:capital:allocations", json.dumps(allocations_data))

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
            "service": "capital-allocator",
            "level": level,
            "message": message,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.redis.publish("nexus:activity", json.dumps(activity))

    # ==================== Public Methods ====================

    async def set_auto_execute(self, enabled: bool) -> None:
        """Enable or disable auto-execution mode."""
        self._config["auto_execute"] = enabled

        # Update system state
        if self.state_manager:
            await self.state_manager.update_state(auto_execute=enabled)

        await self._publish_activity(
            "auto_execute_changed",
            f"Auto-execute mode {'enabled' if enabled else 'disabled'}",
            {"auto_execute": enabled},
        )

        logger.info(f"Auto-execute mode set to {enabled}")

    async def cancel_allocation(self, allocation_id: str) -> dict[str, Any]:
        """Cancel a pending allocation."""
        allocation = self._allocations.get(allocation_id)
        if not allocation:
            return {"success": False, "reason": "Allocation not found"}

        if allocation.status != AllocationStatus.PENDING:
            return {"success": False, "reason": "Can only cancel pending allocations"}

        allocation.status = AllocationStatus.CANCELLED
        self._allocated_capital -= Decimal(str(allocation.amount_usd))

        await self._cache_allocations()

        await self._publish_activity(
            "allocation_cancelled",
            f"Allocation cancelled: {allocation.symbol}",
            allocation.to_dict(),
        )

        return {"success": True}

    @property
    def total_capital(self) -> float:
        """Get total capital."""
        if self._total_capital > 0:
            return float(self._total_capital)
        if self.balance_monitor:
            balances = self.balance_monitor.get_balances()
            return balances.get("total_usd", 0)
        return 0

    @property
    def allocated_capital(self) -> float:
        return float(self._allocated_capital)

    @property
    def available_capital(self) -> Decimal:
        total = Decimal(str(self.total_capital))
        reserve = total * self._reserve_pct
        return max(Decimal("0"), total - self._allocated_capital - reserve)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def auto_execute_enabled(self) -> bool:
        return self._config["auto_execute"]

    def get_state(self) -> dict[str, Any]:
        """Get capital allocator state."""
        total = self.total_capital
        active_allocations = [
            a for a in self._allocations.values()
            if a.status in [AllocationStatus.PENDING, AllocationStatus.EXECUTING, AllocationStatus.ACTIVE]
        ]

        return {
            "total_capital_usd": total,
            "allocated_capital_usd": float(self._allocated_capital),
            "available_capital_usd": float(self.available_capital),
            "reserve_pct": float(self._reserve_pct * 100),
            "utilization_pct": (
                float(self._allocated_capital / Decimal(str(total)) * 100)
                if total > 0 else 0
            ),
            "active_allocations": len(active_allocations),
            "pending_approvals": len(self._pending_approvals),
            "auto_execute": self._config["auto_execute"],
            "min_uos_score": self._config["min_uos_score"],
            "high_quality_threshold": self._config["high_quality_threshold"],
        }

    def get_allocations(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        """Get allocations list."""
        allocations = list(self._allocations.values())
        if status:
            allocations = [a for a in allocations if a.status == status]
        allocations.sort(key=lambda a: a.created_at, reverse=True)
        return [a.to_dict() for a in allocations]

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """Get pending approvals list."""
        return list(self._pending_approvals.values())

    def get_exchange_balances(self) -> dict[str, float]:
        """Get exchange balances from balance monitor."""
        if self.balance_monitor:
            balances = self.balance_monitor.get_balances()
            return {
                slug: data.get("total_usd", 0)
                for slug, data in balances.get("exchanges", {}).items()
                if isinstance(data, dict)
            }
        return {}

    def get_config(self) -> dict[str, Any]:
        """Get current configuration."""
        return {
            k: float(v) if isinstance(v, Decimal) else v
            for k, v in self._config.items()
        }

    async def update_config(self, **kwargs) -> dict[str, Any]:
        """Update configuration."""
        for key, value in kwargs.items():
            if key in self._config:
                if isinstance(self._config[key], Decimal):
                    self._config[key] = Decimal(str(value))
                else:
                    self._config[key] = value

        await self._publish_activity(
            "config_updated",
            "Capital allocator configuration updated",
            kwargs,
        )

        return {"success": True, "config": self.get_config()}
