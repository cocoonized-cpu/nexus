-- NEXUS Migration 010: Add Global Spread History for ML Training
-- Creates funding.spread_history table to capture historical spreads for all coins
-- This data will be used for deep learning-based funding rate forecasting

-- =============================================================================
-- STEP 1: Create global spread history table
-- =============================================================================

CREATE TABLE IF NOT EXISTS funding.spread_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(50) NOT NULL,           -- Base symbol (e.g., "BTC", "ETH", "DEEP")
    long_exchange VARCHAR(50) NOT NULL,    -- Exchange with lower funding rate (long side)
    short_exchange VARCHAR(50) NOT NULL,   -- Exchange with higher funding rate (short side)
    long_rate DECIMAL(20, 10) NOT NULL,    -- Funding rate on long exchange
    short_rate DECIMAL(20, 10) NOT NULL,   -- Funding rate on short exchange
    spread DECIMAL(20, 10) NOT NULL,       -- short_rate - long_rate
    spread_annualized DECIMAL(20, 10),     -- Annualized spread (spread * 3 * 365 for 8h funding)
    long_next_funding TIMESTAMPTZ,         -- Next funding time for long exchange
    short_next_funding TIMESTAMPTZ,        -- Next funding time for short exchange
    data_source VARCHAR(30) DEFAULT 'aggregator',  -- 'aggregator', 'position_manager'
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_spread_history_symbol_time
    ON funding.spread_history(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_spread_history_timestamp
    ON funding.spread_history(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_spread_history_exchanges
    ON funding.spread_history(long_exchange, short_exchange);

CREATE INDEX IF NOT EXISTS idx_spread_history_spread
    ON funding.spread_history(spread DESC);

-- Composite index for ML queries (get all spreads for a symbol-pair)
CREATE INDEX IF NOT EXISTS idx_spread_history_symbol_exchanges
    ON funding.spread_history(symbol, long_exchange, short_exchange, timestamp DESC);

COMMENT ON TABLE funding.spread_history IS 'Historical spread snapshots for ML training and forecasting';
COMMENT ON COLUMN funding.spread_history.symbol IS 'Base asset symbol (e.g., BTC, ETH)';
COMMENT ON COLUMN funding.spread_history.spread IS 'Funding rate spread (short_rate - long_rate)';
COMMENT ON COLUMN funding.spread_history.spread_annualized IS 'Spread annualized (3 funding periods/day * 365 days)';
COMMENT ON COLUMN funding.spread_history.data_source IS 'Source of the data (aggregator or position_manager)';

-- Grant permissions
GRANT SELECT, INSERT, DELETE ON funding.spread_history TO nexus;

-- =============================================================================
-- STEP 2: Create function to record spread snapshots
-- =============================================================================

CREATE OR REPLACE FUNCTION funding.record_spread_snapshot(
    p_symbol VARCHAR(50),
    p_long_exchange VARCHAR(50),
    p_short_exchange VARCHAR(50),
    p_long_rate DECIMAL(20, 10),
    p_short_rate DECIMAL(20, 10),
    p_long_next_funding TIMESTAMPTZ DEFAULT NULL,
    p_short_next_funding TIMESTAMPTZ DEFAULT NULL,
    p_data_source VARCHAR(30) DEFAULT 'aggregator'
) RETURNS UUID AS $$
DECLARE
    v_spread DECIMAL(20, 10);
    v_spread_annualized DECIMAL(20, 10);
    v_id UUID;
BEGIN
    v_spread := p_short_rate - p_long_rate;
    -- Annualize: spread * 3 funding periods/day * 365 days
    v_spread_annualized := v_spread * 3 * 365;

    INSERT INTO funding.spread_history (
        symbol, long_exchange, short_exchange,
        long_rate, short_rate, spread, spread_annualized,
        long_next_funding, short_next_funding, data_source
    ) VALUES (
        p_symbol, p_long_exchange, p_short_exchange,
        p_long_rate, p_short_rate, v_spread, v_spread_annualized,
        p_long_next_funding, p_short_next_funding, p_data_source
    ) RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION funding.record_spread_snapshot IS 'Records a single spread snapshot for ML training';

-- =============================================================================
-- STEP 3: Create function to cleanup old spread history
-- =============================================================================

CREATE OR REPLACE FUNCTION funding.cleanup_old_spread_history(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete snapshots older than retention period
    DELETE FROM funding.spread_history
    WHERE timestamp < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION funding.cleanup_old_spread_history IS 'Cleanup old spread history (default 90 days retention)';

-- =============================================================================
-- STEP 4: Create view for top spreads analysis
-- =============================================================================

CREATE OR REPLACE VIEW funding.v_spread_summary AS
SELECT
    symbol,
    long_exchange,
    short_exchange,
    COUNT(*) as snapshot_count,
    AVG(spread) as avg_spread,
    MAX(spread) as max_spread,
    MIN(spread) as min_spread,
    STDDEV(spread) as spread_volatility,
    AVG(spread_annualized) as avg_annualized,
    MIN(timestamp) as first_seen,
    MAX(timestamp) as last_seen
FROM funding.spread_history
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY symbol, long_exchange, short_exchange
ORDER BY avg_spread DESC;

COMMENT ON VIEW funding.v_spread_summary IS 'Summary statistics for spread analysis and ML feature engineering';

-- =============================================================================
-- VERIFICATION
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'funding'
        AND table_name = 'spread_history'
    ) THEN
        RAISE EXCEPTION 'Migration failed: spread_history table not created';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'funding' AND p.proname = 'record_spread_snapshot'
    ) THEN
        RAISE EXCEPTION 'Migration failed: record_spread_snapshot function not created';
    END IF;

    RAISE NOTICE 'Migration 010_add_global_spread_history completed successfully';
END $$;
