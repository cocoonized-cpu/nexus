"""
Service Heartbeat Utility - Reports service health to Redis.

Services use this to report their status so the gateway can aggregate
health information for the control panel.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Optional

from shared.utils.logging import get_logger

logger = get_logger(__name__)


class ServiceHeartbeat:
    """
    Reports service health to Redis periodically.

    Usage:
        heartbeat = ServiceHeartbeat(
            service_name="data-collector",
            redis_client=redis,
            health_check=my_health_check,  # Optional
        )
        await heartbeat.start()
    """

    def __init__(
        self,
        service_name: str,
        redis_client: Any,
        health_check: Optional[Callable[[], dict]] = None,
        interval_seconds: int = 10,
    ):
        self.service_name = service_name
        self.redis = redis_client
        self.health_check = health_check
        self.interval = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._start_time = datetime.utcnow()

    async def start(self) -> None:
        """Start heartbeat reporting."""
        self._running = True
        self._start_time = datetime.utcnow()
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat started for {self.service_name}")

    async def stop(self) -> None:
        """Stop heartbeat reporting."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Heartbeat stopped for {self.service_name}")

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat to Redis."""
        while self._running:
            try:
                await self._send_heartbeat()
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")

            await asyncio.sleep(self.interval)

    async def _send_heartbeat(self) -> None:
        """Send a single heartbeat."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()

        # Get custom health details if provided
        details = {}
        status = "healthy"

        if self.health_check:
            try:
                health_result = self.health_check()
                details = health_result.get("details", {})
                if health_result.get("status"):
                    status = health_result["status"]
            except Exception as e:
                status = "degraded"
                details["error"] = str(e)

        health_data = {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int(uptime),
            "details": details,
        }

        key = f"nexus:health:{self.service_name}"
        # Set with 30 second expiry (3x heartbeat interval)
        await self.redis.client.setex(key, 30, json.dumps(health_data))
