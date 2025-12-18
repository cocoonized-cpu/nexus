"""
Activity Logger - Unified event logging for all NEXUS services.

This utility provides a consistent way to log activity events across all services,
ensuring events are persisted to the database and published to Redis for real-time
updates in the dashboard.

Usage:
    from shared.utils.activity_logger import ActivityLogger

    # Initialize in service
    activity = ActivityLogger(
        service_name="execution-engine",
        redis_client=redis,
        db_session_factory=db_factory
    )

    # Log events
    await activity.log(
        category="order",
        event_type="order_placed",
        message="Placed buy order for BTC/USDT",
        symbol="BTC/USDT",
        exchange="binance",
        order_id="12345",
        details={"quantity": 0.1, "price": 43000}
    )
"""

import json
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class ActivityCategory:
    """Valid activity event categories."""

    ORDER = "order"
    POSITION = "position"
    FUNDING = "funding"
    RISK = "risk"
    CAPITAL = "capital"
    SYSTEM = "system"
    DATA = "data"
    ANALYTICS = "analytics"
    NOTIFICATION = "notification"


class Severity:
    """Valid event severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ActivityLogger:
    """
    Unified activity event logging for NEXUS services.

    Logs events to both:
    1. PostgreSQL audit.activity_events table (persistence)
    2. Redis nexus:activity channel (real-time updates)
    """

    def __init__(
        self,
        service_name: str,
        redis_client: RedisClient,
        db_session_factory: Optional[Callable[[], AsyncSession]] = None,
    ):
        """
        Initialize the activity logger.

        Args:
            service_name: Name of the service (e.g., "execution-engine")
            redis_client: Redis client for pub/sub
            db_session_factory: Async database session factory
        """
        self.service = service_name
        self.redis = redis_client
        self.db_factory = db_session_factory

    async def log(
        self,
        category: str,
        event_type: str,
        message: str,
        severity: str = Severity.INFO,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        position_id: Optional[str] = None,
        order_id: Optional[str] = None,
        allocation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        persist: bool = True,
        publish: bool = True,
    ) -> Optional[str]:
        """
        Log an activity event.

        Args:
            category: Event category (order, position, funding, risk, capital, system)
            event_type: Specific event type (e.g., "order_placed", "position_opened")
            message: Human-readable event description
            severity: Event severity (debug, info, warning, error, critical)
            symbol: Trading symbol (e.g., "BTC/USDT")
            exchange: Exchange name (e.g., "binance")
            position_id: Associated position ID
            order_id: Associated order ID
            allocation_id: Associated allocation ID
            correlation_id: ID for tracking related events
            details: Additional event details as JSON
            persist: Whether to persist to database (default: True)
            publish: Whether to publish to Redis (default: True)

        Returns:
            Event ID if persisted, None otherwise
        """
        timestamp = datetime.utcnow()
        event_id = None

        event = {
            "service": self.service,
            "category": category,
            "event_type": event_type,
            "severity": severity,
            "symbol": symbol,
            "exchange": exchange,
            "position_id": position_id,
            "order_id": order_id,
            "allocation_id": allocation_id,
            "correlation_id": correlation_id,
            "message": message,
            "details": details or {},
            "timestamp": timestamp.isoformat(),
        }

        # Persist to database
        if persist and self.db_factory:
            try:
                event_id = await self._persist_event(event)
                event["id"] = event_id
            except Exception as e:
                logger.error(
                    f"Failed to persist activity event: {e}",
                    service=self.service,
                    event_type=event_type,
                )

        # Publish to Redis for real-time updates
        if publish:
            try:
                await self.redis.publish("nexus:activity", json.dumps(event))
            except Exception as e:
                logger.error(
                    f"Failed to publish activity event: {e}",
                    service=self.service,
                    event_type=event_type,
                )

        return event_id

    async def _persist_event(self, event: dict[str, Any]) -> str:
        """Persist event to database and return event ID."""
        async with self.db_factory() as db:
            result = await db.execute(
                text("""
                    INSERT INTO audit.activity_events
                    (service, category, event_type, severity, symbol, exchange,
                     position_id, order_id, allocation_id, correlation_id, message, details)
                    VALUES (:service, :category, :event_type, :severity, :symbol,
                            :exchange, :position_id, :order_id, :allocation_id,
                            :correlation_id, :message, :details)
                    RETURNING id
                """),
                {
                    "service": event["service"],
                    "category": event["category"],
                    "event_type": event["event_type"],
                    "severity": event["severity"],
                    "symbol": event.get("symbol"),
                    "exchange": event.get("exchange"),
                    "position_id": event.get("position_id"),
                    "order_id": event.get("order_id"),
                    "allocation_id": event.get("allocation_id"),
                    "correlation_id": event.get("correlation_id"),
                    "message": event["message"],
                    "details": json.dumps(event.get("details", {})),
                },
            )
            row = result.fetchone()
            await db.commit()
            return str(row[0]) if row else None

    # Convenience methods for common event types

    async def order_placed(
        self,
        message: str,
        symbol: str,
        exchange: str,
        order_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log order placed event."""
        return await self.log(
            category=ActivityCategory.ORDER,
            event_type="order_placed",
            message=message,
            symbol=symbol,
            exchange=exchange,
            order_id=order_id,
            details=details,
            **kwargs,
        )

    async def order_filled(
        self,
        message: str,
        symbol: str,
        exchange: str,
        order_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log order filled event."""
        return await self.log(
            category=ActivityCategory.ORDER,
            event_type="order_filled",
            message=message,
            symbol=symbol,
            exchange=exchange,
            order_id=order_id,
            details=details,
            **kwargs,
        )

    async def order_cancelled(
        self,
        message: str,
        symbol: str,
        exchange: str,
        order_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log order cancelled event."""
        return await self.log(
            category=ActivityCategory.ORDER,
            event_type="order_cancelled",
            message=message,
            severity=Severity.WARNING,
            symbol=symbol,
            exchange=exchange,
            order_id=order_id,
            details=details,
            **kwargs,
        )

    async def order_failed(
        self,
        message: str,
        symbol: str,
        exchange: str,
        order_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log order failed event."""
        return await self.log(
            category=ActivityCategory.ORDER,
            event_type="order_failed",
            message=message,
            severity=Severity.ERROR,
            symbol=symbol,
            exchange=exchange,
            order_id=order_id,
            details=details,
            **kwargs,
        )

    async def position_opened(
        self,
        message: str,
        symbol: str,
        position_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log position opened event."""
        return await self.log(
            category=ActivityCategory.POSITION,
            event_type="position_opened",
            message=message,
            symbol=symbol,
            position_id=position_id,
            details=details,
            **kwargs,
        )

    async def position_closed(
        self,
        message: str,
        symbol: str,
        position_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log position closed event."""
        return await self.log(
            category=ActivityCategory.POSITION,
            event_type="position_closed",
            message=message,
            symbol=symbol,
            position_id=position_id,
            details=details,
            **kwargs,
        )

    async def capital_allocated(
        self,
        message: str,
        symbol: str,
        allocation_id: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log capital allocation event."""
        return await self.log(
            category=ActivityCategory.CAPITAL,
            event_type="capital_allocated",
            message=message,
            symbol=symbol,
            allocation_id=allocation_id,
            details=details,
            **kwargs,
        )

    async def risk_alert(
        self,
        message: str,
        severity: str = Severity.WARNING,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log risk alert event."""
        return await self.log(
            category=ActivityCategory.RISK,
            event_type="risk_alert",
            message=message,
            severity=severity,
            details=details,
            **kwargs,
        )

    async def system_event(
        self,
        event_type: str,
        message: str,
        severity: str = Severity.INFO,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log system event."""
        return await self.log(
            category=ActivityCategory.SYSTEM,
            event_type=event_type,
            message=message,
            severity=severity,
            details=details,
            **kwargs,
        )

    async def funding_collected(
        self,
        message: str,
        symbol: str,
        exchange: str,
        position_id: Optional[str] = None,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log funding rate collection event."""
        return await self.log(
            category=ActivityCategory.FUNDING,
            event_type="funding_collected",
            message=message,
            symbol=symbol,
            exchange=exchange,
            position_id=position_id,
            details=details,
            **kwargs,
        )

    async def opportunity_detected(
        self,
        message: str,
        symbol: str,
        details: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """Log opportunity detection event."""
        return await self.log(
            category=ActivityCategory.DATA,
            event_type="opportunity_detected",
            message=message,
            symbol=symbol,
            details=details,
            **kwargs,
        )
