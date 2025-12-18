"""
NEXUS Shared Utilities

Common utilities shared across all microservices.
"""

from shared.utils.activity_logger import ActivityCategory, ActivityLogger, Severity
from shared.utils.config import Settings, get_settings
from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.helpers import (decimal_to_str, generate_id,
                                  normalize_symbol, parse_symbol,
                                  str_to_decimal)
from shared.utils.logging import get_logger, setup_logging
from shared.utils.redis_client import RedisClient, get_redis_client
from shared.utils.system_state import SystemStateManager


# Lazy imports for exchange_client to avoid eth_account dependency in services that don't need it
def __getattr__(name):
    if name in ("ExchangeClient", "ExchangeCredentials", "get_enabled_exchanges", "get_exchange_credentials"):
        from shared.utils.exchange_client import (
            ExchangeClient,
            ExchangeCredentials,
            get_enabled_exchanges,
            get_exchange_credentials,
        )
        return {
            "ExchangeClient": ExchangeClient,
            "ExchangeCredentials": ExchangeCredentials,
            "get_enabled_exchanges": get_enabled_exchanges,
            "get_exchange_credentials": get_exchange_credentials,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Logging
    "setup_logging",
    "get_logger",
    # Config
    "Settings",
    "get_settings",
    # Redis
    "RedisClient",
    "get_redis_client",
    # Heartbeat
    "ServiceHeartbeat",
    # Exchange Client (lazy loaded)
    "ExchangeClient",
    "ExchangeCredentials",
    "get_exchange_credentials",
    "get_enabled_exchanges",
    # Helpers
    "generate_id",
    "normalize_symbol",
    "parse_symbol",
    "decimal_to_str",
    "str_to_decimal",
    # System State
    "SystemStateManager",
    # Activity Logger
    "ActivityLogger",
    "ActivityCategory",
    "Severity",
]
