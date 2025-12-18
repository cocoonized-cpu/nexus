"""
Docker Log Streaming API endpoints.
Provides real-time log streaming from Docker containers via SSE using Docker SDK.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

import docker
from docker.errors import NotFound, APIError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter()

# Initialize Docker client
try:
    docker_client = docker.from_env()
except Exception as e:
    docker_client = None
    print(f"Warning: Could not initialize Docker client: {e}")

# Service name to Docker container name mapping
SERVICE_CONTAINERS = {
    "gateway": "nexus-gateway",
    "data-collector": "nexus-data-collector",
    "funding-aggregator": "nexus-funding-aggregator",
    "opportunity-detector": "nexus-opportunity-detector",
    "execution-engine": "nexus-execution-engine",
    "position-manager": "nexus-position-manager",
    "risk-manager": "nexus-risk-manager",
    "capital-allocator": "nexus-capital-allocator",
    "analytics": "nexus-analytics",
    "notification": "nexus-notification",
    "frontend": "nexus-frontend",
    "postgres": "nexus-postgres",
    "redis": "nexus-redis",
}

# Severity keywords for log classification
SEVERITY_KEYWORDS = {
    "error": ["error", "exception", "failed", "failure", "critical", "fatal", "traceback"],
    "warning": ["warning", "warn", "attention", "caution"],
    "info": ["info", "started", "connected", "completed", "success", "running"],
    "debug": ["debug", "trace", "verbose"],
}


class LogHistoryResponse(BaseModel):
    """Response model for log history."""

    success: bool = True
    data: list[dict[str, Any]]
    meta: dict[str, Any] = Field(default_factory=dict)


def classify_log_level(message: str) -> str:
    """Classify log level based on message content."""
    message_lower = message.lower()
    for level, keywords in SEVERITY_KEYWORDS.items():
        if any(keyword in message_lower for keyword in keywords):
            return level
    return "info"


def parse_log_line(line: str, service: str, container: str) -> Optional[dict[str, Any]]:
    """Parse a log line into a structured format."""
    if not line.strip():
        return None

    # Try to parse as JSON (structured log)
    try:
        log_data = json.loads(line)
        return {
            "timestamp": log_data.get("timestamp", datetime.utcnow().isoformat()),
            "service": service,
            "level": log_data.get("level", log_data.get("severity", "info")).lower(),
            "message": log_data.get("message", log_data.get("msg", line)),
            "container": container,
            "details": {
                k: v
                for k, v in log_data.items()
                if k not in ["timestamp", "level", "severity", "message", "msg"]
            },
        }
    except (json.JSONDecodeError, TypeError):
        pass

    # Parse as plain text
    timestamp = datetime.utcnow().isoformat()
    level = classify_log_level(line)
    message = line

    # Try to extract timestamp and level from common patterns
    parts = line.split(" ", 3)
    if len(parts) >= 3:
        try:
            potential_ts = f"{parts[0]} {parts[1]}"
            datetime.fromisoformat(potential_ts.replace("Z", "+00:00"))
            timestamp = potential_ts
            if parts[2].upper() in ["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"]:
                level = parts[2].lower()
                message = parts[3] if len(parts) > 3 else ""
            else:
                message = " ".join(parts[2:])
        except (ValueError, IndexError):
            pass

    return {
        "timestamp": timestamp,
        "service": service,
        "level": level,
        "message": message.strip(),
        "container": container,
        "details": {},
    }


async def get_docker_logs(
    container_name: str,
    tail: int = 100,
    since: Optional[str] = None,
) -> list[str]:
    """Get logs from a Docker container using Docker SDK."""
    if not docker_client:
        return []

    try:
        container = docker_client.containers.get(container_name)

        # Parse since parameter
        since_param = None
        if since:
            # Handle formats like "10m", "1h", "30s"
            import re
            match = re.match(r"(\d+)([smh])", since)
            if match:
                value, unit = int(match.group(1)), match.group(2)
                from datetime import timedelta
                if unit == "s":
                    delta = timedelta(seconds=value)
                elif unit == "m":
                    delta = timedelta(minutes=value)
                elif unit == "h":
                    delta = timedelta(hours=value)
                since_param = (datetime.utcnow() - delta).isoformat()

        # Get logs
        logs = container.logs(
            tail=tail,
            since=since_param,
            timestamps=False,
            stream=False,
        )

        # Decode and split
        if isinstance(logs, bytes):
            logs = logs.decode("utf-8", errors="replace")

        return logs.strip().split("\n") if logs.strip() else []

    except NotFound:
        return []
    except APIError as e:
        print(f"Docker API error for {container_name}: {e}")
        return []
    except Exception as e:
        print(f"Error getting logs for {container_name}: {e}")
        return []


async def stream_docker_logs_generator(
    containers: list[str],
    services: list[str],
) -> AsyncGenerator[str, None]:
    """Stream logs from multiple Docker containers via SSE using Docker SDK."""
    if not docker_client:
        yield f"data: {json.dumps({'error': 'Docker client not available'})}\n\n"
        return

    # Get container objects and start streaming
    streams = []
    for container_name, service in zip(containers, services):
        try:
            container = docker_client.containers.get(container_name)
            # Get a streaming generator for logs
            log_stream = container.logs(
                stream=True,
                follow=True,
                tail=0,
                timestamps=False,
            )
            streams.append((container_name, service, log_stream))
        except NotFound:
            continue
        except Exception as e:
            print(f"Error setting up stream for {container_name}: {e}")
            continue

    if not streams:
        yield f"data: {json.dumps({'error': 'No containers available for streaming'})}\n\n"
        return

    try:
        # Stream from all containers
        while True:
            for container_name, service, log_stream in streams:
                try:
                    # Non-blocking check - use iterator with timeout
                    for line in log_stream:
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="replace")
                        line = line.strip()
                        if line:
                            log_entry = parse_log_line(line, service, container_name)
                            if log_entry:
                                yield f"data: {json.dumps(log_entry)}\n\n"
                        break  # Process one line per iteration
                except StopIteration:
                    continue
                except Exception:
                    continue

            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        # Clean up streams
        for _, _, stream in streams:
            try:
                stream.close()
            except Exception:
                pass


# IMPORTANT: Specific routes MUST come before the catch-all /{service} route


@router.get("/services")
async def list_available_services() -> dict[str, Any]:
    """
    List all available services for log streaming.
    """
    if not docker_client:
        return {
            "success": False,
            "error": "Docker client not available",
            "data": {"available": [], "unavailable": []},
        }

    available = []
    unavailable = []

    for service, container_name in SERVICE_CONTAINERS.items():
        try:
            container = docker_client.containers.get(container_name)
            if container.status == "running":
                available.append({
                    "service": service,
                    "container": container_name,
                    "status": "running",
                })
            else:
                unavailable.append({
                    "service": service,
                    "container": container_name,
                    "status": container.status,
                })
        except NotFound:
            unavailable.append({
                "service": service,
                "container": container_name,
                "status": "not_found",
            })
        except Exception as e:
            unavailable.append({
                "service": service,
                "container": container_name,
                "status": f"error: {str(e)}",
            })

    return {
        "success": True,
        "data": {
            "available": available,
            "unavailable": unavailable,
        },
        "meta": {
            "total_services": len(SERVICE_CONTAINERS),
            "running": len(available),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.get("/stream")
async def stream_logs(
    request: Request,
    services: Optional[str] = Query(
        None,
        description="Comma-separated list of services to stream (default: all)",
    ),
    level: Optional[str] = Query(None, description="Filter by log level"),
):
    """
    Stream logs from services via Server-Sent Events (SSE).
    """
    if services:
        requested = [s.strip() for s in services.split(",")]
        invalid = [s for s in requested if s not in SERVICE_CONTAINERS]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid services: {invalid}. Available: {list(SERVICE_CONTAINERS.keys())}",
            )
        containers = [SERVICE_CONTAINERS[s] for s in requested]
        service_names = requested
    else:
        containers = list(SERVICE_CONTAINERS.values())
        service_names = list(SERVICE_CONTAINERS.keys())

    async def generate():
        async for log_data in stream_docker_logs_generator(containers, service_names):
            if level:
                try:
                    log_entry = json.loads(log_data.replace("data: ", "").strip())
                    if log_entry.get("level") != level.lower():
                        continue
                except Exception:
                    pass
            yield log_data

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/aggregate")
async def get_aggregate_logs(
    tail: int = Query(50, le=500, description="Number of lines per service"),
    services: Optional[str] = Query(None, description="Comma-separated list of services"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    since: Optional[str] = Query(None, description="Show logs since timestamp"),
) -> LogHistoryResponse:
    """
    Get aggregated logs from multiple services, sorted by timestamp.
    """
    if not docker_client:
        return LogHistoryResponse(
            success=False,
            data=[],
            meta={"error": "Docker client not available"},
        )

    if services:
        requested = [s.strip() for s in services.split(",")]
        invalid = [s for s in requested if s not in SERVICE_CONTAINERS]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid services: {invalid}",
            )
        service_list = requested
    else:
        # Default to core services
        service_list = [
            "gateway",
            "opportunity-detector",
            "position-manager",
            "execution-engine",
            "funding-aggregator",
            "data-collector",
        ]

    all_logs = []
    for service in service_list:
        container = SERVICE_CONTAINERS[service]
        lines = await get_docker_logs(container, tail, since)

        for line in lines:
            log_entry = parse_log_line(line, service, container)
            if log_entry:
                if level and log_entry["level"] != level.lower():
                    continue
                all_logs.append(log_entry)

    # Sort by timestamp (newest first)
    all_logs.sort(key=lambda x: x["timestamp"], reverse=True)

    # Limit total results
    all_logs = all_logs[:tail * 2]

    return LogHistoryResponse(
        data=all_logs,
        meta={
            "services": service_list,
            "count": len(all_logs),
            "level_filter": level,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# This catch-all route MUST be last
@router.get("/{service}")
async def get_service_logs(
    service: str,
    tail: int = Query(100, le=1000, description="Number of lines to return"),
    since: Optional[str] = Query(None, description="Show logs since timestamp (e.g., '10m', '1h')"),
    level: Optional[str] = Query(None, description="Filter by log level"),
) -> LogHistoryResponse:
    """
    Get recent logs from a specific service.
    """
    if service not in SERVICE_CONTAINERS:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service}' not found. Available: {list(SERVICE_CONTAINERS.keys())}",
        )

    container = SERVICE_CONTAINERS[service]
    lines = await get_docker_logs(container, tail, since)

    logs = []
    for line in lines:
        log_entry = parse_log_line(line, service, container)
        if log_entry:
            if level and log_entry["level"] != level.lower():
                continue
            logs.append(log_entry)

    return LogHistoryResponse(
        data=logs,
        meta={
            "service": service,
            "container": container,
            "count": len(logs),
            "tail": tail,
            "level_filter": level,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
