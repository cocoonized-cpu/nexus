"""
Data Collector Manager - Orchestrates data collection from all exchanges.

Features:
- Provider fallback for resilience
- Data validation before publishing
- Automatic recovery of unhealthy providers
- Reliability-based provider selection
"""

import asyncio
from datetime import datetime
from typing import Any, Optional

from src.providers.base import ExchangeProvider
from src.providers.binance import BinanceProvider
from src.providers.bitget import BitgetProvider
from src.providers.bybit import BybitProvider
from src.providers.dydx import DYDXProvider
from src.providers.gate import GateProvider
from src.providers.hyperliquid import HyperliquidProvider
from src.providers.kucoin import KuCoinProvider
from src.providers.okx import OKXProvider
from src.providers.validators import (
    funding_rate_validator,
    price_validator,
    liquidity_validator,
    validate_funding_rate,
)

from shared.events.market import (ExchangeHealthChangedEvent,
                                  FundingRateUpdatedEvent)
from shared.models.exchange import ExchangeHealth
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class DataCollectorManager:
    """
    Manages data collection from all configured exchanges.

    Responsibilities:
    - Initialize exchange providers
    - Schedule periodic data collection
    - Publish events on data updates
    - Monitor exchange health
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.providers: dict[str, ExchangeProvider] = {}
        self._tasks: list[asyncio.Task] = []
        self._running = False

        # Collection intervals (seconds)
        self.funding_rate_interval = 30  # Funding rates every 30s
        self.price_interval = 5  # Prices every 5s
        self.liquidity_interval = 15  # Liquidity every 15s
        self.health_interval = 60  # Health check every 60s
        self.recovery_interval = 120  # Recovery attempt every 2 mins

        # Provider fallback configuration
        self._provider_priority: dict[str, int] = {}  # exchange_id -> priority (lower = higher priority)
        self._min_reliability_score = 0.5  # Minimum reliability to be considered primary

        # Statistics
        self._stats = {
            "funding_updates": 0,
            "price_updates": 0,
            "liquidity_updates": 0,
            "errors": 0,
            "validation_failures": 0,
            "fallback_activations": 0,
            "recovery_successes": 0,
            "recovery_failures": 0,
            "start_time": None,
        }

    async def start(self) -> None:
        """Start the data collector."""
        logger.info("Starting Data Collector Manager")

        # Initialize providers
        await self._init_providers()

        self._running = True
        self._stats["start_time"] = datetime.utcnow()

        # Start collection tasks
        self._tasks = [
            asyncio.create_task(self._collect_funding_rates()),
            asyncio.create_task(self._collect_prices()),
            asyncio.create_task(self._collect_liquidity()),
            asyncio.create_task(self._monitor_health()),
            asyncio.create_task(self._recovery_loop()),
        ]

        logger.info(
            "Data Collector started",
            providers=list(self.providers.keys()),
        )

    async def stop(self) -> None:
        """Stop the data collector."""
        logger.info("Stopping Data Collector Manager")
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close all providers
        for provider in self.providers.values():
            await provider.close()

        logger.info("Data Collector stopped")

    async def _init_providers(self) -> None:
        """Initialize exchange providers with priority ranking."""
        # Provider classes with priority (lower = higher priority)
        # Tier 1 exchanges get higher priority
        provider_config = [
            (BinanceProvider, 1),   # Tier 1
            (BybitProvider, 1),     # Tier 1
            (OKXProvider, 1),       # Tier 1
            (HyperliquidProvider, 1),  # Tier 1 (DEX)
            (DYDXProvider, 2),      # Tier 2
            (GateProvider, 2),      # Tier 2
            (KuCoinProvider, 2),    # Tier 2
            (BitgetProvider, 2),    # Tier 2
        ]

        for provider_class, priority in provider_config:
            try:
                provider = provider_class()
                await provider.initialize()
                self.providers[provider.exchange_id] = provider
                self._provider_priority[provider.exchange_id] = priority
                logger.info(
                    f"Initialized provider: {provider.exchange_id}",
                    priority=priority,
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize provider: {provider_class.__name__}",
                    error=str(e),
                )

    async def _collect_funding_rates(self) -> None:
        """Periodically collect funding rates from all exchanges with fallback."""
        while self._running:
            try:
                # Get providers sorted by priority and reliability
                sorted_providers = self._get_sorted_providers()

                tasks = []
                for exchange_id, provider in sorted_providers:
                    if provider.is_healthy:
                        tasks.append(
                            self._fetch_funding_rates_with_fallback(exchange_id, provider)
                        )

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as e:
                logger.error("Error in funding rate collection", error=str(e))
                self._stats["errors"] += 1

            await asyncio.sleep(self.funding_rate_interval)

    def _get_sorted_providers(self) -> list[tuple[str, ExchangeProvider]]:
        """
        Get providers sorted by priority and reliability score.

        Returns:
            List of (exchange_id, provider) tuples sorted by priority
        """
        providers_with_score = []
        for exchange_id, provider in self.providers.items():
            priority = self._provider_priority.get(exchange_id, 99)
            reliability = provider.reliability_score
            # Combined score: priority first, then reliability (inverted so higher is better)
            combined_score = (priority, -reliability)
            providers_with_score.append((combined_score, exchange_id, provider))

        # Sort by combined score (lower priority number = better, higher reliability = better)
        providers_with_score.sort(key=lambda x: x[0])

        return [(ex_id, prov) for _, ex_id, prov in providers_with_score]

    async def _fetch_funding_rates_with_fallback(
        self, exchange_id: str, provider: ExchangeProvider
    ) -> None:
        """
        Fetch funding rates with retry and fallback to alternative providers.

        Args:
            exchange_id: Primary exchange to fetch from
            provider: Primary provider instance
        """
        try:
            # Try primary provider with built-in retry
            funding_rates = await provider._with_retry(
                provider.get_funding_rates,
                operation_name="get_funding_rates",
            )
            await self._process_funding_rates(exchange_id, funding_rates)

        except Exception as e:
            logger.warning(
                f"Primary provider failed, attempting fallback",
                exchange=exchange_id,
                error=str(e),
            )

            # Try fallback provider
            fallback_success = await self._try_fallback_provider(exchange_id)
            if not fallback_success:
                self._stats["errors"] += 1

    async def _try_fallback_provider(self, failed_exchange_id: str) -> bool:
        """
        Try to use a fallback provider when primary fails.

        Args:
            failed_exchange_id: The exchange that failed

        Returns:
            True if fallback succeeded, False otherwise
        """
        # Get healthy providers sorted by priority
        sorted_providers = self._get_sorted_providers()
        healthy_fallbacks = [
            (ex_id, prov) for ex_id, prov in sorted_providers
            if ex_id != failed_exchange_id
            and prov.is_healthy
            and prov.reliability_score >= self._min_reliability_score
        ]

        if not healthy_fallbacks:
            logger.warning(
                "No healthy fallback providers available",
                failed_exchange=failed_exchange_id,
            )
            return False

        # Try the best fallback
        fallback_id, fallback_provider = healthy_fallbacks[0]

        try:
            funding_rates = await fallback_provider._with_retry(
                fallback_provider.get_funding_rates,
                operation_name="get_funding_rates_fallback",
                max_retries=1,  # Fewer retries for fallback
            )

            # Mark the rates as coming from fallback
            await self._process_funding_rates(
                fallback_id, funding_rates, is_fallback=True
            )

            self._stats["fallback_activations"] += 1
            logger.info(
                "Fallback provider succeeded",
                failed_exchange=failed_exchange_id,
                fallback_exchange=fallback_id,
            )
            return True

        except Exception as e:
            logger.error(
                "Fallback provider also failed",
                fallback_exchange=fallback_id,
                error=str(e),
            )
            return False

    async def _process_funding_rates(
        self,
        exchange_id: str,
        funding_rates: list,
        is_fallback: bool = False,
    ) -> None:
        """
        Process and publish funding rates with validation.

        Args:
            exchange_id: Source exchange
            funding_rates: List of FundingRateData
            is_fallback: Whether this came from a fallback provider
        """
        valid_count = 0
        invalid_count = 0

        for rate in funding_rates:
            # Get historical rates for anomaly detection
            historical = funding_rate_validator.get_historical_rates(
                exchange_id, rate.symbol
            )

            # Validate the rate
            validation_result = validate_funding_rate(rate, historical)

            if not validation_result.is_valid:
                invalid_count += 1
                self._stats["validation_failures"] += 1
                logger.debug(
                    "Funding rate validation failed",
                    exchange=exchange_id,
                    symbol=rate.symbol,
                    errors=validation_result.errors,
                )
                continue

            # Update history for future anomaly detection
            funding_rate_validator.update_history(rate)

            # Publish valid rate
            rate_data = {
                "exchange": exchange_id,
                "symbol": rate.symbol,
                "funding_rate": rate.funding_rate,
                "predicted_rate": float(rate.predicted_rate) if rate.predicted_rate else None,
                "next_funding_time": rate.next_funding_time.isoformat() if rate.next_funding_time else None,
                "timestamp": datetime.utcnow().isoformat(),
                "funding_interval_hours": getattr(rate, 'funding_interval_hours', 8),
                "is_fallback": is_fallback,
                "validation_warnings": validation_result.warnings if validation_result.warnings else None,
            }
            await self.redis.publish(
                f"nexus:market_data:funding_rate",
                rate_data,
            )
            valid_count += 1

        self._stats["funding_updates"] += valid_count
        logger.debug(
            f"Processed funding rates",
            exchange=exchange_id,
            valid=valid_count,
            invalid=invalid_count,
            is_fallback=is_fallback,
        )

    async def _fetch_funding_rates(
        self, exchange_id: str, provider: ExchangeProvider
    ) -> None:
        """Fetch funding rates from a single exchange (legacy method for compatibility)."""
        try:
            funding_rates = await provider.get_funding_rates()
            await self._process_funding_rates(exchange_id, funding_rates)

        except Exception as e:
            logger.warning(
                f"Failed to fetch funding rates",
                exchange=exchange_id,
                error=str(e),
            )
            self._stats["errors"] += 1

    async def _collect_prices(self) -> None:
        """Periodically collect price data from all exchanges."""
        while self._running:
            try:
                tasks = []
                for exchange_id, provider in self.providers.items():
                    if provider.is_healthy:
                        tasks.append(self._fetch_prices(exchange_id, provider))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as e:
                logger.error("Error in price collection", error=str(e))
                self._stats["errors"] += 1

            await asyncio.sleep(self.price_interval)

    async def _fetch_prices(self, exchange_id: str, provider: ExchangeProvider) -> None:
        """Fetch prices from a single exchange."""
        try:
            prices = await provider.get_prices()

            # Batch publish prices
            for price in prices:
                await self.redis.publish(
                    f"nexus:market_data:price",
                    price.model_dump_json(),
                )

            self._stats["price_updates"] += len(prices)

        except Exception as e:
            logger.warning(
                f"Failed to fetch prices",
                exchange=exchange_id,
                error=str(e),
            )
            self._stats["errors"] += 1

    async def _collect_liquidity(self) -> None:
        """Periodically collect liquidity/orderbook data from all exchanges."""
        while self._running:
            try:
                tasks = []
                for exchange_id, provider in self.providers.items():
                    if provider.is_healthy:
                        tasks.append(self._fetch_liquidity(exchange_id, provider))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as e:
                logger.error("Error in liquidity collection", error=str(e))
                self._stats["errors"] += 1

            await asyncio.sleep(self.liquidity_interval)

    async def _fetch_liquidity(
        self, exchange_id: str, provider: ExchangeProvider
    ) -> None:
        """Fetch liquidity data from a single exchange."""
        try:
            liquidity_data = await provider.get_liquidity()

            for data in liquidity_data:
                await self.redis.publish(
                    f"nexus:market_data:liquidity",
                    data.model_dump_json(),
                )

            self._stats["liquidity_updates"] += len(liquidity_data)

        except Exception as e:
            logger.warning(
                f"Failed to fetch liquidity",
                exchange=exchange_id,
                error=str(e),
            )
            self._stats["errors"] += 1

    async def _monitor_health(self) -> None:
        """Monitor exchange health status."""
        previous_health: dict[str, bool] = {}

        while self._running:
            try:
                for exchange_id, provider in self.providers.items():
                    current_healthy = provider.is_healthy
                    prev_healthy = previous_health.get(exchange_id, True)

                    # Publish event if health changed
                    if current_healthy != prev_healthy:
                        event = ExchangeHealthChangedEvent(
                            exchange=exchange_id,
                            is_healthy=current_healthy,
                            reason=provider.health_reason,
                            timestamp=datetime.utcnow(),
                        )
                        await self.redis.publish(
                            f"nexus:system:exchange_health",
                            event.model_dump_json(),
                        )
                        logger.info(
                            "Exchange health changed",
                            exchange=exchange_id,
                            healthy=current_healthy,
                            reason=provider.health_reason,
                        )

                    previous_health[exchange_id] = current_healthy

            except Exception as e:
                logger.error("Error in health monitoring", error=str(e))

            await asyncio.sleep(self.health_interval)

    async def _recovery_loop(self) -> None:
        """Periodically attempt to recover unhealthy providers."""
        while self._running:
            try:
                unhealthy_providers = [
                    (ex_id, prov)
                    for ex_id, prov in self.providers.items()
                    if not prov.is_healthy
                ]

                for exchange_id, provider in unhealthy_providers:
                    logger.info(
                        f"Attempting recovery for {exchange_id}",
                        reason=provider.health_reason,
                    )

                    success = await provider.attempt_recovery()

                    if success:
                        self._stats["recovery_successes"] += 1
                        # Publish health restored event
                        event = ExchangeHealthChangedEvent(
                            exchange=exchange_id,
                            is_healthy=True,
                            reason="Recovered after retry",
                            timestamp=datetime.utcnow(),
                        )
                        await self.redis.publish(
                            f"nexus:system:exchange_health",
                            event.model_dump_json(),
                        )
                    else:
                        self._stats["recovery_failures"] += 1

            except Exception as e:
                logger.error("Error in recovery loop", error=str(e))

            await asyncio.sleep(self.recovery_interval)

    @property
    def active_exchange_count(self) -> int:
        """Get number of active/healthy exchanges."""
        return sum(1 for p in self.providers.values() if p.is_healthy)

    async def get_exchange_health(self) -> dict[str, Any]:
        """Get health status for all exchanges with reliability metrics."""
        health_status = {}
        for exchange_id, provider in self.providers.items():
            health_status[exchange_id] = {
                "healthy": provider.is_healthy,
                "reason": provider.health_reason,
                "last_update": (
                    provider.last_update.isoformat() if provider.last_update else None
                ),
                "requests_made": provider.request_count,
                "error_count": provider.error_count,
                "reliability_score": provider.reliability_score,
                "priority": self._provider_priority.get(exchange_id, 99),
                "last_error": provider.last_error,
                "last_error_time": (
                    provider.last_error_time.isoformat()
                    if provider.last_error_time else None
                ),
            }
        return health_status

    def get_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        uptime = None
        if self._stats["start_time"]:
            uptime = (datetime.utcnow() - self._stats["start_time"]).total_seconds()

        return {
            "uptime_seconds": uptime,
            "funding_updates": self._stats["funding_updates"],
            "price_updates": self._stats["price_updates"],
            "liquidity_updates": self._stats["liquidity_updates"],
            "errors": self._stats["errors"],
            "validation_failures": self._stats["validation_failures"],
            "fallback_activations": self._stats["fallback_activations"],
            "recovery_successes": self._stats["recovery_successes"],
            "recovery_failures": self._stats["recovery_failures"],
            "active_exchanges": self.active_exchange_count,
            "total_exchanges": len(self.providers),
        }
