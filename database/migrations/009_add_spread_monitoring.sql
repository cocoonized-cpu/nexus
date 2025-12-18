-- NEXUS Migration 009: Add Spread Monitoring Support
-- Adds spread tracking columns, spread snapshots table, and guardrail configuration

-- =============================================================================
-- STEP 1: Add spread tracking columns to positions.active
-- =============================================================================

ALTER TABLE positions.active
    ADD COLUMN IF NOT EXISTS initial_spread DECIMAL(20, 10),
    ADD COLUMN IF NOT EXISTS current_spread DECIMAL(20, 10),
    ADD COLUMN IF NOT EXISTS spread_drawdown_pct DECIMAL(10, 6) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS spread_trend VARCHAR(20) DEFAULT 'stable';

COMMENT ON COLUMN positions.active.initial_spread IS 'Spread at position entry (short_rate - long_rate)';
COMMENT ON COLUMN positions.active.current_spread IS 'Current funding rate spread';
COMMENT ON COLUMN positions.active.spread_drawdown_pct IS 'Percentage drop from initial spread';
COMMENT ON COLUMN positions.active.spread_trend IS 'rising, falling, or stable';

-- =============================================================================
-- STEP 2: Create spread snapshots table for charting (time-series)
-- =============================================================================

CREATE TABLE IF NOT EXISTS positions.spread_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES positions.active(id) ON DELETE CASCADE,
    spread DECIMAL(20, 10) NOT NULL,
    long_rate DECIMAL(20, 10),
    short_rate DECIMAL(20, 10),
    price DECIMAL(28, 18),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for efficient querying by position and time range
CREATE INDEX IF NOT EXISTS idx_spread_snapshots_position_time
    ON positions.spread_snapshots(position_id, timestamp DESC);

-- Index for cleanup queries (old snapshots)
CREATE INDEX IF NOT EXISTS idx_spread_snapshots_timestamp
    ON positions.spread_snapshots(timestamp);

COMMENT ON TABLE positions.spread_snapshots IS 'Time-series spread data for TradingView-like charting';
COMMENT ON COLUMN positions.spread_snapshots.spread IS 'Funding rate spread (short_rate - long_rate)';
COMMENT ON COLUMN positions.spread_snapshots.long_rate IS 'Long exchange funding rate at snapshot time';
COMMENT ON COLUMN positions.spread_snapshots.short_rate IS 'Short exchange funding rate at snapshot time';
COMMENT ON COLUMN positions.spread_snapshots.price IS 'Asset price at snapshot time';

-- Grant permissions
GRANT SELECT, INSERT, DELETE ON positions.spread_snapshots TO nexus;

-- =============================================================================
-- STEP 3: Add spread monitoring guardrail columns to config.strategy_parameters
-- =============================================================================

ALTER TABLE config.strategy_parameters
    ADD COLUMN IF NOT EXISTS spread_drawdown_exit_pct DECIMAL(10, 4) DEFAULT 50.0,
    ADD COLUMN IF NOT EXISTS min_time_to_funding_exit_seconds INTEGER DEFAULT 1800;

COMMENT ON COLUMN config.strategy_parameters.spread_drawdown_exit_pct IS 'Exit when spread drops by this % from entry (default 50%)';
COMMENT ON COLUMN config.strategy_parameters.min_time_to_funding_exit_seconds IS 'Funding protection window - dont auto-exit if funding payment is due within this time (default 1800s = 30 min)';

-- =============================================================================
-- STEP 4: Create function to cleanup old spread snapshots
-- =============================================================================

CREATE OR REPLACE FUNCTION positions.cleanup_old_spread_snapshots(retention_days INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete snapshots older than retention period for closed positions
    DELETE FROM positions.spread_snapshots
    WHERE position_id IN (
        SELECT id FROM positions.active
        WHERE status IN ('closed', 'cancelled', 'failed')
        AND closed_at < NOW() - (retention_days || ' days')::INTERVAL
    );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION positions.cleanup_old_spread_snapshots IS 'Cleanup old spread snapshots for closed positions';

-- =============================================================================
-- VERIFICATION
-- =============================================================================

DO $$
BEGIN
    -- Verify columns exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'positions'
        AND table_name = 'active'
        AND column_name = 'spread_drawdown_pct'
    ) THEN
        RAISE EXCEPTION 'Migration failed: spread_drawdown_pct column not created';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'positions'
        AND table_name = 'spread_snapshots'
    ) THEN
        RAISE EXCEPTION 'Migration failed: spread_snapshots table not created';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'config'
        AND table_name = 'strategy_parameters'
        AND column_name = 'spread_drawdown_exit_pct'
    ) THEN
        RAISE EXCEPTION 'Migration failed: spread_drawdown_exit_pct config column not created';
    END IF;

    RAISE NOTICE 'Migration 009_add_spread_monitoring completed successfully';
END $$;
