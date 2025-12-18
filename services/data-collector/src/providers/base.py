"""
Base Exchange Provider - Abstract interface for exchange data providers.

Includes:
- Retry logic with exponential backoff
- Health recovery mechanisms
- Provider reliability tracking
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

from shared.models.exchange import LiquidityData, PriceData
from shared.models.funding import FundingRateData
from shared.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class ExchangeProvider(ABC):
    """
    Abstract base class for exchange data providers.

    Each exchange provider implements this interface to provide:
    - Funding rates
    - Price data
    - Liquidity data
    - Health monitoring

    Providers handle their own rate limiting and error recovery.
    """

    def __init__(self):
        self._is_healthy = True
        self._health_reason: Optional[str] = None
        self._last_update: Optional[datetime] = None
        self._request_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5

        # Retry configuration
        self._max_retries = 3
        self._base_retry_delay = 1.0  # seconds
        self._max_retry_delay = 30.0  # seconds

        # Reliability tracking
        self._success_count = 0
        self._total_requests = 0
        self._last_error: Optional[str] = None
        self._last_error_time: Optional[datetime] = None
        self._recovery_attempts = 0
        self._max_recovery_attempts = 3

    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """Unique identifier for this exchange."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for this exchange."""
        pass

    @property
    def is_healthy(self) -> bool:
        """Whether the exchange connection is healthy."""
        return self._is_healthy

    @property
    def health_reason(self) -> Optional[str]:
        """Reason for unhealthy status."""
        return self._health_reason

    @property
    def last_update(self) -> Optional[datetime]:
        """Timestamp of last successful data fetch."""
        return self._last_update

    @property
    def request_count(self) -> int:
        """Total number of API requests made."""
        return self._request_count

    @property
    def error_count(self) -> int:
        """Total number of errors encountered."""
        return self._error_count

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider (connect, authenticate, etc.)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the provider and clean up resources."""
        pass

    @abstractmethod
    async def get_funding_rates(self) -> list[FundingRateData]:
        """
        Fetch current funding rates for all perpetual contracts.

        Returns:
            List of FundingRateData for each symbol
        """
        pass

    @abstractmethod
    async def get_prices(self) -> list[PriceData]:
        """
        Fetch current prices for tracked symbols.

        Returns:
            List of PriceData for each symbol
        """
        pass

    @abstractmethod
    async def get_liquidity(self) -> list[LiquidityData]:
        """
        Fetch order book liquidity data.

        Returns:
            List of LiquidityData for each symbol
        """
        pass

    def _record_success(self) -> None:
        """Record a successful API call."""
        self._request_count += 1
        self._total_requests += 1
        self._success_count += 1
        self._last_update = datetime.utcnow()
        self._consecutive_errors = 0
        if not self._is_healthy:
            self._is_healthy = True
            self._health_reason = None
            logger.info(f"{self.exchange_id} recovered")

    def _record_error(self, error: str) -> None:
        """Record an API error."""
        self._request_count += 1
        self._error_count += 1
        self._consecutive_errors += 1
        self._total_requests += 1
        self._last_error = error
        self._last_error_time = datetime.utcnow()

        if self._consecutive_errors >= self._max_consecutive_errors:
            self._is_healthy = False
            self._health_reason = f"Too many consecutive errors: {error}"
            logger.warning(
                f"{self.exchange_id} marked unhealthy",
                reason=self._health_reason,
            )

    @property
    def reliability_score(self) -> float:
        """
        Calculate provider reliability score (0.0 to 1.0).

        Based on success rate over total requests.
        """
        if self._total_requests == 0:
            return 1.0  # No data yet, assume reliable
        return self._success_count / self._total_requests

    @property
    def last_error(self) -> Optional[str]:
        """Last error message encountered."""
        return self._last_error

    @property
    def last_error_time(self) -> Optional[datetime]:
        """Timestamp of last error."""
        return self._last_error_time

    async def _with_retry(
        self,
        operation: Callable[[], Any],
        operation_name: str = "operation",
        max_retries: Optional[int] = None,
    ) -> Any:
        """
        Execute an operation with exponential backoff retry.

        Args:
            operation: Async callable to execute
            operation_name: Name for logging purposes
            max_retries: Override default max retries

        Returns:
            Result of the operation

        Raises:
            Exception: If all retries are exhausted
        """
        retries = max_retries if max_retries is not None else self._max_retries
        last_exception: Optional[Exception] = None

        for attempt in range(retries + 1):
            try:
                result = await operation()
                self._record_success()
                return result
            except Exception as e:
                last_exception = e
                delay = min(
                    self._base_retry_delay * (2 ** attempt),
                    self._max_retry_delay,
                )

                if attempt < retries:
                    logger.warning(
                        f"{self.exchange_id} {operation_name} failed, retrying",
                        attempt=attempt + 1,
                        max_retries=retries,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    self._record_error(str(e))
                    logger.error(
                        f"{self.exchange_id} {operation_name} failed after all retries",
                        attempts=retries + 1,
                        error=str(e),
                    )

        raise last_exception  # type: ignore

    async def attempt_recovery(self) -> bool:
        """
        Attempt to recover an unhealthy provider.

        Performs close and re-initialize cycle with backoff.

        Returns:
            True if recovery successful, False otherwise
        """
        if self._is_healthy:
            return True

        if self._recovery_attempts >= self._max_recovery_attempts:
            logger.warning(
                f"{self.exchange_id} max recovery attempts reached",
                attempts=self._recovery_attempts,
            )
            return False

        self._recovery_attempts += 1
        delay = min(
            self._base_retry_delay * (2 ** self._recovery_attempts),
            self._max_retry_delay,
        )

        logger.info(
            f"{self.exchange_id} attempting recovery",
            attempt=self._recovery_attempts,
            delay=delay,
        )

        try:
            # Close existing connection
            try:
                await self.close()
            except Exception as close_err:
                logger.debug(
                    f"{self.exchange_id} error during close",
                    error=str(close_err),
                )

            # Wait before reconnecting
            await asyncio.sleep(delay)

            # Re-initialize
            await self.initialize()

            # Reset health state
            self._is_healthy = True
            self._health_reason = None
            self._consecutive_errors = 0
            self._recovery_attempts = 0

            logger.info(f"{self.exchange_id} recovery successful")
            return True

        except Exception as e:
            logger.error(
                f"{self.exchange_id} recovery failed",
                attempt=self._recovery_attempts,
                error=str(e),
            )
            return False

    def reset_recovery_counter(self) -> None:
        """Reset recovery attempt counter after sustained healthy operation."""
        self._recovery_attempts = 0

    def get_health_stats(self) -> dict:
        """
        Get comprehensive health statistics for this provider.

        Returns:
            Dict with health metrics
        """
        return {
            "exchange_id": self.exchange_id,
            "is_healthy": self._is_healthy,
            "health_reason": self._health_reason,
            "reliability_score": self.reliability_score,
            "total_requests": self._total_requests,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "last_error": self._last_error,
            "last_error_time": (
                self._last_error_time.isoformat() if self._last_error_time else None
            ),
            "recovery_attempts": self._recovery_attempts,
        }
