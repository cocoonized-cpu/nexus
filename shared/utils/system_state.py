"""
System State Manager - Shared state awareness for all services.

Provides a unified way for services to:
- Check if the bot is running
- Check if new positions can be opened
- React to mode changes and emergency stops
- Respect UI control commands

State is loaded from database (config.system_settings) on startup,
with Redis pub/sub used for real-time state change propagation.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Optional

from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class SystemStateManager:
    """
    Manages system state awareness for services.

    Services should use this to check state before taking actions:
    - should_execute() - Is trading allowed?
    - should_open_positions() - Can we open new positions?
    - is_running - Is the system running?
    - mode - Current operating mode

    State is loaded from database on startup for persistence across restarts.
    """

    def __init__(
        self,
        redis: RedisClient,
        service_name: str = "unknown",
        db_session_factory: Optional[Callable] = None,
    ):
        self.redis = redis
        self.service_name = service_name
        self._db_session_factory = db_session_factory
        self._state = {
            "system_running": True,  # Default to true for trading
            "new_positions_enabled": True,
            "mode": "standard",
            "auto_execute": True,  # Default to true for auto-execution
            "circuit_breaker_active": False,
            "start_time": None,
        }
        self._callbacks: list[Callable] = []
        self._running = False
        self._subscription_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the state manager and subscribe to state changes."""
        logger.info(f"Starting SystemStateManager for {self.service_name}")

        # Load initial state from Redis
        await self._load_state()

        self._running = True

        # Subscribe to state change events
        self._subscription_task = asyncio.create_task(self._subscribe_to_changes())

        logger.info(
            f"SystemStateManager started",
            service=self.service_name,
            running=self._state["system_running"],
            mode=self._state["mode"],
        )

    async def stop(self) -> None:
        """Stop the state manager."""
        logger.info(f"Stopping SystemStateManager for {self.service_name}")
        self._running = False

        if self._subscription_task:
            self._subscription_task.cancel()
            try:
                await self._subscription_task
            except asyncio.CancelledError:
                pass

        logger.info(f"SystemStateManager stopped for {self.service_name}")

    async def _load_state(self) -> None:
        """Load current state from database first, then fall back to Redis."""
        # Try to load from database first (authoritative source)
        if self._db_session_factory:
            try:
                await self._load_state_from_db()
                logger.info("Loaded system state from database", state=self._state)
                # Cache state to Redis for quick access
                await self._cache_state_to_redis()
                return
            except Exception as e:
                logger.warning(f"Failed to load state from DB, falling back to Redis", error=str(e))

        # Fall back to Redis
        try:
            # Try to get cached state first
            state_json = await self.redis.get("nexus:system:state")
            if state_json:
                cached_state = json.loads(state_json)
                self._state.update(cached_state)
                logger.debug("Loaded cached system state from Redis", state=self._state)
                return

            # Load individual settings from Redis keys
            keys_to_load = [
                ("nexus:system:running", "system_running", True),
                ("nexus:system:new_positions_enabled", "new_positions_enabled", True),
                ("nexus:system:mode", "mode", "standard"),
                ("nexus:system:auto_execute", "auto_execute", True),
                ("nexus:system:circuit_breaker", "circuit_breaker_active", False),
            ]

            for redis_key, state_key, default in keys_to_load:
                value = await self.redis.get(redis_key)
                if value is not None:
                    # Parse value
                    if isinstance(value, str):
                        if value.lower() == "true":
                            value = True
                        elif value.lower() == "false":
                            value = False
                    self._state[state_key] = value
                else:
                    self._state[state_key] = default

            logger.debug("Loaded system state from Redis keys", state=self._state)

        except Exception as e:
            logger.warning(f"Failed to load system state, using defaults", error=str(e))

    async def _load_state_from_db(self) -> None:
        """Load state from config.system_settings database table."""
        from sqlalchemy import text

        key_mapping = {
            "system_running": "system_running",
            "new_positions_enabled": "new_positions_enabled",
            "system_mode": "mode",
            "auto_execute": "auto_execute",
            "circuit_breaker_active": "circuit_breaker_active",
        }

        async with self._db_session_factory() as db:
            # Use ANY() with array for asyncpg compatibility instead of IN with tuple
            keys_list = list(key_mapping.keys())
            query = text("""
                SELECT key, value, data_type
                FROM config.system_settings
                WHERE key = ANY(:keys)
            """)
            result = await db.execute(
                query,
                {"keys": keys_list}
            )
            rows = result.fetchall()

            for key, value_json, data_type in rows:
                state_key = key_mapping.get(key)
                if not state_key:
                    continue

                # Parse JSON value based on data type
                try:
                    # Handle string values that may or may not be JSON encoded
                    value = value_json
                    if isinstance(value_json, str):
                        # Try to parse as JSON first
                        try:
                            value = json.loads(value_json)
                        except json.JSONDecodeError:
                            # Not valid JSON, use raw string
                            value = value_json

                    # Type conversion based on data_type
                    if data_type == "boolean":
                        if isinstance(value, bool):
                            pass  # Already a boolean
                        else:
                            value = str(value).lower() in ("true", "1", "yes")
                    elif data_type == "integer":
                        value = int(value) if value else 0
                    elif data_type == "decimal" or data_type == "float":
                        value = float(value) if value else 0.0
                    elif data_type == "string":
                        # Remove surrounding quotes if present
                        if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]

                    self._state[state_key] = value
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse DB value for {key}", error=str(e))

    async def _cache_state_to_redis(self) -> None:
        """Cache current state to Redis for quick access."""
        try:
            await self.redis.set(
                "nexus:system:state",
                json.dumps(self._state),
            )
        except Exception as e:
            logger.warning(f"Failed to cache state to Redis", error=str(e))

    async def _subscribe_to_changes(self) -> None:
        """Subscribe to system state change events."""
        channels = [
            "nexus:system:state_changed",
            "nexus:system:mode_changed",
            "nexus:system:emergency",
            "nexus:system:control",
        ]

        async def handle_message(channel: str, message: str):
            await self._handle_state_change(channel, message)

        try:
            for channel in channels:
                await self.redis.subscribe(channel, handle_message)

            # Keep running while active
            while self._running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in state subscription", error=str(e))

    async def _handle_state_change(self, channel: str, message: str) -> None:
        """Handle incoming state change events."""
        try:
            data = json.loads(message) if isinstance(message, str) else message

            logger.info(
                f"Received state change event",
                channel=channel,
                data=data,
            )

            if channel == "nexus:system:emergency":
                # Emergency stop - immediately halt
                self._state["system_running"] = False
                self._state["new_positions_enabled"] = False
                self._state["circuit_breaker_active"] = True
                logger.warning("EMERGENCY STOP received - halting all operations")

            elif channel == "nexus:system:mode_changed":
                new_mode = data.get("mode") or data.get("new_mode")
                if new_mode:
                    self._state["mode"] = new_mode
                    if new_mode == "emergency":
                        self._state["new_positions_enabled"] = False

            elif channel == "nexus:system:control":
                action = data.get("action")
                if action == "start":
                    self._state["system_running"] = True
                    self._state["start_time"] = datetime.utcnow().isoformat()
                elif action == "stop":
                    self._state["system_running"] = False
                elif action == "emergency_stop":
                    self._state["system_running"] = False
                    self._state["new_positions_enabled"] = False
                    self._state["circuit_breaker_active"] = True

            elif channel == "nexus:system:state_changed":
                # Generic state update
                for key in ["system_running", "new_positions_enabled", "mode", "auto_execute"]:
                    if key in data:
                        self._state[key] = data[key]

            # Notify callbacks
            for callback in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(self._state.copy())
                    else:
                        callback(self._state.copy())
                except Exception as e:
                    logger.error(f"Error in state change callback", error=str(e))

        except Exception as e:
            logger.error(f"Failed to handle state change", error=str(e), message=message)

    def on_state_change(self, callback: Callable) -> None:
        """Register a callback for state changes."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable) -> None:
        """Remove a state change callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    # ==================== State Query Methods ====================

    @property
    def is_running(self) -> bool:
        """Check if the system is running."""
        return self._state.get("system_running", False)

    @property
    def new_positions_enabled(self) -> bool:
        """Check if new positions can be opened."""
        return self._state.get("new_positions_enabled", True)

    @property
    def mode(self) -> str:
        """Get current operating mode."""
        return self._state.get("mode", "standard")

    @property
    def auto_execute(self) -> bool:
        """Check if auto-execution is enabled."""
        return self._state.get("auto_execute", False)

    @property
    def circuit_breaker_active(self) -> bool:
        """Check if circuit breaker is active."""
        return self._state.get("circuit_breaker_active", False)

    def should_execute(self) -> bool:
        """
        Check if trading execution should proceed.

        Returns False if:
        - System is not running
        - Mode is 'discovery' (observe only)
        - Mode is 'emergency'
        - Circuit breaker is active
        """
        if not self.is_running:
            return False
        if self.circuit_breaker_active:
            return False
        if self.mode in ["discovery", "emergency"]:
            return False
        return True

    def should_open_positions(self) -> bool:
        """
        Check if new positions can be opened.

        Returns False if:
        - should_execute() returns False
        - new_positions_enabled is False
        """
        if not self.should_execute():
            return False
        return self.new_positions_enabled

    def should_auto_execute(self) -> bool:
        """
        Check if automatic execution is enabled.

        For opportunities that meet thresholds, should they
        be executed automatically or queued for manual approval?
        """
        return self.should_open_positions() and self.auto_execute

    def get_state(self) -> dict[str, Any]:
        """Get a copy of the current state."""
        return self._state.copy()

    # ==================== State Update Methods ====================

    async def update_state(self, **kwargs) -> None:
        """
        Update state and publish change event.

        Example: await state_manager.update_state(system_running=True)
        """
        changed = False
        for key, value in kwargs.items():
            if key in self._state and self._state[key] != value:
                self._state[key] = value
                changed = True

        if changed:
            # Publish state change
            await self.redis.publish(
                "nexus:system:state_changed",
                json.dumps({
                    **kwargs,
                    "source": self.service_name,
                    "timestamp": datetime.utcnow().isoformat(),
                }),
            )

            # Cache full state
            await self.redis.set(
                "nexus:system:state",
                json.dumps(self._state),
            )

    async def trigger_emergency_stop(self, reason: str = "Unknown") -> None:
        """Trigger an emergency stop from this service."""
        logger.warning(f"Triggering emergency stop", reason=reason, service=self.service_name)

        await self.redis.publish(
            "nexus:system:emergency",
            json.dumps({
                "action": "emergency_stop",
                "reason": reason,
                "source": self.service_name,
                "timestamp": datetime.utcnow().isoformat(),
            }),
        )

        # Update local state immediately
        self._state["system_running"] = False
        self._state["new_positions_enabled"] = False
        self._state["circuit_breaker_active"] = True
