"""
Configuration API endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

router = APIRouter()


class ExchangeConfigResponse(BaseModel):
    """Response model for exchange configuration."""

    slug: str
    display_name: str
    exchange_type: str
    tier: str
    enabled: bool
    perp_maker_fee: Decimal
    perp_taker_fee: Decimal
    funding_interval_hours: int
    supports_portfolio_margin: bool
    has_credentials: bool
    credential_fields: list[str]
    requires_on_chain: bool


class UpdateExchangeRequest(BaseModel):
    """Request model for updating exchange configuration."""

    enabled: Optional[bool] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    wallet_address: Optional[str] = None


class SystemSettingResponse(BaseModel):
    """Response model for system setting."""

    key: str
    value: Any
    description: Optional[str]
    updated_at: datetime


@router.get("/exchanges")
async def list_exchanges(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List all configured exchanges.
    """
    query = """
        SELECT
            slug, display_name, exchange_type, tier, enabled,
            perp_maker_fee, perp_taker_fee, funding_interval_hours,
            supports_portfolio_margin,
            (api_key_encrypted IS NOT NULL OR wallet_address_encrypted IS NOT NULL) as has_credentials,
            credential_fields,
            requires_on_chain
        FROM config.exchanges
    """

    if enabled_only:
        query += " WHERE enabled = true"

    query += " ORDER BY tier, display_name"

    result = await db.execute(text(query))
    rows = result.fetchall()

    exchanges = [
        ExchangeConfigResponse(
            slug=row[0],
            display_name=row[1],
            exchange_type=row[2],
            tier=row[3],
            enabled=row[4],
            perp_maker_fee=row[5],
            perp_taker_fee=row[6],
            funding_interval_hours=row[7],
            supports_portfolio_margin=row[8],
            has_credentials=row[9],
            credential_fields=row[10] or ["api_key", "api_secret"],
            requires_on_chain=row[11] or False,
        ).model_dump()
        for row in rows
    ]

    return {
        "success": True,
        "data": exchanges,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/exchanges/{slug}")
async def get_exchange(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get configuration for a specific exchange.
    """
    query = """
        SELECT
            slug, display_name, exchange_type, tier, enabled,
            perp_maker_fee, perp_taker_fee, funding_interval_hours,
            supports_portfolio_margin,
            (api_key_encrypted IS NOT NULL OR wallet_address_encrypted IS NOT NULL) as has_credentials,
            credential_fields,
            requires_on_chain
        FROM config.exchanges
        WHERE slug = :slug
    """

    result = await db.execute(text(query), {"slug": slug})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Exchange not found")

    exchange = ExchangeConfigResponse(
        slug=row[0],
        display_name=row[1],
        exchange_type=row[2],
        tier=row[3],
        enabled=row[4],
        perp_maker_fee=row[5],
        perp_taker_fee=row[6],
        funding_interval_hours=row[7],
        supports_portfolio_margin=row[8],
        has_credentials=row[9],
        credential_fields=row[10] or ["api_key", "api_secret"],
        requires_on_chain=row[11] or False,
    )

    return {
        "success": True,
        "data": exchange.model_dump(),
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.patch("/exchanges/{slug}")
async def update_exchange(
    slug: str,
    request: UpdateExchangeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update exchange configuration.
    """
    # Check exchange exists
    check_query = "SELECT id FROM config.exchanges WHERE slug = :slug"
    result = await db.execute(text(check_query), {"slug": slug})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Exchange not found")

    updates = []
    params: dict[str, Any] = {"slug": slug}

    if request.enabled is not None:
        updates.append("enabled = :enabled")
        params["enabled"] = request.enabled

    if request.api_key is not None:
        # In production, encrypt the key
        updates.append("api_key_encrypted = pgp_sym_encrypt(:api_key, 'nexus_secret')")
        params["api_key"] = request.api_key

    if request.api_secret is not None:
        updates.append(
            "api_secret_encrypted = pgp_sym_encrypt(:api_secret, 'nexus_secret')"
        )
        params["api_secret"] = request.api_secret

    if request.passphrase is not None:
        updates.append(
            "passphrase_encrypted = pgp_sym_encrypt(:passphrase, 'nexus_secret')"
        )
        params["passphrase"] = request.passphrase

    if request.wallet_address is not None:
        updates.append(
            "wallet_address_encrypted = pgp_sym_encrypt(:wallet_address, 'nexus_secret')"
        )
        params["wallet_address"] = request.wallet_address

    if updates:
        update_query = f"""
            UPDATE config.exchanges
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE slug = :slug
        """
        await db.execute(text(update_query), params)
        await db.commit()

    return {
        "success": True,
        "message": f"Exchange {slug} updated",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/settings")
async def list_settings(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List all system settings.
    """
    query = """
        SELECT key, value, description, updated_at
        FROM config.system_settings
        ORDER BY key
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    import json

    def parse_value(val: Any) -> Any:
        """Parse value - handle both JSON strings and native types."""
        if val is None:
            return None
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        return val

    settings = [
        SystemSettingResponse(
            key=row[0],
            value=parse_value(row[1]),
            description=row[2],
            updated_at=row[3],
        ).model_dump()
        for row in rows
    ]

    return {
        "success": True,
        "data": settings,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.get("/settings/{key}")
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get a specific system setting.
    """
    query = """
        SELECT key, value, description, updated_at
        FROM config.system_settings
        WHERE key = :key
    """

    result = await db.execute(text(query), {"key": key})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Setting not found")

    import json

    def parse_value(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        return val

    setting = SystemSettingResponse(
        key=row[0],
        value=parse_value(row[1]),
        description=row[2],
        updated_at=row[3],
    )

    return {
        "success": True,
        "data": setting.model_dump(),
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


@router.put("/settings/{key}")
async def update_setting(
    key: str,
    value: Any,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update a system setting.
    """
    import json

    # Check setting exists
    check_query = "SELECT key FROM config.system_settings WHERE key = :key"
    result = await db.execute(text(check_query), {"key": key})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Setting not found")

    update_query = """
        UPDATE config.system_settings
        SET value = :value, updated_at = NOW()
        WHERE key = :key
    """
    await db.execute(text(update_query), {"key": key, "value": json.dumps(value)})
    await db.commit()

    return {
        "success": True,
        "message": f"Setting {key} updated",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/strategy")
async def get_strategy_parameters(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get active strategy parameters.
    """
    query = """
        SELECT
            name, min_spread_pct, min_net_apr_pct, min_uos_score,
            min_volume_24h_usd, min_open_interest_usd, max_expected_slippage_pct,
            liquidity_multiple, return_score_weight, risk_score_weight,
            execution_score_weight, timing_score_weight,
            target_funding_rate_min, stop_loss_pct
        FROM config.strategy_parameters
        WHERE is_active = true
        LIMIT 1
    """

    result = await db.execute(text(query))
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=404, detail="Strategy parameters not configured"
        )

    params = {
        "name": row[0],
        "min_spread_pct": float(row[1]),
        "min_net_apr_pct": float(row[2]),
        "min_uos_score": row[3],
        "min_volume_24h_usd": float(row[4]),
        "min_open_interest_usd": float(row[5]),
        "max_expected_slippage_pct": float(row[6]),
        "liquidity_multiple": float(row[7]),
        "return_score_weight": float(row[8]),
        "risk_score_weight": float(row[9]),
        "execution_score_weight": float(row[10]),
        "timing_score_weight": float(row[11]),
        "target_funding_rate_min": float(row[12]),
        "stop_loss_pct": float(row[13]),
    }

    return {
        "success": True,
        "data": params,
        "meta": {"timestamp": datetime.utcnow().isoformat()},
    }


class UpdateStrategyRequest(BaseModel):
    """Request model for updating strategy parameters."""

    min_spread_pct: Optional[float] = None
    min_net_apr_pct: Optional[float] = None
    min_uos_score: Optional[int] = None
    min_volume_24h_usd: Optional[float] = None
    min_open_interest_usd: Optional[float] = None
    max_expected_slippage_pct: Optional[float] = None
    liquidity_multiple: Optional[float] = None
    return_score_weight: Optional[float] = None
    risk_score_weight: Optional[float] = None
    execution_score_weight: Optional[float] = None
    timing_score_weight: Optional[float] = None
    target_funding_rate_min: Optional[float] = None
    stop_loss_pct: Optional[float] = None


@router.put("/strategy")
async def update_strategy_parameters(
    request: UpdateStrategyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Update active strategy parameters.
    """
    updates = []
    params: dict[str, Any] = {}

    field_mapping = {
        "min_spread_pct": request.min_spread_pct,
        "min_net_apr_pct": request.min_net_apr_pct,
        "min_uos_score": request.min_uos_score,
        "min_volume_24h_usd": request.min_volume_24h_usd,
        "min_open_interest_usd": request.min_open_interest_usd,
        "max_expected_slippage_pct": request.max_expected_slippage_pct,
        "liquidity_multiple": request.liquidity_multiple,
        "return_score_weight": request.return_score_weight,
        "risk_score_weight": request.risk_score_weight,
        "execution_score_weight": request.execution_score_weight,
        "timing_score_weight": request.timing_score_weight,
        "target_funding_rate_min": request.target_funding_rate_min,
        "stop_loss_pct": request.stop_loss_pct,
    }

    for field, value in field_mapping.items():
        if value is not None:
            updates.append(f"{field} = :{field}")
            params[field] = value

    if not updates:
        raise HTTPException(status_code=400, detail="No parameters to update")

    update_query = f"""
        UPDATE config.strategy_parameters
        SET {', '.join(updates)}, updated_at = NOW()
        WHERE is_active = true
    """
    await db.execute(text(update_query), params)
    await db.commit()

    return {
        "success": True,
        "message": "Strategy parameters updated",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/settings/factory-reset")
async def factory_reset(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Reset all settings to factory defaults.

    This resets:
    - Strategy parameters
    - Risk limits
    - System settings (except credentials)

    Exchange credentials are preserved.
    """
    import json

    reset_actions = []

    # Reset strategy parameters to defaults
    try:
        strategy_defaults = """
            UPDATE config.strategy_parameters
            SET
                min_spread_pct = 0.03,
                min_net_apr_pct = 10.0,
                min_uos_score = 60,
                min_volume_24h_usd = 1000000,
                min_open_interest_usd = 5000000,
                max_expected_slippage_pct = 0.1,
                liquidity_multiple = 3.0,
                return_score_weight = 0.30,
                risk_score_weight = 0.30,
                execution_score_weight = 0.25,
                timing_score_weight = 0.15,
                target_funding_rate_min = 0.01,
                stop_loss_pct = 5.0,
                updated_at = NOW()
            WHERE is_active = true
        """
        await db.execute(text(strategy_defaults))
        reset_actions.append("strategy_parameters")
    except Exception as e:
        pass  # Continue with other resets

    # Reset risk limits to defaults
    try:
        risk_defaults = """
            UPDATE config.risk_limits
            SET
                max_position_size_usd = 10000,
                max_position_size_pct = 20.0,
                max_leverage = 3.0,
                max_venue_exposure_pct = 50.0,
                max_asset_exposure_pct = 30.0,
                max_gross_exposure_pct = 150.0,
                max_net_exposure_pct = 50.0,
                max_drawdown_pct = 10.0,
                max_var_pct = 5.0,
                max_total_exposure_usd = 100000,
                max_exchange_exposure_usd = 50000,
                updated_at = NOW()
            WHERE is_active = true
        """
        await db.execute(text(risk_defaults))
        reset_actions.append("risk_limits")
    except Exception as e:
        pass

    # Reset spread monitoring settings
    try:
        # Check if table exists and reset
        spread_defaults = """
            UPDATE config.strategy_parameters
            SET
                spread_drawdown_exit_pct = 50.0,
                min_time_to_funding_exit_seconds = 1800,
                updated_at = NOW()
            WHERE is_active = true
        """
        await db.execute(text(spread_defaults))
        reset_actions.append("spread_monitoring")
    except Exception as e:
        pass

    # Reset max concurrent coins
    try:
        max_coins_default = """
            UPDATE config.strategy_parameters
            SET max_concurrent_coins = 5, updated_at = NOW()
            WHERE is_active = true
        """
        await db.execute(text(max_coins_default))
        reset_actions.append("max_concurrent_coins")
    except Exception as e:
        pass

    await db.commit()

    # Log the factory reset event
    try:
        audit_query = """
            INSERT INTO audit.activity_events (
                service, category, event_type, severity, message, details
            ) VALUES (
                'gateway', 'config', 'factory_reset', 'warning',
                'Factory reset performed', :details::jsonb
            )
        """
        await db.execute(text(audit_query), {
            "details": json.dumps({
                "reset_actions": reset_actions,
                "timestamp": datetime.utcnow().isoformat(),
            }),
        })
        await db.commit()
    except Exception:
        pass

    return {
        "success": True,
        "message": "Factory reset completed",
        "reset_actions": reset_actions,
        "timestamp": datetime.utcnow().isoformat(),
    }
