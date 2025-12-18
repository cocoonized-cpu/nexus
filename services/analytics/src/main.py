"""
Analytics Service - Performance tracking and attribution analysis.

Responsibilities:
- Track daily P&L (funding, price, fees)
- Calculate performance metrics (Sharpe, drawdown, win rate)
- Attribution analysis by exchange, symbol, strategy
- Generate performance reports
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.api import health, metrics
from src.service import AnalyticsService

from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Analytics service")
    redis = await get_redis_client()
    app.state.redis = redis

    service = AnalyticsService(redis)
    app.state.service = service
    await service.start()

    heartbeat = ServiceHeartbeat(
        service_name="analytics",
        redis_client=redis,
        health_check=lambda: {"status": "healthy"},
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    logger.info("Shutting down Analytics service")
    await heartbeat.stop()
    await service.stop()


app = FastAPI(
    title="NEXUS Analytics",
    description="Performance tracking and analytics service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])


@app.get("/")
async def root():
    return {"service": "analytics", "status": "running", "version": "1.0.0"}
