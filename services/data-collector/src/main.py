"""
Data Collector Service - Main Application.

Responsible for fetching real-time data from cryptocurrency exchanges:
- Funding rates
- Price data
- Order book / liquidity data
- Exchange health monitoring
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.api import health
from src.collector import DataCollectorManager

from shared.utils.config import get_settings
from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    logger.info("Starting Data Collector service")

    # Initialize Redis connection
    redis = await get_redis_client()
    app.state.redis = redis

    # Initialize and start the data collector manager
    collector_manager = DataCollectorManager(redis)
    app.state.collector_manager = collector_manager

    # Start collection tasks
    await collector_manager.start()

    # Start heartbeat
    def get_health():
        stats = collector_manager.get_stats()
        return {
            "status": "healthy" if collector_manager.active_exchange_count > 0 else "degraded",
            "details": {
                "active_exchanges": collector_manager.active_exchange_count,
                "total_exchanges": len(collector_manager.providers),
                "funding_updates": stats.get("funding_updates", 0),
                "errors": stats.get("errors", 0),
            },
        }

    heartbeat = ServiceHeartbeat(
        service_name="data-collector",
        redis_client=redis,
        health_check=get_health,
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    # Shutdown
    logger.info("Shutting down Data Collector service")
    await heartbeat.stop()
    await collector_manager.stop()


app = FastAPI(
    title="NEXUS Data Collector",
    description="Exchange data collection service",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "data-collector",
        "status": "running",
        "version": "1.0.0",
    }
