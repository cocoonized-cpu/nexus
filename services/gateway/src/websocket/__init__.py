"""WebSocket module for real-time communication."""

from src.websocket.manager import WebSocketManager
from src.websocket.routes import router as websocket_router

__all__ = ["WebSocketManager", "websocket_router"]
