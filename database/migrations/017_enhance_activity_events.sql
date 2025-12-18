-- Migration 017: Enhanced Activity Events
-- Purpose: Add additional columns to activity_events for richer event logging
-- Adds: worker_name, entity_type, entity_id, decision, narrative for better traceability

-- Add new columns to activity_events table
ALTER TABLE audit.activity_events
    ADD COLUMN IF NOT EXISTS worker_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS entity_id UUID,
    ADD COLUMN IF NOT EXISTS decision VARCHAR(50),
    ADD COLUMN IF NOT EXISTS narrative TEXT;

-- Create indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_activity_events_worker_name
    ON audit.activity_events(worker_name)
    WHERE worker_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_activity_events_entity
    ON audit.activity_events(entity_type, entity_id)
    WHERE entity_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_activity_events_decision
    ON audit.activity_events(decision)
    WHERE decision IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN audit.activity_events.worker_name IS 'Name of the worker/task that generated this event (e.g., funding_monitor, health_checker)';
COMMENT ON COLUMN audit.activity_events.entity_type IS 'Type of entity this event relates to: position, opportunity, order, allocation';
COMMENT ON COLUMN audit.activity_events.entity_id IS 'UUID of the entity this event relates to';
COMMENT ON COLUMN audit.activity_events.decision IS 'Decision made at this event: kept_open, triggered_exit, rebalanced, skipped, executed, rejected';
COMMENT ON COLUMN audit.activity_events.narrative IS 'Human-readable narrative explaining what happened and why';

-- Update the recent_activity view to include new columns
DROP VIEW IF EXISTS audit.recent_activity CASCADE;
CREATE OR REPLACE VIEW audit.recent_activity AS
SELECT
    id,
    timestamp,
    service,
    category,
    event_type,
    severity,
    symbol,
    exchange,
    position_id,
    order_id,
    allocation_id,
    correlation_id,
    worker_name,
    entity_type,
    entity_id,
    decision,
    narrative,
    message,
    details
FROM audit.activity_events
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

COMMENT ON VIEW audit.recent_activity IS
    'Last 24 hours of activity events with enhanced worker and entity details';

-- Create a view for worker-specific activity
CREATE OR REPLACE VIEW audit.worker_activity AS
SELECT
    worker_name,
    service,
    COUNT(*) as event_count,
    COUNT(*) FILTER (WHERE severity = 'error') as error_count,
    COUNT(*) FILTER (WHERE severity = 'warning') as warning_count,
    MAX(timestamp) as last_event_at
FROM audit.activity_events
WHERE timestamp > NOW() - INTERVAL '1 hour'
    AND worker_name IS NOT NULL
GROUP BY worker_name, service
ORDER BY last_event_at DESC;

COMMENT ON VIEW audit.worker_activity IS
    'Summary of worker activity in the last hour';

-- Log the migration
INSERT INTO audit.activity_events (
    service, category, event_type, severity, message, details
) VALUES (
    'migration', 'system', 'migration_applied', 'info',
    'Applied migration 017_enhance_activity_events',
    '{"migration_number": 17, "description": "Add worker_name, entity_type, entity_id, decision, narrative columns to activity_events"}'::jsonb
);
