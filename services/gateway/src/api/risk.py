"""
Risk API endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

router = APIRouter()


class RiskStateResponse(BaseModel):
    """Response model for risk state."""

    total_capital_usd: Decimal
    total_exposure_usd: Decimal
    gross_exposure_pct: Decimal
    net_exposure_pct: Decimal
    current_drawdown_pct: Decimal
    peak_equity: Decimal
    current_equity: Decimal
    var_budget_used_pct: Decimal
    drawdown_budget_remaining_pct: Decimal
    positions_total: int
    positions_healthy: int
    positions_attention: int
    positions_warning: int
    positions_critical: int
    risk_mode: str
    active_alerts: int
    critical_alerts: int
    venue_exposures: dict[str, Decimal]
    asset_exposures: dict[str, Decimal]


class RiskLimitsResponse(BaseModel):
    """Response model for risk limits."""

    max_position_size_usd: Decimal
    max_position_size_pct: Decimal
    max_leverage: Decimal
    max_venue_exposure_pct: Decimal
    max_asset_exposure_pct: Decimal
    max_gross_exposure_pct: Decimal
    max_net_exposure_pct: Decimal
    max_drawdown_pct: Decimal
    max_var_pct: Decimal
    max_delta_exposure_pct: Decimal
    min_liquidation_distance_pct: Decimal
    max_margin_utilization_pct: Decimal


class RiskAlertResponse(BaseModel):
    """Response model for risk alert."""

    id: str
    alert_type: str
    severity: str
    title: str
    message: str
    position_id: Optional[str]
    exchange: Optional[str]
    current_value: Optional[Decimal]
    threshold_value: Optional[Decimal]
    created_at: datetime
    acknowledged_at: Optional[datetime]


class UpdateRiskModeRequest(BaseModel):
    """Request model for updating risk mode."""

    mode: str = Field(
        ...,
        description="Risk mode: discovery, conservative, standard, aggressive, emergency",
    )


class UpdateRiskLimitsRequest(BaseModel):
    """Request model for updating risk limits."""

    max_position_size_usd: Optional[Decimal] = None
    max_position_size_pct: Optional[Decimal] = None
    max_leverage: Optional[Decimal] = None
    max_venue_exposure_pct: Optional[Decimal] = None
    max_asset_exposure_pct: Optional[Decimal] = None
    max_gross_exposure_pct: Optional[Decimal] = None
    max_net_exposure_pct: Optional[Decimal] = None
    max_drawdown_pct: Optional[Decimal] = None
    max_var_pct: Optional[Decimal] = None
    max_delta_exposure_pct: Optional[Decimal] = None
    min_liquidation_distance_pct: Optional[Decimal] = None
    max_margin_utilization_pct: Optional[Decimal] = None
    max_total_exposure_usd: Optional[Decimal] = None
    max_exchange_exposure_usd: Optional[Decimal] = None


@router.get("/state")
async def get_risk_state(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get current risk state.
    """
    # Get latest risk snapshot
    query = """
        SELECT
            total_capital_usd, total_exposure_usd, gross_exposure_pct, net_exposure_pct,
            current_drawdown_pct, peak_equity, current_equity,
            var_budget_used_pct, drawdown_budget_remaining_pct,
            positions_total, positions_healthy, positions_attention, positions_warning, positions_critical,
            risk_mode, active_alerts, critical_alerts,
            venue_exposures, asset_exposures
        FROM risk.snapshots
        ORDER BY created_at DESC
        LIMIT 1
    """

    result = await db.execute(text(query))
    row = result.fetchone()

    if not row:
        # Return default state if no snapshots
        return {
            "success": True,
            "data": RiskStateResponse(
                total_capital_usd=Decimal("0"),
                total_exposure_usd=Decimal("0"),
                gross_exposure_pct=Decimal("0"),
                net_exposure_pct=Decimal("0"),
                current_drawdown_pct=Decimal("0"),
                peak_equity=Decimal("0"),
                current_equity=Decimal("0"),
                var_budget_used_pct=Decimal("0"),
                drawdown_budget_remaining_pct=Decimal("100"),
                positions_total=0,
                positions_healthy=0,
                positions_attention=0,
                positions_warning=0,
                positions_critical=0,
                risk_mode="standard",
                active_alerts=0,
                critical_alerts=0,
                venue_exposures={},
                asset_exposures={},
            ).model_dump(),
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    state = RiskStateResponse(
        total_capital_usd=row[0] or Decimal("0"),
        total_exposure_usd=row[1] or Decimal("0"),
        gross_exposure_pct=row[2] or Decimal("0"),
        net_exposure_pct=row[3] or Decimal("0"),
        current_drawdown_pct=row[4] or Decimal("0"),
        peak_equity=row[5] or Decimal("0"),
        current_equity=row[6] or Decimal("0"),
        var_budget_used_pct=row[7] or Decimal("0"),
        drawdown_budget_remaining_pct=row[8] or Decimal("100"),
        positions_total=row[9] or 0,
        positions_healthy=row[10] or 0,
        positions_attention=row[11] or 0,
        positions_warning=row[12] or 0,
        positions_critical=row[13] or 0,
        risk_mode=row[14] or "standard",
        active_alerts=row[15] or 0,
        critical_alerts=row[16] or 0,
        venue_exposures=row[17] or {},
        asset_exposures=row[18] or {},
    )

    return {
        "success": True,
        "data": state.model_dump(),
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/limits")
async def get_risk_limits(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get current risk limits configuration.
    """
    query = """
        SELECT
            max_position_size_usd, max_position_size_pct, max_leverage,
            max_venue_exposure_pct, max_asset_exposure_pct,
            max_gross_exposure_pct, max_net_exposure_pct,
            max_drawdown_pct, max_var_pct,
            max_delta_exposure_pct, min_liquidation_distance_pct, max_margin_utilization_pct
        FROM config.risk_limits
        WHERE is_active = true
        LIMIT 1
    """

    result = await db.execute(text(query))
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Risk limits not configured")

    limits = RiskLimitsResponse(
        max_position_size_usd=row[0],
        max_position_size_pct=row[1],
        max_leverage=row[2],
        max_venue_exposure_pct=row[3],
        max_asset_exposure_pct=row[4],
        max_gross_exposure_pct=row[5],
        max_net_exposure_pct=row[6],
        max_drawdown_pct=row[7],
        max_var_pct=row[8],
        max_delta_exposure_pct=row[9],
        min_liquidation_distance_pct=row[10],
        max_margin_utilization_pct=row[11],
    )

    return {
        "success": True,
        "data": limits.model_dump(),
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/alerts")
async def get_risk_alerts(
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get risk alerts with optional filtering.
    """
    query = """
        SELECT
            id, alert_type, severity, title, message,
            position_id, exchange, current_value, threshold_value,
            created_at, acknowledged_at
        FROM risk.alerts
        WHERE resolved_at IS NULL
    """
    params: dict[str, Any] = {}

    if severity:
        query += " AND severity = :severity"
        params["severity"] = severity

    if acknowledged is not None:
        if acknowledged:
            query += " AND acknowledged_at IS NOT NULL"
        else:
            query += " AND acknowledged_at IS NULL"

    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    alerts = [
        RiskAlertResponse(
            id=str(row[0]),
            alert_type=row[1],
            severity=row[2],
            title=row[3],
            message=row[4],
            position_id=str(row[5]) if row[5] else None,
            exchange=row[6],
            current_value=row[7],
            threshold_value=row[8],
            created_at=row[9],
            acknowledged_at=row[10],
        )
        for row in rows
    ]

    return {
        "success": True,
        "data": [a.model_dump() for a in alerts],
        "meta": {
            "total": len(alerts),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.post("/mode")
async def update_risk_mode(
    request: UpdateRiskModeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update the risk mode.
    """
    valid_modes = ["discovery", "conservative", "standard", "aggressive", "emergency"]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Must be one of: {', '.join(valid_modes)}",
        )

    # Update system setting
    query = """
        UPDATE config.system_settings
        SET value = :value, updated_at = NOW()
        WHERE key = 'system_mode'
    """
    await db.execute(text(query), {"value": f'"{request.mode}"'})
    await db.commit()

    # Publish mode change event
    from shared.utils.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.publish(
        "nexus:risk:risk.mode_changed",
        {
            "mode": request.mode,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    return {
        "success": True,
        "message": f"Risk mode updated to {request.mode}",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/emergency/halt")
async def emergency_halt(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Trigger emergency halt - stops all new positions and initiates close of existing positions.
    """
    # Set emergency mode
    query = """
        UPDATE config.system_settings
        SET value = '"emergency"', updated_at = NOW()
        WHERE key = 'system_mode'
    """
    await db.execute(text(query))
    await db.commit()

    # Publish emergency event
    from shared.utils.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.publish(
        "nexus:system:system.emergency",
        {
            "action": "halt",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    return {
        "success": True,
        "message": "Emergency halt triggered",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.put("/limits")
async def update_risk_limits(
    request: UpdateRiskLimitsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update risk limits configuration.
    """
    updates = []
    params: dict[str, Any] = {}

    field_mapping = {
        'max_position_size_usd': 'max_position_size_usd',
        'max_position_size_pct': 'max_position_size_pct',
        'max_leverage': 'max_leverage',
        'max_venue_exposure_pct': 'max_venue_exposure_pct',
        'max_asset_exposure_pct': 'max_asset_exposure_pct',
        'max_gross_exposure_pct': 'max_gross_exposure_pct',
        'max_net_exposure_pct': 'max_net_exposure_pct',
        'max_drawdown_pct': 'max_drawdown_pct',
        'max_var_pct': 'max_var_pct',
        'max_delta_exposure_pct': 'max_delta_exposure_pct',
        'min_liquidation_distance_pct': 'min_liquidation_distance_pct',
        'max_margin_utilization_pct': 'max_margin_utilization_pct',
    }

    for field, column in field_mapping.items():
        value = getattr(request, field, None)
        if value is not None:
            updates.append(f"{column} = :{field}")
            params[field] = float(value)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = f"""
        UPDATE config.risk_limits
        SET {', '.join(updates)}, updated_at = NOW()
        WHERE is_active = true
    """
    await db.execute(text(query), params)
    await db.commit()

    # Publish config change event
    from shared.utils.redis_client import get_redis_client

    try:
        redis = await get_redis_client()
        await redis.publish(
            "nexus:config:risk_limits_updated",
            {
                "updated_fields": list(params.keys()),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": "Risk limits updated",
        "updated_fields": list(params.keys()),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Acknowledge a risk alert.
    """
    query = """
        UPDATE risk.alerts
        SET acknowledged_at = NOW(), acknowledged_by = 'user'
        WHERE id = :alert_id AND acknowledged_at IS NULL
        RETURNING id
    """
    result = await db.execute(text(query), {"alert_id": alert_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")

    await db.commit()

    return {
        "success": True,
        "message": "Alert acknowledged",
        "alert_id": alert_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_note: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Resolve a risk alert.
    """
    query = """
        UPDATE risk.alerts
        SET resolved_at = NOW(), resolution_note = :note
        WHERE id = :alert_id AND resolved_at IS NULL
        RETURNING id
    """
    result = await db.execute(text(query), {"alert_id": alert_id, "note": resolution_note})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")

    await db.commit()

    return {
        "success": True,
        "message": "Alert resolved",
        "alert_id": alert_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Stress Testing Endpoints
# ============================================================================

STRESS_SCENARIOS = {
    "flash_crash_mild": {
        "name": "Mild Flash Crash",
        "type": "flash_crash",
        "severity": "mild",
        "description": "5% price drop across all assets",
        "price_move_pct": -5.0,
    },
    "flash_crash_moderate": {
        "name": "Moderate Flash Crash",
        "type": "flash_crash",
        "severity": "moderate",
        "description": "10% price drop with increased volatility",
        "price_move_pct": -10.0,
    },
    "flash_crash_severe": {
        "name": "Severe Flash Crash",
        "type": "flash_crash",
        "severity": "severe",
        "description": "20% price drop, liquidity crisis",
        "price_move_pct": -20.0,
    },
    "flash_crash_extreme": {
        "name": "Extreme Flash Crash (Black Swan)",
        "type": "flash_crash",
        "severity": "extreme",
        "description": "40% price collapse, complete liquidity evaporation",
        "price_move_pct": -40.0,
    },
    "funding_flip_mild": {
        "name": "Mild Funding Flip",
        "type": "funding_flip",
        "severity": "mild",
        "description": "Spread reduces by 50%",
        "spread_change": -0.005,
    },
    "funding_flip_moderate": {
        "name": "Moderate Funding Flip",
        "type": "funding_flip",
        "severity": "moderate",
        "description": "Spread flips negative",
        "spread_change": -0.015,
    },
    "funding_flip_severe": {
        "name": "Severe Funding Flip",
        "type": "funding_flip",
        "severity": "severe",
        "description": "Large negative spread",
        "spread_change": -0.03,
    },
    "exchange_outage_single": {
        "name": "Single Exchange Outage",
        "type": "exchange_outage",
        "severity": "moderate",
        "description": "One major exchange goes offline",
        "offline_exchanges": ["binance"],
    },
    "exchange_outage_multiple": {
        "name": "Multiple Exchange Outages",
        "type": "exchange_outage",
        "severity": "severe",
        "description": "Two exchanges go offline simultaneously",
        "offline_exchanges": ["binance", "bybit"],
    },
    "liquidity_crisis": {
        "name": "Liquidity Crisis",
        "type": "liquidity_crisis",
        "severity": "severe",
        "description": "Market-wide liquidity drops 80%",
        "liquidity_reduction": 0.8,
    },
    "correlation_breakdown": {
        "name": "Correlation Breakdown",
        "type": "correlation_breakdown",
        "severity": "severe",
        "description": "Exchange prices diverge significantly",
        "price_move_pct": -5.0,
    },
    "combined_crisis": {
        "name": "Combined Market Crisis",
        "type": "combined",
        "severity": "extreme",
        "description": "Flash crash + funding flip + liquidity crisis",
        "price_move_pct": -25.0,
        "spread_change": -0.02,
    },
}


@router.get("/stress-test/scenarios")
async def get_stress_test_scenarios() -> dict[str, Any]:
    """
    Get available stress test scenarios.
    """
    scenarios = [
        {
            "key": key,
            "name": scenario["name"],
            "type": scenario["type"],
            "severity": scenario["severity"],
            "description": scenario["description"],
        }
        for key, scenario in STRESS_SCENARIOS.items()
    ]

    return {
        "success": True,
        "data": scenarios,
        "meta": {
            "total": len(scenarios),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


@router.post("/stress-test/run")
async def run_stress_test(
    scenario_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Run stress test(s) on current portfolio.
    If scenario_name is provided, run only that scenario.
    Otherwise, run all scenarios.
    """
    # Get current positions
    positions_query = """
        SELECT
            id::text as position_id,
            symbol,
            total_capital_deployed as size_usd,
            long_exchange,
            short_exchange,
            COALESCE(
                (SELECT rate FROM funding.spread_history
                 WHERE symbol = positions.active.symbol
                 ORDER BY timestamp DESC LIMIT 1), 0.02
            ) as current_spread,
            COALESCE(realized_pnl_funding + realized_pnl_price, 0) as unrealized_pnl
        FROM positions.active
        WHERE status IN ('active', 'opening')
    """
    positions_result = await db.execute(text(positions_query))
    positions_rows = positions_result.fetchall()

    positions = [
        {
            "position_id": row[0],
            "symbol": row[1],
            "size_usd": float(row[2] or 0),
            "long_exchange": row[3],
            "short_exchange": row[4],
            "current_spread": float(row[5] or 0.02),
            "unrealized_pnl": float(row[6] or 0),
        }
        for row in positions_rows
    ]

    # Get total capital
    capital_query = """
        SELECT COALESCE(SUM(available_balance), 0) as total_capital
        FROM capital.venue_balances
    """
    capital_result = await db.execute(text(capital_query))
    capital_row = capital_result.fetchone()
    total_capital = Decimal(str(capital_row[0] or 100000))  # Default 100k if no data

    # Calculate current exposure
    current_exposure = Decimal(sum(p["size_usd"] for p in positions))

    # Run stress test(s)
    scenarios_to_run = [scenario_name] if scenario_name else list(STRESS_SCENARIOS.keys())
    results = []

    for scenario_key in scenarios_to_run:
        if scenario_key not in STRESS_SCENARIOS:
            continue

        scenario = STRESS_SCENARIOS[scenario_key]
        total_pnl_impact = Decimal("0")
        positions_affected = 0
        positions_liquidated = 0
        margin_calls = 0

        for position in positions:
            position_size = Decimal(str(position.get("size_usd", 0)))
            current_spread = Decimal(str(position.get("current_spread", 0.01)))
            long_exchange = position.get("long_exchange", "")
            short_exchange = position.get("short_exchange", "")

            if position_size <= 0:
                continue

            positions_affected += 1
            pnl_impact = Decimal("0")

            # Price movement impact
            price_move = scenario.get("price_move_pct", 0)
            if price_move != 0:
                delta_exposure_pct = Decimal("0.02")
                price_impact = position_size * Decimal(str(abs(price_move) / 100)) * delta_exposure_pct
                pnl_impact -= price_impact

            # Spread change impact
            spread_change = scenario.get("spread_change", 0)
            if spread_change != 0:
                spread_impact = position_size * Decimal(str(abs(spread_change)))
                pnl_impact -= spread_impact

            # Exchange outage impact
            offline = scenario.get("offline_exchanges", [])
            if offline:
                if long_exchange in offline or short_exchange in offline:
                    outage_impact = position_size * Decimal("0.05")
                    pnl_impact -= outage_impact
                    margin_calls += 1

            # Liquidity crisis impact
            liquidity_reduction = scenario.get("liquidity_reduction", 0)
            if liquidity_reduction > 0:
                slippage_multiplier = Decimal(str(1 + liquidity_reduction * 2))
                base_slippage = Decimal("0.001")
                liquidity_impact = position_size * base_slippage * slippage_multiplier
                pnl_impact -= liquidity_impact

            # Liquidation check
            if position_size > 0:
                loss_pct = abs(pnl_impact) / position_size * 100
                if loss_pct > Decimal("15"):
                    positions_liquidated += 1

            total_pnl_impact += pnl_impact

        # Calculate metrics
        pnl_pct = (
            total_pnl_impact / total_capital * 100
            if total_capital > 0
            else Decimal("0")
        )
        max_drawdown = abs(pnl_pct)

        # Generate recommendations
        recommendations = []
        severity = scenario["severity"]

        if severity == "extreme":
            recommendations.append("Consider reducing overall exposure by 50%")
        if severity in ["severe", "extreme"]:
            recommendations.append("Review and potentially tighten stop-loss levels")
        if scenario["type"] == "flash_crash":
            recommendations.append("Ensure adequate margin buffers on all exchanges")
        if scenario["type"] == "funding_flip":
            recommendations.append("Monitor funding rate trends more frequently")
        if scenario["type"] == "exchange_outage":
            recommendations.append("Diversify positions across more exchanges")
        if positions_liquidated > 0:
            recommendations.append(f"Reduce leverage to prevent {positions_liquidated} potential liquidations")
        if float(max_drawdown) > 10:
            recommendations.append(f"Consider portfolio hedging to limit {float(max_drawdown):.1f}% potential loss")

        results.append({
            "scenario": scenario["name"],
            "key": scenario_key,
            "type": scenario["type"],
            "severity": severity,
            "projected_pnl": float(total_pnl_impact.quantize(Decimal("0.01"))),
            "projected_pnl_pct": float(pnl_pct.quantize(Decimal("0.01"))),
            "max_drawdown_pct": float(max_drawdown.quantize(Decimal("0.01"))),
            "positions_affected": positions_affected,
            "positions_liquidated": positions_liquidated,
            "margin_calls": margin_calls,
            "recommendations": recommendations,
        })

    # Calculate summary stats
    worst_case_pnl = min(r["projected_pnl"] for r in results) if results else 0
    worst_case_drawdown = max(r["max_drawdown_pct"] for r in results) if results else 0
    total_liquidation_risk = sum(r["positions_liquidated"] for r in results)

    return {
        "success": True,
        "data": {
            "scenarios_run": len(results),
            "worst_case_pnl": worst_case_pnl,
            "worst_case_drawdown_pct": worst_case_drawdown,
            "total_liquidation_risk": total_liquidation_risk,
            "results": results,
        },
        "meta": {
            "total_positions": len(positions),
            "total_capital": float(total_capital),
            "current_exposure": float(current_exposure),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


# ============================================================================
# VaR/CVaR Endpoints
# ============================================================================

@router.get("/var")
async def get_value_at_risk(
    confidence: float = 0.95,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Calculate Value at Risk (VaR) and Conditional VaR (CVaR).
    Uses historical simulation based on closed position P&L.
    """
    # Get historical P&L data
    pnl_query = """
        SELECT
            realized_pnl_funding + realized_pnl_price as net_pnl,
            total_capital_deployed
        FROM positions.active
        WHERE status = 'closed'
          AND total_capital_deployed > 0
        ORDER BY closed_at DESC
        LIMIT 100
    """
    result = await db.execute(text(pnl_query))
    rows = result.fetchall()

    if not rows:
        return {
            "success": True,
            "data": {
                "var": 0,
                "cvar": 0,
                "confidence": confidence,
                "sample_size": 0,
                "message": "Insufficient data for VaR calculation",
            },
            "meta": {"timestamp": datetime.utcnow().isoformat()},
        }

    # Calculate returns as percentages
    returns = []
    for row in rows:
        pnl = float(row[0] or 0)
        capital = float(row[1] or 1)
        returns.append(pnl / capital * 100)

    # Sort returns (ascending - worst first)
    returns.sort()

    # Calculate VaR (percentile)
    var_index = int((1 - confidence) * len(returns))
    var = abs(returns[var_index]) if var_index < len(returns) else 0

    # Calculate CVaR (average of losses beyond VaR)
    tail_losses = [abs(r) for r in returns[:var_index + 1]]
    cvar = sum(tail_losses) / len(tail_losses) if tail_losses else 0

    return {
        "success": True,
        "data": {
            "var": round(var, 2),
            "cvar": round(cvar, 2),
            "var_99": round(abs(returns[int(0.01 * len(returns))]) if len(returns) > 100 else var * 1.5, 2),
            "confidence": confidence,
            "sample_size": len(returns),
            "avg_return": round(sum(returns) / len(returns), 2),
            "worst_return": round(min(returns), 2),
            "best_return": round(max(returns), 2),
        },
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }
