-- Migration 015: Position Interactions
-- Purpose: Track all bot interactions with positions for the Interactions timeline feature
-- This table stores every decision point and action taken by workers on positions

-- Create the position interactions table
CREATE TABLE IF NOT EXISTS positions.interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Entity references
    position_id UUID REFERENCES positions.active(id) ON DELETE CASCADE,
    opportunity_id UUID,
    symbol VARCHAR(50),

    -- Timing
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Interaction details
    interaction_type VARCHAR(50) NOT NULL,  -- funding_check, health_check, spread_evaluation, exit_decision, rebalance, entry_check, monitoring, etc.
    worker_service VARCHAR(50) NOT NULL,    -- position-manager, execution-engine, risk-manager, opportunity-detector, capital-allocator

    -- Decision and outcome
    decision VARCHAR(50),                   -- kept_open, triggered_exit, rebalanced, skipped, executed, rejected, etc.
    narrative TEXT NOT NULL,                -- Human-readable description of what happened and why

    -- Context metrics at time of interaction
    metrics JSONB DEFAULT '{}',             -- Relevant metrics (spread, funding_rate, health_score, etc.)

    -- Audit
    correlation_id UUID,                    -- For tracing related interactions
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_position_interactions_position_id
    ON positions.interactions(position_id);

CREATE INDEX IF NOT EXISTS idx_position_interactions_position_timestamp
    ON positions.interactions(position_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_position_interactions_type
    ON positions.interactions(interaction_type);

CREATE INDEX IF NOT EXISTS idx_position_interactions_worker
    ON positions.interactions(worker_service);

CREATE INDEX IF NOT EXISTS idx_position_interactions_symbol
    ON positions.interactions(symbol);

CREATE INDEX IF NOT EXISTS idx_position_interactions_timestamp
    ON positions.interactions(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_position_interactions_opportunity
    ON positions.interactions(opportunity_id);

-- Add comments for documentation
COMMENT ON TABLE positions.interactions IS 'Granular timeline of all bot interactions with positions. Each row represents a decision point or action taken by a worker.';
COMMENT ON COLUMN positions.interactions.interaction_type IS 'Type of interaction: funding_check, health_check, spread_evaluation, exit_decision, rebalance, entry_check, monitoring';
COMMENT ON COLUMN positions.interactions.worker_service IS 'The service that generated this interaction: position-manager, execution-engine, risk-manager, etc.';
COMMENT ON COLUMN positions.interactions.decision IS 'The decision made: kept_open, triggered_exit, rebalanced, skipped, executed, rejected';
COMMENT ON COLUMN positions.interactions.narrative IS 'Human-readable description explaining what happened and why';
COMMENT ON COLUMN positions.interactions.metrics IS 'JSON object with relevant metrics at time of interaction (spread, funding_rate, health_score, etc.)';

-- Create a view for easy querying of recent interactions
CREATE OR REPLACE VIEW positions.recent_interactions AS
SELECT
    i.id,
    i.position_id,
    COALESCE(p.symbol, i.symbol) as symbol,
    i.timestamp,
    i.interaction_type,
    i.worker_service,
    i.decision,
    i.narrative,
    i.metrics
FROM positions.interactions i
LEFT JOIN positions.active p ON i.position_id = p.id
WHERE i.timestamp > NOW() - INTERVAL '24 hours'
ORDER BY i.timestamp DESC;

COMMENT ON VIEW positions.recent_interactions IS 'Recent position interactions from the last 24 hours with position details';
