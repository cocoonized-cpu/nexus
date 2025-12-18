"""
Opportunity Detector Manager - Identifies and scores arbitrage opportunities.

The Unified Opportunity Score (UOS) is a 0-100 point composite score:
- Return Score (0-30): Based on net APR and spread
- Risk Score (0-30): Based on volatility, correlation, liquidity
- Execution Score (0-25): Based on slippage, fees, exchange reliability
- Timing Score (0-15): Based on funding cycle timing

Opportunities must meet minimum thresholds to be considered actionable.
Only opportunities involving exchanges with configured credentials are
considered executable (shown by default). All opportunities can optionally
be shown in the UI for informational purposes.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.detector.scorer import UOSScorer

from shared.events.opportunity import (OpportunityDetectedEvent,
                                       OpportunityExpiredEvent,
                                       OpportunityUpdatedEvent)
from shared.models.opportunity import BotAction, Opportunity, OpportunityLeg, UOSScores
from shared.utils.logging import get_logger
from src.detector.bot_action import BotActionCalculator
from shared.utils.redis_client import RedisClient
from shared.utils.system_state import SystemStateManager

logger = get_logger(__name__)

# Exchange name mapping from short names to full slug names
EXCHANGE_NAME_MAP = {
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


class OpportunityDetector:
    """
    Detects and scores funding rate arbitrage opportunities.

    Consumes unified funding snapshots and produces scored opportunities.
    """

    def __init__(self, redis: RedisClient, db_session_factory=None):
        self.redis = redis
        self.db_session_factory = db_session_factory
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # System state manager for auto-execution checks
        self.state_manager = SystemStateManager(redis, "opportunity-detector", db_session_factory)

        # UOS Scorer
        self.scorer = UOSScorer()

        # Active opportunities: {opportunity_id: Opportunity}
        self._opportunities: dict[str, Opportunity] = {}

        # Exchanges with configured credentials (loaded on start)
        # Only opportunities involving these exchanges will be considered executable
        self._exchanges_with_credentials: set[str] = set()

        # Blacklisted symbols (loaded from database)
        # Opportunities for these symbols will never be created
        self._blacklisted_symbols: set[str] = set()

        # Configuration (would be loaded from DB in production)
        self._config = {
            "min_spread_pct": 0.01,  # Minimum 0.01% spread
            "min_net_apr_pct": 10.0,  # Minimum 10% annualized APR
            "min_uos_score": 50,  # Minimum UOS score to publish
            "min_uos_auto_execute": 75,  # Minimum UOS score for auto-execution
            "min_volume_24h_usd": 1_000_000,  # Minimum $1M 24h volume
            "min_liquidity_usd": 100_000,  # Minimum $100K liquidity
            "detection_interval": 10,  # Run detection every 10 seconds
            "opportunity_ttl_minutes": 30,  # Opportunities expire after 30 min
            "only_executable": True,  # Only detect opportunities for exchanges with credentials
            "max_position_size_usd": 5000,  # Maximum position size in USD (loaded from DB)
        }

        # Risk limits (loaded from database)
        self._risk_limits = {
            "max_position_size_usd": 5000,  # Default max $5000 per position
        }

        # Statistics
        self._stats = {
            "detection_cycles": 0,
            "opportunities_detected": 0,
            "opportunities_expired": 0,
            "opportunities_published": 0,
            "opportunities_skipped_no_credentials": 0,
            "opportunities_skipped_blacklisted": 0,
            "auto_executions_triggered": 0,
            "start_time": None,
        }

        # Debounce tracking for detection cycles
        self._last_detection_time: Optional[datetime] = None
        self._detection_debounce_seconds = 5  # Skip detection if run within 5 seconds

        # Bot action calculator (initialized after state manager is ready)
        self._bot_action_calculator: Optional[BotActionCalculator] = None

        # Allocation context cache (refreshed periodically)
        self._allocation_context = {
            "active_coins": 0,
            "max_coins": 5,
            "available_capital": 0,
            "positions_by_symbol": set(),
            "last_update": None,
        }

    async def start(self) -> None:
        """Start the opportunity detector."""
        logger.info("Starting Opportunity Detector")

        self._running = True
        self._stats["start_time"] = datetime.utcnow()

        # Start system state manager
        await self.state_manager.start()

        # Load risk limits from database
        await self._load_risk_limits()

        # Load exchanges with configured credentials
        await self._load_exchanges_with_credentials()

        # Load blacklisted symbols
        await self._load_blacklisted_symbols()

        # Recover unexpired opportunities from database
        await self._recover_opportunities()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._listen_funding_updates()),
            asyncio.create_task(self._run_detection_loop()),
            asyncio.create_task(self._cleanup_expired()),
            asyncio.create_task(self._listen_position_events()),
            asyncio.create_task(self._refresh_exchange_credentials()),
            asyncio.create_task(self._listen_config_updates()),
            asyncio.create_task(self._listen_blacklist_updates()),
            asyncio.create_task(self._run_redis_listener()),
            asyncio.create_task(self._publish_status_updates()),
        ]

        logger.info(
            "Opportunity Detector started",
            auto_execute=self.state_manager.auto_execute,
            system_running=self.state_manager.is_running,
            executable_exchanges=list(self._exchanges_with_credentials),
            blacklisted_symbols=list(self._blacklisted_symbols),
        )

    async def stop(self) -> None:
        """Stop the opportunity detector."""
        logger.info("Stopping Opportunity Detector")
        self._running = False

        # Stop state manager
        await self.state_manager.stop()

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("Opportunity Detector stopped")

    @property
    def is_running(self) -> bool:
        """Check if detector is running."""
        return self._running

    @property
    def active_opportunity_count(self) -> int:
        """Get count of active opportunities."""
        return len(self._opportunities)

    async def _load_risk_limits(self) -> None:
        """Load risk limits from database."""
        if not self.db_session_factory:
            logger.warning("No database connection - using default risk limits")
            return

        try:
            async with self.db_session_factory() as db:
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

    async def _load_exchanges_with_credentials(self) -> None:
        """Load list of exchanges that have configured credentials."""
        if not self.db_session_factory:
            logger.warning("No database connection - cannot load exchange credentials")
            return

        try:
            async with self.db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT slug
                    FROM config.exchanges
                    WHERE enabled = true
                    AND (api_key_encrypted IS NOT NULL OR wallet_address_encrypted IS NOT NULL)
                """))
                rows = result.fetchall()

                self._exchanges_with_credentials = {row[0] for row in rows}

                # Also add short name versions for matching
                short_names = set()
                for slug in self._exchanges_with_credentials:
                    # Extract short name from slug (e.g., 'binance_futures' -> 'binance')
                    short_name = slug.replace('_futures', '').replace('_spot', '')
                    short_names.add(short_name)

                self._exchanges_with_credentials.update(short_names)

                logger.info(
                    "Loaded exchanges with credentials",
                    exchanges=list(self._exchanges_with_credentials),
                    count=len(self._exchanges_with_credentials),
                )

        except Exception as e:
            logger.error("Failed to load exchanges with credentials", error=str(e))

    async def _load_blacklisted_symbols(self) -> None:
        """Load blacklisted symbols from database."""
        if not self.db_session_factory:
            logger.warning("No database connection - cannot load blacklisted symbols")
            return

        try:
            async with self.db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT symbol FROM config.symbol_blacklist
                """))
                rows = result.fetchall()

                self._blacklisted_symbols = {row[0].upper() for row in rows}

                logger.info(
                    "Loaded blacklisted symbols",
                    symbols=list(self._blacklisted_symbols),
                    count=len(self._blacklisted_symbols),
                )

        except Exception as e:
            logger.warning("Failed to load blacklisted symbols", error=str(e))

    async def _listen_blacklist_updates(self) -> None:
        """Listen for blacklist changes via Redis pub/sub."""
        try:
            await self.redis.subscribe(
                "nexus:config:blacklist_changed",
                self._handle_blacklist_update,
            )
            logger.info("Subscribed to blacklist updates")
        except Exception as e:
            logger.error("Failed to subscribe to blacklist updates", error=str(e))

    async def _handle_blacklist_update(self, channel: str, message: str) -> None:
        """Handle blacklist change notifications."""
        try:
            data = json.loads(message)
            action = data.get("action")
            symbol = data.get("symbol", "").upper()

            if action == "added" and symbol:
                self._blacklisted_symbols.add(symbol)
                logger.info(
                    "Symbol added to blacklist",
                    symbol=symbol,
                    reason=data.get("reason"),
                )

                # Remove any active opportunities for this symbol
                opps_to_remove = [
                    opp_id for opp_id, opp in self._opportunities.items()
                    if opp.symbol.upper() == symbol
                ]
                for opp_id in opps_to_remove:
                    opp = self._opportunities.pop(opp_id)
                    await self._publish_expired(opp, "blacklisted")
                    logger.info(
                        "Removed opportunity for blacklisted symbol",
                        opportunity_id=opp_id,
                        symbol=symbol,
                    )

            elif action == "removed" and symbol:
                self._blacklisted_symbols.discard(symbol)
                logger.info("Symbol removed from blacklist", symbol=symbol)

        except Exception as e:
            logger.error("Failed to handle blacklist update", error=str(e))

    def _is_symbol_blacklisted(self, symbol: str) -> bool:
        """Check if a symbol is blacklisted."""
        return symbol.upper() in self._blacklisted_symbols

    async def _refresh_exchange_credentials(self) -> None:
        """Periodically refresh the list of exchanges with credentials."""
        while self._running:
            await asyncio.sleep(60)  # Refresh every 60 seconds for responsive credential updates
            try:
                await self._load_exchanges_with_credentials()
                # Also refresh risk limits
                await self._load_risk_limits()
            except Exception as e:
                logger.warning("Failed to refresh exchange credentials", error=str(e))

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

    async def _run_redis_listener(self) -> None:
        """Run the Redis pub/sub listener to dispatch messages to handlers."""
        try:
            logger.info("Starting Redis listener for config updates")
            await self.redis.listen()
        except asyncio.CancelledError:
            logger.debug("Redis listener cancelled")
        except Exception as e:
            logger.error("Redis listener error", error=str(e))

    async def _publish_status_updates(self) -> None:
        """Periodically publish status updates with trading decision explanations."""
        # Wait for initial startup
        await asyncio.sleep(10)

        while self._running:
            try:
                # Count opportunities by score range
                high_score_opps = [o for o in self._opportunities.values() if o.uos_score >= 75]
                medium_score_opps = [o for o in self._opportunities.values() if 60 <= o.uos_score < 75]

                # Determine trading status
                max_size = self._risk_limits.get("max_position_size_usd", 5000)
                auto_execute = self.state_manager.auto_execute
                system_ready = self.state_manager.should_execute()

                # Build status message
                if not self.state_manager.is_running:
                    status = "System is stopped"
                    action = "Start the system to enable trading"
                elif not auto_execute:
                    status = "Auto-execution is disabled"
                    action = "Enable auto-execute in Situation Room to allow automatic trading"
                elif self.state_manager.mode == "discovery":
                    status = "System in discovery mode"
                    action = "Switch to standard mode to enable trading"
                elif self.state_manager.circuit_breaker_active:
                    status = "Circuit breaker active"
                    action = "Review risk alerts and reset circuit breaker"
                elif not high_score_opps:
                    status = "No high-quality opportunities"
                    action = f"Waiting for opportunities with UOS ≥ 75 (best current: {max(o.uos_score for o in self._opportunities.values()) if self._opportunities else 0:.0f})"
                else:
                    status = "Ready to trade"
                    action = f"{len(high_score_opps)} opportunities ready for execution"

                # Publish status update
                await self._publish_activity(
                    "system_status",
                    {
                        "status": status,
                        "action": action,
                        "auto_execute": auto_execute,
                        "system_running": self.state_manager.is_running,
                        "mode": self.state_manager.mode,
                        "max_position_size_usd": max_size,
                        "total_opportunities": len(self._opportunities),
                        "high_score_opportunities": len(high_score_opps),
                        "medium_score_opportunities": len(medium_score_opps),
                        "exchanges_connected": len(self._exchanges_with_credentials),
                    },
                    level="info",
                )

                # If there are high-score opportunities but not trading, explain why for each
                if high_score_opps and not auto_execute:
                    # Report top 3 missed opportunities
                    top_opps = sorted(high_score_opps, key=lambda o: o.uos_score, reverse=True)[:3]
                    for opp in top_opps:
                        await self._publish_activity(
                            "opportunity_ready",
                            {
                                "opportunity_id": opp.id,
                                "symbol": opp.symbol,
                                "uos_score": float(opp.uos_score),
                                "recommended_size_usd": float(opp.recommended_size_usd) if opp.recommended_size_usd else 0,
                                "long_exchange": opp.long_leg.exchange,
                                "short_exchange": opp.short_leg.exchange,
                                "reason": "Auto-execute disabled - enable to trade",
                                "action": "none",
                            },
                            level="info",
                        )

            except Exception as e:
                logger.warning("Failed to publish status update", error=str(e))

            # Publish every 30 seconds
            await asyncio.sleep(30)

    def _normalize_exchange_name(self, exchange: str) -> str:
        """Normalize exchange name to slug format."""
        return EXCHANGE_NAME_MAP.get(exchange.lower(), exchange)

    def _is_exchange_executable(self, exchange: str) -> bool:
        """Check if an exchange has credentials configured."""
        # Check both the raw name and normalized name
        normalized = self._normalize_exchange_name(exchange)
        return (
            exchange.lower() in self._exchanges_with_credentials
            or normalized in self._exchanges_with_credentials
        )

    async def _listen_funding_updates(self) -> None:
        """Listen to unified funding snapshot events."""
        logger.info("Subscribing to unified funding snapshots")

        async def handle_snapshot(channel: str, message: str):
            try:
                # Snapshot received - trigger detection
                await self.run_detection_cycle()
            except Exception as e:
                logger.warning("Failed to process snapshot", error=str(e))

        await self.redis.subscribe(
            "nexus:market_data:unified_snapshot",
            handle_snapshot,
        )

        while self._running:
            await asyncio.sleep(1)

    async def _run_detection_loop(self) -> None:
        """Periodic detection loop."""
        while self._running:
            try:
                await self.run_detection_cycle()
            except Exception as e:
                logger.error("Error in detection loop", error=str(e))

            await asyncio.sleep(self._config["detection_interval"])

    async def run_detection_cycle(self) -> None:
        """Run a single detection cycle with debouncing to prevent duplicates."""
        # Debounce: Skip if we ran detection very recently
        now = datetime.utcnow()
        if self._last_detection_time is not None:
            elapsed = (now - self._last_detection_time).total_seconds()
            if elapsed < self._detection_debounce_seconds:
                logger.debug(
                    "Skipping detection cycle (debounced)",
                    elapsed_seconds=elapsed,
                    debounce_threshold=self._detection_debounce_seconds,
                )
                return

        self._last_detection_time = now
        self._stats["detection_cycles"] += 1

        # Fetch funding spreads from Funding Aggregator
        spreads = await self._fetch_funding_spreads()

        # Process each spread as potential opportunity
        for spread in spreads:
            await self._process_spread(spread)

        logger.debug(
            "Detection cycle complete",
            spreads=len(spreads),
            opportunities=len(self._opportunities),
        )

    async def _fetch_funding_spreads(self) -> list[dict[str, Any]]:
        """Fetch funding spreads from Redis cache or Funding Aggregator."""
        # In production, this would call the Funding Aggregator API
        # For now, simulate with Redis subscription data

        # Check for cached spreads
        spreads_json = await self.redis.get("nexus:cache:funding_spreads")
        if spreads_json:
            return json.loads(spreads_json)

        # Return empty if no data available
        return []

    async def _process_spread(self, spread: dict[str, Any]) -> None:
        """Process a funding spread and create/update opportunity."""
        symbol = spread.get("symbol", "")
        long_exchange = spread.get("long_exchange", "")
        short_exchange = spread.get("short_exchange", "")
        spread_pct = spread.get("spread_pct", 0)

        # Check if symbol is blacklisted
        if self._is_symbol_blacklisted(symbol):
            self._stats["opportunities_skipped_blacklisted"] += 1
            # Log occasionally to avoid spam
            if self._stats["opportunities_skipped_blacklisted"] % 100 == 1:
                logger.debug(
                    "Skipping opportunity - symbol is blacklisted",
                    symbol=symbol,
                )
            return

        # Check minimum spread threshold
        if spread_pct < self._config["min_spread_pct"]:
            return

        # Check if both exchanges have credentials (if only_executable is enabled)
        if self._config.get("only_executable", True):
            long_executable = self._is_exchange_executable(long_exchange)
            short_executable = self._is_exchange_executable(short_exchange)

            if not long_executable or not short_executable:
                self._stats["opportunities_skipped_no_credentials"] += 1
                # Log occasionally to avoid spam
                if self._stats["opportunities_skipped_no_credentials"] % 100 == 1:
                    logger.debug(
                        "Skipping opportunity - exchange(s) without credentials",
                        symbol=symbol,
                        long_exchange=long_exchange,
                        long_has_credentials=long_executable,
                        short_exchange=short_exchange,
                        short_has_credentials=short_executable,
                    )
                return

        # Generate opportunity ID based on components
        opp_key = f"{symbol}:{long_exchange}:{short_exchange}"

        # Check if opportunity already exists
        existing = self._find_existing_opportunity(opp_key)

        if existing:
            # Update existing opportunity
            await self._update_opportunity(existing, spread)
        else:
            # Create new opportunity
            await self._create_opportunity(spread)

    def _find_existing_opportunity(self, opp_key: str) -> Optional[Opportunity]:
        """Find existing opportunity by key."""
        for opp in self._opportunities.values():
            key = f"{opp.symbol}:{opp.long_leg.exchange}:{opp.short_leg.exchange}"
            if key == opp_key:
                return opp
        return None

    async def _create_opportunity(self, spread: dict[str, Any]) -> None:
        """Create a new opportunity from spread data."""
        try:
            # Calculate UOS score
            scores = self.scorer.calculate_scores(spread)
            total_score = scores.total  # Use 'total' computed property

            # Check minimum score threshold
            if total_score < self._config["min_uos_score"]:
                return

            # Calculate recommended position size based on score
            # Get max position size from risk limits (default $5000)
            max_size = self._risk_limits.get("max_position_size_usd", 5000)

            # Base size scaled by UOS score quality, capped at max_position_size_usd
            if total_score >= 80:  # exceptional - use up to max allowed
                recommended_size = max_size
            elif total_score >= 70:  # strong - 50% of max
                recommended_size = max_size * 0.5
            elif total_score >= 60:  # good - 20% of max
                recommended_size = max_size * 0.2
            else:  # minimum size - 10% of max
                recommended_size = max_size * 0.1

            # Create opportunity
            opportunity = Opportunity(
                id=str(uuid4()),
                symbol=spread["symbol"],
                opportunity_type="funding_arbitrage",
                long_leg=OpportunityLeg(
                    exchange=spread["long_exchange"],
                    side="long",
                    funding_rate=spread["long_rate"],
                    estimated_slippage=0.001,  # Would be calculated
                ),
                short_leg=OpportunityLeg(
                    exchange=spread["short_exchange"],
                    side="short",
                    funding_rate=spread["short_rate"],
                    estimated_slippage=0.001,
                ),
                funding_spread=spread["spread"],
                funding_spread_pct=spread["spread_pct"],
                estimated_net_apr=spread.get("annualized_apr", 0),
                uos_score_direct=total_score,
                uos_breakdown=scores,
                recommended_size_usd=recommended_size,
                detected_at=datetime.utcnow(),
                expires_at=datetime.utcnow()
                + timedelta(minutes=self._config["opportunity_ttl_minutes"]),
                status="active",
            )

            self._opportunities[opportunity.id] = opportunity
            self._stats["opportunities_detected"] += 1

            # Publish event
            event = OpportunityDetectedEvent(
                opportunity_id=opportunity.id,
                symbol=opportunity.symbol,
                long_exchange=spread["long_exchange"],
                short_exchange=spread["short_exchange"],
                spread_pct=spread["spread_pct"],
                gross_apr=spread.get("annualized_apr", 0),
            )
            await self.redis.publish(
                "nexus:opportunity:detected",
                event.model_dump_json(),
            )

            self._stats["opportunities_published"] += 1

            # Persist to database
            await self._save_opportunity_to_db(opportunity, spread)

            logger.info(
                "New opportunity detected",
                id=opportunity.id,
                symbol=opportunity.symbol,
                score=total_score,
                spread_pct=spread["spread_pct"],
            )

            # Check for auto-execution
            await self._check_auto_execute(opportunity)

        except Exception as e:
            logger.error("Failed to create opportunity", error=str(e))

    async def _check_auto_execute(self, opportunity: Opportunity) -> None:
        """Check if opportunity should be auto-executed and trigger if so."""
        try:
            # Always publish opportunity assessment for visibility
            assessment = {
                "opportunity_id": opportunity.id,
                "symbol": opportunity.symbol,
                "uos_score": float(opportunity.uos_score) if hasattr(opportunity.uos_score, '__float__') else opportunity.uos_score,
                "recommended_size_usd": float(opportunity.recommended_size_usd) if opportunity.recommended_size_usd else 0,
                "long_exchange": opportunity.long_leg.exchange,
                "short_exchange": opportunity.short_leg.exchange,
                "funding_spread_pct": float(opportunity.funding_spread_pct) if hasattr(opportunity.funding_spread_pct, '__float__') else opportunity.funding_spread_pct,
                "net_apr": float(opportunity.net_apr) if opportunity.net_apr and hasattr(opportunity.net_apr, '__float__') else 0,
            }

            # Check if auto-execution is enabled and system is ready
            if not self.state_manager.should_auto_execute():
                reason = "Auto-execution disabled" if not self.state_manager.auto_execute else "System not ready for trading"
                if not self.state_manager.is_running:
                    reason = "System is stopped"
                elif self.state_manager.mode == "discovery":
                    reason = "System in discovery mode (no trading)"
                elif self.state_manager.circuit_breaker_active:
                    reason = "Circuit breaker active"

                # Only publish for high-quality opportunities (to avoid spam)
                if opportunity.uos_score >= 70:
                    await self._publish_activity(
                        "opportunity_not_executed",
                        {
                            **assessment,
                            "reason": reason,
                            "action": "none",
                        },
                        level="info",
                    )
                logger.debug(
                    "Auto-execution not enabled or system not ready",
                    auto_execute=self.state_manager.auto_execute,
                    should_execute=self.state_manager.should_execute(),
                )
                return

            # Check minimum UOS score for auto-execution
            min_score = self._config.get("min_uos_auto_execute", 75)
            if opportunity.uos_score < min_score:
                # Only publish for decent opportunities
                if opportunity.uos_score >= 60:
                    await self._publish_activity(
                        "opportunity_below_threshold",
                        {
                            **assessment,
                            "reason": f"Score {opportunity.uos_score:.1f} below threshold {min_score}",
                            "threshold": min_score,
                            "action": "none",
                        },
                        level="info",
                    )
                logger.debug(
                    "Opportunity score below auto-execute threshold",
                    score=opportunity.uos_score,
                    threshold=min_score,
                )
                return

            # Trigger auto-execution
            logger.info(
                "Auto-executing opportunity",
                id=opportunity.id,
                symbol=opportunity.symbol,
                score=opportunity.uos_score,
                size_usd=opportunity.recommended_size_usd,
            )

            # Publish execution request to execution engine
            size_usd = opportunity.recommended_size_usd or 1000
            execution_request = {
                "opportunity_id": opportunity.id,
                "symbol": opportunity.symbol,
                "position_size_usd": float(size_usd) if hasattr(size_usd, '__float__') else size_usd,
                "long_exchange": opportunity.long_leg.exchange,
                "short_exchange": opportunity.short_leg.exchange,
                "uos_score": float(opportunity.uos_score) if hasattr(opportunity.uos_score, '__float__') else opportunity.uos_score,
                "auto_executed": True,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.redis.publish(
                "nexus:execution:request",
                json.dumps(execution_request),
            )

            # Update opportunity status
            opportunity.status = "executing"

            # Update stats
            self._stats["auto_executions_triggered"] += 1

            # Publish activity event
            await self._publish_activity(
                "auto_execution_triggered",
                {
                    "opportunity_id": opportunity.id,
                    "symbol": opportunity.symbol,
                    "uos_score": float(opportunity.uos_score) if hasattr(opportunity.uos_score, '__float__') else opportunity.uos_score,
                    "size_usd": float(size_usd) if hasattr(size_usd, '__float__') else size_usd,
                    "long_exchange": opportunity.long_leg.exchange,
                    "short_exchange": opportunity.short_leg.exchange,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to auto-execute opportunity",
                opportunity_id=opportunity.id,
                error=str(e),
            )

    async def _publish_activity(
        self,
        activity_type: str,
        details: dict[str, Any],
        level: str = "info",
    ) -> None:
        """Publish activity event for real-time monitoring."""
        message = f"{activity_type.replace('_', ' ').title()}: {details.get('symbol', '')}"
        activity = {
            "type": activity_type,
            "service": "opportunity-detector",
            "level": level,
            "message": message,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            await self.redis.publish("nexus:activity", json.dumps(activity))
        except Exception as e:
            logger.warning(f"Failed to publish activity", error=str(e))

    async def _save_opportunity_to_db(
        self, opportunity: Opportunity, spread: dict[str, Any]
    ) -> None:
        """Save opportunity to database for API access."""
        if not self.db_session_factory:
            return

        try:
            async with self.db_session_factory() as session:
                # Extract base asset from symbol (e.g., "BTC" from "BTCUSDT")
                symbol = opportunity.symbol
                base_asset = symbol.replace("USDT", "").replace("USD", "").replace("PERP", "")

                query = text("""
                    INSERT INTO opportunities.detected (
                        id, opportunity_type, symbol, base_asset, status,
                        primary_exchange, primary_side, primary_rate,
                        hedge_exchange, hedge_side, hedge_rate,
                        gross_funding_rate, gross_apr, net_apr,
                        uos_score, return_score, risk_score, execution_score, timing_score,
                        confidence, recommended_size_usd,
                        detected_at, expires_at
                    ) VALUES (
                        :id, :opportunity_type, :symbol, :base_asset, :status,
                        :primary_exchange, :primary_side, :primary_rate,
                        :hedge_exchange, :hedge_side, :hedge_rate,
                        :gross_funding_rate, :gross_apr, :net_apr,
                        :uos_score, :return_score, :risk_score, :execution_score, :timing_score,
                        :confidence, :recommended_size_usd,
                        :detected_at, :expires_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        gross_funding_rate = EXCLUDED.gross_funding_rate,
                        gross_apr = EXCLUDED.gross_apr,
                        net_apr = EXCLUDED.net_apr,
                        uos_score = EXCLUDED.uos_score,
                        return_score = EXCLUDED.return_score,
                        risk_score = EXCLUDED.risk_score,
                        execution_score = EXCLUDED.execution_score,
                        timing_score = EXCLUDED.timing_score,
                        expires_at = EXCLUDED.expires_at,
                        primary_rate = EXCLUDED.primary_rate,
                        hedge_rate = EXCLUDED.hedge_rate
                """)

                scores = opportunity.uos_breakdown
                annualized_apr = spread.get("annualized_apr", 0)

                await session.execute(query, {
                    "id": opportunity.id,
                    "opportunity_type": "funding_arbitrage",
                    "symbol": symbol,
                    "base_asset": base_asset,
                    "status": "detected",
                    "primary_exchange": opportunity.long_leg.exchange,
                    "primary_side": "long",
                    "primary_rate": opportunity.long_leg.funding_rate,
                    "hedge_exchange": opportunity.short_leg.exchange,
                    "hedge_side": "short",
                    "hedge_rate": opportunity.short_leg.funding_rate,
                    "gross_funding_rate": opportunity.funding_spread_pct,
                    "gross_apr": annualized_apr,
                    "net_apr": opportunity.estimated_net_apr or annualized_apr * 0.9,
                    "uos_score": scores.total if scores else 0,
                    "return_score": scores.return_score if scores else 0,
                    "risk_score": scores.risk_score if scores else 0,
                    "execution_score": scores.execution_score if scores else 0,
                    "timing_score": scores.timing_score if scores else 0,
                    "confidence": scores.quality if scores else "medium",
                    "recommended_size_usd": 1000,  # Default, would be calculated
                    "detected_at": opportunity.detected_at,
                    "expires_at": opportunity.expires_at,
                })
                await session.commit()

        except Exception as e:
            logger.warning(f"Failed to save opportunity to DB: {e}")

    async def _update_opportunity(
        self, opportunity: Opportunity, spread: dict[str, Any]
    ) -> None:
        """Update an existing opportunity."""
        try:
            # Recalculate scores
            scores = self.scorer.calculate_scores(spread)
            total_score = scores.total

            # Calculate recommended position size based on score
            # Get max position size from risk limits (default $5000)
            max_size = self._risk_limits.get("max_position_size_usd", 5000)

            # Base size scaled by UOS score quality, capped at max_position_size_usd
            if total_score >= 80:  # exceptional - use up to max allowed
                recommended_size = max_size
            elif total_score >= 70:  # strong - 50% of max
                recommended_size = max_size * 0.5
            elif total_score >= 60:  # good - 20% of max
                recommended_size = max_size * 0.2
            else:  # minimum size - 10% of max
                recommended_size = max_size * 0.1

            # Update opportunity
            opportunity.funding_spread = spread["spread"]
            opportunity.funding_spread_pct = spread["spread_pct"]
            opportunity.estimated_net_apr = spread.get("annualized_apr", 0)
            opportunity.uos_score_direct = total_score
            opportunity.uos_breakdown = scores
            opportunity.recommended_size_usd = recommended_size
            opportunity.long_leg.funding_rate = spread["long_rate"]
            opportunity.short_leg.funding_rate = spread["short_rate"]

            # Check if still viable
            if scores.total < self._config["min_uos_score"]:
                # Remove opportunity
                del self._opportunities[opportunity.id]
                await self._publish_expired(opportunity, "score_below_threshold")
                return

            # Publish update event
            event = OpportunityUpdatedEvent(
                opportunity_id=opportunity.id,
                updates={
                    "uos_score": scores.total,
                    "funding_spread_pct": spread["spread_pct"],
                    "estimated_net_apr": spread.get("annualized_apr", 0),
                },
                timestamp=datetime.utcnow(),
            )
            await self.redis.publish(
                "nexus:opportunity:updated",
                event.model_dump_json(),
            )

        except Exception as e:
            logger.error("Failed to update opportunity", error=str(e))

    async def _cleanup_expired(self) -> None:
        """Clean up expired opportunities."""
        while self._running:
            try:
                now = datetime.utcnow()
                expired = []
                for opp in self._opportunities.values():
                    if opp.expires_at:
                        # Handle both timezone-aware and timezone-naive datetimes
                        expires_at = opp.expires_at
                        if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
                            # Convert to naive UTC for comparison
                            expires_at = expires_at.replace(tzinfo=None)
                        if expires_at < now:
                            expired.append(opp)

                for opp in expired:
                    del self._opportunities[opp.id]
                    await self._publish_expired(opp, "expired")
                    self._stats["opportunities_expired"] += 1

                if expired:
                    logger.debug(f"Cleaned up {len(expired)} expired opportunities")

            except Exception as e:
                logger.error("Error in cleanup task", error=str(e))

            await asyncio.sleep(60)

    async def _publish_expired(self, opportunity: Opportunity, reason: str) -> None:
        """Publish opportunity expired event."""
        event = OpportunityExpiredEvent(
            opportunity_id=opportunity.id,
            reason=reason,
            timestamp=datetime.utcnow(),
        )
        await self.redis.publish(
            "nexus:opportunity:expired",
            event.model_dump_json(),
        )

    def get_stats(self) -> dict[str, Any]:
        """Get detection statistics."""
        uptime = None
        if self._stats["start_time"]:
            uptime = (datetime.utcnow() - self._stats["start_time"]).total_seconds()

        return {
            "uptime_seconds": uptime,
            "detection_cycles": self._stats["detection_cycles"],
            "opportunities_detected": self._stats["opportunities_detected"],
            "opportunities_expired": self._stats["opportunities_expired"],
            "opportunities_published": self._stats["opportunities_published"],
            "opportunities_skipped_no_credentials": self._stats["opportunities_skipped_no_credentials"],
            "opportunities_skipped_blacklisted": self._stats["opportunities_skipped_blacklisted"],
            "auto_executions_triggered": self._stats["auto_executions_triggered"],
            "active_opportunities": len(self._opportunities),
            "auto_execute_enabled": self.state_manager.auto_execute,
            "system_running": self.state_manager.is_running,
            "executable_exchanges": list(self._exchanges_with_credentials),
            "blacklisted_symbols": list(self._blacklisted_symbols),
            "config": self._config,
        }

    def get_opportunities(
        self,
        min_score: int = 0,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> list[Opportunity]:
        """Get opportunities with optional filters."""
        opportunities = list(self._opportunities.values())

        if min_score > 0:
            opportunities = [o for o in opportunities if o.uos_score >= min_score]

        if symbol:
            opportunities = [
                o for o in opportunities if symbol.upper() in o.symbol.upper()
            ]

        # Sort by UOS score descending
        opportunities.sort(key=lambda o: o.uos_score, reverse=True)

        return opportunities[:limit]

    def get_top_opportunities(self, limit: int = 10) -> list[Opportunity]:
        """Get top opportunities by UOS score."""
        opportunities = sorted(
            self._opportunities.values(),
            key=lambda o: o.uos_score,
            reverse=True,
        )
        return opportunities[:limit]

    def get_opportunity_by_id(self, opportunity_id: str) -> Optional[Opportunity]:
        """Get opportunity by ID."""
        return self._opportunities.get(opportunity_id)

    def get_opportunities_for_symbol(self, symbol: str) -> list[Opportunity]:
        """Get all opportunities for a symbol."""
        return [
            o
            for o in self._opportunities.values()
            if symbol.upper() in o.symbol.upper()
        ]

    def get_score_breakdown(self, opportunity_id: str) -> Optional[dict[str, Any]]:
        """Get detailed score breakdown for an opportunity."""
        opportunity = self._opportunities.get(opportunity_id)
        if not opportunity or not opportunity.uos_breakdown:
            return None

        return {
            "opportunity_id": opportunity_id,
            "total_score": opportunity.uos_score,
            "breakdown": opportunity.uos_breakdown.model_dump(),
            "thresholds": {
                "min_score": self._config["min_uos_score"],
                "min_spread_pct": self._config["min_spread_pct"],
                "min_net_apr_pct": self._config["min_net_apr_pct"],
            },
        }

    async def _recover_opportunities(self) -> None:
        """Load unexpired opportunities from database on startup."""
        if not self.db_session_factory:
            logger.debug("No database session factory - skipping opportunity recovery")
            return

        try:
            async with self.db_session_factory() as session:
                query = text("""
                    SELECT id, symbol, opportunity_type, status,
                           primary_exchange, primary_rate,
                           hedge_exchange, hedge_rate,
                           gross_funding_rate, net_apr, uos_score,
                           return_score, risk_score, execution_score, timing_score,
                           detected_at, expires_at
                    FROM opportunities.detected
                    WHERE status IN ('detected', 'validated', 'scored', 'allocated', 'active')
                      AND expires_at > NOW()
                    ORDER BY uos_score DESC
                    LIMIT 100
                """)
                result = await session.execute(query)
                rows = result.fetchall()

                for row in rows:
                    opp_id = str(row[0])
                    if opp_id in self._opportunities:
                        continue

                    # Reconstruct opportunity from database
                    scores = UOSScores(
                        return_score=row[11] or 0,
                        risk_score=row[12] or 0,
                        execution_score=row[13] or 0,
                        timing_score=row[14] or 0,
                        quality="medium",
                    )

                    opportunity = Opportunity(
                        id=opp_id,
                        symbol=row[1],
                        opportunity_type=row[2] or "funding_arbitrage",
                        long_leg=OpportunityLeg(
                            exchange=row[4],
                            side="long",
                            funding_rate=float(row[5] or 0),
                            estimated_slippage=0.001,
                        ),
                        short_leg=OpportunityLeg(
                            exchange=row[6],
                            side="short",
                            funding_rate=float(row[7] or 0),
                            estimated_slippage=0.001,
                        ),
                        funding_spread=float(row[8] or 0),
                        funding_spread_pct=float(row[8] or 0) * 100,
                        estimated_net_apr=float(row[9] or 0),
                        uos_score_direct=row[10] or 0,
                        uos_breakdown=scores,
                        detected_at=row[15] or datetime.utcnow(),
                        expires_at=row[16] or datetime.utcnow() + timedelta(minutes=30),
                        status=row[3] or "active",
                    )

                    self._opportunities[opp_id] = opportunity

                logger.info(
                    "Recovered opportunities from database",
                    count=len(rows),
                    active=len(self._opportunities),
                )

        except Exception as e:
            logger.warning(f"Failed to recover opportunities from database: {e}")

    async def _listen_position_events(self) -> None:
        """Listen to position events to update opportunity status."""
        logger.info("Subscribing to position events for status updates")

        async def handle_position_opened(channel: str, message: str):
            try:
                data = json.loads(message)
                opportunity_id = data.get("opportunity_id")

                if opportunity_id and opportunity_id in self._opportunities:
                    # Update in-memory status
                    self._opportunities[opportunity_id].status = "executed"
                    logger.info(
                        "Opportunity status updated to executed",
                        opportunity_id=opportunity_id,
                    )

                    # Update database status
                    if self.db_session_factory:
                        try:
                            async with self.db_session_factory() as session:
                                await session.execute(
                                    text("""
                                        UPDATE opportunities.detected
                                        SET status = 'executed',
                                            executed_at = NOW()
                                        WHERE id = :id
                                    """),
                                    {"id": opportunity_id},
                                )
                                await session.commit()
                        except Exception as db_err:
                            logger.warning(f"Failed to update opportunity status in DB: {db_err}")

            except Exception as e:
                logger.warning(f"Failed to handle position opened event: {e}")

        await self.redis.subscribe("nexus:position:opened", handle_position_opened)

        while self._running:
            await asyncio.sleep(1)
