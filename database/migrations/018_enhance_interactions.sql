-- Migration 018: Enhance Position Interactions
-- Purpose: Add event_category and severity columns, change FK behavior to preserve interactions

-- Add event_category column for filtering interactions by category
ALTER TABLE positions.interactions
ADD COLUMN IF NOT EXISTS event_category VARCHAR(50);

-- Add severity column for visual distinction
ALTER TABLE positions.interactions
ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'info';

-- Create indexes for efficient filtering
CREATE INDEX IF NOT EXISTS idx_interactions_category
    ON positions.interactions(event_category);

CREATE INDEX IF NOT EXISTS idx_interactions_severity
    ON positions.interactions(severity);

CREATE INDEX IF NOT EXISTS idx_interactions_symbol_ts
    ON positions.interactions(symbol, timestamp DESC);

-- Change FK behavior to SET NULL instead of CASCADE
-- This preserves interactions when positions are deleted/reset
DO $$
BEGIN
    -- Check if the constraint exists
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'interactions_position_id_fkey'
        AND table_schema = 'positions'
        AND table_name = 'interactions'
    ) THEN
        ALTER TABLE positions.interactions
        DROP CONSTRAINT interactions_position_id_fkey;
    END IF;
END $$;

-- Re-add the constraint with ON DELETE SET NULL
ALTER TABLE positions.interactions
ADD CONSTRAINT interactions_position_id_fkey
FOREIGN KEY (position_id) REFERENCES positions.active(id) ON DELETE SET NULL;

-- Update existing interaction types with categories
UPDATE positions.interactions
SET event_category = CASE
    WHEN interaction_type IN ('position_opened', 'position_closed', 'health_check', 'health_changed', 'rebalance_check', 'rebalance_triggered', 'exit_evaluation', 'exit_triggered') THEN 'position'
    WHEN interaction_type IN ('funding_check', 'funding_collected') THEN 'funding'
    WHEN interaction_type IN ('spread_update') THEN 'price'
    ELSE 'position'
END
WHERE event_category IS NULL;

-- Update severity based on interaction type and decision
UPDATE positions.interactions
SET severity = CASE
    WHEN interaction_type = 'exit_triggered' THEN 'warning'
    WHEN interaction_type = 'position_closed' THEN 'info'
    WHEN interaction_type = 'health_changed' AND decision = 'degraded' THEN 'warning'
    WHEN interaction_type = 'health_changed' AND decision = 'recovered' THEN 'info'
    WHEN interaction_type = 'rebalance_triggered' THEN 'warning'
    WHEN interaction_type = 'funding_collected' THEN 'info'
    ELSE 'info'
END
WHERE severity IS NULL OR severity = 'info';

-- Add comments for documentation
COMMENT ON COLUMN positions.interactions.event_category IS 'Category for filtering: position, opportunity, funding, price, order, risk';
COMMENT ON COLUMN positions.interactions.severity IS 'Severity level: debug, info, warning, error, critical';
