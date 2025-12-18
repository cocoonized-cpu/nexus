"""
Opportunity Detector Service - Main Application.

Responsible for:
- Scanning for funding rate arbitrage opportunities
- Calculating Unified Opportunity Score (UOS) for each opportunity
- Filtering by configurable thresholds
- Publishing opportunity events for downstream services
- Persisting opportunities to database for API access
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.api import health, opportunities
from src.detector import OpportunityDetector

from shared.utils.config import get_settings
from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger
from shared.utils.redis_client import get_redis_client

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    logger.info("Starting Opportunity Detector service")

    # Initialize Redis connection
    redis = await get_redis_client()
    app.state.redis = redis

    # Initialize database connection
    database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://"
    ).replace("postgresql+asyncpg+asyncpg://", "postgresql+asyncpg://")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app.state.db_session = async_session

    # Initialize and start the opportunity detector with database
    detector = OpportunityDetector(redis, async_session)
    app.state.detector = detector

    # Start detection loop
    await detector.start()

    # Start heartbeat
    def get_health():
        return {
            "status": "healthy" if detector.is_running else "degraded",
            "details": {
                "active_opportunities": detector.active_opportunity_count,
                "detection_cycles": detector._stats.get("detection_cycles", 0),
            },
        }

    heartbeat = ServiceHeartbeat(
        service_name="opportunity-detector",
        redis_client=redis,
        health_check=get_health,
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    # Shutdown
    logger.info("Shutting down Opportunity Detector service")
    await heartbeat.stop()
    await detector.stop()
    await engine.dispose()


app = FastAPI(
    title="NEXUS Opportunity Detector",
    description="Funding rate arbitrage opportunity detection service",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(
    opportunities.router, prefix="/opportunities", tags=["opportunities"]
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "opportunity-detector",
        "status": "running",
        "version": "1.0.0",
    }
