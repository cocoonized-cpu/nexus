"""
NEXUS Gateway Service

Main FastAPI application providing REST API and WebSocket endpoints.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api import (analytics_router, blacklist_router, capital_router, config_router,
                     funding_router, health_router, logs_router, opportunities_router,
                     positions_router, risk_router, system_router)
from src.database import close_database, init_database
from src.websocket.manager import WebSocketManager
from src.websocket.routes import router as websocket_router

from shared.utils.config import get_settings
from shared.utils.heartbeat import ServiceHeartbeat
from shared.utils.logging import get_logger, setup_logging
from shared.utils.redis_client import get_redis_client
from src.services.position_sync import PositionSyncService

# Initialize logging
settings = get_settings()
setup_logging("gateway", level=settings.log_level, json_format=settings.log_json)
logger = get_logger(__name__)

# WebSocket manager singleton
ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    logger.info("Starting NEXUS Gateway service", version="0.1.0")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Initialize Redis
    redis = await get_redis_client()
    logger.info("Redis connected")

    # Initialize WebSocket manager
    await ws_manager.start()
    logger.info("WebSocket manager started")

    # Start Redis subscription listener
    asyncio.create_task(ws_manager.listen_to_events())

    # Start position sync service
    position_sync = PositionSyncService(redis_client=redis, sync_interval=30)
    await position_sync.start()
    app.state.position_sync = position_sync
    logger.info("Position sync service started")

    # Start heartbeat
    def get_health():
        return {
            "status": "healthy",
            "details": {
                "websocket_connections": ws_manager.connection_count if hasattr(ws_manager, 'connection_count') else 0,
            },
        }

    heartbeat = ServiceHeartbeat(
        service_name="gateway",
        redis_client=redis,
        health_check=get_health,
    )
    await heartbeat.start()
    app.state.heartbeat = heartbeat

    yield

    # Cleanup
    logger.info("Shutting down NEXUS Gateway service")
    await heartbeat.stop()
    await position_sync.stop()
    await ws_manager.stop()
    await close_database()


# Create FastAPI application
app = FastAPI(
    title="NEXUS Gateway",
    description="API Gateway for NEXUS Funding Rate Arbitrage System",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix="/api/v1", tags=["Health"])
app.include_router(
    opportunities_router, prefix="/api/v1/opportunities", tags=["Opportunities"]
)
app.include_router(positions_router, prefix="/api/v1/positions", tags=["Positions"])
app.include_router(risk_router, prefix="/api/v1/risk", tags=["Risk"])
app.include_router(capital_router, prefix="/api/v1/capital", tags=["Capital"])
app.include_router(config_router, prefix="/api/v1/config", tags=["Configuration"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(system_router, prefix="/api/v1/system", tags=["System"])
app.include_router(funding_router, prefix="/api/v1/funding", tags=["Funding"])
app.include_router(blacklist_router, prefix="/api/v1/blacklist", tags=["Blacklist"])
app.include_router(logs_router, prefix="/api/v1/system/logs", tags=["Logs"])
app.include_router(websocket_router, tags=["WebSocket"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            },
        },
    )


# Store WebSocket manager in app state for access in routes
app.state.ws_manager = ws_manager
