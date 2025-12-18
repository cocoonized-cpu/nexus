-- Migration: 012_unified_activity_events
-- Description: Create unified activity_events table for comprehensive event logging
-- Purpose: Consolidate all service events into a single queryable table
--          to power Activity Log in the frontend dashboard

-- Create audit schema if not exists
CREATE SCHEMA IF NOT EXISTS audit;

-- Create the unified activity events table
CREATE TABLE IF NOT EXISTS audit.activity_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    service VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL,  -- order, position, funding, risk, capital, system
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',  -- debug, info, warning, error, critical
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    position_id UUID,
    order_id VARCHAR(100),
    allocation_id UUID,
    correlation_id UUID,  -- For tracking related events
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_activity_events_timestamp
    ON audit.activity_events(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_activity_events_category
    ON audit.activity_events(category);

CREATE INDEX IF NOT EXISTS idx_activity_events_service
    ON audit.activity_events(service);

CREATE INDEX IF NOT EXISTS idx_activity_events_symbol
    ON audit.activity_events(symbol)
    WHERE symbol IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_activity_events_severity
    ON audit.activity_events(severity);

CREATE INDEX IF NOT EXISTS idx_activity_events_position_id
    ON audit.activity_events(position_id)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_activity_events_correlation_id
    ON audit.activity_events(correlation_id)
    WHERE correlation_id IS NOT NULL;

-- Composite index for common query pattern (recent events by category)
CREATE INDEX IF NOT EXISTS idx_activity_events_category_timestamp
    ON audit.activity_events(category, timestamp DESC);

-- Composite index for filtering by service and time
CREATE INDEX IF NOT EXISTS idx_activity_events_service_timestamp
    ON audit.activity_events(service, timestamp DESC);

-- Comment on table
COMMENT ON TABLE audit.activity_events IS
    'Unified activity event log for all NEXUS services. Powers the Activity Log in the dashboard.';

-- Define valid categories
COMMENT ON COLUMN audit.activity_events.category IS
    'Event category: order, position, funding, risk, capital, system';

-- Define valid severities
COMMENT ON COLUMN audit.activity_events.severity IS
    'Event severity: debug, info, warning, error, critical';

-- Function to automatically clean up old events (retention policy)
CREATE OR REPLACE FUNCTION audit.cleanup_old_activity_events()
RETURNS void AS $$
BEGIN
    -- Keep events for 30 days by default
    DELETE FROM audit.activity_events
    WHERE timestamp < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT SELECT, INSERT ON audit.activity_events TO nexus_app;
GRANT EXECUTE ON FUNCTION audit.cleanup_old_activity_events() TO nexus_app;

-- Create a view for easy querying of recent activity
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
    message,
    details
FROM audit.activity_events
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

COMMENT ON VIEW audit.recent_activity IS
    'Last 24 hours of activity events for quick dashboard queries';

-- Log the migration
INSERT INTO audit.activity_events (
    service, category, event_type, severity, message, details
) VALUES (
    'migration', 'system', 'migration_applied', 'info',
    'Applied migration 012_unified_activity_events',
    '{"migration_number": 12, "description": "Create unified activity_events table"}'::jsonb
);
