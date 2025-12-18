"""
Risk Manager Service - Enforces risk limits and monitors exposure.

Responsibilities:
- Enforce position and portfolio risk limits
- Monitor exposure across exchanges
- Track drawdown and trigger circuit breakers
- Validate trades before execution
- Generate risk alerts
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.api import health, risk
from src.manager import RiskManager

from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Risk Manager service")
    redis = await get_redis_client()
    app.state.redis = redis

    manager = RiskManager(redis)
    app.state.manager = manager
    await manager.start()

    heartbeat = ServiceHeartbeat(
        service_name="risk-manager",
        redis_client=redis,
        health_check=lambda: {"status": "healthy"},
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    logger.info("Shutting down Risk Manager service")
    await heartbeat.stop()
    await manager.stop()


app = FastAPI(
    title="NEXUS Risk Manager",
    description="Risk monitoring and enforcement service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(risk.router, prefix="/risk", tags=["risk"])


@app.get("/")
async def root():
    return {"service": "risk-manager", "status": "running", "version": "1.0.0"}
