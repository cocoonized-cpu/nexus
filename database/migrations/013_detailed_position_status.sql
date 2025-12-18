-- Migration: 013_detailed_position_status
-- Description: Add detailed trading status fields to positions for enhanced UI display
-- Purpose: Allow frontend to show detailed "what is happening now" status with hover tooltips

-- Add detailed status columns to positions.active
ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    current_activity VARCHAR(50) DEFAULT 'monitoring';

ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    activity_description TEXT;

ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    activity_started_at TIMESTAMPTZ;

ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    next_action VARCHAR(100);

ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    next_action_time TIMESTAMPTZ;

ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    status_reason TEXT;

ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS
    blockers JSONB DEFAULT '[]';

-- Create index on current_activity for filtering
CREATE INDEX IF NOT EXISTS idx_positions_active_current_activity
    ON positions.active(current_activity)
    WHERE status IN ('pending', 'opening', 'active', 'closing');

-- Document the activity values
COMMENT ON COLUMN positions.active.current_activity IS
    'Current detailed activity: monitoring, rebalancing, closing, risk_halted, cap_enforcement, stale_data, unhedged';

COMMENT ON COLUMN positions.active.activity_description IS
    'Human-readable description of current activity for tooltip display';

COMMENT ON COLUMN positions.active.activity_started_at IS
    'When the current activity state began';

COMMENT ON COLUMN positions.active.next_action IS
    'Description of next planned action (e.g., "Next funding at 08:00 UTC")';

COMMENT ON COLUMN positions.active.next_action_time IS
    'When the next action is scheduled';

COMMENT ON COLUMN positions.active.status_reason IS
    'Why the position is in this status (useful for non-active states)';

COMMENT ON COLUMN positions.active.blockers IS
    'Array of current blockers preventing normal operation';

-- Create a view for easy querying of position details with status
CREATE OR REPLACE VIEW positions.positions_with_status AS
SELECT
    p.id,
    p.symbol,
    p.status,
    p.current_activity,
    p.activity_description,
    p.activity_started_at,
    p.next_action,
    p.next_action_time,
    p.status_reason,
    p.blockers,
    p.long_exchange,
    p.short_exchange,
    p.total_capital_deployed,
    p.net_funding_pnl,
    p.unrealized_pnl,
    p.current_spread,
    p.initial_spread,
    p.spread_drawdown_pct,
    p.spread_trend,
    p.health,
    p.opened_at,
    p.closed_at,
    p.updated_at,
    -- Calculate time in current activity
    EXTRACT(EPOCH FROM (NOW() - COALESCE(p.activity_started_at, p.opened_at))) / 60 AS minutes_in_activity,
    -- Calculate if next action is imminent (within 1 hour)
    CASE
        WHEN p.next_action_time IS NOT NULL AND p.next_action_time < NOW() + INTERVAL '1 hour'
        THEN true
        ELSE false
    END AS action_imminent
FROM positions.active p;

COMMENT ON VIEW positions.positions_with_status IS
    'Positions with detailed status information for dashboard display';

-- Grant permissions
GRANT SELECT ON positions.positions_with_status TO nexus_app;

-- Initialize existing positions with default activity
UPDATE positions.active
SET
    current_activity = CASE
        WHEN status = 'active' THEN 'monitoring'
        WHEN status = 'opening' THEN 'opening'
        WHEN status = 'closing' THEN 'closing'
        ELSE 'unknown'
    END,
    activity_description = CASE
        WHEN status = 'active' THEN 'Collecting funding payments, monitoring spread'
        WHEN status = 'opening' THEN 'Opening position legs'
        WHEN status = 'closing' THEN 'Closing position legs'
        ELSE 'Unknown state'
    END,
    activity_started_at = COALESCE(opened_at, NOW())
WHERE current_activity IS NULL;

-- Log the migration
INSERT INTO audit.activity_events (
    service, category, event_type, severity, message, details
) VALUES (
    'migration', 'system', 'migration_applied', 'info',
    'Applied migration 013_detailed_position_status',
    '{"migration_number": 13, "description": "Add detailed trading status fields"}'::jsonb
);
