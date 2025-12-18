"""
Unified Opportunity Score (UOS) Calculator.

The UOS is a 0-100 point composite score that evaluates arbitrage opportunities
across four dimensions:

1. Return Score (0-30 points)
   - Net APR after fees
   - Funding rate spread
   - Expected holding period returns

2. Risk Score (0-30 points)
   - Price correlation between exchanges
   - Historical volatility
   - Funding rate stability
   - Exchange counterparty risk

3. Execution Score (0-25 points)
   - Expected slippage
   - Trading fees
   - Order book depth
   - Exchange reliability

4. Timing Score (0-15 points)
   - Time to next funding period
   - Funding rate trend
   - Market momentum alignment

Enhanced Features:
- Real slippage estimation from liquidity data
- Actual exchange fees from configuration
- Funding rate stability from historical data
- Time to funding from actual funding schedules
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from shared.models.opportunity import UOSScores
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class UOSScorer:
    """
    Calculates Unified Opportunity Score (UOS) for arbitrage opportunities.

    Higher scores indicate more attractive opportunities.
    Minimum actionable score is typically 50.

    Enhanced with:
    - Real liquidity data for slippage estimation
    - Exchange fee configuration from database
    - Historical funding rate stability analysis
    - Actual time to funding calculations
    """

    # Exchange fee defaults (used when config not available)
    DEFAULT_EXCHANGE_FEES = {
        "binance": {"maker": 0.0002, "taker": 0.0004},  # 2bps / 4bps
        "bybit": {"maker": 0.0001, "taker": 0.0006},    # 1bp / 6bps
        "okx": {"maker": 0.0002, "taker": 0.0005},      # 2bps / 5bps
        "hyperliquid": {"maker": 0.0002, "taker": 0.0005},
        "dydx": {"maker": 0.0002, "taker": 0.0005},
        "gate": {"maker": 0.0002, "taker": 0.0005},
        "kucoin": {"maker": 0.0002, "taker": 0.0006},
        "bitget": {"maker": 0.0002, "taker": 0.0006},
    }

    # Funding intervals by exchange (hours)
    FUNDING_INTERVALS = {
        "binance": 8,
        "bybit": 8,
        "okx": 8,
        "hyperliquid": 1,  # Hourly funding
        "dydx": 1,         # Hourly funding
        "gate": 8,
        "kucoin": 8,
        "bitget": 8,
    }

    def __init__(
        self,
        redis: Optional[RedisClient] = None,
        db_session_factory: Optional[Any] = None,
    ):
        self.redis = redis
        self._db_session_factory = db_session_factory

        # Score weights (must sum to 100)
        self.weights = {
            "return": 30,
            "risk": 30,
            "execution": 25,
            "timing": 15,
        }

        # Thresholds for normalization
        self.thresholds = {
            "max_apr": 100.0,  # 100% APR = max return score
            "min_volume": 1_000_000,  # $1M = baseline volume
            "max_volume": 100_000_000,  # $100M = max volume bonus
            "optimal_spread": 0.05,  # 0.05% = optimal spread
            "max_slippage": 0.5,  # 0.5% = max acceptable slippage
            "optimal_time_to_funding": 4,  # 4 hours = optimal
            "max_stability_std": 0.001,  # Max std dev for full stability score
        }

        # Cache for exchange fees and liquidity
        self._fee_cache: dict[str, dict] = {}
        self._liquidity_cache: dict[str, dict] = {}
        self._stability_cache: dict[str, float] = {}
        self._cache_ttl = timedelta(minutes=5)

    def calculate_scores(self, spread_data: dict[str, Any]) -> UOSScores:
        """
        Calculate UOS scores for a spread opportunity.

        Args:
            spread_data: Dict containing spread and market data

        Returns:
            UOSScores with breakdown and total
        """
        return_score = int(self._calculate_return_score(spread_data))
        risk_score = int(self._calculate_risk_score(spread_data))
        execution_score = int(self._calculate_execution_score(spread_data))
        timing_score = int(self._calculate_timing_score(spread_data))

        return UOSScores(
            return_score=return_score,
            risk_score=risk_score,
            execution_score=execution_score,
            timing_score=timing_score,
        )

    def _calculate_return_score(self, data: dict[str, Any]) -> float:
        """
        Calculate return score (0-30 points).

        Based on:
        - Annualized APR from funding spread
        - Spread magnitude
        - Fee-adjusted returns
        """
        max_points = self.weights["return"]
        score = 0.0

        # APR component (0-20 points)
        apr = data.get("annualized_apr", 0)
        apr_ratio = min(apr / self.thresholds["max_apr"], 1.0)
        score += apr_ratio * 20

        # Spread component (0-10 points)
        spread_pct = data.get("spread_pct", 0)
        spread_ratio = min(spread_pct / self.thresholds["optimal_spread"], 1.0)
        score += spread_ratio * 10

        return min(score, max_points)

    def _calculate_risk_score(self, data: dict[str, Any]) -> float:
        """
        Calculate risk score (0-30 points).

        Higher score = lower risk = better opportunity.

        Based on:
        - Exchange tier (Tier 1 = lower risk)
        - Volume (higher = lower risk)
        - Funding rate stability (from historical data)
        - Price correlation
        """
        max_points = self.weights["risk"]
        score = 0.0

        # Exchange tier component (0-12 points)
        long_exchange = data.get("long_exchange", "").lower()
        short_exchange = data.get("short_exchange", "").lower()

        tier1_exchanges = {"binance", "bybit", "okx", "hyperliquid", "dydx"}
        tier2_exchanges = {"gate", "kucoin", "bitget"}

        exchanges = {long_exchange, short_exchange}
        if exchanges <= tier1_exchanges:
            score += 12  # Both Tier 1
        elif exchanges & tier1_exchanges:
            score += 8  # At least one Tier 1
        elif exchanges <= tier2_exchanges:
            score += 5  # Both Tier 2
        else:
            score += 2  # Unknown tiers

        # Volume component (0-10 points)
        volume_24h = data.get("volume_24h", self.thresholds["min_volume"])
        volume_ratio = min(
            (volume_24h - self.thresholds["min_volume"])
            / (self.thresholds["max_volume"] - self.thresholds["min_volume"]),
            1.0,
        )
        volume_ratio = max(volume_ratio, 0)
        score += volume_ratio * 10

        # Stability component (0-8 points) - Use real data if available
        stability_score = self._calculate_stability_score(data)
        score += stability_score

        return min(score, max_points)

    def _calculate_stability_score(self, data: dict[str, Any]) -> float:
        """
        Calculate funding rate stability score (0-8 points).

        Uses historical spread variance if available.
        """
        symbol = data.get("symbol", "")
        long_exchange = data.get("long_exchange", "").lower()
        short_exchange = data.get("short_exchange", "").lower()

        # Check for pre-calculated stability in data
        if "spread_stability" in data:
            stability = data["spread_stability"]
            # Lower stability (std dev) = higher score
            stability_ratio = 1 - min(
                stability / self.thresholds["max_stability_std"], 1.0
            )
            return stability_ratio * 8

        # Check cache for historical stability
        cache_key = f"{symbol}:{long_exchange}:{short_exchange}"
        if cache_key in self._stability_cache:
            stability = self._stability_cache[cache_key]
            stability_ratio = 1 - min(
                stability / self.thresholds["max_stability_std"], 1.0
            )
            return stability_ratio * 8

        # Default to moderate stability if no data
        return 5.0

    def _calculate_execution_score(self, data: dict[str, Any]) -> float:
        """
        Calculate execution score (0-25 points).

        Based on:
        - Expected slippage (from liquidity data if available)
        - Trading fees (from exchange config)
        - Order book depth
        - Exchange API reliability
        """
        max_points = self.weights["execution"]
        score = 0.0

        long_exchange = data.get("long_exchange", "").lower()
        short_exchange = data.get("short_exchange", "").lower()
        symbol = data.get("symbol", "")
        position_size_usd = data.get("position_size_usd", 5000)  # Default $5000

        # Slippage component (0-12 points)
        # Use real slippage if available, otherwise estimate
        estimated_slippage = self._estimate_slippage(
            data, symbol, long_exchange, short_exchange, position_size_usd
        )
        slippage_ratio = 1 - min(
            estimated_slippage / self.thresholds["max_slippage"], 1.0
        )
        score += slippage_ratio * 12

        # Fee component (0-8 points) - Use actual exchange fees
        total_fees = self._calculate_total_fees(long_exchange, short_exchange)
        # Convert from decimal to percentage for comparison
        fee_pct = total_fees * 100
        fee_ratio = 1 - min(fee_pct / 0.1, 1.0)  # 0.1% = 10bps max
        score += fee_ratio * 8

        # Reliability component (0-5 points)
        reliable_exchanges = {"binance", "bybit", "okx", "hyperliquid"}
        exchanges = {long_exchange, short_exchange}

        if exchanges <= reliable_exchanges:
            score += 5
        elif exchanges & reliable_exchanges:
            score += 3
        else:
            score += 1

        return min(score, max_points)

    def _estimate_slippage(
        self,
        data: dict[str, Any],
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        position_size_usd: float,
    ) -> float:
        """
        Estimate slippage based on liquidity data or defaults.

        Returns slippage as a percentage (e.g., 0.1 = 0.1%)
        """
        # Check if pre-calculated slippage is provided
        if "estimated_slippage" in data:
            return data["estimated_slippage"]

        # Check liquidity data from cache
        liquidity = self._get_liquidity_data(symbol, long_exchange, short_exchange)

        if liquidity:
            # Calculate slippage from orderbook depth
            bid_depth = liquidity.get("bid_depth_usd", 0)
            ask_depth = liquidity.get("ask_depth_usd", 0)
            avg_depth = (bid_depth + ask_depth) / 2

            if avg_depth > 0:
                # Simple slippage model: impact proportional to size/depth
                impact_ratio = position_size_usd / avg_depth
                # Assume 1% impact per 100% of depth
                slippage = min(impact_ratio * 1.0, 2.0)  # Cap at 2%
                return slippage

        # Default slippage based on exchange tier
        tier1_exchanges = {"binance", "bybit", "okx"}
        exchanges = {long_exchange, short_exchange}

        if exchanges <= tier1_exchanges:
            return 0.05  # 5bps for major exchanges
        elif exchanges & tier1_exchanges:
            return 0.08  # 8bps mixed
        else:
            return 0.1  # 10bps for others

    def _calculate_total_fees(
        self,
        long_exchange: str,
        short_exchange: str,
    ) -> float:
        """
        Calculate total trading fees for both legs.

        Returns fees as a decimal (e.g., 0.0008 = 8bps)
        """
        # Get fees for each exchange
        long_fees = self._get_exchange_fees(long_exchange)
        short_fees = self._get_exchange_fees(short_exchange)

        # Use taker fees for market orders (most conservative)
        long_fee = long_fees.get("taker", 0.0005)
        short_fee = short_fees.get("taker", 0.0005)

        # Total fees = fees for both entry and exit on both legs
        # Entry: long + short, Exit: long + short = 4 fee events
        return (long_fee + short_fee) * 2

    def _get_exchange_fees(self, exchange: str) -> dict:
        """Get fee structure for an exchange."""
        exchange = exchange.lower()

        # Check cache first
        if exchange in self._fee_cache:
            return self._fee_cache[exchange]

        # Use defaults
        fees = self.DEFAULT_EXCHANGE_FEES.get(
            exchange,
            {"maker": 0.0002, "taker": 0.0005}  # Default fees
        )

        self._fee_cache[exchange] = fees
        return fees

    def _get_liquidity_data(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
    ) -> Optional[dict]:
        """Get liquidity data from cache if available."""
        cache_key = f"{symbol}:{long_exchange}:{short_exchange}"

        if cache_key in self._liquidity_cache:
            return self._liquidity_cache[cache_key]

        return None

    def _calculate_timing_score(self, data: dict[str, Any]) -> float:
        """
        Calculate timing score (0-15 points).

        Based on:
        - Time to next funding period (from actual funding schedule)
        - Funding rate trend direction
        - Optimal entry windows
        """
        max_points = self.weights["timing"]
        score = 0.0

        long_exchange = data.get("long_exchange", "").lower()
        short_exchange = data.get("short_exchange", "").lower()

        # Calculate hours to funding using actual schedules
        hours_to_funding = self._calculate_hours_to_funding(
            data, long_exchange, short_exchange
        )

        # Time to funding component (0-10 points)
        # Optimal entry depends on funding interval
        avg_interval = (
            self.FUNDING_INTERVALS.get(long_exchange, 8) +
            self.FUNDING_INTERVALS.get(short_exchange, 8)
        ) / 2

        # Scale optimal window to funding interval
        optimal_start = avg_interval * 0.375  # ~3h for 8h interval
        optimal_end = avg_interval * 0.75     # ~6h for 8h interval

        if optimal_start <= hours_to_funding <= optimal_end:
            score += 10  # Optimal window
        elif hours_to_funding >= avg_interval * 0.25 and hours_to_funding <= avg_interval * 0.875:
            score += 7  # Good window
        elif hours_to_funding >= avg_interval * 0.125:
            score += 4  # Acceptable
        else:
            score += 2  # Suboptimal (too close to funding)

        # Trend component (0-5 points)
        rate_trend = data.get("rate_trend", "stable")

        # Map trend strings to scores
        trend_scores = {
            "stable": 5,
            "rising": 4,  # Generally favorable for shorts
            "falling": 4,  # Generally favorable for longs
            "favorable": 4,
            "unfavorable": 1,
            "unknown": 3,
        }
        score += trend_scores.get(rate_trend, 3)

        return min(score, max_points)

    def _calculate_hours_to_funding(
        self,
        data: dict[str, Any],
        long_exchange: str,
        short_exchange: str,
    ) -> float:
        """
        Calculate hours to next funding based on exchange schedules.

        Returns the minimum hours to funding across both exchanges.
        """
        # Check if provided in data
        if "hours_to_funding" in data:
            return data["hours_to_funding"]

        # Check for next_funding_time in data
        next_funding_time = data.get("next_funding_time")
        if next_funding_time:
            if isinstance(next_funding_time, str):
                try:
                    next_funding_time = datetime.fromisoformat(
                        next_funding_time.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            if isinstance(next_funding_time, datetime):
                now = datetime.utcnow()
                if next_funding_time.tzinfo:
                    next_funding_time = next_funding_time.replace(tzinfo=None)
                delta = (next_funding_time - now).total_seconds() / 3600
                return max(delta, 0)

        # Estimate based on exchange funding intervals
        # Get the minimum interval (soonest next funding)
        long_interval = self.FUNDING_INTERVALS.get(long_exchange, 8)
        short_interval = self.FUNDING_INTERVALS.get(short_exchange, 8)

        # For estimation, assume we're at a random point in the cycle
        # Return half the minimum interval as expected time
        min_interval = min(long_interval, short_interval)
        return min_interval / 2

    def update_liquidity_cache(
        self,
        symbol: str,
        exchange: str,
        liquidity_data: dict,
    ) -> None:
        """Update liquidity cache with new data."""
        # Store by symbol and exchange
        for other_exchange in ["binance", "bybit", "okx", "hyperliquid", "dydx", "gate", "kucoin", "bitget"]:
            if other_exchange != exchange:
                key = f"{symbol}:{exchange}:{other_exchange}"
                self._liquidity_cache[key] = liquidity_data
                key = f"{symbol}:{other_exchange}:{exchange}"
                self._liquidity_cache[key] = liquidity_data

    def update_stability_cache(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        stability: float,
    ) -> None:
        """Update stability cache with historical variance."""
        key = f"{symbol}:{long_exchange}:{short_exchange}"
        self._stability_cache[key] = stability

    async def load_exchange_fees_from_db(self) -> None:
        """Load exchange fees from database configuration."""
        if not self._db_session_factory:
            logger.debug("No database session - using default fees")
            return

        try:
            from sqlalchemy import text
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT slug, perp_maker_fee, perp_taker_fee
                    FROM config.exchanges
                    WHERE is_enabled = true
                """))

                for row in result:
                    slug = row[0]
                    maker_fee = float(row[1]) if row[1] else 0.0002
                    taker_fee = float(row[2]) if row[2] else 0.0005
                    self._fee_cache[slug] = {
                        "maker": maker_fee,
                        "taker": taker_fee,
                    }

                logger.info(
                    "Loaded exchange fees from database",
                    exchanges=list(self._fee_cache.keys()),
                )
        except Exception as e:
            logger.warning("Failed to load exchange fees from DB", error=str(e))
