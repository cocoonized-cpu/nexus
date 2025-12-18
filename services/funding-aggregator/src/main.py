"""
Funding Aggregator Service - Main Application.

Responsible for merging funding rate data from dual sources:
- PRIMARY: Exchange APIs (via Data Collector)
- SECONDARY: ArbitrageScanner API (for validation and gap-filling)

Produces unified funding snapshots for downstream services.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.aggregator import FundingAggregator
from src.api import funding, health

from shared.utils.config import get_settings
from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    logger.info("Starting Funding Aggregator service")

    # Initialize Redis connection
    redis = await get_redis_client()
    app.state.redis = redis

    # Initialize and start the funding aggregator
    aggregator = FundingAggregator(redis)
    app.state.aggregator = aggregator

    # Start aggregation tasks
    await aggregator.start()

    # Start heartbeat
    def get_health():
        return {
            "status": "healthy" if aggregator.is_running else "degraded",
            "details": {
                "exchange_count": aggregator.exchange_count,
                "symbol_count": aggregator.symbol_count,
            },
        }

    heartbeat = ServiceHeartbeat(
        service_name="funding-aggregator",
        redis_client=redis,
        health_check=get_health,
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    # Shutdown
    logger.info("Shutting down Funding Aggregator service")
    await heartbeat.stop()
    await aggregator.stop()


app = FastAPI(
    title="NEXUS Funding Aggregator",
    description="Dual-source funding rate aggregation service",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(funding.router, prefix="/funding", tags=["funding"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "funding-aggregator",
        "status": "running",
        "version": "1.0.0",
    }
