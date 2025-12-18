"""
Performance Attribution Module.

Provides detailed P&L breakdown and attribution analysis:
- Funding P&L vs Price P&L separation
- Per-exchange contribution analysis
- Per-symbol cohort analysis
- Win rate and edge calculation by UOS score range
- Time-based performance patterns
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.utils.config import get_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


class AttributionDimension(str, Enum):
    """Dimension for P&L attribution."""
    EXCHANGE = "exchange"
    SYMBOL = "symbol"
    UOS_SCORE = "uos_score"
    TIME_PERIOD = "time_period"
    FUNDING_VS_PRICE = "funding_vs_price"


@dataclass
class AttributionResult:
    """Result of attribution analysis."""
    dimension: AttributionDimension
    period_start: datetime
    period_end: datetime
    total_pnl: Decimal
    total_trades: int
    breakdown: list[dict[str, Any]]
    generated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CohortAnalysis:
    """Analysis of a cohort (e.g., trades in a UOS score range)."""
    cohort_name: str
    trade_count: int
    total_pnl: Decimal
    avg_pnl: Decimal
    win_rate: float
    avg_win: Decimal
    avg_loss: Decimal
    sharpe_estimate: float
    best_trade: Decimal
    worst_trade: Decimal


@dataclass
class TimePattern:
    """Time-based performance pattern."""
    hour_of_day: int
    day_of_week: int  # 0=Monday, 6=Sunday
    avg_pnl: Decimal
    trade_count: int
    win_rate: float


class PerformanceAttribution:
    """
    Analyzes and attributes trading performance across multiple dimensions.

    Provides insights into:
    - Which exchanges are most profitable
    - Which symbols perform best
    - How UOS score correlates with outcomes
    - Time-of-day and day-of-week patterns
    - Funding vs price P&L breakdown
    """

    def __init__(self, db_session_factory: Optional[Callable] = None):
        self._db_session_factory = db_session_factory or self._create_db_session_factory()

        # UOS score cohort boundaries
        self._score_cohorts = [
            (0, 60, "Low (0-60)"),
            (60, 70, "Medium-Low (60-70)"),
            (70, 80, "Medium (70-80)"),
            (80, 90, "Medium-High (80-90)"),
            (90, 100, "High (90-100)"),
        ]

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

    async def get_pnl_breakdown(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Get detailed P&L breakdown separating funding and price components.

        Returns:
            Dict with funding_pnl, price_pnl, total_pnl, and percentage breakdown
        """
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT
                        COALESCE(SUM(realized_pnl_funding), 0) as funding_pnl,
                        COALESCE(SUM(realized_pnl_price), 0) as price_pnl,
                        COALESCE(SUM(realized_pnl_funding + realized_pnl_price), 0) as total_pnl,
                        COUNT(*) as trade_count,
                        AVG(realized_pnl_funding + realized_pnl_price) as avg_pnl
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at BETWEEN :start AND :end
                """), {"start": start, "end": end})
                row = result.fetchone()

                if not row:
                    return self._empty_breakdown()

                funding_pnl = Decimal(str(row[0] or 0))
                price_pnl = Decimal(str(row[1] or 0))
                total_pnl = Decimal(str(row[2] or 0))
                trade_count = row[3] or 0
                avg_pnl = Decimal(str(row[4] or 0))

                # Calculate percentages
                if total_pnl != 0:
                    funding_pct = float(funding_pnl / abs(total_pnl) * 100)
                    price_pct = float(price_pnl / abs(total_pnl) * 100)
                else:
                    funding_pct = 0
                    price_pct = 0

                return {
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                    "funding_pnl": float(funding_pnl),
                    "price_pnl": float(price_pnl),
                    "total_pnl": float(total_pnl),
                    "funding_pct": funding_pct,
                    "price_pct": price_pct,
                    "trade_count": trade_count,
                    "avg_pnl_per_trade": float(avg_pnl),
                    "analysis": self._analyze_pnl_composition(funding_pnl, price_pnl),
                }

        except Exception as e:
            logger.error("Failed to get P&L breakdown", error=str(e))
            return self._empty_breakdown()

    def _empty_breakdown(self) -> dict[str, Any]:
        """Return empty breakdown structure."""
        return {
            "funding_pnl": 0,
            "price_pnl": 0,
            "total_pnl": 0,
            "funding_pct": 0,
            "price_pct": 0,
            "trade_count": 0,
            "avg_pnl_per_trade": 0,
            "analysis": "",
        }

    def _analyze_pnl_composition(self, funding: Decimal, price: Decimal) -> str:
        """Generate analysis text for P&L composition."""
        if funding > 0 and price > 0:
            return "Both funding and price components positive - ideal performance"
        elif funding > 0 > price:
            if funding > abs(price):
                return "Funding profits offsetting price losses - strategy working as designed"
            else:
                return "Price losses exceeding funding gains - review hedging effectiveness"
        elif price > 0 > funding:
            return "Price gains but negative funding - may indicate timing issues"
        elif funding < 0 and price < 0:
            return "Both components negative - urgent strategy review needed"
        else:
            return "Mixed performance - continue monitoring"

    async def get_exchange_attribution(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> AttributionResult:
        """
        Get P&L attribution by exchange.

        Shows which exchanges contribute most to profits/losses.
        """
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        try:
            async with self._db_session_factory() as db:
                # Get P&L by long exchange
                long_result = await db.execute(text("""
                    SELECT
                        long_exchange as exchange,
                        'long' as side,
                        COUNT(*) as trade_count,
                        SUM(realized_pnl_funding + realized_pnl_price) as total_pnl,
                        AVG(realized_pnl_funding + realized_pnl_price) as avg_pnl,
                        SUM(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at BETWEEN :start AND :end
                    GROUP BY long_exchange
                    ORDER BY total_pnl DESC
                """), {"start": start, "end": end})
                long_rows = long_result.fetchall()

                # Get P&L by short exchange
                short_result = await db.execute(text("""
                    SELECT
                        short_exchange as exchange,
                        'short' as side,
                        COUNT(*) as trade_count,
                        SUM(realized_pnl_funding + realized_pnl_price) as total_pnl,
                        AVG(realized_pnl_funding + realized_pnl_price) as avg_pnl,
                        SUM(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at BETWEEN :start AND :end
                    GROUP BY short_exchange
                    ORDER BY total_pnl DESC
                """), {"start": start, "end": end})
                short_rows = short_result.fetchall()

                # Combine by exchange
                exchange_data: dict[str, dict] = {}

                for row in long_rows:
                    exchange = row[0]
                    if exchange not in exchange_data:
                        exchange_data[exchange] = {
                            "exchange": exchange,
                            "long_trades": 0,
                            "short_trades": 0,
                            "long_pnl": 0,
                            "short_pnl": 0,
                            "total_pnl": 0,
                            "wins": 0,
                            "total_trades": 0,
                        }
                    exchange_data[exchange]["long_trades"] = row[2]
                    exchange_data[exchange]["long_pnl"] = float(row[3] or 0)
                    exchange_data[exchange]["wins"] += row[5]
                    exchange_data[exchange]["total_trades"] += row[2]

                for row in short_rows:
                    exchange = row[0]
                    if exchange not in exchange_data:
                        exchange_data[exchange] = {
                            "exchange": exchange,
                            "long_trades": 0,
                            "short_trades": 0,
                            "long_pnl": 0,
                            "short_pnl": 0,
                            "total_pnl": 0,
                            "wins": 0,
                            "total_trades": 0,
                        }
                    exchange_data[exchange]["short_trades"] = row[2]
                    exchange_data[exchange]["short_pnl"] = float(row[3] or 0)
                    exchange_data[exchange]["wins"] += row[5]
                    exchange_data[exchange]["total_trades"] += row[2]

                # Calculate totals and win rates
                breakdown = []
                total_pnl = Decimal("0")
                total_trades = 0

                for data in exchange_data.values():
                    data["total_pnl"] = data["long_pnl"] + data["short_pnl"]
                    data["win_rate"] = (
                        data["wins"] / data["total_trades"] * 100
                        if data["total_trades"] > 0 else 0
                    )
                    total_pnl += Decimal(str(data["total_pnl"]))
                    total_trades += data["total_trades"]
                    breakdown.append(data)

                # Sort by total P&L
                breakdown.sort(key=lambda x: x["total_pnl"], reverse=True)

                return AttributionResult(
                    dimension=AttributionDimension.EXCHANGE,
                    period_start=start,
                    period_end=end,
                    total_pnl=total_pnl,
                    total_trades=total_trades,
                    breakdown=breakdown,
                )

        except Exception as e:
            logger.error("Failed to get exchange attribution", error=str(e))
            return AttributionResult(
                dimension=AttributionDimension.EXCHANGE,
                period_start=start,
                period_end=end,
                total_pnl=Decimal("0"),
                total_trades=0,
                breakdown=[],
            )

    async def get_symbol_attribution(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
    ) -> AttributionResult:
        """Get P&L attribution by symbol."""
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT
                        symbol,
                        COUNT(*) as trade_count,
                        SUM(realized_pnl_funding + realized_pnl_price) as total_pnl,
                        SUM(realized_pnl_funding) as funding_pnl,
                        SUM(realized_pnl_price) as price_pnl,
                        AVG(realized_pnl_funding + realized_pnl_price) as avg_pnl,
                        SUM(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins,
                        AVG(total_capital_deployed) as avg_size
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at BETWEEN :start AND :end
                    GROUP BY symbol
                    ORDER BY total_pnl DESC
                    LIMIT :limit
                """), {"start": start, "end": end, "limit": limit})
                rows = result.fetchall()

                breakdown = []
                total_pnl = Decimal("0")
                total_trades = 0

                for row in rows:
                    trade_count = row[1]
                    wins = row[6]
                    data = {
                        "symbol": row[0],
                        "trade_count": trade_count,
                        "total_pnl": float(row[2] or 0),
                        "funding_pnl": float(row[3] or 0),
                        "price_pnl": float(row[4] or 0),
                        "avg_pnl": float(row[5] or 0),
                        "win_rate": wins / trade_count * 100 if trade_count > 0 else 0,
                        "avg_size_usd": float(row[7] or 0),
                    }
                    breakdown.append(data)
                    total_pnl += Decimal(str(row[2] or 0))
                    total_trades += trade_count

                return AttributionResult(
                    dimension=AttributionDimension.SYMBOL,
                    period_start=start,
                    period_end=end,
                    total_pnl=total_pnl,
                    total_trades=total_trades,
                    breakdown=breakdown,
                )

        except Exception as e:
            logger.error("Failed to get symbol attribution", error=str(e))
            return AttributionResult(
                dimension=AttributionDimension.SYMBOL,
                period_start=start,
                period_end=end,
                total_pnl=Decimal("0"),
                total_trades=0,
                breakdown=[],
            )

    async def get_uos_score_cohorts(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[CohortAnalysis]:
        """
        Analyze performance by UOS score cohorts.

        Helps identify optimal UOS score thresholds for trading.
        """
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        cohorts = []

        try:
            async with self._db_session_factory() as db:
                for min_score, max_score, name in self._score_cohorts:
                    result = await db.execute(text("""
                        SELECT
                            COUNT(*) as trade_count,
                            SUM(realized_pnl_funding + realized_pnl_price) as total_pnl,
                            AVG(realized_pnl_funding + realized_pnl_price) as avg_pnl,
                            SUM(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins,
                            AVG(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0
                                THEN (realized_pnl_funding + realized_pnl_price) ELSE NULL END) as avg_win,
                            AVG(CASE WHEN (realized_pnl_funding + realized_pnl_price) <= 0
                                THEN ABS(realized_pnl_funding + realized_pnl_price) ELSE NULL END) as avg_loss,
                            MAX(realized_pnl_funding + realized_pnl_price) as best_trade,
                            MIN(realized_pnl_funding + realized_pnl_price) as worst_trade,
                            STDDEV(realized_pnl_funding + realized_pnl_price) as pnl_stddev
                        FROM positions.active
                        WHERE status = 'closed'
                          AND closed_at BETWEEN :start AND :end
                          AND entry_score >= :min_score
                          AND entry_score < :max_score
                    """), {
                        "start": start,
                        "end": end,
                        "min_score": min_score,
                        "max_score": max_score,
                    })
                    row = result.fetchone()

                    if row and row[0] > 0:
                        trade_count = row[0]
                        total_pnl = Decimal(str(row[1] or 0))
                        avg_pnl = Decimal(str(row[2] or 0))
                        wins = row[3] or 0
                        avg_win = Decimal(str(row[4] or 0))
                        avg_loss = Decimal(str(row[5] or 0))
                        best_trade = Decimal(str(row[6] or 0))
                        worst_trade = Decimal(str(row[7] or 0))
                        stddev = float(row[8] or 1)

                        # Calculate Sharpe estimate
                        sharpe = float(avg_pnl) / stddev if stddev > 0 else 0

                        cohorts.append(CohortAnalysis(
                            cohort_name=name,
                            trade_count=trade_count,
                            total_pnl=total_pnl,
                            avg_pnl=avg_pnl,
                            win_rate=wins / trade_count * 100 if trade_count > 0 else 0,
                            avg_win=avg_win,
                            avg_loss=avg_loss,
                            sharpe_estimate=sharpe,
                            best_trade=best_trade,
                            worst_trade=worst_trade,
                        ))
                    else:
                        cohorts.append(CohortAnalysis(
                            cohort_name=name,
                            trade_count=0,
                            total_pnl=Decimal("0"),
                            avg_pnl=Decimal("0"),
                            win_rate=0,
                            avg_win=Decimal("0"),
                            avg_loss=Decimal("0"),
                            sharpe_estimate=0,
                            best_trade=Decimal("0"),
                            worst_trade=Decimal("0"),
                        ))

        except Exception as e:
            logger.error("Failed to analyze UOS score cohorts", error=str(e))

        return cohorts

    async def get_time_patterns(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[TimePattern]:
        """
        Analyze performance patterns by time of day and day of week.

        Useful for identifying optimal trading windows.
        """
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        patterns = []

        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT
                        EXTRACT(HOUR FROM opened_at) as hour,
                        EXTRACT(DOW FROM opened_at) as dow,
                        COUNT(*) as trade_count,
                        AVG(realized_pnl_funding + realized_pnl_price) as avg_pnl,
                        SUM(CASE WHEN (realized_pnl_funding + realized_pnl_price) > 0 THEN 1 ELSE 0 END) as wins
                    FROM positions.active
                    WHERE status = 'closed'
                      AND closed_at BETWEEN :start AND :end
                    GROUP BY EXTRACT(HOUR FROM opened_at), EXTRACT(DOW FROM opened_at)
                    ORDER BY avg_pnl DESC
                """), {"start": start, "end": end})
                rows = result.fetchall()

                for row in rows:
                    trade_count = row[2]
                    wins = row[4]
                    patterns.append(TimePattern(
                        hour_of_day=int(row[0]),
                        day_of_week=int(row[1]),
                        trade_count=trade_count,
                        avg_pnl=Decimal(str(row[3] or 0)),
                        win_rate=wins / trade_count * 100 if trade_count > 0 else 0,
                    ))

        except Exception as e:
            logger.error("Failed to analyze time patterns", error=str(e))

        return patterns

    async def get_optimal_score_threshold(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Determine optimal UOS score threshold based on historical performance.

        Returns the score threshold that maximizes risk-adjusted returns.
        """
        cohorts = await self.get_uos_score_cohorts(start_date, end_date)

        if not cohorts:
            return {
                "recommended_threshold": 75,
                "reason": "Insufficient data",
            }

        # Find cohort with best Sharpe ratio that has enough trades
        best_cohort = None
        best_sharpe = float("-inf")

        for cohort in cohorts:
            if cohort.trade_count >= 10 and cohort.sharpe_estimate > best_sharpe:
                best_sharpe = cohort.sharpe_estimate
                best_cohort = cohort

        if best_cohort:
            # Extract threshold from cohort name
            recommended = 70  # Default
            if "90-100" in best_cohort.cohort_name:
                recommended = 90
            elif "80-90" in best_cohort.cohort_name:
                recommended = 80
            elif "70-80" in best_cohort.cohort_name:
                recommended = 70
            elif "60-70" in best_cohort.cohort_name:
                recommended = 60

            return {
                "recommended_threshold": recommended,
                "best_cohort": best_cohort.cohort_name,
                "sharpe_estimate": best_cohort.sharpe_estimate,
                "win_rate": best_cohort.win_rate,
                "avg_pnl": float(best_cohort.avg_pnl),
                "trade_count": best_cohort.trade_count,
                "reason": f"Based on {best_cohort.trade_count} trades with {best_cohort.win_rate:.1f}% win rate",
            }

        return {
            "recommended_threshold": 75,
            "reason": "Insufficient data for optimization",
        }

    async def get_full_attribution_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Generate comprehensive attribution report."""
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        # Run all analyses
        pnl_breakdown = await self.get_pnl_breakdown(start, end)
        exchange_attr = await self.get_exchange_attribution(start, end)
        symbol_attr = await self.get_symbol_attribution(start, end)
        uos_cohorts = await self.get_uos_score_cohorts(start, end)
        time_patterns = await self.get_time_patterns(start, end)
        optimal_threshold = await self.get_optimal_score_threshold(start, end)

        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "pnl_breakdown": pnl_breakdown,
            "exchange_attribution": {
                "total_pnl": float(exchange_attr.total_pnl),
                "total_trades": exchange_attr.total_trades,
                "breakdown": exchange_attr.breakdown,
            },
            "symbol_attribution": {
                "total_pnl": float(symbol_attr.total_pnl),
                "total_trades": symbol_attr.total_trades,
                "breakdown": symbol_attr.breakdown,
            },
            "uos_score_cohorts": [
                {
                    "cohort": c.cohort_name,
                    "trade_count": c.trade_count,
                    "total_pnl": float(c.total_pnl),
                    "avg_pnl": float(c.avg_pnl),
                    "win_rate": c.win_rate,
                    "sharpe": c.sharpe_estimate,
                }
                for c in uos_cohorts
            ],
            "time_patterns": {
                "best_hours": [
                    {"hour": p.hour_of_day, "avg_pnl": float(p.avg_pnl), "trades": p.trade_count}
                    for p in sorted(time_patterns, key=lambda x: x.avg_pnl, reverse=True)[:5]
                ],
                "worst_hours": [
                    {"hour": p.hour_of_day, "avg_pnl": float(p.avg_pnl), "trades": p.trade_count}
                    for p in sorted(time_patterns, key=lambda x: x.avg_pnl)[:5]
                ],
            },
            "optimal_threshold": optimal_threshold,
            "generated_at": datetime.utcnow().isoformat(),
        }


# Singleton instance
performance_attribution = PerformanceAttribution()


# Convenience functions
async def get_pnl_breakdown(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict[str, Any]:
    """Get P&L breakdown."""
    return await performance_attribution.get_pnl_breakdown(start_date, end_date)


async def get_exchange_attribution(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AttributionResult:
    """Get exchange attribution."""
    return await performance_attribution.get_exchange_attribution(start_date, end_date)


async def get_full_report(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict[str, Any]:
    """Get full attribution report."""
    return await performance_attribution.get_full_attribution_report(start_date, end_date)
