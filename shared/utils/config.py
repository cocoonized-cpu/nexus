"""
Configuration management for NEXUS services.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Base settings for all NEXUS services.

    Settings are loaded from environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service Identity
    service_name: str = "nexus"
    environment: str = Field(
        "development", description="development, staging, production"
    )
    debug: bool = False

    # Database
    database_url: str = Field(
        "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus",
        description="PostgreSQL connection URL",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Redis
    redis_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_pool_size: int = 10

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # Security
    secret_key: str = Field(
        "development-secret-key-change-in-production",
        description="Secret key for encryption",
    )
    api_key: Optional[str] = None

    # Exchange API (loaded from database, these are fallbacks)
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    bybit_api_key: Optional[str] = None
    bybit_api_secret: Optional[str] = None

    # ArbitrageScanner
    arbitragescanner_enabled: bool = True
    arbitragescanner_funding_url: str = (
        "https://screener.arbitragescanner.io/api/funding-table"
    )
    arbitragescanner_exchanges_url: str = "https://api.arbitragescanner.io/exchanges"

    # Risk Defaults
    default_max_position_size_usd: int = 50000
    default_max_leverage: float = 3.0
    default_max_drawdown_pct: float = 5.0

    # Timing
    data_refresh_interval_seconds: int = 5
    opportunity_scan_interval_seconds: int = 30
    position_monitor_interval_seconds: int = 10
    risk_check_interval_seconds: int = 30


class ServiceSettings(Settings):
    """Extended settings with service-specific configuration."""

    # Can be extended by individual services
    pass


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings instance
    """
    return Settings()


def get_service_settings(service_name: str) -> ServiceSettings:
    """
    Get settings for a specific service.

    Args:
        service_name: Name of the service

    Returns:
        Service-specific settings
    """
    settings = ServiceSettings()
    settings.service_name = service_name
    return settings
