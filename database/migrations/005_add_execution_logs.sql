-- Migration: Add execution_logs table for comprehensive order logging
-- This table stores detailed execution events for analysis and debugging

-- Create the execution_logs table in the audit schema
CREATE TABLE IF NOT EXISTS audit.execution_logs (
    id UUID PRIMARY KEY,
    opportunity_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_execution_logs_opportunity_id
    ON audit.execution_logs(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_execution_logs_event_type
    ON audit.execution_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_execution_logs_status
    ON audit.execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_execution_logs_created_at
    ON audit.execution_logs(created_at DESC);

-- Composite index for filtering by opportunity and event type
CREATE INDEX IF NOT EXISTS idx_execution_logs_opp_event
    ON audit.execution_logs(opportunity_id, event_type);

-- Add comment for documentation
COMMENT ON TABLE audit.execution_logs IS 'Detailed execution event logs for opportunity execution analysis';
COMMENT ON COLUMN audit.execution_logs.event_type IS 'Type of execution event (execution_started, placing_primary_order, etc.)';
COMMENT ON COLUMN audit.execution_logs.status IS 'Status of the event (pending, completed, error, success)';
COMMENT ON COLUMN audit.execution_logs.details IS 'JSON details specific to the event type';

COMMIT;
