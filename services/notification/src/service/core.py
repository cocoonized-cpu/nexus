"""Notification Service Core - Sends alerts via multiple channels."""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

import aiohttp

from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class NotificationService:
    """Sends notifications via multiple channels."""

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._session: Optional[aiohttp.ClientSession] = None

        # Channel configuration (would be loaded from DB)
        self._channels = {
            "telegram": {"enabled": False, "bot_token": None, "chat_id": None},
            "discord": {"enabled": False, "webhook_url": None},
            "email": {"enabled": False, "smtp_host": None},
            "webhook": {"enabled": False, "url": None},
        }

        # Notification history
        self._history: list[dict[str, Any]] = []

    async def start(self) -> None:
        logger.info("Starting Notification Service")
        self._running = True
        self._session = aiohttp.ClientSession()

        self._tasks = [
            asyncio.create_task(self._listen_events()),
        ]
        logger.info("Notification Service started")

    async def stop(self) -> None:
        logger.info("Stopping Notification Service")
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._session:
            await self._session.close()

    async def _listen_events(self) -> None:
        """Listen for events that trigger notifications."""

        async def handle_alert(channel: str, message: str):
            try:
                data = json.loads(message)
                level = data.get("level", "info")
                await self._send_to_all(
                    title=f"NEXUS Alert: {level.upper()}",
                    message=data.get("message", ""),
                    level=level,
                )
            except Exception as e:
                logger.error("Failed to process alert", error=str(e))

        async def handle_position(channel: str, message: str):
            try:
                data = json.loads(message)
                if "opened" in channel:
                    await self._send_to_all(
                        title="Position Opened",
                        message=f"New position: {data.get('symbol')} - ${data.get('size_usd', 0):,.0f}",
                        level="info",
                    )
                elif "closed" in channel:
                    await self._send_to_all(
                        title="Position Closed",
                        message=f"Closed: {data.get('symbol')} - PnL: ${data.get('net_pnl', 0):,.2f}",
                        level="info",
                    )
            except Exception as e:
                logger.error("Failed to process position event", error=str(e))

        await self.redis.subscribe("nexus:risk:alert", handle_alert)
        await self.redis.subscribe("nexus:position:opened", handle_position)
        await self.redis.subscribe("nexus:position:closed", handle_position)

        while self._running:
            await asyncio.sleep(1)

    async def _send_to_all(self, title: str, message: str, level: str) -> None:
        """Send to all enabled channels."""
        for channel_name, config in self._channels.items():
            if config.get("enabled"):
                await self.send(channel_name, title, message, level)

    async def send(
        self, channel: str, title: str, message: str, level: str = "info"
    ) -> bool:
        """Send notification to a specific channel."""
        config = self._channels.get(channel, {})
        if not config.get("enabled"):
            logger.debug(f"Channel {channel} not enabled")
            return False

        try:
            if channel == "telegram":
                await self._send_telegram(config, title, message)
            elif channel == "discord":
                await self._send_discord(config, title, message, level)
            elif channel == "webhook":
                await self._send_webhook(config, title, message, level)

            self._history.append(
                {
                    "channel": channel,
                    "title": title,
                    "message": message,
                    "level": level,
                    "timestamp": datetime.utcnow().isoformat(),
                    "success": True,
                }
            )
            self._history = self._history[-100:]  # Keep last 100

            return True
        except Exception as e:
            logger.error(f"Failed to send to {channel}", error=str(e))
            return False

    async def _send_telegram(self, config: dict, title: str, message: str) -> None:
        if not self._session:
            return
        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        await self._session.post(
            url,
            json={
                "chat_id": config["chat_id"],
                "text": f"*{title}*\n{message}",
                "parse_mode": "Markdown",
            },
        )

    async def _send_discord(
        self, config: dict, title: str, message: str, level: str
    ) -> None:
        if not self._session:
            return
        colors = {"info": 3447003, "warning": 16776960, "critical": 15158332}
        await self._session.post(
            config["webhook_url"],
            json={
                "embeds": [
                    {
                        "title": title,
                        "description": message,
                        "color": colors.get(level, 3447003),
                    }
                ]
            },
        )

    async def _send_webhook(
        self, config: dict, title: str, message: str, level: str
    ) -> None:
        if not self._session:
            return
        await self._session.post(
            config["url"],
            json={
                "title": title,
                "message": message,
                "level": level,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @property
    def configured_channel_count(self) -> int:
        return sum(1 for c in self._channels.values() if c.get("enabled"))

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._history[-limit:]

    def get_channels(self) -> dict[str, Any]:
        return {
            k: {"enabled": v.get("enabled", False)} for k, v in self._channels.items()
        }
