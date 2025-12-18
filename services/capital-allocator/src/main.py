"""
Capital Allocator Service - Distributes capital across opportunities.

Responsibilities:
- Track available capital across exchanges
- Allocate capital to opportunities based on UOS score
- Request trade execution
- Rebalance allocations
- Monitor exchange balances
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.allocator import BalanceMonitor, CapitalAllocator
from src.api import capital, health

from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Capital Allocator service")
    redis = await get_redis_client()
    app.state.redis = redis

    # Start balance monitor
    balance_monitor = BalanceMonitor(
        redis=redis,
        db_url=DATABASE_URL,
        sync_interval=60,  # Sync every 60 seconds
    )
    app.state.balance_monitor = balance_monitor
    await balance_monitor.start()

    allocator = CapitalAllocator(redis, balance_monitor)
    app.state.allocator = allocator
    await allocator.start()

    def get_health() -> dict:
        return {
            "status": "healthy",
            "balance_monitor": balance_monitor.is_running,
            "allocator": allocator.is_running,
        }

    heartbeat = ServiceHeartbeat(
        service_name="capital-allocator",
        redis_client=redis,
        health_check=get_health,
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    logger.info("Shutting down Capital Allocator service")
    await heartbeat.stop()
    await allocator.stop()
    await balance_monitor.stop()


app = FastAPI(
    title="NEXUS Capital Allocator",
    description="Capital allocation and distribution service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(capital.router, prefix="/capital", tags=["capital"])


@app.get("/")
async def root():
    return {"service": "capital-allocator", "status": "running", "version": "1.0.0"}
