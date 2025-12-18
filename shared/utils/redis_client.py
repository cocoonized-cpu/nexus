"""
Redis client utilities for NEXUS.
"""

import asyncio
import json
from typing import Any, Callable, Optional
from uuid import UUID

import redis.asyncio as redis
from pydantic import BaseModel

from shared.utils.config import get_settings


class RedisClient:
    """
    Async Redis client with pub/sub support.

    Provides caching, pub/sub, and distributed locking capabilities.
    """

    def __init__(self, url: Optional[str] = None):
        """
        Initialize Redis client.

        Args:
            url: Redis URL (defaults to settings)
        """
        self.url = url or get_settings().redis_url
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._subscriptions: dict[str, list[Callable]] = {}

    async def connect(self) -> None:
        """Establish connection to Redis."""
        self._pool = redis.ConnectionPool.from_url(
            self.url,
            max_connections=get_settings().redis_pool_size,
            decode_responses=True,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self._pubsub = self._client.pubsub()

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._pubsub:
            await self._pubsub.close()
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()

    @property
    def client(self) -> redis.Redis:
        """Get the Redis client instance."""
        if self._client is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client

    # Cache Operations

    async def get(self, key: str) -> Optional[str]:
        """Get a value from cache."""
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        expire_seconds: Optional[int] = None,
    ) -> bool:
        """Set a value in cache."""
        return await self.client.set(key, value, ex=expire_seconds)

    async def get_json(self, key: str) -> Optional[dict]:
        """Get a JSON value from cache."""
        data = await self.get(key)
        if data:
            return json.loads(data)
        return None

    async def set_json(
        self,
        key: str,
        value: dict | BaseModel,
        expire_seconds: Optional[int] = None,
    ) -> bool:
        """Set a JSON value in cache."""
        if isinstance(value, BaseModel):
            data = value.model_dump_json()
        else:
            data = json.dumps(value, default=str)
        return await self.set(key, data, expire_seconds)

    async def delete(self, key: str) -> int:
        """Delete a key from cache."""
        return await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return await self.client.exists(key) > 0

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key."""
        return await self.client.expire(key, seconds)

    async def keys(self, pattern: str = "*") -> list[str]:
        """Get keys matching a pattern."""
        return await self.client.keys(pattern)

    # Pub/Sub Operations

    async def publish(self, channel: str, message: str | dict | BaseModel) -> int:
        """
        Publish a message to a channel.

        Args:
            channel: Channel name
            message: Message to publish

        Returns:
            Number of subscribers that received the message
        """
        if isinstance(message, BaseModel):
            data = message.model_dump_json()
        elif isinstance(message, dict):
            data = json.dumps(message, default=str)
        else:
            data = message

        return await self.client.publish(channel, data)

    async def subscribe(
        self,
        channel: str,
        handler: Callable[[str, str], None],
    ) -> None:
        """
        Subscribe to a channel.

        Args:
            channel: Channel pattern (supports wildcards)
            handler: Callback function(channel, message)
        """
        if channel not in self._subscriptions:
            self._subscriptions[channel] = []
            if "*" in channel:
                await self._pubsub.psubscribe(channel)
            else:
                await self._pubsub.subscribe(channel)

        self._subscriptions[channel].append(handler)

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        if channel in self._subscriptions:
            del self._subscriptions[channel]
            if "*" in channel:
                await self._pubsub.punsubscribe(channel)
            else:
                await self._pubsub.unsubscribe(channel)

    async def listen(self) -> None:
        """
        Listen for messages on subscribed channels.

        This is a blocking operation that should run in a background task.
        """
        from shared.utils.logging import get_logger
        logger = get_logger(__name__)

        async for message in self._pubsub.listen():
            msg_type = message.get("type")
            if msg_type in ("message", "pmessage"):
                # For pmessage, channel is the actual channel, pattern is what we subscribed to
                # For message, channel is what we subscribed to
                channel = message.get("channel")
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8")
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                # Find matching subscriptions
                matched = False
                for pattern, handlers in self._subscriptions.items():
                    if self._matches_pattern(channel, pattern):
                        matched = True
                        for handler in handlers:
                            try:
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(channel, data)
                                else:
                                    handler(channel, data)
                            except Exception as e:
                                logger.error(f"Error in subscription handler: {e}")

                if not matched:
                    logger.debug(
                        "No handler matched for channel",
                        channel=channel,
                        subscriptions=list(self._subscriptions.keys()),
                    )

    def _matches_pattern(self, channel: str, pattern: str) -> bool:
        """Check if a channel matches a pattern."""
        if "*" not in pattern:
            return channel == pattern

        # Simple glob matching
        import fnmatch

        return fnmatch.fnmatch(channel, pattern)

    # Distributed Locking

    async def acquire_lock(
        self,
        name: str,
        timeout_seconds: int = 30,
        blocking: bool = True,
        blocking_timeout: float = 10,
    ) -> Optional[str]:
        """
        Acquire a distributed lock.

        Args:
            name: Lock name
            timeout_seconds: Lock auto-expire time
            blocking: Whether to wait for lock
            blocking_timeout: Max time to wait for lock

        Returns:
            Lock token if acquired, None otherwise
        """
        import uuid

        token = str(uuid.uuid4())
        lock_key = f"lock:{name}"

        if blocking:
            end_time = asyncio.get_event_loop().time() + blocking_timeout
            while asyncio.get_event_loop().time() < end_time:
                if await self.client.set(lock_key, token, nx=True, ex=timeout_seconds):
                    return token
                await asyncio.sleep(0.1)
            return None
        else:
            if await self.client.set(lock_key, token, nx=True, ex=timeout_seconds):
                return token
            return None

    async def release_lock(self, name: str, token: str) -> bool:
        """
        Release a distributed lock.

        Args:
            name: Lock name
            token: Token received from acquire_lock

        Returns:
            True if lock was released
        """
        lock_key = f"lock:{name}"
        # Only release if we own the lock
        current = await self.get(lock_key)
        if current == token:
            await self.delete(lock_key)
            return True
        return False


# Singleton instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """
    Get the singleton Redis client.

    Returns:
        Connected Redis client
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    return _redis_client
