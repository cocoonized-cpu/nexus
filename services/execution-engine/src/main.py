"""
Execution Engine Service - Main Application.

Responsible for:
- Executing trades across exchanges
- Managing order lifecycle (place, monitor, fill, cancel)
- Handling order failures and retries
- Publishing execution events
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.api import health, orders
from src.engine import ExecutionEngine

from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    logger.info("Starting Execution Engine service")

    redis = await get_redis_client()
    app.state.redis = redis

    engine = ExecutionEngine(redis)
    app.state.engine = engine

    await engine.start()

    heartbeat = ServiceHeartbeat(
        service_name="execution-engine",
        redis_client=redis,
        health_check=lambda: {"status": "healthy"},
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    logger.info("Shutting down Execution Engine service")
    await heartbeat.stop()
    await engine.stop()


app = FastAPI(
    title="NEXUS Execution Engine",
    description="Order execution and management service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(orders.router, prefix="/orders", tags=["orders"])


@app.get("/")
async def root():
    return {"service": "execution-engine", "status": "running", "version": "1.0.0"}
