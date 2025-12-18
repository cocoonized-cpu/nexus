"""
WebSocket routes for real-time communication.
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for real-time updates.

    Protocol:
    - Client connects to /ws
    - Server sends: {"event": "connected", "client_id": "...", "timestamp": "..."}
    - Client subscribes: {"action": "subscribe", "channel": "funding_rates"}
    - Server confirms: {"event": "subscribed", "channel": "funding_rates", "timestamp": "..."}
    - Server pushes updates: {"event": "funding_rate.update", "channel": "funding_rates", "data": {...}, "timestamp": "..."}
    - Client unsubscribes: {"action": "unsubscribe", "channel": "funding_rates"}
    - Client sends ping: {"action": "ping"}
    - Server responds: {"event": "pong", "timestamp": "..."}

    Available channels:
    - funding_rates: Real-time funding rate updates
    - opportunities: Opportunity detection and scoring updates
    - positions: Position status and P&L updates
    - risk: Risk alerts and state changes
    - capital: Capital allocation updates
    - system: System events and health status
    """
    # Get WebSocket manager from app state
    ws_manager = websocket.app.state.ws_manager

    # Accept connection and get client ID
    client_id = await ws_manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,  # 60 second timeout for heartbeat
                )
            except asyncio.TimeoutError:
                # Send ping on timeout
                await ws_manager.send_to_client(client_id, {"event": "ping"})
                continue

            # Parse message
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await ws_manager.send_to_client(
                    client_id,
                    {
                        "event": "error",
                        "message": "Invalid JSON",
                    },
                )
                continue

            # Handle message
            await handle_client_message(ws_manager, client_id, message)

    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected", client=client_id)
    except Exception as e:
        # Only log actual errors, not connection closures
        error_str = str(e)
        if "not connected" not in error_str.lower() and "closed" not in error_str.lower():
            logger.error("WebSocket error", error=error_str, client=client_id)
    finally:
        await ws_manager.disconnect(client_id)


async def handle_client_message(
    ws_manager: Any, client_id: str, message: dict[str, Any]
) -> None:
    """Handle a message from a WebSocket client."""
    action = message.get("action")

    if action == "subscribe":
        channel = message.get("channel")
        if channel:
            await ws_manager.subscribe(client_id, channel)
        else:
            await ws_manager.send_to_client(
                client_id,
                {
                    "event": "error",
                    "message": "Missing channel parameter",
                },
            )

    elif action == "unsubscribe":
        channel = message.get("channel")
        if channel:
            await ws_manager.unsubscribe(client_id, channel)
        else:
            await ws_manager.send_to_client(
                client_id,
                {
                    "event": "error",
                    "message": "Missing channel parameter",
                },
            )

    elif action == "ping":
        await ws_manager.send_to_client(client_id, {"event": "pong"})

    elif action == "get_channels":
        # Return list of available channels
        await ws_manager.send_to_client(
            client_id,
            {
                "event": "channels",
                "data": [
                    {
                        "name": "funding_rates",
                        "description": "Real-time funding rate updates",
                    },
                    {
                        "name": "opportunities",
                        "description": "Opportunity detection and scoring updates",
                    },
                    {
                        "name": "positions",
                        "description": "Position status and P&L updates",
                    },
                    {
                        "name": "risk",
                        "description": "Risk alerts and state changes",
                    },
                    {
                        "name": "capital",
                        "description": "Capital allocation updates",
                    },
                    {
                        "name": "system",
                        "description": "System events and health status",
                    },
                ],
            },
        )

    elif action == "get_stats":
        # Return connection statistics
        stats = ws_manager.get_stats()
        await ws_manager.send_to_client(
            client_id,
            {
                "event": "stats",
                "data": stats,
            },
        )

    else:
        await ws_manager.send_to_client(
            client_id,
            {
                "event": "error",
                "message": f"Unknown action: {action}",
            },
        )
