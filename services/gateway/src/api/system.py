"""
System control API endpoints.

Provides endpoints for controlling the NEXUS trading system:
- System status (running/stopped)
- Operating mode (discovery, conservative, standard, aggressive, emergency)
- Start/Stop trading
- Service health aggregation
- Service restart and logs
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

from shared.utils.redis_client import get_redis_client

router = APIRouter()


class SystemMode(BaseModel):
    """System operating mode."""
    mode: str  # discovery, conservative, standard, aggressive, emergency


class SystemStatus(BaseModel):
    """Complete system status."""
    is_running: bool
    mode: str
    new_positions_enabled: bool
    circuit_breaker_active: bool
    services_healthy: int
    services_total: int
    last_opportunity_detected: Optional[datetime] = None
    active_positions: int
    total_exposure_usd: float
    uptime_seconds: Optional[int] = None


class SystemControlRequest(BaseModel):
    """Request to control system state."""
    action: str  # start, stop, emergency_stop
    reason: Optional[str] = None


class ModeChangeRequest(BaseModel):
    """Request to change system mode."""
    mode: str  # discovery, conservative, standard, aggressive, emergency
    reason: Optional[str] = None


@router.get("/status")
async def get_system_status(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get comprehensive system status.

    Returns current operating state, mode, and health metrics.
    """
    # Get system settings
    settings_query = """
        SELECT key, value FROM config.system_settings
        WHERE key IN ('system_mode', 'new_positions_enabled', 'system_running', 'system_start_time')
    """
    result = await db.execute(text(settings_query))
    settings = {}
    for row in result.fetchall():
        if row[1] is not None:
            # Value is JSONB, already deserialized by SQLAlchemy
            # Just use the value directly - it's already a Python type
            settings[row[0]] = row[1]

    # Get circuit breaker status from risk snapshot
    risk_query = """
        SELECT risk_mode, circuit_breaker_active
        FROM (
            SELECT risk_mode,
                   CASE WHEN risk_mode = 'emergency' THEN true ELSE false END as circuit_breaker_active
            FROM risk.snapshots
            ORDER BY created_at DESC
            LIMIT 1
        ) r
    """
    risk_result = await db.execute(text(risk_query))
    risk_row = risk_result.fetchone()

    circuit_breaker_active = False
    if risk_row:
        circuit_breaker_active = risk_row[1] if risk_row[1] is not None else False

    # Get active positions count
    positions_query = """
        SELECT COUNT(*), COALESCE(SUM(total_capital_deployed), 0)
        FROM positions.active
        WHERE status IN ('active', 'opening')
    """
    pos_result = await db.execute(text(positions_query))
    pos_row = pos_result.fetchone()
    active_positions = pos_row[0] if pos_row else 0
    total_exposure = float(pos_row[1]) if pos_row and pos_row[1] else 0.0

    # Get last opportunity detection time
    opp_query = """
        SELECT detected_at FROM opportunities.detected
        ORDER BY detected_at DESC
        LIMIT 1
    """
    opp_result = await db.execute(text(opp_query))
    opp_row = opp_result.fetchone()
    last_opportunity = opp_row[0] if opp_row else None

    # Check service health via Redis
    services_healthy = 0
    services_total = 10  # Total number of services
    try:
        redis = await get_redis_client()
        for service in ['gateway', 'data-collector', 'funding-aggregator',
                       'opportunity-detector', 'execution-engine', 'position-manager',
                       'risk-manager', 'capital-allocator', 'analytics', 'notification']:
            health_key = f"nexus:health:{service}"
            health_data = await redis.client.get(health_key)
            if health_data:
                health = json.loads(health_data)
                if health.get('status') == 'healthy':
                    services_healthy += 1
    except Exception:
        pass  # Redis not available, services_healthy stays 0

    # Calculate uptime
    uptime_seconds = None
    if settings.get('system_start_time'):
        try:
            start_time = datetime.fromisoformat(settings['system_start_time'].replace('Z', '+00:00'))
            uptime_seconds = int((datetime.utcnow() - start_time.replace(tzinfo=None)).total_seconds())
        except Exception:
            pass

    status = SystemStatus(
        is_running=settings.get('system_running', False),
        mode=settings.get('system_mode', 'standard'),
        new_positions_enabled=settings.get('new_positions_enabled', True),
        circuit_breaker_active=circuit_breaker_active,
        services_healthy=services_healthy,
        services_total=services_total,
        last_opportunity_detected=last_opportunity,
        active_positions=active_positions,
        total_exposure_usd=total_exposure,
        uptime_seconds=uptime_seconds,
    )

    return {
        "success": True,
        "data": status.model_dump(),
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.post("/control")
async def control_system(
    request: SystemControlRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Control system operation (start/stop).

    Actions:
    - start: Enable trading and opportunity detection
    - stop: Gracefully stop new positions, let existing continue
    - emergency_stop: Immediately halt all trading, trigger position closes
    """
    valid_actions = ['start', 'stop', 'emergency_stop']
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}"
        )

    if request.action == 'start':
        # Enable system
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('system_running', 'true', 'System running state', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """))
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('system_start_time', :start_time, 'System start timestamp', NOW())
            ON CONFLICT (key) DO UPDATE SET value = :start_time, updated_at = NOW()
        """), {"start_time": json.dumps(datetime.utcnow().isoformat())})
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('new_positions_enabled', 'true', 'Allow new positions', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """))

        message = "System started successfully"

    elif request.action == 'stop':
        # Graceful stop - disable new positions but let existing run
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('new_positions_enabled', 'false', 'Allow new positions', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'false', updated_at = NOW()
        """))
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('system_running', 'false', 'System running state', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'false', updated_at = NOW()
        """))

        message = "System stopped gracefully. Existing positions will continue."

    else:  # emergency_stop
        # Emergency stop - halt everything
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('new_positions_enabled', 'false', 'Allow new positions', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'false', updated_at = NOW()
        """))
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('system_running', 'false', 'System running state', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'false', updated_at = NOW()
        """))
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('system_mode', '"emergency"', 'Operating mode', NOW())
            ON CONFLICT (key) DO UPDATE SET value = '"emergency"', updated_at = NOW()
        """))

        # Publish emergency event to Redis for other services
        try:
            redis = await get_redis_client()
            await redis.client.publish('nexus:system:emergency', json.dumps({
                'action': 'emergency_stop',
                'reason': request.reason or 'Manual emergency stop',
                'timestamp': datetime.utcnow().isoformat()
            }))
        except Exception:
            pass

        message = "EMERGENCY STOP activated. All trading halted."

    # Log the action
    await db.execute(text("""
        INSERT INTO audit.actions (actor, action_type, resource_type, details)
        VALUES ('user', :action, 'system', :details)
    """), {
        "action": f"system_{request.action}",
        "details": json.dumps({"reason": request.reason})
    })

    await db.commit()

    return {
        "success": True,
        "message": message,
        "action": request.action,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/mode")
async def change_system_mode(
    request: ModeChangeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Change system operating mode.

    Modes:
    - discovery: Only detect opportunities, no trading
    - conservative: Trade only highest-confidence opportunities
    - standard: Normal trading parameters
    - aggressive: Accept lower-scoring opportunities
    - emergency: Halt new positions, manage existing
    """
    valid_modes = ['discovery', 'conservative', 'standard', 'aggressive', 'emergency']
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Must be one of: {valid_modes}"
        )

    # Get previous mode
    result = await db.execute(text(
        "SELECT value FROM config.system_settings WHERE key = 'system_mode'"
    ))
    row = result.fetchone()
    previous_mode = row[0] if row and row[0] else 'standard'

    # Update mode
    await db.execute(text("""
        INSERT INTO config.system_settings (key, value, description, updated_at)
        VALUES ('system_mode', :mode, 'Operating mode', NOW())
        ON CONFLICT (key) DO UPDATE SET value = :mode, updated_at = NOW()
    """), {"mode": json.dumps(request.mode)})

    # If switching to emergency, disable new positions
    if request.mode == 'emergency':
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('new_positions_enabled', 'false', 'Allow new positions', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'false', updated_at = NOW()
        """))
    # If switching from emergency, re-enable new positions
    elif previous_mode == 'emergency':
        await db.execute(text("""
            INSERT INTO config.system_settings (key, value, description, updated_at)
            VALUES ('new_positions_enabled', 'true', 'Allow new positions', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """))

    # Log the change
    await db.execute(text("""
        INSERT INTO audit.actions (actor, action_type, resource_type, details)
        VALUES ('user', 'mode_change', 'system', :details)
    """), {
        "details": json.dumps({
            "previous_mode": previous_mode,
            "new_mode": request.mode,
            "reason": request.reason
        })
    })

    # Publish mode change event
    try:
        redis = await get_redis_client()
        await redis.client.publish('nexus:system:mode_changed', json.dumps({
            'previous_mode': previous_mode,
            'new_mode': request.mode,
            'reason': request.reason,
            'timestamp': datetime.utcnow().isoformat()
        }))
    except Exception:
        pass

    await db.commit()

    return {
        "success": True,
        "message": f"Mode changed from {previous_mode} to {request.mode}",
        "previous_mode": previous_mode,
        "current_mode": request.mode,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/services")
async def get_services_health(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get health status of all NEXUS services.
    """
    services = [
        {'name': 'gateway', 'display_name': 'API Gateway', 'critical': True},
        {'name': 'data-collector', 'display_name': 'Data Collector', 'critical': True},
        {'name': 'funding-aggregator', 'display_name': 'Funding Aggregator', 'critical': True},
        {'name': 'opportunity-detector', 'display_name': 'Opportunity Detector', 'critical': True},
        {'name': 'execution-engine', 'display_name': 'Execution Engine', 'critical': True},
        {'name': 'position-manager', 'display_name': 'Position Manager', 'critical': True},
        {'name': 'risk-manager', 'display_name': 'Risk Manager', 'critical': True},
        {'name': 'capital-allocator', 'display_name': 'Capital Allocator', 'critical': False},
        {'name': 'analytics', 'display_name': 'Analytics', 'critical': False},
        {'name': 'notification', 'display_name': 'Notification', 'critical': False},
    ]

    service_statuses = []

    try:
        redis = await get_redis_client()
        for service in services:
            health_key = f"nexus:health:{service['name']}"
            health_data = await redis.client.get(health_key)

            if health_data:
                health = json.loads(health_data)
                service_statuses.append({
                    'name': service['name'],
                    'display_name': service['display_name'],
                    'status': health.get('status', 'unknown'),
                    'last_heartbeat': health.get('timestamp'),
                    'uptime_seconds': health.get('uptime_seconds'),
                    'critical': service['critical'],
                    'details': health.get('details', {}),
                })
            else:
                service_statuses.append({
                    'name': service['name'],
                    'display_name': service['display_name'],
                    'status': 'offline',
                    'last_heartbeat': None,
                    'uptime_seconds': None,
                    'critical': service['critical'],
                    'details': {},
                })
    except Exception as e:
        # Redis not available - mark all services as unknown
        for service in services:
            service_statuses.append({
                'name': service['name'],
                'display_name': service['display_name'],
                'status': 'unknown',
                'last_heartbeat': None,
                'uptime_seconds': None,
                'critical': service['critical'],
                'details': {'error': str(e)},
            })

    return {
        "success": True,
        "data": service_statuses,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/events")
async def get_recent_events(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get recent system events for activity feed.
    """
    # Combine events from multiple sources
    # Use a subquery to gather all events, then sort and limit at the outer level
    events_query = """
        SELECT source, event_type, resource_type, details, created_at
        FROM (
            SELECT
                'audit' as source,
                action_type as event_type,
                resource_type,
                details,
                created_at
            FROM audit.actions
            WHERE created_at > NOW() - INTERVAL '7 days'

            UNION ALL

            SELECT
                'opportunity' as source,
                'opportunity_detected' as event_type,
                symbol as resource_type,
                jsonb_build_object('uos_score', uos_score, 'net_apr', net_apr) as details,
                detected_at as created_at
            FROM opportunities.detected
            WHERE detected_at > NOW() - INTERVAL '1 day'

            UNION ALL

            SELECT
                'risk' as source,
                alert_type as event_type,
                COALESCE(symbol, exchange, 'system') as resource_type,
                jsonb_build_object('severity', severity, 'message', message) as details,
                created_at
            FROM risk.alerts
            WHERE resolved_at IS NULL

            UNION ALL

            SELECT
                'position' as source,
                event_type,
                COALESCE(symbol, 'unknown') as resource_type,
                details,
                created_at
            FROM positions.events
            WHERE created_at > NOW() - INTERVAL '7 days'

            UNION ALL

            SELECT
                'execution' as source,
                event_type,
                COALESCE(symbol, exchange, 'system') as resource_type,
                COALESCE(details, '{}'::jsonb) as details,
                created_at
            FROM audit.execution_events
            WHERE created_at > NOW() - INTERVAL '7 days'
        ) combined
        ORDER BY created_at DESC
        LIMIT :limit
    """

    result = await db.execute(text(events_query), {"limit": limit})
    rows = result.fetchall()

    events = [
        {
            'source': row[0],
            'event_type': row[1],
            'resource': row[2],
            'details': row[3],
            'timestamp': row[4].isoformat() if row[4] else None,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": events,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


# Valid service names for restart/logs operations
VALID_SERVICES = [
    'gateway', 'data-collector', 'funding-aggregator',
    'opportunity-detector', 'execution-engine', 'position-manager',
    'risk-manager', 'capital-allocator', 'analytics', 'notification'
]


@router.post("/services/{service_name}/restart")
async def restart_service(
    service_name: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Restart a specific NEXUS service using Docker Compose.

    This endpoint triggers a restart of the specified service container.
    Use with caution as it may temporarily disrupt service operations.
    """
    if service_name not in VALID_SERVICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service name. Must be one of: {VALID_SERVICES}"
        )

    try:
        # Run docker compose restart asynchronously
        process = await asyncio.create_subprocess_exec(
            'docker', 'compose', 'restart', service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        success = process.returncode == 0

        # Log the restart action
        await db.execute(text("""
            INSERT INTO audit.actions (actor, action_type, resource_type, details)
            VALUES ('user', 'service_restart', :service, :details)
        """), {
            "service": service_name,
            "details": json.dumps({
                "success": success,
                "return_code": process.returncode,
                "stdout": stdout.decode()[:500] if stdout else None,
                "stderr": stderr.decode()[:500] if stderr else None,
            })
        })
        await db.commit()

        if success:
            return {
                "success": True,
                "message": f"Service '{service_name}' restarted successfully",
                "service": service_name,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restart service: {stderr.decode()[:200] if stderr else 'Unknown error'}"
            )

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Restart operation timed out for service '{service_name}'"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Docker Compose is not available on this system"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart service: {str(e)}"
        )


@router.get("/services/{service_name}/logs")
async def get_service_logs(
    service_name: str,
    lines: int = Query(100, ge=1, le=500, description="Number of log lines to retrieve"),
) -> dict[str, Any]:
    """
    Get recent logs from a specific NEXUS service.

    Returns the last N lines of logs from the service container via Docker API.
    """
    if service_name not in VALID_SERVICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service name. Must be one of: {VALID_SERVICES}"
        )

    try:
        import docker
        from docker.errors import NotFound, APIError

        # Connect to Docker via socket
        client = docker.from_env()

        # Find the container by name (docker compose names containers as nexus-{service_name})
        container_name = f"nexus-{service_name}"

        try:
            container = client.containers.get(container_name)
        except NotFound:
            raise HTTPException(
                status_code=404,
                detail=f"Container '{container_name}' not found"
            )

        # Get logs from container
        log_output = container.logs(tail=lines, timestamps=True).decode('utf-8', errors='replace')
        log_lines = [line.strip() for line in log_output.split('\n') if line.strip()]

        return {
            "success": True,
            "data": {
                "service": service_name,
                "lines": log_lines,
                "count": len(log_lines),
            },
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Docker SDK not available"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get logs: {str(e)}"
        )


# ============================================================================
# Spread Monitoring Settings API
# ============================================================================


class SpreadMonitoringSettingsRequest(BaseModel):
    """Request model for spread monitoring settings."""
    spread_drawdown_exit_pct: float
    min_time_to_funding_exit_seconds: int


@router.get("/settings/spread-monitoring")
async def get_spread_monitoring_settings(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get current spread monitoring guardrail settings.

    These settings control when positions auto-exit due to spread deterioration.
    """
    query = """
        SELECT spread_drawdown_exit_pct, min_time_to_funding_exit_seconds
        FROM config.strategy_parameters
        WHERE is_active = true
        LIMIT 1
    """
    result = await db.execute(text(query))
    row = result.fetchone()

    if row:
        return {
            "spread_drawdown_exit_pct": float(row[0]) if row[0] else 50.0,
            "min_time_to_funding_exit_seconds": int(row[1]) if row[1] else 1800,
        }
    else:
        # Return defaults if no config exists
        return {
            "spread_drawdown_exit_pct": 50.0,
            "min_time_to_funding_exit_seconds": 1800,
        }


@router.put("/settings/spread-monitoring")
async def update_spread_monitoring_settings(
    body: SpreadMonitoringSettingsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update spread monitoring guardrail settings.

    - spread_drawdown_exit_pct: Exit when spread drops by this % from entry (10-90)
    - min_time_to_funding_exit_seconds: Don't auto-exit if funding is due within this time
    """
    # Validate ranges
    if not (10 <= body.spread_drawdown_exit_pct <= 90):
        raise HTTPException(
            status_code=400,
            detail="spread_drawdown_exit_pct must be between 10 and 90"
        )
    if not (0 <= body.min_time_to_funding_exit_seconds <= 3600):
        raise HTTPException(
            status_code=400,
            detail="min_time_to_funding_exit_seconds must be between 0 and 3600"
        )

    await db.execute(
        text("""
            UPDATE config.strategy_parameters
            SET spread_drawdown_exit_pct = :drawdown,
                min_time_to_funding_exit_seconds = :funding_time,
                updated_at = NOW()
            WHERE is_active = true
        """),
        {
            "drawdown": body.spread_drawdown_exit_pct,
            "funding_time": body.min_time_to_funding_exit_seconds,
        },
    )
    await db.commit()

    # Publish config update event for Position Manager to reload
    try:
        redis = await get_redis_client()
        await redis.client.publish(
            "nexus:config:strategy_updated",
            json.dumps({"updated": "spread_monitoring", "timestamp": datetime.utcnow().isoformat()})
        )
    except Exception:
        pass  # Non-critical if Redis publish fails

    return {
        "success": True,
        "message": "Spread monitoring settings updated",
        "settings": {
            "spread_drawdown_exit_pct": body.spread_drawdown_exit_pct,
            "min_time_to_funding_exit_seconds": body.min_time_to_funding_exit_seconds,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Max Concurrent Coins Settings API
# ============================================================================


class MaxConcurrentCoinsRequest(BaseModel):
    """Request model for max concurrent coins setting."""
    max_concurrent_coins: int


class MaxConcurrentCoinsResponse(BaseModel):
    """Response model for max concurrent coins setting."""
    max_concurrent_coins: int
    current_coins: int
    at_limit: bool


@router.get("/settings/max-concurrent-coins", response_model=MaxConcurrentCoinsResponse)
async def get_max_concurrent_coins(
    db: AsyncSession = Depends(get_db),
) -> MaxConcurrentCoinsResponse:
    """
    Get max concurrent coins setting and current active count.

    Max concurrent coins limits how many unique coins can have open arbitrage positions.
    Each coin = 2 exchange positions (1 long + 1 short leg).
    """
    # Get setting from database
    query = """
        SELECT max_concurrent_coins
        FROM config.strategy_parameters
        WHERE is_active = true
        LIMIT 1
    """
    result = await db.execute(text(query))
    row = result.fetchone()
    max_coins = int(row[0]) if row and row[0] else 5

    # Get current active coin count (unique symbols with active positions)
    count_query = """
        SELECT COUNT(DISTINCT symbol)
        FROM positions.active
        WHERE status IN ('active', 'opening')
    """
    count_result = await db.execute(text(count_query))
    current_coins = count_result.scalar() or 0

    return MaxConcurrentCoinsResponse(
        max_concurrent_coins=max_coins,
        current_coins=current_coins,
        at_limit=current_coins >= max_coins,
    )


@router.put("/settings/max-concurrent-coins")
async def update_max_concurrent_coins(
    body: MaxConcurrentCoinsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update max concurrent coins setting.

    Controls maximum number of unique coins that can have open arbitrage positions.
    Valid range: 1-20 coins.
    """
    # Validate range
    if not (1 <= body.max_concurrent_coins <= 20):
        raise HTTPException(
            status_code=400,
            detail="max_concurrent_coins must be between 1 and 20"
        )

    await db.execute(
        text("""
            UPDATE config.strategy_parameters
            SET max_concurrent_coins = :value,
                updated_at = NOW()
            WHERE is_active = true
        """),
        {"value": body.max_concurrent_coins},
    )
    await db.commit()

    # Publish config update event for Capital Allocator to reload
    try:
        redis = await get_redis_client()
        await redis.client.publish(
            "nexus:config:strategy_updated",
            json.dumps({
                "updated": "max_concurrent_coins",
                "value": body.max_concurrent_coins,
                "timestamp": datetime.utcnow().isoformat(),
            })
        )
    except Exception:
        pass  # Non-critical if Redis publish fails

    # Log the action
    await db.execute(text("""
        INSERT INTO audit.actions (actor, action_type, resource_type, details)
        VALUES ('user', 'settings_update', 'max_concurrent_coins', :details)
    """), {
        "details": json.dumps({"max_concurrent_coins": body.max_concurrent_coins})
    })
    await db.commit()

    return {
        "success": True,
        "message": f"Max concurrent coins updated to {body.max_concurrent_coins}",
        "max_concurrent_coins": body.max_concurrent_coins,
        "timestamp": datetime.utcnow().isoformat(),
    }
