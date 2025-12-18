"""
Docker Log Streaming API endpoints.
Provides real-time log streaming from Docker containers via SSE.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter()

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
    "error": ["error", "exception", "failed", "failure", "critical", "fatal"],
    "warning": ["warning", "warn", "attention", "caution"],
    "info": ["info", "started", "connected", "completed", "success"],
    "debug": ["debug", "trace", "verbose"],
}


class LogEntry(BaseModel):
    """Model for a log entry."""

    timestamp: datetime
    service: str
    level: str
    message: str
    container: str
    raw: str


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
    # Common formats: "2025-01-01 12:00:00 INFO message" or just "message"
    parts = line.split(" ", 3)
    timestamp = datetime.utcnow().isoformat()
    level = classify_log_level(line)
    message = line

    # Try to extract timestamp and level from common patterns
    if len(parts) >= 3:
        # Check if first two parts look like datetime
        try:
            potential_ts = f"{parts[0]} {parts[1]}"
            datetime.fromisoformat(potential_ts.replace("Z", "+00:00"))
            timestamp = potential_ts
            # Third part might be level
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
    container: str,
    tail: int = 100,
    since: Optional[str] = None,
) -> list[str]:
    """Get logs from a Docker container."""
    import subprocess

    cmd = ["docker", "logs", container, f"--tail={tail}"]
    if since:
        cmd.extend(["--since", since])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Docker logs go to stderr for some reason
        output = result.stdout + result.stderr
        return output.strip().split("\n") if output.strip() else []
    except subprocess.TimeoutExpired:
        return []
    except FileNotFoundError:
        # Docker not available
        return []
    except Exception:
        return []


async def stream_docker_logs(
    containers: list[str],
    services: list[str],
) -> AsyncGenerator[str, None]:
    """Stream logs from multiple Docker containers via SSE."""
    import subprocess

    processes: list[tuple[str, str, subprocess.Popen]] = []

    try:
        # Start a tail -f process for each container
        for container, service in zip(containers, services):
            try:
                proc = subprocess.Popen(
                    ["docker", "logs", container, "-f", "--tail=0"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                processes.append((container, service, proc))
            except Exception:
                continue

        if not processes:
            yield f"data: {json.dumps({'error': 'No containers available'})}\n\n"
            return

        # Stream logs from all processes
        while True:
            for container, service, proc in processes:
                if proc.stdout:
                    # Non-blocking read
                    import select

                    ready, _, _ = select.select([proc.stdout], [], [], 0.1)
                    if ready:
                        line = proc.stdout.readline()
                        if line:
                            log_entry = parse_log_line(line, service, container)
                            if log_entry:
                                yield f"data: {json.dumps(log_entry)}\n\n"

            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.1)

    finally:
        # Clean up processes
        for _, _, proc in processes:
            proc.terminate()
            proc.wait()


@router.get("/services")
async def list_available_services() -> dict[str, Any]:
    """
    List all available services for log streaming.
    """
    # Check which containers are actually running
    import subprocess

    available = []
    unavailable = []

    for service, container in SERVICE_CONTAINERS.items():
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and "true" in result.stdout.lower():
                available.append({"service": service, "container": container, "status": "running"})
            else:
                unavailable.append({"service": service, "container": container, "status": "stopped"})
        except Exception:
            unavailable.append({"service": service, "container": container, "status": "unknown"})

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
            # Apply level filter
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

    Connect to this endpoint with an EventSource to receive real-time logs.

    Example:
    ```javascript
    const eventSource = new EventSource('/api/v1/system/logs/stream?services=gateway,position-manager');
    eventSource.onmessage = (event) => {
        const log = JSON.parse(event.data);
        console.log(log);
    };
    ```
    """
    # Parse requested services
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
        async for log_data in stream_docker_logs(containers, service_names):
            # Apply level filter if specified
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
    # Parse requested services
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
