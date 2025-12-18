"""
Notification Service - Sends alerts via multiple channels.

Supported channels:
- Telegram
- Discord
- Email
- Webhook
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from src.api import health, notifications
from src.service import NotificationService

from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Notification service")
    redis = await get_redis_client()
    app.state.redis = redis

    service = NotificationService(redis)
    app.state.service = service
    await service.start()

    heartbeat = ServiceHeartbeat(
        service_name="notification",
        redis_client=redis,
        health_check=lambda: {"status": "healthy"},
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    logger.info("Shutting down Notification service")
    await heartbeat.stop()
    await service.stop()


app = FastAPI(
    title="NEXUS Notification",
    description="Alert and notification service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(
    notifications.router, prefix="/notifications", tags=["notifications"]
)


@app.get("/")
async def root():
    return {"service": "notification", "status": "running", "version": "1.0.0"}
