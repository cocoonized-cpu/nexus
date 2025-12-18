"""
Data Validation Layer for Exchange Providers.

Validates funding rate data, price data, and liquidity data before
publishing to ensure data quality and detect anomalies.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from shared.models.funding import FundingRateData
from shared.models.exchange import PriceData, LiquidityData
from shared.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]

    @classmethod
    def valid(cls) -> "ValidationResult":
        return cls(is_valid=True, errors=[], warnings=[])

    @classmethod
    def invalid(cls, error: str) -> "ValidationResult":
        return cls(is_valid=False, errors=[error], warnings=[])

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge another validation result into this one."""
        return ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )


class FundingRateValidator:
    """Validates funding rate data for quality and anomalies."""

    # Funding rate bounds (most exchanges use -1% to 1% per period)
    MIN_RATE = Decimal("-0.01")  # -1%
    MAX_RATE = Decimal("0.01")  # 1%

    # Extreme bounds for warning (not rejection)
    EXTREME_MIN_RATE = Decimal("-0.005")  # -0.5%
    EXTREME_MAX_RATE = Decimal("0.005")  # 0.5%

    # Timestamp freshness threshold
    MAX_AGE_SECONDS = 300  # 5 minutes

    # Z-score threshold for anomaly detection
    ANOMALY_ZSCORE_THRESHOLD = 3.0

    def __init__(self):
        # Store recent rates for anomaly detection
        self._rate_history: dict[str, list[tuple[datetime, Decimal]]] = {}
        self._history_window = 50  # Keep last 50 rates per symbol

    def validate(
        self,
        rate: FundingRateData,
        historical_rates: Optional[list[Decimal]] = None,
    ) -> ValidationResult:
        """
        Validate a funding rate data point.

        Args:
            rate: The funding rate to validate
            historical_rates: Optional list of recent rates for anomaly detection

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        result = ValidationResult.valid()

        # Check rate bounds
        bounds_result = self._validate_bounds(rate)
        result = result.merge(bounds_result)

        # Check timestamp freshness
        freshness_result = self._validate_freshness(rate)
        result = result.merge(freshness_result)

        # Check for anomalies if historical data available
        if historical_rates:
            anomaly_result = self._detect_anomaly(rate, historical_rates)
            result = result.merge(anomaly_result)

        # Log validation result
        if not result.is_valid:
            logger.warning(
                "Funding rate validation failed",
                exchange=rate.exchange,
                symbol=rate.symbol,
                rate=float(rate.rate),
                errors=result.errors,
            )
        elif result.warnings:
            logger.debug(
                "Funding rate validation warnings",
                exchange=rate.exchange,
                symbol=rate.symbol,
                warnings=result.warnings,
            )

        return result

    def _validate_bounds(self, rate: FundingRateData) -> ValidationResult:
        """Check if funding rate is within acceptable bounds."""
        result = ValidationResult.valid()

        funding_rate = rate.rate
        if funding_rate is None:
            result.add_error("Funding rate is None")
            return result

        # Hard bounds - reject if outside
        if funding_rate < self.MIN_RATE or funding_rate > self.MAX_RATE:
            result.add_error(
                f"Rate {float(funding_rate):.6f} outside bounds "
                f"[{float(self.MIN_RATE)}, {float(self.MAX_RATE)}]"
            )
            return result

        # Soft bounds - warn if extreme but accept
        if funding_rate < self.EXTREME_MIN_RATE or funding_rate > self.EXTREME_MAX_RATE:
            result.add_warning(
                f"Rate {float(funding_rate):.6f} is extreme "
                f"(outside [{float(self.EXTREME_MIN_RATE)}, {float(self.EXTREME_MAX_RATE)}])"
            )

        return result

    def _validate_freshness(self, rate: FundingRateData) -> ValidationResult:
        """Check if the data timestamp is recent enough."""
        result = ValidationResult.valid()

        if rate.timestamp is None:
            result.add_error("Timestamp is None")
            return result

        age = (datetime.utcnow() - rate.timestamp).total_seconds()

        if age > self.MAX_AGE_SECONDS:
            result.add_error(
                f"Data is stale: {age:.0f}s old (max: {self.MAX_AGE_SECONDS}s)"
            )
        elif age > self.MAX_AGE_SECONDS / 2:
            result.add_warning(f"Data is getting stale: {age:.0f}s old")

        return result

    def _detect_anomaly(
        self,
        rate: FundingRateData,
        historical_rates: list[Decimal],
    ) -> ValidationResult:
        """
        Detect if the rate is an anomaly using z-score.

        Args:
            rate: Current rate to check
            historical_rates: Recent historical rates for comparison

        Returns:
            ValidationResult with anomaly detection status
        """
        result = ValidationResult.valid()

        if len(historical_rates) < 5:
            # Not enough history for reliable anomaly detection
            return result

        # Calculate mean and standard deviation
        rates_float = [float(r) for r in historical_rates]
        mean = sum(rates_float) / len(rates_float)
        variance = sum((r - mean) ** 2 for r in rates_float) / len(rates_float)
        std_dev = variance ** 0.5

        if std_dev == 0:
            # All rates identical, any difference is notable
            if float(rate.rate) != mean:
                result.add_warning(
                    f"Rate {float(rate.rate):.6f} differs from constant historical rate {mean:.6f}"
                )
            return result

        # Calculate z-score
        z_score = abs(float(rate.rate) - mean) / std_dev

        if z_score > self.ANOMALY_ZSCORE_THRESHOLD:
            result.add_warning(
                f"Potential anomaly detected: z-score={z_score:.2f} "
                f"(threshold: {self.ANOMALY_ZSCORE_THRESHOLD})"
            )

        return result

    def update_history(self, rate: FundingRateData) -> None:
        """
        Update rate history for a symbol.

        Args:
            rate: Rate data to add to history
        """
        key = f"{rate.exchange}:{rate.symbol}"

        if key not in self._rate_history:
            self._rate_history[key] = []

        history = self._rate_history[key]
        history.append((rate.timestamp, rate.rate))

        # Trim to window size
        if len(history) > self._history_window:
            self._rate_history[key] = history[-self._history_window :]

    def get_historical_rates(self, exchange: str, symbol: str) -> list[Decimal]:
        """
        Get historical rates for anomaly detection.

        Args:
            exchange: Exchange identifier
            symbol: Trading symbol

        Returns:
            List of recent funding rates
        """
        key = f"{exchange}:{symbol}"
        history = self._rate_history.get(key, [])
        return [rate for _, rate in history]


class PriceValidator:
    """Validates price data for quality and anomalies."""

    # Price must be positive
    MIN_PRICE = Decimal("0")

    # Maximum price change per tick (100% = price doubled)
    MAX_PRICE_CHANGE_PCT = Decimal("0.50")  # 50%

    # Timestamp freshness threshold
    MAX_AGE_SECONDS = 60  # 1 minute for price data

    def __init__(self):
        self._last_prices: dict[str, Decimal] = {}

    def validate(self, price: PriceData) -> ValidationResult:
        """Validate price data."""
        result = ValidationResult.valid()

        # Check positive price
        if price.price is None or price.price <= self.MIN_PRICE:
            result.add_error(f"Invalid price: {price.price}")
            return result

        # Check for extreme price jump
        key = f"{price.exchange}:{price.symbol}"
        if key in self._last_prices:
            last_price = self._last_prices[key]
            change_pct = abs(price.price - last_price) / last_price

            if change_pct > self.MAX_PRICE_CHANGE_PCT:
                result.add_warning(
                    f"Large price change: {float(change_pct)*100:.1f}% "
                    f"({float(last_price):.4f} -> {float(price.price):.4f})"
                )

        # Check freshness
        if price.timestamp:
            age = (datetime.utcnow() - price.timestamp).total_seconds()
            if age > self.MAX_AGE_SECONDS:
                result.add_error(f"Price data stale: {age:.0f}s old")

        # Update last price
        self._last_prices[key] = price.price

        return result


class LiquidityValidator:
    """Validates liquidity/orderbook data."""

    # Minimum expected liquidity for major pairs
    MIN_BID_ASK_LEVELS = 1

    # Maximum bid-ask spread percentage
    MAX_SPREAD_PCT = Decimal("0.05")  # 5%

    def validate(self, liquidity: LiquidityData) -> ValidationResult:
        """Validate liquidity data."""
        result = ValidationResult.valid()

        # Check we have bid/ask data
        if not liquidity.best_bid or not liquidity.best_ask:
            result.add_error("Missing bid or ask price")
            return result

        # Check bid < ask (no crossed book)
        if liquidity.best_bid >= liquidity.best_ask:
            result.add_error(
                f"Crossed orderbook: bid={float(liquidity.best_bid)} >= "
                f"ask={float(liquidity.best_ask)}"
            )
            return result

        # Check spread
        spread = liquidity.best_ask - liquidity.best_bid
        mid_price = (liquidity.best_ask + liquidity.best_bid) / 2
        spread_pct = spread / mid_price

        if spread_pct > self.MAX_SPREAD_PCT:
            result.add_warning(
                f"Wide spread: {float(spread_pct)*100:.2f}% "
                f"(max: {float(self.MAX_SPREAD_PCT)*100:.1f}%)"
            )

        # Check depth
        if liquidity.bid_depth is not None and liquidity.bid_depth <= 0:
            result.add_warning("Zero bid depth")
        if liquidity.ask_depth is not None and liquidity.ask_depth <= 0:
            result.add_warning("Zero ask depth")

        return result


# Singleton validators for use across the service
funding_rate_validator = FundingRateValidator()
price_validator = PriceValidator()
liquidity_validator = LiquidityValidator()


def validate_funding_rate(
    rate: FundingRateData,
    historical_rates: Optional[list[Decimal]] = None,
) -> ValidationResult:
    """
    Convenience function to validate a funding rate.

    Args:
        rate: Funding rate data to validate
        historical_rates: Optional historical rates for anomaly detection

    Returns:
        ValidationResult
    """
    return funding_rate_validator.validate(rate, historical_rates)


def validate_price(price: PriceData) -> ValidationResult:
    """
    Convenience function to validate price data.

    Args:
        price: Price data to validate

    Returns:
        ValidationResult
    """
    return price_validator.validate(price)


def validate_liquidity(liquidity: LiquidityData) -> ValidationResult:
    """
    Convenience function to validate liquidity data.

    Args:
        liquidity: Liquidity data to validate

    Returns:
        ValidationResult
    """
    return liquidity_validator.validate(liquidity)
