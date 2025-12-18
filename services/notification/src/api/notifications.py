"""Notification endpoints."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class SendNotificationRequest(BaseModel):
    channel: str  # telegram, discord, email, webhook
    title: str
    message: str
    level: str = "info"  # info, warning, critical


@router.post("/send")
async def send_notification(
    request: Request, body: SendNotificationRequest
) -> dict[str, Any]:
    service = request.app.state.service
    result = await service.send(body.channel, body.title, body.message, body.level)
    return {"success": result, "timestamp": datetime.utcnow().isoformat()}


@router.get("/history")
async def get_history(request: Request, limit: int = 50) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "success": True,
        "data": service.get_history(limit),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/channels")
async def get_channels(request: Request) -> dict[str, Any]:
    service = request.app.state.service
    return {
        "success": True,
        "data": service.get_channels(),
        "timestamp": datetime.utcnow().isoformat(),
    }
