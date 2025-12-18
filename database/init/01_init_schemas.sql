-- NEXUS Database Initialization
-- Creates all schemas and extensions

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create schemas for each service domain
CREATE SCHEMA IF NOT EXISTS config;
CREATE SCHEMA IF NOT EXISTS funding;
CREATE SCHEMA IF NOT EXISTS opportunities;
CREATE SCHEMA IF NOT EXISTS positions;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS capital;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS auth;

-- Grant usage on schemas
GRANT USAGE ON SCHEMA config TO nexus;
GRANT USAGE ON SCHEMA funding TO nexus;
GRANT USAGE ON SCHEMA opportunities TO nexus;
GRANT USAGE ON SCHEMA positions TO nexus;
GRANT USAGE ON SCHEMA risk TO nexus;
GRANT USAGE ON SCHEMA capital TO nexus;
GRANT USAGE ON SCHEMA analytics TO nexus;
GRANT USAGE ON SCHEMA audit TO nexus;
GRANT USAGE ON SCHEMA auth TO nexus;

-- =============================================================================
-- CONFIG SCHEMA - System configuration stored in database
-- =============================================================================

-- Exchange configurations
CREATE TABLE config.exchanges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    exchange_type VARCHAR(20) NOT NULL DEFAULT 'cex', -- cex, dex
    tier VARCHAR(20) NOT NULL DEFAULT 'tier_2',
    enabled BOOLEAN NOT NULL DEFAULT true,

    -- API Configuration
    api_type VARCHAR(20) NOT NULL DEFAULT 'ccxt',
    base_url TEXT,
    websocket_url TEXT,

    -- Credentials (encrypted)
    api_key_encrypted BYTEA,
    api_secret_encrypted BYTEA,
    passphrase_encrypted BYTEA,
    wallet_address_encrypted BYTEA,

    -- Credential configuration
    credential_fields JSONB DEFAULT '["api_key", "api_secret"]'::jsonb,

    -- Fees (as percentages)
    spot_maker_fee DECIMAL(10, 6) DEFAULT 0.001,
    spot_taker_fee DECIMAL(10, 6) DEFAULT 0.001,
    perp_maker_fee DECIMAL(10, 6) DEFAULT 0.0002,
    perp_taker_fee DECIMAL(10, 6) DEFAULT 0.0005,

    -- Rate limits
    requests_per_minute INTEGER DEFAULT 1200,
    orders_per_second INTEGER DEFAULT 10,

    -- Funding configuration
    funding_interval_hours INTEGER DEFAULT 8,
    funding_times_utc JSONB DEFAULT '["00:00", "08:00", "16:00"]'::jsonb,

    -- Features
    supports_portfolio_margin BOOLEAN DEFAULT false,
    supports_spot BOOLEAN DEFAULT true,
    supports_perpetual BOOLEAN DEFAULT true,
    requires_on_chain BOOLEAN DEFAULT false,
    chain VARCHAR(50),

    -- URLs
    trading_url_template TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Risk limits configuration
CREATE TABLE config.risk_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL DEFAULT 'default',
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Position limits
    max_position_size_usd DECIMAL(18, 2) DEFAULT 50000,
    max_position_size_pct DECIMAL(10, 4) DEFAULT 5.0,
    max_leverage DECIMAL(10, 4) DEFAULT 3.0,

    -- Concentration limits
    max_venue_exposure_pct DECIMAL(10, 4) DEFAULT 35.0,
    max_asset_exposure_pct DECIMAL(10, 4) DEFAULT 20.0,
    max_correlated_exposure_pct DECIMAL(10, 4) DEFAULT 40.0,

    -- Portfolio limits
    max_gross_exposure_pct DECIMAL(10, 4) DEFAULT 200.0,
    max_net_exposure_pct DECIMAL(10, 4) DEFAULT 10.0,
    max_drawdown_pct DECIMAL(10, 4) DEFAULT 5.0,
    max_var_pct DECIMAL(10, 4) DEFAULT 2.0,

    -- Position health limits
    max_delta_exposure_pct DECIMAL(10, 4) DEFAULT 2.0,
    min_liquidation_distance_pct DECIMAL(10, 4) DEFAULT 20.0,
    max_margin_utilization_pct DECIMAL(10, 4) DEFAULT 70.0,

    -- Timing limits
    min_hold_funding_periods INTEGER DEFAULT 2,
    max_hold_days INTEGER DEFAULT 30,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Strategy parameters
CREATE TABLE config.strategy_parameters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL DEFAULT 'default',
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Detection parameters
    min_spread_pct DECIMAL(10, 6) DEFAULT 0.01,
    min_net_apr_pct DECIMAL(10, 4) DEFAULT 10.0,
    min_uos_score INTEGER DEFAULT 40,
    min_volume_24h_usd DECIMAL(18, 2) DEFAULT 1000000,
    min_open_interest_usd DECIMAL(18, 2) DEFAULT 500000,
    max_expected_slippage_pct DECIMAL(10, 6) DEFAULT 0.1,
    liquidity_multiple DECIMAL(10, 4) DEFAULT 3.0,

    -- Scoring weights
    return_score_weight DECIMAL(10, 4) DEFAULT 0.4,
    risk_score_weight DECIMAL(10, 4) DEFAULT 0.3,
    execution_score_weight DECIMAL(10, 4) DEFAULT 0.2,
    timing_score_weight DECIMAL(10, 4) DEFAULT 0.1,

    -- Exit triggers
    target_funding_rate_min DECIMAL(10, 6) DEFAULT 0.005,
    stop_loss_pct DECIMAL(10, 4) DEFAULT 2.0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- System settings
CREATE TABLE config.system_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- Configuration change log
CREATE TABLE config.change_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(100),
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- FUNDING SCHEMA - Funding rate data
-- =============================================================================

-- Funding rates from all sources
CREATE TABLE funding.rates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    rate DECIMAL(20, 10) NOT NULL,
    next_funding_time TIMESTAMPTZ NOT NULL,
    source VARCHAR(30) NOT NULL, -- 'exchange_api' or 'arbitragescanner'
    is_validated BOOLEAN DEFAULT false,
    is_fallback BOOLEAN DEFAULT false,
    discrepancy DECIMAL(20, 10),
    funding_interval_hours INTEGER DEFAULT 8,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Index for common queries
    CONSTRAINT unique_rate_per_snapshot UNIQUE (exchange, symbol, timestamp)
);

-- Create partitioning for rates table (by month)
CREATE INDEX idx_funding_rates_symbol_exchange ON funding.rates (symbol, exchange);
CREATE INDEX idx_funding_rates_timestamp ON funding.rates (timestamp);
CREATE INDEX idx_funding_rates_exchange ON funding.rates (exchange);

-- Unified snapshots (point-in-time aggregations)
CREATE TABLE funding.snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fetched_at TIMESTAMPTZ NOT NULL,
    total_symbols INTEGER NOT NULL DEFAULT 0,
    total_rates INTEGER NOT NULL DEFAULT 0,
    exchange_api_rates INTEGER NOT NULL DEFAULT 0,
    arbitragescanner_rates INTEGER NOT NULL DEFAULT 0,
    validated_rates INTEGER NOT NULL DEFAULT 0,
    discrepancy_count INTEGER NOT NULL DEFAULT 0,
    exchanges_healthy JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Data source discrepancies
CREATE TABLE funding.discrepancies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    exchange_api_rate DECIMAL(20, 10),
    arbitragescanner_rate DECIMAL(20, 10),
    discrepancy DECIMAL(20, 10) NOT NULL,
    discrepancy_pct DECIMAL(10, 6) NOT NULL,
    resolved BOOLEAN DEFAULT false,
    resolution_note TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_funding_discrepancies_unresolved ON funding.discrepancies (resolved) WHERE NOT resolved;

-- =============================================================================
-- OPPORTUNITIES SCHEMA - Detected arbitrage opportunities
-- =============================================================================

CREATE TABLE opportunities.detected (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opportunity_type VARCHAR(30) NOT NULL, -- spot_perp, cross_exchange_perp, etc.
    symbol VARCHAR(50) NOT NULL,
    base_asset VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'detected',

    -- Legs
    primary_exchange VARCHAR(50) NOT NULL,
    primary_side VARCHAR(10) NOT NULL,
    primary_rate DECIMAL(20, 10) NOT NULL,
    hedge_exchange VARCHAR(50) NOT NULL,
    hedge_side VARCHAR(10) NOT NULL,
    hedge_rate DECIMAL(20, 10) NOT NULL,

    -- Financial metrics
    gross_funding_rate DECIMAL(20, 10) NOT NULL,
    gross_apr DECIMAL(20, 10) NOT NULL,
    total_entry_cost DECIMAL(20, 10) DEFAULT 0,
    total_exit_cost DECIMAL(20, 10) DEFAULT 0,
    net_apr DECIMAL(20, 10) NOT NULL,
    basis DECIMAL(20, 10) DEFAULT 0,
    basis_risk DECIMAL(20, 10) DEFAULT 0,

    -- Scoring
    uos_score INTEGER DEFAULT 0,
    return_score INTEGER DEFAULT 0,
    risk_score INTEGER DEFAULT 0,
    execution_score INTEGER DEFAULT 0,
    timing_score INTEGER DEFAULT 0,
    confidence VARCHAR(20) DEFAULT 'medium',

    -- Recommendations
    recommended_size_usd DECIMAL(18, 2) DEFAULT 0,
    minimum_hold_periods INTEGER DEFAULT 2,
    maximum_hold_periods INTEGER DEFAULT 24,

    -- Metadata
    data_source VARCHAR(30) DEFAULT 'exchange_api',
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    validated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,

    -- Indexes
    CONSTRAINT opportunities_detected_status_check CHECK (
        status IN ('detected', 'validated', 'scored', 'allocated', 'executing', 'executed', 'expired', 'rejected')
    )
);

CREATE INDEX idx_opportunities_status ON opportunities.detected (status);
CREATE INDEX idx_opportunities_symbol ON opportunities.detected (symbol);
CREATE INDEX idx_opportunities_uos_score ON opportunities.detected (uos_score DESC);
CREATE INDEX idx_opportunities_detected_at ON opportunities.detected (detected_at);

-- =============================================================================
-- POSITIONS SCHEMA - Active and historical positions
-- =============================================================================

CREATE TABLE positions.active (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opportunity_id UUID REFERENCES opportunities.detected(id),
    opportunity_type VARCHAR(30) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    base_asset VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    health_status VARCHAR(20) NOT NULL DEFAULT 'healthy',

    -- Capital
    total_capital_deployed DECIMAL(18, 2) NOT NULL,
    entry_costs_paid DECIMAL(18, 6) DEFAULT 0,
    exit_costs_paid DECIMAL(18, 6) DEFAULT 0,

    -- Funding P&L
    funding_received DECIMAL(18, 6) DEFAULT 0,
    funding_paid DECIMAL(18, 6) DEFAULT 0,

    -- Risk metrics
    net_delta DECIMAL(18, 6) DEFAULT 0,
    delta_exposure_pct DECIMAL(10, 6) DEFAULT 0,
    max_margin_utilization DECIMAL(10, 6) DEFAULT 0,
    min_liquidation_distance DECIMAL(10, 6),

    -- Timing
    opened_at TIMESTAMPTZ,
    last_funding_collected TIMESTAMPTZ,
    funding_periods_collected INTEGER DEFAULT 0,
    expected_next_funding TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,

    -- Exit configuration
    target_funding_rate_min DECIMAL(20, 10) DEFAULT 0.005,
    stop_loss_pct DECIMAL(10, 6) DEFAULT 2.0,
    take_profit_pct DECIMAL(10, 6),
    max_hold_periods INTEGER DEFAULT 72,

    -- Exit reason
    exit_reason VARCHAR(100),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT positions_status_check CHECK (
        status IN ('pending', 'opening', 'active', 'closing', 'closed', 'cancelled', 'failed', 'emergency_close')
    ),
    CONSTRAINT positions_health_check CHECK (
        health_status IN ('healthy', 'attention', 'warning', 'critical')
    )
);

CREATE INDEX idx_positions_status ON positions.active (status);
CREATE INDEX idx_positions_symbol ON positions.active (symbol);
CREATE INDEX idx_positions_health ON positions.active (health_status);

-- Position legs
CREATE TABLE positions.legs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES positions.active(id) ON DELETE CASCADE,
    leg_type VARCHAR(20) NOT NULL, -- 'primary', 'hedge', 'additional'
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    market_type VARCHAR(20) NOT NULL, -- 'spot', 'perpetual'
    side VARCHAR(10) NOT NULL, -- 'long', 'short'

    -- Position details
    quantity DECIMAL(28, 18) NOT NULL,
    entry_price DECIMAL(28, 18) NOT NULL,
    current_price DECIMAL(28, 18) NOT NULL,
    notional_value_usd DECIMAL(18, 2) NOT NULL,

    -- Margin (for perpetuals)
    margin_used DECIMAL(18, 6) DEFAULT 0,
    leverage DECIMAL(10, 4) DEFAULT 1,
    liquidation_price DECIMAL(28, 18),

    -- P&L
    unrealized_pnl DECIMAL(18, 6) DEFAULT 0,
    realized_pnl DECIMAL(18, 6) DEFAULT 0,
    funding_pnl DECIMAL(18, 6) DEFAULT 0,

    -- Execution details
    entry_timestamp TIMESTAMPTZ,
    entry_order_ids JSONB DEFAULT '[]'::jsonb,
    entry_fees DECIMAL(18, 6) DEFAULT 0,
    avg_entry_price DECIMAL(28, 18),
    exit_timestamp TIMESTAMPTZ,
    exit_order_ids JSONB DEFAULT '[]'::jsonb,
    exit_fees DECIMAL(18, 6) DEFAULT 0,
    avg_exit_price DECIMAL(28, 18),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_position_legs_position_id ON positions.legs (position_id);

-- Position events log
CREATE TABLE positions.events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES positions.active(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_position_events_position_id ON positions.events (position_id);
CREATE INDEX idx_position_events_type ON positions.events (event_type);

-- Funding payments
CREATE TABLE positions.funding_payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES positions.active(id) ON DELETE CASCADE,
    leg_id UUID NOT NULL REFERENCES positions.legs(id) ON DELETE CASCADE,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    funding_rate DECIMAL(20, 10) NOT NULL,
    payment_amount DECIMAL(18, 6) NOT NULL,
    position_size DECIMAL(28, 18) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_funding_payments_position_id ON positions.funding_payments (position_id);

-- =============================================================================
-- RISK SCHEMA - Risk metrics and alerts
-- =============================================================================

-- Risk state snapshots
CREATE TABLE risk.snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    total_capital_usd DECIMAL(18, 2) NOT NULL DEFAULT 0,
    total_exposure_usd DECIMAL(18, 2) NOT NULL DEFAULT 0,
    gross_exposure_pct DECIMAL(10, 6) NOT NULL DEFAULT 0,
    net_exposure_pct DECIMAL(10, 6) NOT NULL DEFAULT 0,
    portfolio_delta DECIMAL(18, 6) NOT NULL DEFAULT 0,
    portfolio_var DECIMAL(18, 6) NOT NULL DEFAULT 0,
    current_drawdown_pct DECIMAL(10, 6) NOT NULL DEFAULT 0,
    peak_equity DECIMAL(18, 2) NOT NULL DEFAULT 0,
    current_equity DECIMAL(18, 2) NOT NULL DEFAULT 0,

    -- Exposure breakdowns
    venue_exposures JSONB DEFAULT '{}'::jsonb,
    asset_exposures JSONB DEFAULT '{}'::jsonb,
    strategy_exposures JSONB DEFAULT '{}'::jsonb,

    -- Risk budget
    var_budget_used_pct DECIMAL(10, 6) DEFAULT 0,
    drawdown_budget_remaining_pct DECIMAL(10, 6) DEFAULT 100,

    -- Position health summary
    positions_total INTEGER DEFAULT 0,
    positions_healthy INTEGER DEFAULT 0,
    positions_attention INTEGER DEFAULT 0,
    positions_warning INTEGER DEFAULT 0,
    positions_critical INTEGER DEFAULT 0,

    -- Current mode
    risk_mode VARCHAR(20) DEFAULT 'standard',

    -- Active alerts
    active_alerts INTEGER DEFAULT 0,
    critical_alerts INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_risk_snapshots_created_at ON risk.snapshots (created_at);

-- Risk alerts
CREATE TABLE risk.alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL, -- info, low, medium, high, critical
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    position_id UUID,
    exchange VARCHAR(50),
    symbol VARCHAR(50),
    current_value DECIMAL(18, 6),
    threshold_value DECIMAL(18, 6),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_risk_alerts_severity ON risk.alerts (severity);
CREATE INDEX idx_risk_alerts_unresolved ON risk.alerts (resolved_at) WHERE resolved_at IS NULL;

-- Risk limit breaches
CREATE TABLE risk.limit_breaches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    limit_name VARCHAR(100) NOT NULL,
    limit_value DECIMAL(18, 6) NOT NULL,
    actual_value DECIMAL(18, 6) NOT NULL,
    breach_amount DECIMAL(18, 6) NOT NULL,
    action_taken VARCHAR(200),
    position_id UUID,
    exchange VARCHAR(50),
    asset VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- CAPITAL SCHEMA - Capital allocation tracking
-- =============================================================================

-- Capital allocations
CREATE TABLE capital.allocations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opportunity_id UUID,
    position_id UUID,
    amount_usd DECIMAL(18, 2) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'reserved',
    allocated_at TIMESTAMPTZ DEFAULT NOW(),
    deployed_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    expiry TIMESTAMPTZ,

    CONSTRAINT capital_allocation_status_check CHECK (
        status IN ('reserved', 'deployed', 'releasing', 'released')
    )
);

CREATE INDEX idx_capital_allocations_status ON capital.allocations (status);
CREATE INDEX idx_capital_allocations_venue ON capital.allocations (venue);

-- Capital transfers
CREATE TABLE capital.transfers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_venue VARCHAR(50) NOT NULL,
    to_venue VARCHAR(50) NOT NULL,
    asset VARCHAR(20) NOT NULL DEFAULT 'USDT',
    amount DECIMAL(18, 6) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    tx_hash VARCHAR(200),
    fee DECIMAL(18, 6) DEFAULT 0,
    error_message TEXT,
    initiated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Venue balances (cached)
CREATE TABLE capital.venue_balances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue VARCHAR(50) NOT NULL,
    balances JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_usd DECIMAL(18, 2) NOT NULL DEFAULT 0,
    margin_used DECIMAL(18, 2) DEFAULT 0,
    margin_available DECIMAL(18, 2) DEFAULT 0,
    unrealized_pnl DECIMAL(18, 6) DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_venue_balance UNIQUE (venue)
);

-- =============================================================================
-- ANALYTICS SCHEMA - Performance tracking
-- =============================================================================

-- Daily P&L
CREATE TABLE analytics.daily_pnl (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL,

    -- P&L breakdown
    funding_pnl DECIMAL(18, 6) NOT NULL DEFAULT 0,
    price_pnl DECIMAL(18, 6) NOT NULL DEFAULT 0,
    fee_costs DECIMAL(18, 6) NOT NULL DEFAULT 0,
    net_pnl DECIMAL(18, 6) NOT NULL DEFAULT 0,

    -- Returns
    return_pct DECIMAL(10, 6) NOT NULL DEFAULT 0,
    cumulative_return_pct DECIMAL(10, 6) NOT NULL DEFAULT 0,

    -- Positions
    positions_opened INTEGER DEFAULT 0,
    positions_closed INTEGER DEFAULT 0,
    positions_active_eod INTEGER DEFAULT 0,

    -- Capital
    capital_deployed_avg DECIMAL(18, 2) DEFAULT 0,
    capital_utilization_pct DECIMAL(10, 6) DEFAULT 0,

    -- Risk
    max_drawdown_pct DECIMAL(10, 6) DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_daily_pnl UNIQUE (date)
);

-- Trade statistics
CREATE TABLE analytics.trade_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period VARCHAR(20) NOT NULL, -- 'daily', 'weekly', 'monthly', 'all_time'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Trade counts
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,

    -- Returns
    win_rate DECIMAL(10, 6) DEFAULT 0,
    avg_return_pct DECIMAL(10, 6) DEFAULT 0,
    avg_win_pct DECIMAL(10, 6) DEFAULT 0,
    avg_loss_pct DECIMAL(10, 6) DEFAULT 0,
    profit_factor DECIMAL(10, 6) DEFAULT 0,

    -- Risk
    sharpe_ratio DECIMAL(10, 6),
    sortino_ratio DECIMAL(10, 6),
    max_drawdown_pct DECIMAL(10, 6) DEFAULT 0,

    -- Timing
    avg_hold_hours DECIMAL(10, 2) DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- AUDIT SCHEMA - Compliance and debugging
-- =============================================================================

-- User/system actions
CREATE TABLE audit.actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor VARCHAR(100) NOT NULL, -- 'system' or user identifier
    action_type VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    details JSONB DEFAULT '{}'::jsonb,
    ip_address VARCHAR(45),
    user_agent TEXT,
    outcome VARCHAR(20) DEFAULT 'success', -- success, failure
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_actions_actor ON audit.actions (actor);
CREATE INDEX idx_audit_actions_action_type ON audit.actions (action_type);
CREATE INDEX idx_audit_actions_created_at ON audit.actions (created_at);

-- API calls to external services
CREATE TABLE audit.api_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service VARCHAR(50) NOT NULL, -- exchange name or 'arbitragescanner'
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    request_body JSONB,
    response_status INTEGER,
    response_body JSONB,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_api_calls_service ON audit.api_calls (service);
CREATE INDEX idx_audit_api_calls_created_at ON audit.api_calls (created_at);

-- =============================================================================
-- AUTH SCHEMA - Authentication (minimal for now)
-- =============================================================================

CREATE TABLE auth.api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    permissions JSONB DEFAULT '["read"]'::jsonb,
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_exchanges_updated_at
    BEFORE UPDATE ON config.exchanges
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_risk_limits_updated_at
    BEFORE UPDATE ON config.risk_limits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategy_parameters_updated_at
    BEFORE UPDATE ON config.strategy_parameters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions.active
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_position_legs_updated_at
    BEFORE UPDATE ON positions.legs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- SEED DATA
-- =============================================================================

-- Insert default risk limits
INSERT INTO config.risk_limits (name, is_active) VALUES ('default', true);

-- Insert default strategy parameters
INSERT INTO config.strategy_parameters (name, is_active) VALUES ('default', true);

-- Insert system settings
INSERT INTO config.system_settings (key, value, description) VALUES
    ('system_mode', '"standard"', 'Current operational mode: discovery, conservative, standard, aggressive, emergency'),
    ('arbitragescanner_enabled', 'true', 'Whether ArbitrageScanner API is enabled'),
    ('new_positions_enabled', 'true', 'Whether new positions can be opened'),
    ('alerts_enabled', 'true', 'Whether alerts are enabled'),
    ('system_running', 'false', 'Whether the trading system is running'),
    ('version', '"0.1.0"', 'Current system version');

-- Insert default exchanges
INSERT INTO config.exchanges (slug, display_name, exchange_type, tier, enabled, api_type, perp_maker_fee, perp_taker_fee, funding_interval_hours, trading_url_template, requires_on_chain, credential_fields) VALUES
    ('binance_futures', 'Binance (Futures)', 'cex', 'tier_1', true, 'ccxt', 0.0002, 0.0004, 8, 'https://www.binance.com/en/futures/{symbol}', false, '["api_key", "api_secret"]'),
    ('bybit_futures', 'Bybit (Futures)', 'cex', 'tier_1', true, 'ccxt', 0.0001, 0.0006, 8, 'https://www.bybit.com/trade/usdt/{symbol}', false, '["api_key", "api_secret"]'),
    ('okex_futures', 'OKX (Futures)', 'cex', 'tier_1', true, 'ccxt', 0.0002, 0.0005, 8, 'https://www.okx.com/trade-swap/{symbol}-swap', false, '["api_key", "api_secret", "passphrase"]'),
    ('gate_futures', 'Gate (Futures)', 'cex', 'tier_2', true, 'ccxt', 0.00015, 0.0005, 8, 'https://www.gate.io/futures/USDT/{symbol}', false, '["api_key", "api_secret"]'),
    ('kucoin_futures', 'KuCoin (Futures)', 'cex', 'tier_2', true, 'ccxt', 0.0002, 0.0006, 8, 'https://www.kucoin.com/futures/trade/{symbol}M', false, '["api_key", "api_secret", "passphrase"]'),
    ('bitget_futures', 'Bitget (Futures)', 'cex', 'tier_2', true, 'ccxt', 0.0002, 0.0006, 8, 'https://www.bitget.com/futures/usdt/{symbol}', false, '["api_key", "api_secret", "passphrase"]'),
    ('mexc_futures', 'MEXC (Futures)', 'cex', 'tier_2', true, 'ccxt', 0.0002, 0.0006, 8, NULL, false, '["api_key", "api_secret"]'),
    ('bingx_futures', 'BingX (Futures)', 'cex', 'tier_2', true, 'ccxt', 0.0002, 0.0005, 8, NULL, false, '["api_key", "api_secret"]'),
    ('hyperliquid_futures', 'Hyperliquid (Futures)', 'dex', 'tier_3', true, 'native', 0.0001, 0.00035, 1, 'https://app.hyperliquid.xyz/trade/{symbol}', true, '["wallet_address", "api_secret"]'),
    ('dydx_futures', 'dYdX (Futures)', 'dex', 'tier_3', true, 'native', 0.0001, 0.0005, 1, 'https://dydx.trade/trade/{symbol}-USD', true, '["wallet_address", "api_secret"]');

COMMIT;
