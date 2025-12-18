"""
WebSocket connection manager for real-time updates.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional, Set
from uuid import uuid4

from fastapi import WebSocket

from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)


class WebSocketConnection:
    """Represents a single WebSocket connection."""

    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.subscriptions: Set[str] = set()
        self.connected_at = datetime.utcnow()
        self.is_active = True

    async def send(self, message: dict[str, Any]) -> bool:
        """Send a message to this connection."""
        if not self.is_active:
            return False
        try:
            await self.websocket.send_json(message)
            return True
        except Exception:
            # Connection is no longer active - mark it for cleanup
            self.is_active = False
            return False


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts.

    Features:
    - Connection tracking
    - Channel subscriptions
    - Redis Pub/Sub integration for cross-service events
    - Heartbeat monitoring
    """

    def __init__(self):
        self.connections: dict[str, WebSocketConnection] = {}
        self.channel_subscribers: dict[str, Set[str]] = {}
        self._redis = None
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the WebSocket manager."""
        self._redis = await get_redis_client()
        self._running = True
        logger.info("WebSocket manager started")

    async def stop(self) -> None:
        """Stop the WebSocket manager."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()

        # Close all connections
        for conn in list(self.connections.values()):
            await self.disconnect(conn.client_id)

        logger.info("WebSocket manager stopped")

    async def connect(self, websocket: WebSocket) -> str:
        """
        Accept a new WebSocket connection.

        Returns:
            Client ID for the connection
        """
        await websocket.accept()
        client_id = str(uuid4())

        connection = WebSocketConnection(websocket, client_id)
        self.connections[client_id] = connection

        logger.info("WebSocket client connected", client=client_id)

        # Send welcome message
        await connection.send(
            {
                "event": "connected",
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        return client_id

    async def disconnect(self, client_id: str) -> None:
        """Disconnect a WebSocket client."""
        if client_id in self.connections:
            connection = self.connections[client_id]

            # Remove from all channel subscriptions
            for channel in connection.subscriptions:
                if channel in self.channel_subscribers:
                    self.channel_subscribers[channel].discard(client_id)

            del self.connections[client_id]
            logger.info("WebSocket client disconnected", client=client_id)

    async def subscribe(self, client_id: str, channel: str) -> bool:
        """
        Subscribe a client to a channel.

        Channels:
        - funding_rates: Real-time funding rate updates
        - opportunities: New and updated opportunities
        - positions: Position updates
        - risk: Risk alerts and state changes
        - system: System events
        """
        if client_id not in self.connections:
            return False

        connection = self.connections[client_id]
        connection.subscriptions.add(channel)

        if channel not in self.channel_subscribers:
            self.channel_subscribers[channel] = set()
        self.channel_subscribers[channel].add(client_id)

        logger.debug("Client subscribed to channel", client=client_id, channel=channel)

        # Send subscription confirmation
        await connection.send(
            {
                "event": "subscribed",
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        return True

    async def unsubscribe(self, client_id: str, channel: str) -> bool:
        """Unsubscribe a client from a channel."""
        if client_id not in self.connections:
            return False

        connection = self.connections[client_id]
        connection.subscriptions.discard(channel)

        if channel in self.channel_subscribers:
            self.channel_subscribers[channel].discard(client_id)

        logger.debug(
            "Client unsubscribed from channel", client=client_id, channel=channel
        )

        await connection.send(
            {
                "event": "unsubscribed",
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        return True

    async def broadcast_to_channel(self, channel: str, message: dict[str, Any]) -> int:
        """
        Broadcast a message to all subscribers of a channel.

        Returns:
            Number of clients that received the message
        """
        if channel not in self.channel_subscribers:
            return 0

        message["channel"] = channel
        message["timestamp"] = datetime.utcnow().isoformat()

        sent_count = 0
        failed_clients = []

        for client_id in self.channel_subscribers[channel]:
            if client_id in self.connections:
                success = await self.connections[client_id].send(message)
                if success:
                    sent_count += 1
                else:
                    failed_clients.append(client_id)

        # Clean up failed connections
        for client_id in failed_clients:
            await self.disconnect(client_id)

        return sent_count

    async def broadcast_all(self, message: dict[str, Any]) -> int:
        """
        Broadcast a message to all connected clients.

        Returns:
            Number of clients that received the message
        """
        message["timestamp"] = datetime.utcnow().isoformat()

        sent_count = 0
        failed_clients = []

        for client_id, connection in self.connections.items():
            success = await connection.send(message)
            if success:
                sent_count += 1
            else:
                failed_clients.append(client_id)

        # Clean up failed connections
        for client_id in failed_clients:
            await self.disconnect(client_id)

        return sent_count

    async def send_to_client(self, client_id: str, message: dict[str, Any]) -> bool:
        """Send a message to a specific client."""
        if client_id not in self.connections:
            return False

        message["timestamp"] = datetime.utcnow().isoformat()
        return await self.connections[client_id].send(message)

    async def listen_to_events(self) -> None:
        """
        Listen to Redis Pub/Sub events and broadcast to WebSocket clients.

        This should run as a background task.
        """
        if not self._redis:
            logger.error("Redis not connected")
            return

        # Subscribe to NEXUS event channels
        channels = [
            "nexus:market_data:*",
            "nexus:opportunity:*",
            "nexus:position:*",
            "nexus:risk:*",
            "nexus:capital:*",
            "nexus:system:*",
            "nexus:activity",  # Activity events from all services
            "nexus:execution:*",  # Execution engine events
        ]

        for channel in channels:
            await self._redis.subscribe(channel, self._handle_redis_event)

        logger.info("Listening to Redis event channels", channels=channels)

        # Start listening
        await self._redis.listen()

    async def _handle_redis_event(self, channel: str, message: str) -> None:
        """Handle an event received from Redis."""
        try:
            data = json.loads(message)

            # Map Redis channel to WebSocket channel
            ws_channel = self._map_channel(channel)
            logger.debug(
                "Received Redis event",
                redis_channel=channel,
                ws_channel=ws_channel,
                event_type=data.get("type") if isinstance(data, dict) else None,
            )

            if ws_channel:
                event_type = channel.split(":")[-1]
                # For activity channel, use the type from the message
                if channel == "nexus:activity" and isinstance(data, dict):
                    event_type = data.get("type", "activity")

                sent_count = await self.broadcast_to_channel(
                    ws_channel,
                    {
                        "event": event_type,
                        "data": data,
                    },
                )
                logger.debug(
                    "Broadcast event to WebSocket clients",
                    ws_channel=ws_channel,
                    event_type=event_type,
                    clients_reached=sent_count,
                )
        except Exception as e:
            logger.error("Error handling Redis event", error=str(e), channel=channel)

    def _map_channel(self, redis_channel: str) -> Optional[str]:
        """Map Redis channel to WebSocket channel."""
        # Handle exact channel matches first
        if redis_channel == "nexus:activity":
            return "system"  # Activity events go to system channel

        parts = redis_channel.split(":")
        if len(parts) >= 2:
            category = parts[1]
            channel_map = {
                "market_data": "funding_rates",
                "opportunity": "opportunities",
                "position": "positions",
                "risk": "risk",
                "capital": "capital",
                "system": "system",
                "execution": "system",  # Execution events go to system channel
                "activity": "system",  # Activity events go to system channel
            }
            return channel_map.get(category)
        return None

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.connections)

    def get_stats(self) -> dict[str, Any]:
        """Get WebSocket manager statistics."""
        return {
            "connections": self.connection_count,
            "channels": {
                channel: len(subscribers)
                for channel, subscribers in self.channel_subscribers.items()
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
