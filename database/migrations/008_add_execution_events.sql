-- Migration: Add execution_events table for detailed activity logging
-- This table stores execution events from the execution engine for the activity log

-- Ensure audit schema exists
CREATE SCHEMA IF NOT EXISTS audit;

-- Create execution_events table
CREATE TABLE IF NOT EXISTS audit.execution_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    service VARCHAR(50) NOT NULL DEFAULT 'execution-engine',
    opportunity_id UUID,
    position_id UUID,
    allocation_id UUID,
    exchange VARCHAR(50),
    symbol VARCHAR(50),
    order_id VARCHAR(100),
    side VARCHAR(10),
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    details JSONB DEFAULT '{}',
    level VARCHAR(20) DEFAULT 'info',
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_execution_events_created_at
    ON audit.execution_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_execution_events_event_type
    ON audit.execution_events(event_type);
CREATE INDEX IF NOT EXISTS idx_execution_events_opportunity_id
    ON audit.execution_events(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_position_id
    ON audit.execution_events(position_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_service
    ON audit.execution_events(service);
CREATE INDEX IF NOT EXISTS idx_execution_events_level
    ON audit.execution_events(level);
CREATE INDEX IF NOT EXISTS idx_execution_events_symbol
    ON audit.execution_events(symbol);

-- Composite index for common activity log queries
CREATE INDEX IF NOT EXISTS idx_execution_events_created_level
    ON audit.execution_events(created_at DESC, level);

-- Add comments for documentation
COMMENT ON TABLE audit.execution_events IS 'Execution engine events for activity log and audit trail';
COMMENT ON COLUMN audit.execution_events.event_type IS 'Type of execution event (execution_started, order_placed, order_filled, execution_complete, execution_failed, etc.)';
COMMENT ON COLUMN audit.execution_events.service IS 'Source service that generated the event';
COMMENT ON COLUMN audit.execution_events.opportunity_id IS 'Related opportunity ID if applicable';
COMMENT ON COLUMN audit.execution_events.position_id IS 'Related position ID if applicable';
COMMENT ON COLUMN audit.execution_events.allocation_id IS 'Related capital allocation ID if applicable';
COMMENT ON COLUMN audit.execution_events.level IS 'Log level: debug, info, warning, error';
COMMENT ON COLUMN audit.execution_events.message IS 'Human-readable event message';
COMMENT ON COLUMN audit.execution_events.details IS 'JSON with additional event details';

-- Create a view for easy activity log querying (combines all event sources)
CREATE OR REPLACE VIEW audit.activity_log_unified AS
SELECT
    id,
    'execution' as source,
    event_type,
    service,
    opportunity_id,
    position_id,
    COALESCE(symbol, exchange, 'system') as resource_type,
    details,
    level,
    message,
    created_at
FROM audit.execution_events
UNION ALL
SELECT
    id,
    'position' as source,
    event_type,
    'position-manager' as service,
    NULL as opportunity_id,
    position_id,
    COALESCE(symbol, 'system') as resource_type,
    details,
    'info' as level,
    NULL as message,
    created_at
FROM positions.events
ORDER BY created_at DESC;

COMMENT ON VIEW audit.activity_log_unified IS 'Unified view of all activity log events from various sources';

COMMIT;
