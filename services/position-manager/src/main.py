"""
Position Manager Service - Tracks position lifecycle, P&L, and exit optimization.

Responsibilities:
- Track active positions across exchanges
- Monitor funding payments received/paid
- Calculate real-time P&L (funding + price)
- Determine optimal exit timing
- Manage position health status
- Sync positions and orders from all exchanges
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.api import health, positions
from src.manager import PositionManager, PositionSyncWorker

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
    logger.info("Starting Position Manager service")
    redis = await get_redis_client()
    app.state.redis = redis

    # Start position sync worker
    sync_worker = PositionSyncWorker(
        redis=redis,
        db_url=DATABASE_URL,
        sync_interval=30,  # Sync every 30 seconds
    )
    app.state.sync_worker = sync_worker
    await sync_worker.start()

    manager = PositionManager(redis)
    app.state.manager = manager
    await manager.start()

    def get_health() -> dict:
        return {
            "status": "healthy",
            "sync_worker": sync_worker.is_running,
            "manager": manager._running,
        }

    heartbeat = ServiceHeartbeat(
        service_name="position-manager",
        redis_client=redis,
        health_check=get_health,
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    logger.info("Shutting down Position Manager service")
    await heartbeat.stop()
    await manager.stop()
    await sync_worker.stop()


app = FastAPI(
    title="NEXUS Position Manager",
    description="Position lifecycle and P&L tracking service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(positions.router, prefix="/positions", tags=["positions"])


@app.get("/")
async def root():
    return {"service": "position-manager", "status": "running", "version": "1.0.0"}
