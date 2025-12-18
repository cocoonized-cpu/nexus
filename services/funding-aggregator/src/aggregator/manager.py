"""
Funding Aggregator Manager - Merges dual-source funding rate data.

Architecture:
- PRIMARY source: Exchange APIs (via Data Collector service)
- SECONDARY source: ArbitrageScanner API (for validation and gap-filling)

Features:
- Automatic reconnection with exponential backoff
- Staleness detection for both sources
- Source health tracking
- Trend analysis for funding rates

The aggregator reconciles both sources to produce unified funding snapshots.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.aggregator.arb_scanner import ArbitrageScannerClient

from shared.events.market import UnifiedFundingSnapshotEvent
from shared.models.funding import (ArbitrageScannerToken, FundingRateData,
                                   UnifiedFundingSnapshot)
from shared.utils.config import get_settings
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class SourceHealth(str, Enum):
    """Health status for data sources."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    DISCONNECTED = "disconnected"


class FundingAggregator:
    """
    Aggregates funding rates from dual sources.

    Key responsibilities:
    - Subscribe to funding rate events from Data Collector
    - Periodically fetch data from ArbitrageScanner API
    - Reconcile and validate data from both sources
    - Produce unified funding snapshots
    - Calculate cross-exchange spreads
    """

    def __init__(self, redis: RedisClient, db_session_factory: Optional[Callable] = None):
        self.redis = redis
        self._db_session_factory = db_session_factory or self._create_db_session_factory()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # ArbitrageScanner client
        self.arb_scanner = ArbitrageScannerClient()

        # Funding rate cache: {(exchange, symbol): FundingRateData}
        self._primary_rates: dict[tuple[str, str], FundingRateData] = {}
        self._secondary_rates: dict[tuple[str, str], FundingRateData] = {}
        self._unified_rates: dict[tuple[str, str], FundingRateData] = {}

        # Latest unified snapshot
        self._latest_snapshot: Optional[UnifiedFundingSnapshot] = None

        # Configuration
        self._arb_scanner_interval = 60  # Fetch from ArbitrageScanner every 60s
        self._snapshot_interval = 30  # Produce snapshot every 30s
        self._spread_history_interval = 300  # Record spread history every 5 minutes
        self._stale_threshold = timedelta(minutes=5)  # Data older than 5m is stale
        self._degraded_threshold = timedelta(minutes=2)  # Data older than 2m is degraded

        # Reconnection configuration
        self._reconnect_base_delay = 1.0  # seconds
        self._reconnect_max_delay = 60.0  # seconds
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

        # Source timestamps for staleness tracking
        self._source_timestamps: dict[str, datetime] = {
            "primary": datetime.utcnow(),
            "secondary": datetime.utcnow(),
        }

        # Statistics
        self._stats = {
            "primary_updates": 0,
            "secondary_updates": 0,
            "snapshots_produced": 0,
            "reconciliation_conflicts": 0,
            "spread_history_recorded": 0,
            "reconnect_attempts": 0,
            "reconnect_successes": 0,
            "stale_data_events": 0,
            "start_time": None,
        }

        # Source status with health enum
        self._source_status = {
            "primary": {
                "health": SourceHealth.DISCONNECTED,
                "last_update": None,
                "symbols": 0,
                "updates_per_minute": 0,
                "last_error": None,
            },
            "secondary": {
                "health": SourceHealth.DISCONNECTED,
                "last_update": None,
                "symbols": 0,
                "updates_per_minute": 0,
                "last_error": None,
            },
        }

        # Update rate tracking (for updates per minute calculation)
        self._update_counts: dict[str, list[datetime]] = {
            "primary": [],
            "secondary": [],
        }

    def _create_db_session_factory(self) -> Callable:
        """Create database session factory."""
        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=3,
            max_overflow=5,
        )
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def start(self) -> None:
        """Start the funding aggregator."""
        logger.info("Starting Funding Aggregator")

        self._running = True
        self._stats["start_time"] = datetime.utcnow()

        # Initialize ArbitrageScanner client
        await self.arb_scanner.initialize()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._listen_primary_source_with_reconnect()),
            asyncio.create_task(self._fetch_secondary_source()),
            asyncio.create_task(self._produce_snapshots()),
            asyncio.create_task(self._cleanup_stale_data()),
            asyncio.create_task(self._record_spread_history()),
            asyncio.create_task(self._monitor_source_health()),
        ]

        logger.info("Funding Aggregator started")

    async def stop(self) -> None:
        """Stop the funding aggregator."""
        logger.info("Stopping Funding Aggregator")
        self._running = False

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.arb_scanner.close()

        logger.info("Funding Aggregator stopped")

    async def _listen_primary_source_with_reconnect(self) -> None:
        """Listen to funding rate events with automatic reconnection."""
        logger.info("Starting primary source listener with reconnection support")

        while self._running:
            try:
                await self._listen_primary_source()
            except asyncio.CancelledError:
                logger.info("Primary source listener cancelled")
                break
            except Exception as e:
                self._stats["reconnect_attempts"] += 1
                self._reconnect_attempts += 1
                self._source_status["primary"]["health"] = SourceHealth.DISCONNECTED
                self._source_status["primary"]["last_error"] = str(e)

                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error(
                        "Max reconnection attempts reached for primary source",
                        attempts=self._reconnect_attempts,
                    )
                    # Reset counter but continue trying (with max delay)
                    self._reconnect_attempts = self._max_reconnect_attempts

                # Calculate backoff delay
                delay = min(
                    self._reconnect_base_delay * (2 ** min(self._reconnect_attempts, 6)),
                    self._reconnect_max_delay,
                )

                logger.warning(
                    "Primary source connection lost, reconnecting",
                    error=str(e),
                    attempt=self._reconnect_attempts,
                    delay=delay,
                )

                await asyncio.sleep(delay)

    async def _listen_primary_source(self) -> None:
        """Listen to funding rate events from Data Collector."""
        logger.info("Subscribing to primary funding rate source")

        async def handle_funding_update(channel: str, message: str):
            try:
                data = json.loads(message)
                rate = FundingRateData(**data)

                key = (rate.exchange, rate.symbol)
                self._primary_rates[key] = rate
                self._stats["primary_updates"] += 1

                # Update timestamps and tracking
                now = datetime.utcnow()
                self._source_timestamps["primary"] = now
                self._track_update("primary")

                # Update source status
                self._source_status["primary"]["health"] = SourceHealth.HEALTHY
                self._source_status["primary"]["last_update"] = now.isoformat()
                self._source_status["primary"]["symbols"] = len(self._primary_rates)
                self._source_status["primary"]["last_error"] = None

                # Reset reconnection counter on successful update
                if self._reconnect_attempts > 0:
                    self._stats["reconnect_successes"] += 1
                    self._reconnect_attempts = 0
                    logger.info("Primary source reconnected successfully")

                # Log periodically
                if self._stats["primary_updates"] % 100 == 0:
                    logger.info(
                        "Primary source progress",
                        updates=self._stats["primary_updates"],
                        symbols=len(self._primary_rates),
                    )

            except Exception as e:
                logger.warning("Failed to process funding rate event", error=str(e))

        await self.redis.subscribe(
            "nexus:market_data:funding_rate", handle_funding_update
        )

        # Actually listen for messages
        logger.info("Starting Redis pub/sub listener for funding rates")
        await self.redis.listen()

    async def _fetch_secondary_source(self) -> None:
        """Periodically fetch data from ArbitrageScanner API."""
        logger.info("Starting ArbitrageScanner data fetch")

        while self._running:
            try:
                tokens = await self.arb_scanner.fetch_funding_rates()

                for token in tokens:
                    # Convert ArbitrageScanner data to FundingRateData
                    for exchange, rate_info in token.exchanges.items():
                        funding_rate = rate_info.get("funding_rate", 0)
                        symbol = f"{token.symbol}/USDT:USDT"

                        rate = FundingRateData(
                            exchange=exchange.lower(),
                            symbol=symbol,
                            funding_rate=funding_rate,
                            predicted_rate=rate_info.get("predicted_rate"),
                            next_funding_time=None,
                            funding_interval_hours=rate_info.get("interval_hours", 8),
                            timestamp=datetime.utcnow(),
                        )

                        key = (rate.exchange, rate.symbol)
                        self._secondary_rates[key] = rate
                        self._stats["secondary_updates"] += 1

                # Update source status and timestamps
                now = datetime.utcnow()
                self._source_timestamps["secondary"] = now
                self._track_update("secondary")
                self._source_status["secondary"]["health"] = SourceHealth.HEALTHY
                self._source_status["secondary"]["last_update"] = now.isoformat()
                self._source_status["secondary"]["symbols"] = len(self._secondary_rates)
                self._source_status["secondary"]["last_error"] = None

                logger.debug(
                    "Fetched ArbitrageScanner data",
                    tokens=len(tokens),
                )

            except Exception as e:
                logger.error("Failed to fetch ArbitrageScanner data", error=str(e))
                self._source_status["secondary"]["health"] = SourceHealth.DEGRADED
                self._source_status["secondary"]["last_error"] = str(e)

            await asyncio.sleep(self._arb_scanner_interval)

    def _track_update(self, source: str) -> None:
        """Track update timestamps for rate calculation."""
        now = datetime.utcnow()
        self._update_counts[source].append(now)

        # Keep only last minute of updates
        cutoff = now - timedelta(minutes=1)
        self._update_counts[source] = [
            ts for ts in self._update_counts[source] if ts > cutoff
        ]

        # Update updates per minute
        self._source_status[source]["updates_per_minute"] = len(
            self._update_counts[source]
        )

    def _is_source_stale(self, source: str, threshold_seconds: Optional[int] = None) -> bool:
        """
        Check if a data source is stale.

        Args:
            source: "primary" or "secondary"
            threshold_seconds: Custom threshold (uses default stale_threshold if None)

        Returns:
            True if source data is stale
        """
        last_update = self._source_timestamps.get(source)
        if not last_update:
            return True

        threshold = (
            timedelta(seconds=threshold_seconds)
            if threshold_seconds
            else self._stale_threshold
        )

        return (datetime.utcnow() - last_update) > threshold

    def _get_source_health(self, source: str) -> SourceHealth:
        """
        Determine health status of a data source.

        Args:
            source: "primary" or "secondary"

        Returns:
            SourceHealth enum value
        """
        last_update = self._source_timestamps.get(source)
        if not last_update:
            return SourceHealth.DISCONNECTED

        age = datetime.utcnow() - last_update

        if age > self._stale_threshold:
            return SourceHealth.STALE
        elif age > self._degraded_threshold:
            return SourceHealth.DEGRADED
        else:
            return SourceHealth.HEALTHY

    async def _monitor_source_health(self) -> None:
        """Monitor health of data sources and emit alerts."""
        logger.info("Starting source health monitoring")

        # Track previous health for change detection
        previous_health: dict[str, SourceHealth] = {}

        while self._running:
            try:
                for source in ["primary", "secondary"]:
                    current_health = self._get_source_health(source)
                    prev_health = previous_health.get(source)

                    # Update status
                    self._source_status[source]["health"] = current_health

                    # Check for health transitions
                    if prev_health and current_health != prev_health:
                        if current_health == SourceHealth.STALE:
                            self._stats["stale_data_events"] += 1
                            logger.warning(
                                f"{source} source became stale",
                                last_update=self._source_timestamps.get(source),
                            )

                            # Publish health event
                            await self.redis.publish(
                                "nexus:system:aggregator_health",
                                json.dumps({
                                    "source": source,
                                    "health": current_health.value,
                                    "timestamp": datetime.utcnow().isoformat(),
                                }),
                            )

                        elif current_health == SourceHealth.HEALTHY and prev_health != SourceHealth.HEALTHY:
                            logger.info(f"{source} source recovered to healthy")

                    previous_health[source] = current_health

                # Log overall status periodically
                primary_health = self._source_status["primary"]["health"]
                secondary_health = self._source_status["secondary"]["health"]

                if (
                    primary_health != SourceHealth.HEALTHY
                    or secondary_health != SourceHealth.HEALTHY
                ):
                    logger.debug(
                        "Source health status",
                        primary=primary_health.value,
                        secondary=secondary_health.value,
                    )

            except Exception as e:
                logger.error("Error in health monitoring", error=str(e))

            await asyncio.sleep(10)  # Check every 10 seconds

    async def _produce_snapshots(self) -> None:
        """Periodically produce unified funding snapshots."""
        logger.info("Starting snapshot production")

        while self._running:
            try:
                # Reconcile data from both sources
                self._reconcile_sources()

                # Create snapshot
                if self._unified_rates:
                    # Convert flat dict to nested dict: symbol -> exchange -> rate
                    rates_nested: dict[str, dict[str, FundingRateData]] = {}
                    for (exchange, symbol), rate in self._unified_rates.items():
                        # Extract base symbol for grouping
                        base_symbol = symbol.split("/")[0] if "/" in symbol else symbol
                        if base_symbol not in rates_nested:
                            rates_nested[base_symbol] = {}
                        rates_nested[base_symbol][exchange] = rate

                    snapshot = UnifiedFundingSnapshot(
                        rates=rates_nested,
                        fetched_at=datetime.utcnow(),
                        total_symbols=len(rates_nested),
                        total_rates=len(self._unified_rates),
                        exchange_api_rates=len(self._primary_rates),
                        arbitragescanner_rates=len(self._secondary_rates),
                    )

                    self._latest_snapshot = snapshot
                    self._stats["snapshots_produced"] += 1

                    # Publish snapshot event
                    event = UnifiedFundingSnapshotEvent(
                        snapshot=snapshot,
                        timestamp=datetime.utcnow(),
                    )
                    await self.redis.publish(
                        "nexus:market_data:unified_snapshot",
                        event.model_dump_json(),
                    )

                    logger.debug(
                        "Produced unified snapshot",
                        unified_count=len(self._unified_rates),
                        symbols=len(rates_nested),
                    )

                    # Cache funding spreads for opportunity detector
                    spreads = self.calculate_spreads(min_spread=0.0, limit=100)
                    if spreads:
                        await self.redis.set(
                            "nexus:cache:funding_spreads",
                            json.dumps(spreads),
                            expire_seconds=60,  # 60 second TTL
                        )
                        logger.debug("Cached funding spreads", count=len(spreads))

            except Exception as e:
                logger.error("Failed to produce snapshot", error=str(e))

            await asyncio.sleep(self._snapshot_interval)

    def _reconcile_sources(self) -> None:
        """
        Reconcile primary and secondary data sources.

        Strategy:
        1. Primary source is authoritative for recent data
        2. Secondary source fills gaps and validates
        3. Flag conflicts for investigation
        """
        self._unified_rates.clear()

        # All keys from both sources
        all_keys = set(self._primary_rates.keys()) | set(self._secondary_rates.keys())

        for key in all_keys:
            primary = self._primary_rates.get(key)
            secondary = self._secondary_rates.get(key)

            if primary and secondary:
                # Both sources have data - validate and prefer primary
                unified = self._merge_rates(primary, secondary)
            elif primary:
                # Only primary
                unified = primary
            else:
                # Only secondary (gap-filling)
                unified = secondary

            if unified:
                self._unified_rates[key] = unified

    def _merge_rates(
        self, primary: FundingRateData, secondary: FundingRateData
    ) -> FundingRateData:
        """
        Merge funding rate data from both sources.

        Primary is authoritative, but we validate against secondary.
        """
        # Check for significant discrepancy (>20% difference)
        if secondary.funding_rate != 0:
            diff_pct = abs(primary.funding_rate - secondary.funding_rate) / abs(
                secondary.funding_rate
            )
            if diff_pct > 0.2:
                self._stats["reconciliation_conflicts"] += 1
                logger.warning(
                    "Funding rate discrepancy",
                    exchange=primary.exchange,
                    symbol=primary.symbol,
                    primary=primary.funding_rate,
                    secondary=secondary.funding_rate,
                    diff_pct=diff_pct,
                )

        # Use primary rate, but fill in missing fields from secondary
        return FundingRateData(
            exchange=primary.exchange,
            symbol=primary.symbol,
            funding_rate=primary.funding_rate,
            predicted_rate=primary.predicted_rate or secondary.predicted_rate,
            next_funding_time=primary.next_funding_time or secondary.next_funding_time,
            funding_interval_hours=primary.funding_interval_hours
            or secondary.funding_interval_hours,
            timestamp=primary.timestamp,
        )

    async def _cleanup_stale_data(self) -> None:
        """Remove stale data from caches and cleanup old spread history."""
        cleanup_counter = 0
        while self._running:
            try:
                now = datetime.utcnow()
                threshold = now - self._stale_threshold

                # Clean primary cache
                stale_primary = [
                    key
                    for key, rate in self._primary_rates.items()
                    if rate.timestamp < threshold
                ]
                for key in stale_primary:
                    del self._primary_rates[key]

                # Clean secondary cache
                stale_secondary = [
                    key
                    for key, rate in self._secondary_rates.items()
                    if rate.timestamp < threshold
                ]
                for key in stale_secondary:
                    del self._secondary_rates[key]

                if stale_primary or stale_secondary:
                    logger.debug(
                        "Cleaned stale data",
                        primary=len(stale_primary),
                        secondary=len(stale_secondary),
                    )

                # Cleanup old spread history every hour (60 iterations * 60s = 1 hour)
                cleanup_counter += 1
                if cleanup_counter >= 60:
                    cleanup_counter = 0
                    try:
                        async with self._db_session_factory() as db:
                            # Keep 90 days of spread history for ML training
                            result = await db.execute(
                                text("SELECT funding.cleanup_old_spread_history(90)")
                            )
                            deleted = result.scalar()
                            await db.commit()

                            if deleted and deleted > 0:
                                logger.info(
                                    "Cleaned old spread history records",
                                    deleted_count=deleted,
                                )
                    except Exception as e:
                        logger.warning(
                            "Failed to cleanup old spread history",
                            error=str(e),
                        )

            except Exception as e:
                logger.error("Error in cleanup task", error=str(e))

            await asyncio.sleep(60)

    async def _record_spread_history(self) -> None:
        """
        Periodically record spread history for all symbols to database.

        This captures historical spread data for ML training and forecasting.
        Records all spreads across all exchange pairs for comprehensive coverage.
        """
        logger.info("Starting spread history recording for ML training data")

        # Wait for initial data collection
        await asyncio.sleep(60)

        while self._running:
            try:
                # Calculate all spreads (no minimum threshold, capture everything)
                all_spreads = self.calculate_spreads(min_spread=0.0, limit=1000)

                if not all_spreads:
                    logger.debug("No spreads to record")
                    await asyncio.sleep(self._spread_history_interval)
                    continue

                # Batch insert all spreads into database
                async with self._db_session_factory() as db:
                    records_inserted = 0

                    for spread_data in all_spreads:
                        try:
                            await db.execute(
                                text("""
                                    INSERT INTO funding.spread_history (
                                        symbol, long_exchange, short_exchange,
                                        long_rate, short_rate, spread, spread_annualized,
                                        data_source, timestamp
                                    ) VALUES (
                                        :symbol, :long_exchange, :short_exchange,
                                        :long_rate, :short_rate, :spread, :spread_annualized,
                                        'aggregator', NOW()
                                    )
                                """),
                                {
                                    "symbol": spread_data["symbol"],
                                    "long_exchange": spread_data["long_exchange"],
                                    "short_exchange": spread_data["short_exchange"],
                                    "long_rate": float(spread_data["long_rate"]),
                                    "short_rate": float(spread_data["short_rate"]),
                                    "spread": float(spread_data["spread"]),
                                    "spread_annualized": float(spread_data["annualized_apr"]) / 100,  # Convert from % to decimal
                                },
                            )
                            records_inserted += 1
                        except Exception as e:
                            logger.warning(
                                "Failed to insert spread record",
                                symbol=spread_data["symbol"],
                                error=str(e),
                            )

                    await db.commit()

                    self._stats["spread_history_recorded"] += records_inserted

                    logger.info(
                        "Recorded spread history for ML training",
                        records=records_inserted,
                        total_recorded=self._stats["spread_history_recorded"],
                    )

            except Exception as e:
                import traceback
                logger.error(
                    "Error recording spread history",
                    error=str(e),
                    traceback=traceback.format_exc(),
                )

            await asyncio.sleep(self._spread_history_interval)

    @property
    def is_running(self) -> bool:
        """Check if aggregator is running."""
        return self._running

    @property
    def exchange_count(self) -> int:
        """Get number of tracked exchanges."""
        exchanges = set()
        for exchange, _ in self._unified_rates.keys():
            exchanges.add(exchange)
        return len(exchanges)

    @property
    def symbol_count(self) -> int:
        """Get number of tracked symbols."""
        return len(self._unified_rates)

    @property
    def active_source_count(self) -> int:
        """Get number of active (healthy or degraded) data sources."""
        count = 0
        primary_health = self._source_status["primary"]["health"]
        secondary_health = self._source_status["secondary"]["health"]

        if primary_health in (SourceHealth.HEALTHY, SourceHealth.DEGRADED):
            count += 1
        if secondary_health in (SourceHealth.HEALTHY, SourceHealth.DEGRADED):
            count += 1
        return count

    def get_source_status(self) -> dict[str, Any]:
        """Get detailed status of data sources."""
        # Convert SourceHealth enum to string for JSON serialization
        status = {}
        for source in ["primary", "secondary"]:
            status[source] = {
                **self._source_status[source],
                "health": self._source_status[source]["health"].value,
                "is_stale": self._is_source_stale(source),
                "age_seconds": (
                    (datetime.utcnow() - self._source_timestamps[source]).total_seconds()
                    if self._source_timestamps.get(source)
                    else None
                ),
            }
        return status

    def get_stats(self) -> dict[str, Any]:
        """Get aggregation statistics."""
        uptime = None
        if self._stats["start_time"]:
            uptime = (datetime.utcnow() - self._stats["start_time"]).total_seconds()

        return {
            "uptime_seconds": uptime,
            "primary_updates": self._stats["primary_updates"],
            "secondary_updates": self._stats["secondary_updates"],
            "snapshots_produced": self._stats["snapshots_produced"],
            "reconciliation_conflicts": self._stats["reconciliation_conflicts"],
            "spread_history_recorded": self._stats["spread_history_recorded"],
            "reconnect_attempts": self._stats["reconnect_attempts"],
            "reconnect_successes": self._stats["reconnect_successes"],
            "stale_data_events": self._stats["stale_data_events"],
            "unified_symbols": len(self._unified_rates),
            "active_sources": self.active_source_count,
        }

    def get_unified_rates(
        self,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> list[FundingRateData]:
        """Get unified funding rates with optional filters."""
        rates = list(self._unified_rates.values())

        if exchange:
            rates = [r for r in rates if r.exchange == exchange.lower()]

        if symbol:
            rates = [r for r in rates if symbol.upper() in r.symbol.upper()]

        return rates

    def get_rates_for_symbol(self, symbol: str) -> list[FundingRateData]:
        """Get all funding rates for a symbol across exchanges."""
        return [
            rate
            for rate in self._unified_rates.values()
            if symbol.upper() in rate.symbol.upper()
        ]

    def get_latest_snapshot(self) -> Optional[UnifiedFundingSnapshot]:
        """Get the latest unified funding snapshot."""
        return self._latest_snapshot

    def calculate_spreads(
        self, min_spread: float = 0.0, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Calculate funding rate spreads between exchanges.

        Returns sorted list of (exchange_a, exchange_b, symbol, spread) tuples.
        This is the key input for opportunity detection.
        """
        # Group rates by normalized symbol
        symbol_rates: dict[str, list[FundingRateData]] = {}
        for rate in self._unified_rates.values():
            # Normalize symbol (extract base asset)
            parts = rate.symbol.split("/")
            base = parts[0] if parts else rate.symbol

            if base not in symbol_rates:
                symbol_rates[base] = []
            symbol_rates[base].append(rate)

        spreads = []
        for symbol, rates in symbol_rates.items():
            if len(rates) < 2:
                continue

            # Calculate all pairwise spreads
            for i, rate_a in enumerate(rates):
                for rate_b in rates[i + 1 :]:
                    spread = abs(rate_a.funding_rate - rate_b.funding_rate)
                    spread_pct = spread * 100  # Convert to percentage

                    if spread_pct >= min_spread:
                        # Determine long/short assignment
                        if rate_a.funding_rate > rate_b.funding_rate:
                            long_exchange = rate_b.exchange
                            short_exchange = rate_a.exchange
                            long_rate = rate_b.funding_rate
                            short_rate = rate_a.funding_rate
                        else:
                            long_exchange = rate_a.exchange
                            short_exchange = rate_b.exchange
                            long_rate = rate_a.funding_rate
                            short_rate = rate_b.funding_rate

                        # Calculate annualized APR based on actual funding interval
                        # Use the smaller interval (more conservative) between the two exchanges
                        long_interval = getattr(rate_a, 'funding_interval_hours', 8) if rate_a.funding_rate <= rate_b.funding_rate else getattr(rate_b, 'funding_interval_hours', 8)
                        short_interval = getattr(rate_b, 'funding_interval_hours', 8) if rate_a.funding_rate <= rate_b.funding_rate else getattr(rate_a, 'funding_interval_hours', 8)
                        # Use the minimum interval for most accurate APR estimation
                        effective_interval = min(long_interval, short_interval)
                        # Funding occurs (24 / interval) times per day, * 365 days per year
                        periods_per_year = (24 / effective_interval) * 365
                        annualized_apr = spread_pct * periods_per_year

                        spreads.append(
                            {
                                "symbol": symbol,
                                "long_exchange": long_exchange,
                                "short_exchange": short_exchange,
                                "long_rate": long_rate,
                                "short_rate": short_rate,
                                "spread": spread,
                                "spread_pct": spread_pct,
                                "annualized_apr": annualized_apr,
                                "long_funding_interval_hours": long_interval,
                                "short_funding_interval_hours": short_interval,
                            }
                        )

        # Sort by spread descending
        spreads.sort(key=lambda x: x["spread"], reverse=True)

        return spreads[:limit]

    async def get_arb_scanner_status(self) -> dict[str, Any]:
        """Get ArbitrageScanner API status."""
        return await self.arb_scanner.get_status()
