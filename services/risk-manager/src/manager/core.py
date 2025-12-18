"""
Risk Manager Core - Enforces risk limits and monitors exposure.

This module provides real-time risk monitoring and enforcement:
- Tracks exposure across all exchanges and positions
- Enforces position and portfolio risk limits
- Monitors drawdown and triggers circuit breakers
- Validates trades before execution
- Generates risk alerts and broadcasts to UI
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.events.risk import (
    CircuitBreakerEvent,
    RiskAlertEvent,
    RiskLimitBreachEvent,
    RiskLimitWarningEvent,
    RiskModeChangedEvent,
    RiskStateUpdatedEvent,
)
from shared.models.risk import RiskAlertSeverity, RiskAlertType, RiskLimits, RiskMode
from shared.utils.config import get_settings
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.system_state import SystemStateManager

logger = get_logger(__name__)


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RiskAlert(BaseModel):
    id: str
    level: AlertLevel
    alert_type: RiskAlertType
    message: str
    metric: str
    value: float
    threshold: float
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    timestamp: datetime
    acknowledged: bool = False


class TrackedPosition(BaseModel):
    """Internal position tracking for exposure calculation."""

    position_id: str
    opportunity_id: str
    symbol: str
    size_usd: Decimal
    primary_exchange: str
    hedge_exchange: str
    opened_at: datetime


class RiskManager:
    """
    Manages risk limits, exposure tracking, and circuit breakers.

    Listens to position events and maintains real-time exposure state.
    Validates trades before execution and enforces risk limits.
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
        self._circuit_breaker_active = False
        self._alerts: list[RiskAlert] = []

        # System state manager for coordinated control
        self.state_manager: Optional[SystemStateManager] = None

        # Risk limits (loaded from DB on start)
        self._limits = RiskLimits()
        self._risk_mode = RiskMode.STANDARD

        # Current exposure state
        self._state = {
            "total_exposure_usd": Decimal("0"),
            "exchange_exposure": {},  # exchange -> Decimal
            "symbol_exposure": {},  # symbol -> Decimal
            "position_count": 0,
            "current_drawdown_pct": Decimal("0"),
            "peak_equity": Decimal("0"),
            "current_equity": Decimal("0"),
            "total_capital_usd": Decimal("0"),
            # Advanced risk metrics
            "var_95": Decimal("0"),  # Value at Risk (95% confidence)
            "var_99": Decimal("0"),  # Value at Risk (99% confidence)
            "cvar_95": Decimal("0"),  # Conditional VaR (95% confidence)
            "cvar_99": Decimal("0"),  # Conditional VaR (99% confidence)
            "market_volatility": Decimal("0"),  # Current market volatility estimate
        }

        # Historical P&L for VaR calculation
        self._pnl_history: list[Decimal] = []
        self._max_pnl_history = 252  # ~1 year of daily returns

        # Dynamic limit adjustment
        self._base_limits: Optional[RiskLimits] = None  # Original limits
        self._volatility_regime = "normal"  # "low", "normal", "high"
        self._high_vol_threshold = Decimal("0.03")  # 3% daily volatility = high
        self._low_vol_threshold = Decimal("0.01")  # 1% daily volatility = low

        # Active positions for tracking
        self._positions: dict[str, TrackedPosition] = {}

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
        """Start the risk manager."""
        logger.info("Starting Risk Manager")
        self._running = True

        # Initialize system state manager
        self.state_manager = SystemStateManager(self.redis, "risk-manager")
        await self.state_manager.start()

        # Load risk limits from database
        await self._load_limits()

        # Load initial capital from database
        await self._load_total_capital()

        # Recover position state from Redis
        await self._recover_position_state()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._listen_position_events()),
            asyncio.create_task(self._listen_balance_events()),
            asyncio.create_task(self._monitor_drawdown()),
            asyncio.create_task(self._check_limits_periodic()),
            asyncio.create_task(self._publish_state_periodic()),
            asyncio.create_task(self._calculate_risk_metrics()),
            asyncio.create_task(self._adjust_limits_for_volatility()),
        ]

        logger.info(
            "Risk Manager started",
            total_exposure=float(self._state["total_exposure_usd"]),
            position_count=self._state["position_count"],
            risk_mode=self._risk_mode.value,
        )

    async def stop(self) -> None:
        """Stop the risk manager."""
        logger.info("Stopping Risk Manager")
        self._running = False

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.state_manager:
            await self.state_manager.stop()

        logger.info("Risk Manager stopped")

    # ==================== Initialization ====================

    async def _load_limits(self) -> None:
        """Load risk limits from database."""
        try:
            async with self._db_session_factory() as db:
                # Try new schema first (with data_type and category columns)
                try:
                    query = text("""
                        SELECT key, value, data_type
                        FROM config.system_settings
                        WHERE category = 'risk'
                    """)
                    result = await db.execute(query)
                    rows = result.fetchall()

                    for key, value, data_type in rows:
                        if hasattr(self._limits, key):
                            if data_type == "decimal":
                                setattr(self._limits, key, Decimal(value))
                            elif data_type == "integer":
                                setattr(self._limits, key, int(value))
                            elif data_type == "float":
                                setattr(self._limits, key, float(value))

                except Exception:
                    # Fall back to old schema (just key and value as JSONB)
                    query = text("""
                        SELECT key, value
                        FROM config.system_settings
                        WHERE key LIKE 'risk_%' OR key LIKE 'max_%' OR key LIKE 'min_%'
                    """)
                    result = await db.execute(query)
                    rows = result.fetchall()

                    for key, value in rows:
                        if hasattr(self._limits, key):
                            # value is JSONB, extract the actual value
                            actual_value = value if not isinstance(value, dict) else value.get("value", value)
                            if isinstance(actual_value, (int, float)):
                                setattr(self._limits, key, Decimal(str(actual_value)))

                logger.info("Loaded risk limits from database")

        except Exception as e:
            logger.warning(f"Failed to load risk limits from DB, using defaults", error=str(e))

    async def _load_total_capital(self) -> None:
        """Load total capital from exchange balances."""
        try:
            # Get cached balance data from Redis
            balance_json = await self.redis.get("nexus:balances:total")
            if balance_json:
                data = json.loads(balance_json)
                self._state["total_capital_usd"] = Decimal(str(data.get("total_usd", 0)))
                self._state["current_equity"] = self._state["total_capital_usd"]
                self._state["peak_equity"] = max(
                    self._state["peak_equity"],
                    self._state["current_equity"],
                )
                logger.info(
                    f"Loaded total capital",
                    capital=float(self._state["total_capital_usd"]),
                )
        except Exception as e:
            logger.warning(f"Failed to load capital", error=str(e))

    async def _recover_position_state(self) -> None:
        """Recover position tracking from Redis cache."""
        try:
            # Get active positions from Redis
            positions_json = await self.redis.get("nexus:positions:active")
            if positions_json:
                positions = json.loads(positions_json)
                for pos in positions:
                    position_id = pos.get("position_id") or pos.get("id")
                    if position_id:
                        tracked = TrackedPosition(
                            position_id=str(position_id),
                            opportunity_id=str(pos.get("opportunity_id", "")),
                            symbol=pos.get("symbol", ""),
                            size_usd=Decimal(str(pos.get("size_usd", 0))),
                            primary_exchange=pos.get("primary_exchange", pos.get("long_exchange", "")),
                            hedge_exchange=pos.get("hedge_exchange", pos.get("short_exchange", "")),
                            opened_at=datetime.fromisoformat(pos.get("opened_at", datetime.utcnow().isoformat())),
                        )
                        self._positions[tracked.position_id] = tracked

                # Recalculate exposure from recovered positions
                self._recalculate_exposure()
                logger.info(
                    f"Recovered position state",
                    positions=len(self._positions),
                    exposure=float(self._state["total_exposure_usd"]),
                )

        except Exception as e:
            logger.warning(f"Failed to recover position state", error=str(e))

    def _recalculate_exposure(self) -> None:
        """Recalculate all exposure from tracked positions."""
        total = Decimal("0")
        exchange_exp: dict[str, Decimal] = {}
        symbol_exp: dict[str, Decimal] = {}

        for pos in self._positions.values():
            # Each leg contributes to exposure
            leg_size = pos.size_usd / 2

            # Total exposure is the position size (both legs combined represent one position)
            total += pos.size_usd

            # Per-exchange exposure
            exchange_exp[pos.primary_exchange] = exchange_exp.get(
                pos.primary_exchange, Decimal("0")
            ) + leg_size
            exchange_exp[pos.hedge_exchange] = exchange_exp.get(
                pos.hedge_exchange, Decimal("0")
            ) + leg_size

            # Per-symbol exposure
            symbol_exp[pos.symbol] = symbol_exp.get(
                pos.symbol, Decimal("0")
            ) + pos.size_usd

        self._state["total_exposure_usd"] = total
        self._state["exchange_exposure"] = exchange_exp
        self._state["symbol_exposure"] = symbol_exp
        self._state["position_count"] = len(self._positions)

    # ==================== Event Listeners ====================

    async def _listen_position_events(self) -> None:
        """Listen for position events to track exposure."""
        channels = [
            "nexus:position:opened",
            "nexus:position:closed",
            "nexus:position:opening",
            "nexus:position:closing",
        ]

        async def handle_event(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message
                await self._handle_position_event(channel, data)
            except Exception as e:
                logger.error("Failed to process position event", error=str(e))

        try:
            for channel in channels:
                await self.redis.subscribe(channel, handle_event)

            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in position event listener", error=str(e))

    async def _handle_position_event(self, channel: str, data: dict[str, Any]) -> None:
        """Handle position event and update exposure tracking."""
        event_type = channel.split(":")[-1]  # opened, closed, opening, closing

        logger.info(f"Processing position event", event_type=event_type, data=data)

        if event_type == "opened":
            await self._on_position_opened(data)
        elif event_type == "closed":
            await self._on_position_closed(data)
        elif event_type == "opening":
            # Reserve exposure for pending position
            await self._on_position_opening(data)

        # Publish activity for UI
        await self._publish_activity(
            f"position_{event_type}",
            f"Position {event_type}: {data.get('symbol', 'unknown')}",
            data,
        )

    async def _on_position_opened(self, data: dict[str, Any]) -> None:
        """Track newly opened position."""
        position_id = str(data.get("position_id", ""))
        if not position_id:
            return

        # Create tracked position
        tracked = TrackedPosition(
            position_id=position_id,
            opportunity_id=str(data.get("opportunity_id", "")),
            symbol=data.get("symbol", ""),
            size_usd=Decimal(str(data.get("size_usd", 0))),
            primary_exchange=data.get("primary_exchange", data.get("long_exchange", "")),
            hedge_exchange=data.get("hedge_exchange", data.get("short_exchange", "")),
            opened_at=datetime.utcnow(),
        )

        self._positions[position_id] = tracked
        self._recalculate_exposure()

        # Cache state in Redis
        await self._cache_exposure_state()

        logger.info(
            f"Position opened - exposure updated",
            position_id=position_id,
            size_usd=float(tracked.size_usd),
            total_exposure=float(self._state["total_exposure_usd"]),
        )

        # Check if exposure is approaching limits
        await self._check_exposure_limits()

    async def _on_position_closed(self, data: dict[str, Any]) -> None:
        """Remove closed position from tracking."""
        position_id = str(data.get("position_id", ""))
        if position_id and position_id in self._positions:
            closed_pos = self._positions.pop(position_id)
            self._recalculate_exposure()

            # Cache state in Redis
            await self._cache_exposure_state()

            logger.info(
                f"Position closed - exposure reduced",
                position_id=position_id,
                released_usd=float(closed_pos.size_usd),
                total_exposure=float(self._state["total_exposure_usd"]),
            )

    async def _on_position_opening(self, data: dict[str, Any]) -> None:
        """Handle position opening - reserve exposure."""
        # For now just log - actual tracking happens on opened event
        logger.debug(
            f"Position opening",
            opportunity_id=data.get("opportunity_id"),
            size_usd=data.get("size_usd"),
        )

    async def _listen_balance_events(self) -> None:
        """Listen for balance updates to track equity."""
        async def handle_balance(channel: str, message: str):
            try:
                data = json.loads(message) if isinstance(message, str) else message
                await self._update_equity(data)
            except Exception as e:
                logger.error("Failed to process balance event", error=str(e))

        try:
            await self.redis.subscribe("nexus:balances:updated", handle_balance)
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in balance event listener", error=str(e))

    async def _update_equity(self, data: dict[str, Any]) -> None:
        """Update equity tracking for drawdown calculation."""
        total_usd = Decimal(str(data.get("total_usd", 0)))
        if total_usd > 0:
            old_equity = self._state["current_equity"]
            self._state["current_equity"] = total_usd
            self._state["total_capital_usd"] = total_usd

            # Update peak equity
            if total_usd > self._state["peak_equity"]:
                self._state["peak_equity"] = total_usd

            # Log significant changes
            if old_equity > 0:
                change_pct = (total_usd - old_equity) / old_equity * 100
                if abs(change_pct) > Decimal("0.5"):
                    logger.info(
                        f"Equity changed",
                        old=float(old_equity),
                        new=float(total_usd),
                        change_pct=float(change_pct),
                    )

    # ==================== Monitoring Tasks ====================

    async def _monitor_drawdown(self) -> None:
        """Monitor portfolio drawdown continuously."""
        while self._running:
            try:
                peak = self._state["peak_equity"]
                current = self._state["current_equity"]

                if peak > 0:
                    drawdown = (peak - current) / peak * 100
                    self._state["current_drawdown_pct"] = drawdown

                    max_dd = float(self._limits.max_drawdown_pct)

                    # Warning at 75% of limit
                    if drawdown >= Decimal(str(max_dd * 0.75)) and drawdown < Decimal(str(max_dd)):
                        await self._create_alert(
                            AlertLevel.WARNING,
                            RiskAlertType.DRAWDOWN,
                            f"Drawdown approaching limit: {float(drawdown):.2f}%",
                            "drawdown",
                            float(drawdown),
                            max_dd,
                        )

                    # Critical at limit
                    if drawdown >= Decimal(str(max_dd)):
                        await self._create_alert(
                            AlertLevel.CRITICAL,
                            RiskAlertType.DRAWDOWN,
                            f"Drawdown exceeds limit: {float(drawdown):.2f}%",
                            "drawdown",
                            float(drawdown),
                            max_dd,
                        )
                        await self.activate_circuit_breaker("max_drawdown_exceeded")

            except Exception as e:
                logger.error("Error monitoring drawdown", error=str(e))

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _check_limits_periodic(self) -> None:
        """Periodic limit checking."""
        while self._running:
            try:
                await self._check_exposure_limits()
            except Exception as e:
                logger.error("Error checking limits", error=str(e))
            await asyncio.sleep(60)  # Check every minute

    async def _check_exposure_limits(self) -> None:
        """Check if any exposure limits are being approached or breached."""
        total_exp = self._state["total_exposure_usd"]
        capital = self._state["total_capital_usd"]

        if capital <= 0:
            return

        # Check gross exposure percentage
        gross_exposure_pct = total_exp / capital * 100
        max_gross = float(self._limits.max_gross_exposure_pct)

        if gross_exposure_pct >= Decimal(str(max_gross)):
            await self._create_alert(
                AlertLevel.CRITICAL,
                RiskAlertType.CONCENTRATION,
                f"Gross exposure at limit: {float(gross_exposure_pct):.1f}%",
                "gross_exposure",
                float(gross_exposure_pct),
                max_gross,
            )
        elif gross_exposure_pct >= Decimal(str(max_gross * 0.8)):
            await self._create_alert(
                AlertLevel.WARNING,
                RiskAlertType.CONCENTRATION,
                f"Gross exposure approaching limit: {float(gross_exposure_pct):.1f}%",
                "gross_exposure",
                float(gross_exposure_pct),
                max_gross,
            )

        # Check per-exchange exposure
        max_venue_pct = float(self._limits.max_venue_exposure_pct)
        for exchange, exp in self._state["exchange_exposure"].items():
            venue_pct = float(exp / capital * 100) if capital > 0 else 0
            if venue_pct >= max_venue_pct:
                await self._create_alert(
                    AlertLevel.WARNING,
                    RiskAlertType.VENUE_EXPOSURE,
                    f"{exchange} exposure at limit: {venue_pct:.1f}%",
                    "venue_exposure",
                    venue_pct,
                    max_venue_pct,
                    exchange=exchange,
                )

    async def _publish_state_periodic(self) -> None:
        """Periodically publish risk state to Redis for dashboard."""
        while self._running:
            try:
                await self._cache_exposure_state()
                await self._publish_risk_state_event()
            except Exception as e:
                logger.error("Error publishing state", error=str(e))
            await asyncio.sleep(10)  # Every 10 seconds

    async def _calculate_risk_metrics(self) -> None:
        """Calculate VaR, CVaR, and other advanced risk metrics."""
        while self._running:
            try:
                # Record current P&L for VaR calculation
                await self._record_pnl_snapshot()

                if len(self._pnl_history) >= 20:  # Need minimum data
                    # Calculate VaR at 95% and 99% confidence
                    self._state["var_95"] = self._calculate_var(confidence=0.95)
                    self._state["var_99"] = self._calculate_var(confidence=0.99)

                    # Calculate CVaR (Expected Shortfall)
                    self._state["cvar_95"] = self._calculate_cvar(confidence=0.95)
                    self._state["cvar_99"] = self._calculate_cvar(confidence=0.99)

                    # Calculate market volatility
                    self._state["market_volatility"] = self._calculate_market_volatility()

                    logger.debug(
                        "Risk metrics updated",
                        var_95=float(self._state["var_95"]),
                        cvar_95=float(self._state["cvar_95"]),
                        volatility=float(self._state["market_volatility"]),
                    )

                    # Alert if VaR exceeds threshold
                    capital = self._state["total_capital_usd"]
                    if capital > 0:
                        var_pct = self._state["var_95"] / capital * 100
                        if var_pct > Decimal("5"):  # VaR > 5% of capital
                            await self._create_alert(
                                AlertLevel.WARNING,
                                RiskAlertType.DRAWDOWN,
                                f"VaR(95%) at {float(var_pct):.2f}% of capital",
                                "var_95",
                                float(self._state["var_95"]),
                                float(capital * Decimal("0.05")),
                            )

            except Exception as e:
                logger.error("Error calculating risk metrics", error=str(e))

            await asyncio.sleep(300)  # Calculate every 5 minutes

    async def _record_pnl_snapshot(self) -> None:
        """Record current P&L for historical VaR calculation."""
        try:
            # Get total unrealized + realized P&L from positions
            async with self._db_session_factory() as db:
                query = text("""
                    SELECT
                        COALESCE(SUM(unrealized_pnl), 0) as unrealized,
                        COALESCE(SUM(realized_pnl_funding + realized_pnl_price), 0) as realized
                    FROM positions.active
                    WHERE status = 'active'
                """)
                result = await db.execute(query)
                row = result.fetchone()

                if row:
                    total_pnl = Decimal(str(row[0])) + Decimal(str(row[1]))
                    self._pnl_history.append(total_pnl)

                    # Trim to max history
                    if len(self._pnl_history) > self._max_pnl_history:
                        self._pnl_history = self._pnl_history[-self._max_pnl_history:]

        except Exception as e:
            logger.warning("Failed to record P&L snapshot", error=str(e))

    def _calculate_var(self, confidence: float = 0.95) -> Decimal:
        """
        Calculate Value at Risk using historical simulation.

        VaR represents the maximum expected loss at the given confidence level.
        E.g., 95% VaR means we expect losses to not exceed this value 95% of the time.
        """
        if len(self._pnl_history) < 20:
            return Decimal("0")

        # Calculate returns (P&L changes)
        returns = []
        for i in range(1, len(self._pnl_history)):
            prev = self._pnl_history[i - 1]
            curr = self._pnl_history[i]
            if prev != 0:
                returns.append(float((curr - prev) / abs(prev)))
            else:
                returns.append(float(curr))

        if not returns:
            return Decimal("0")

        # Sort returns (worst to best)
        sorted_returns = sorted(returns)

        # Find the percentile cutoff
        index = int((1 - confidence) * len(sorted_returns))
        index = max(0, min(index, len(sorted_returns) - 1))

        # VaR is the negative of the percentile (loss is negative)
        var_pct = sorted_returns[index]

        # Scale to current exposure
        exposure = float(self._state["total_exposure_usd"])
        var_usd = abs(var_pct) * exposure

        return Decimal(str(round(var_usd, 2)))

    def _calculate_cvar(self, confidence: float = 0.95) -> Decimal:
        """
        Calculate Conditional VaR (Expected Shortfall).

        CVaR is the expected loss given that the loss exceeds VaR.
        It provides a measure of tail risk.
        """
        if len(self._pnl_history) < 20:
            return Decimal("0")

        # Calculate returns
        returns = []
        for i in range(1, len(self._pnl_history)):
            prev = self._pnl_history[i - 1]
            curr = self._pnl_history[i]
            if prev != 0:
                returns.append(float((curr - prev) / abs(prev)))
            else:
                returns.append(float(curr))

        if not returns:
            return Decimal("0")

        # Sort returns (worst to best)
        sorted_returns = sorted(returns)

        # Find the cutoff index for VaR
        cutoff_index = int((1 - confidence) * len(sorted_returns))
        cutoff_index = max(1, cutoff_index)

        # CVaR is the average of all returns worse than VaR
        tail_returns = sorted_returns[:cutoff_index]
        if not tail_returns:
            return Decimal("0")

        avg_tail_return = sum(tail_returns) / len(tail_returns)

        # Scale to current exposure
        exposure = float(self._state["total_exposure_usd"])
        cvar_usd = abs(avg_tail_return) * exposure

        return Decimal(str(round(cvar_usd, 2)))

    def _calculate_market_volatility(self) -> Decimal:
        """
        Calculate current market volatility from P&L history.

        Returns annualized volatility estimate.
        """
        if len(self._pnl_history) < 10:
            return Decimal("0")

        # Calculate returns
        returns = []
        for i in range(1, len(self._pnl_history)):
            prev = self._pnl_history[i - 1]
            curr = self._pnl_history[i]
            if prev != 0:
                returns.append(float((curr - prev) / abs(prev)))

        if not returns:
            return Decimal("0")

        # Calculate standard deviation
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5

        # Annualize (assuming 5-minute samples, ~288 per day, ~252 trading days)
        # For simplicity, we'll return the raw volatility
        return Decimal(str(round(std_dev, 6)))

    async def _adjust_limits_for_volatility(self) -> None:
        """Dynamically adjust risk limits based on market volatility."""
        while self._running:
            try:
                volatility = self._state["market_volatility"]

                # Store base limits on first run
                if self._base_limits is None:
                    self._base_limits = RiskLimits(
                        max_position_size_usd=self._limits.max_position_size_usd,
                        max_position_size_pct=self._limits.max_position_size_pct,
                        max_gross_exposure_pct=self._limits.max_gross_exposure_pct,
                        max_venue_exposure_pct=self._limits.max_venue_exposure_pct,
                        max_asset_exposure_pct=self._limits.max_asset_exposure_pct,
                        max_drawdown_pct=self._limits.max_drawdown_pct,
                        max_leverage=self._limits.max_leverage,
                    )

                # Determine volatility regime
                old_regime = self._volatility_regime
                if volatility >= self._high_vol_threshold:
                    self._volatility_regime = "high"
                elif volatility <= self._low_vol_threshold:
                    self._volatility_regime = "low"
                else:
                    self._volatility_regime = "normal"

                # Adjust limits based on regime
                if self._volatility_regime == "high":
                    # Reduce limits in high volatility
                    self._limits.max_position_size_usd = self._base_limits.max_position_size_usd * Decimal("0.5")
                    self._limits.max_position_size_pct = self._base_limits.max_position_size_pct * Decimal("0.5")
                    self._limits.max_gross_exposure_pct = self._base_limits.max_gross_exposure_pct * Decimal("0.6")

                elif self._volatility_regime == "low":
                    # Can be slightly more aggressive in low volatility
                    self._limits.max_position_size_usd = self._base_limits.max_position_size_usd * Decimal("1.2")
                    self._limits.max_position_size_pct = self._base_limits.max_position_size_pct * Decimal("1.1")
                    self._limits.max_gross_exposure_pct = self._base_limits.max_gross_exposure_pct

                else:  # normal
                    # Use base limits
                    self._limits.max_position_size_usd = self._base_limits.max_position_size_usd
                    self._limits.max_position_size_pct = self._base_limits.max_position_size_pct
                    self._limits.max_gross_exposure_pct = self._base_limits.max_gross_exposure_pct

                # Log regime change
                if old_regime != self._volatility_regime:
                    logger.info(
                        "Volatility regime changed",
                        old_regime=old_regime,
                        new_regime=self._volatility_regime,
                        volatility=float(volatility),
                    )

                    await self._publish_activity(
                        "volatility_regime_changed",
                        f"Risk limits adjusted: {old_regime} → {self._volatility_regime} volatility",
                        {
                            "old_regime": old_regime,
                            "new_regime": self._volatility_regime,
                            "volatility": float(volatility),
                            "new_max_position_usd": float(self._limits.max_position_size_usd),
                            "new_max_gross_exposure_pct": float(self._limits.max_gross_exposure_pct),
                        },
                        level="warning" if self._volatility_regime == "high" else "info",
                    )

            except Exception as e:
                logger.error("Error adjusting limits for volatility", error=str(e))

            await asyncio.sleep(300)  # Check every 5 minutes

    async def _cache_exposure_state(self) -> None:
        """Cache current exposure state in Redis."""
        state = {
            "total_exposure_usd": str(self._state["total_exposure_usd"]),
            "exchange_exposure": {
                k: str(v) for k, v in self._state["exchange_exposure"].items()
            },
            "symbol_exposure": {
                k: str(v) for k, v in self._state["symbol_exposure"].items()
            },
            "position_count": self._state["position_count"],
            "current_drawdown_pct": str(self._state["current_drawdown_pct"]),
            "total_capital_usd": str(self._state["total_capital_usd"]),
            "circuit_breaker_active": self._circuit_breaker_active,
            "risk_mode": self._risk_mode.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        await self.redis.set("nexus:risk:state", json.dumps(state))

    async def _publish_risk_state_event(self) -> None:
        """Publish risk state update event."""
        capital = self._state["total_capital_usd"]
        exposure = self._state["total_exposure_usd"]

        event = RiskStateUpdatedEvent(
            total_exposure_usd=exposure,
            gross_exposure_pct=(exposure / capital * 100) if capital > 0 else Decimal("0"),
            current_drawdown_pct=self._state["current_drawdown_pct"],
            positions_healthy=len([p for p in self._positions.values()]),
            positions_at_risk=0,  # TODO: Track unhealthy positions
        )
        await self.redis.publish("nexus:risk:state_updated", event.model_dump_json())

    # ==================== Trade Validation ====================

    async def validate_trade(
        self,
        opportunity_id: str,
        position_size_usd: float,
        long_exchange: str,
        short_exchange: str,
        symbol: str = "",
    ) -> dict[str, Any]:
        """
        Validate a trade against risk limits.

        Returns:
            dict with 'approved', 'reason', 'max_allowed_size', 'warnings'
        """
        result = {
            "approved": False,
            "reason": "",
            "max_allowed_size": 0.0,
            "warnings": [],
        }

        # Check circuit breaker
        if self._circuit_breaker_active:
            result["reason"] = "Circuit breaker active - no new positions allowed"
            return result

        # Check system state
        if self.state_manager and not self.state_manager.should_open_positions():
            result["reason"] = "System not accepting new positions"
            return result

        # Check risk mode
        if self._risk_mode == RiskMode.EMERGENCY:
            result["reason"] = "Emergency mode active - no new positions"
            return result

        position_size = Decimal(str(position_size_usd))
        capital = self._state["total_capital_usd"]
        current_exposure = self._state["total_exposure_usd"]

        # Check position size limit
        max_pos = self._limits.max_position_size_usd
        if position_size > max_pos:
            result["reason"] = f"Position size ${position_size} exceeds max ${max_pos}"
            result["max_allowed_size"] = float(max_pos)
            return result

        # Check position size as percentage of capital
        if capital > 0:
            pos_pct = position_size / capital * 100
            if pos_pct > self._limits.max_position_size_pct:
                max_allowed = capital * self._limits.max_position_size_pct / 100
                result["reason"] = f"Position {float(pos_pct):.1f}% exceeds max {self._limits.max_position_size_pct}%"
                result["max_allowed_size"] = float(max_allowed)
                return result

        # Check total exposure limit
        new_total = current_exposure + position_size
        if capital > 0:
            new_gross_pct = new_total / capital * 100
            if new_gross_pct > self._limits.max_gross_exposure_pct:
                remaining = capital * self._limits.max_gross_exposure_pct / 100 - current_exposure
                result["reason"] = f"Would exceed gross exposure limit ({float(new_gross_pct):.1f}% > {self._limits.max_gross_exposure_pct}%)"
                result["max_allowed_size"] = float(max(Decimal("0"), remaining))
                return result

        # Check per-exchange exposure
        leg_size = position_size / 2
        for exchange in [long_exchange, short_exchange]:
            current_venue = self._state["exchange_exposure"].get(exchange, Decimal("0"))
            new_venue = current_venue + leg_size
            if capital > 0:
                venue_pct = new_venue / capital * 100
                if venue_pct > self._limits.max_venue_exposure_pct:
                    result["reason"] = f"{exchange} exposure would exceed limit ({float(venue_pct):.1f}% > {self._limits.max_venue_exposure_pct}%)"
                    return result

        # Check per-asset exposure
        if symbol:
            current_asset = self._state["symbol_exposure"].get(symbol, Decimal("0"))
            new_asset = current_asset + position_size
            if capital > 0:
                asset_pct = new_asset / capital * 100
                if asset_pct > self._limits.max_asset_exposure_pct:
                    result["warnings"].append(
                        f"{symbol} concentration would be {float(asset_pct):.1f}%"
                    )

        # Calculate max allowed size
        remaining_exposure = (
            capital * self._limits.max_gross_exposure_pct / 100 - current_exposure
            if capital > 0 else Decimal("0")
        )
        max_allowed = min(max_pos, remaining_exposure)

        # Approved
        result["approved"] = True
        result["max_allowed_size"] = float(max(Decimal("0"), max_allowed))

        logger.info(
            f"Trade validated",
            opportunity_id=opportunity_id,
            size=position_size_usd,
            approved=True,
            max_allowed=float(max_allowed),
        )

        return result

    # ==================== Alert Management ====================

    async def _create_alert(
        self,
        level: AlertLevel,
        alert_type: RiskAlertType,
        message: str,
        metric: str,
        value: float,
        threshold: float,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> None:
        """Create and publish a risk alert."""
        # Check for duplicate recent alert
        recent_same = [
            a for a in self._alerts[-20:]
            if a.metric == metric
            and a.exchange == exchange
            and not a.acknowledged
            and (datetime.utcnow() - a.timestamp).seconds < 300  # 5 min cooldown
        ]
        if recent_same:
            return  # Skip duplicate

        alert = RiskAlert(
            id=str(uuid4()),
            level=level,
            alert_type=alert_type,
            message=message,
            metric=metric,
            value=value,
            threshold=threshold,
            exchange=exchange,
            symbol=symbol,
            timestamp=datetime.utcnow(),
        )
        self._alerts.append(alert)
        self._alerts = self._alerts[-100:]  # Keep last 100

        # Publish event
        event = RiskAlertEvent(
            alert_type=alert_type,
            severity=RiskAlertSeverity.CRITICAL if level == AlertLevel.CRITICAL else RiskAlertSeverity.MEDIUM,
            message=message,
            details={
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "exchange": exchange,
                "symbol": symbol,
            },
        )
        await self.redis.publish("nexus:risk:alert", event.model_dump_json())

        # Publish activity
        await self._publish_activity(
            "risk_alert",
            message,
            {
                "level": level.value,
                "alert_type": alert_type.value,
                "metric": metric,
                "value": value,
                "threshold": threshold,
            },
            level="warning" if level == AlertLevel.WARNING else "error",
        )

        logger.warning(f"Risk alert created", level=level.value, message=message)

    # ==================== Circuit Breaker ====================

    async def activate_circuit_breaker(self, reason: str) -> None:
        """Activate circuit breaker - halt all new trades."""
        if self._circuit_breaker_active:
            return  # Already active

        self._circuit_breaker_active = True
        self._risk_mode = RiskMode.EMERGENCY

        # Publish event
        event = CircuitBreakerEvent(
            triggered=True,
            reason=reason,
            triggered_by="automatic",
            affected_positions=len(self._positions),
        )
        await self.redis.publish("nexus:risk:circuit_breaker", event.model_dump_json())

        # Update system state
        if self.state_manager:
            await self.state_manager.update_state(
                circuit_breaker_active=True,
                new_positions_enabled=False,
            )

        # Publish activity
        await self._publish_activity(
            "circuit_breaker_activated",
            f"Circuit breaker ACTIVATED: {reason}",
            {"reason": reason, "positions_affected": len(self._positions)},
            level="error",
        )

        logger.critical(f"Circuit breaker ACTIVATED", reason=reason)

    async def deactivate_circuit_breaker(self) -> None:
        """Deactivate circuit breaker - allow trading to resume."""
        if not self._circuit_breaker_active:
            return

        self._circuit_breaker_active = False
        self._risk_mode = RiskMode.STANDARD

        # Publish event
        event = CircuitBreakerEvent(
            triggered=False,
            reason="manual_reset",
            triggered_by="manual",
            affected_positions=0,
        )
        await self.redis.publish("nexus:risk:circuit_breaker", event.model_dump_json())

        # Update system state
        if self.state_manager:
            await self.state_manager.update_state(
                circuit_breaker_active=False,
                new_positions_enabled=True,
            )

        # Publish activity
        await self._publish_activity(
            "circuit_breaker_deactivated",
            "Circuit breaker deactivated - trading can resume",
            {},
            level="info",
        )

        logger.info("Circuit breaker deactivated")

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
            "service": "risk-manager",
            "level": level,
            "message": message,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.redis.publish("nexus:activity", json.dumps(activity))

    # ==================== Public Properties ====================

    @property
    def circuit_breaker_active(self) -> bool:
        return self._circuit_breaker_active

    @property
    def risk_mode(self) -> RiskMode:
        return self._risk_mode

    @property
    def active_alert_count(self) -> int:
        return len([
            a for a in self._alerts
            if a.level in [AlertLevel.WARNING, AlertLevel.CRITICAL]
            and not a.acknowledged
        ])

    def get_risk_state(self) -> dict[str, Any]:
        """Get current risk state for API."""
        capital = self._state["total_capital_usd"]
        exposure = self._state["total_exposure_usd"]

        return {
            "total_exposure_usd": float(exposure),
            "gross_exposure_pct": float(exposure / capital * 100) if capital > 0 else 0,
            "exchange_exposure": {
                k: float(v) for k, v in self._state["exchange_exposure"].items()
            },
            "symbol_exposure": {
                k: float(v) for k, v in self._state["symbol_exposure"].items()
            },
            "position_count": self._state["position_count"],
            "current_drawdown_pct": float(self._state["current_drawdown_pct"]),
            "total_capital_usd": float(capital),
            "circuit_breaker_active": self._circuit_breaker_active,
            "risk_mode": self._risk_mode.value,
            "active_alerts": self.active_alert_count,
        }

    def get_limits(self) -> dict[str, Any]:
        """Get current risk limits for API."""
        return {
            "max_position_size_usd": float(self._limits.max_position_size_usd),
            "max_position_size_pct": float(self._limits.max_position_size_pct),
            "max_venue_exposure_pct": float(self._limits.max_venue_exposure_pct),
            "max_asset_exposure_pct": float(self._limits.max_asset_exposure_pct),
            "max_gross_exposure_pct": float(self._limits.max_gross_exposure_pct),
            "max_drawdown_pct": float(self._limits.max_drawdown_pct),
            "max_leverage": float(self._limits.max_leverage),
        }

    def get_alerts(self) -> list[dict[str, Any]]:
        """Get recent alerts for API."""
        return [
            {
                "id": a.id,
                "level": a.level.value,
                "alert_type": a.alert_type.value,
                "message": a.message,
                "metric": a.metric,
                "value": a.value,
                "threshold": a.threshold,
                "exchange": a.exchange,
                "symbol": a.symbol,
                "timestamp": a.timestamp.isoformat(),
                "acknowledged": a.acknowledged,
            }
            for a in self._alerts[-50:]
        ]

    async def set_risk_mode(self, mode: RiskMode, reason: str = "") -> None:
        """Change the risk mode."""
        old_mode = self._risk_mode
        self._risk_mode = mode

        # Publish mode change event
        event = RiskModeChangedEvent(
            previous_mode=old_mode,
            current_mode=mode,
            reason=reason,
            triggered_by="manual",
        )
        await self.redis.publish("nexus:risk:mode_changed", event.model_dump_json())

        # Publish activity
        await self._publish_activity(
            "risk_mode_changed",
            f"Risk mode changed: {old_mode.value} → {mode.value}",
            {"previous_mode": old_mode.value, "new_mode": mode.value, "reason": reason},
            level="info",
        )

        logger.info(f"Risk mode changed", old=old_mode.value, new=mode.value, reason=reason)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False
