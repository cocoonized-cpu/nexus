-- Migration: Add position_events table for activity logging
-- This table stores position lifecycle events for the activity log

-- Create the position_events table in the positions schema
CREATE TABLE IF NOT EXISTS positions.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id UUID REFERENCES positions.active(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_position_events_position_id
    ON positions.events(position_id);
CREATE INDEX IF NOT EXISTS idx_position_events_event_type
    ON positions.events(event_type);
CREATE INDEX IF NOT EXISTS idx_position_events_created_at
    ON positions.events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_position_events_symbol
    ON positions.events(symbol);

-- Composite index for filtering by position and event type
CREATE INDEX IF NOT EXISTS idx_position_events_pos_type
    ON positions.events(position_id, event_type);

-- Add comments for documentation
COMMENT ON TABLE positions.events IS 'Position lifecycle events for activity log display';
COMMENT ON COLUMN positions.events.event_type IS 'Type of position event (position_opened, position_closed, funding_received, funding_paid, health_changed, rebalance_triggered, stop_loss_triggered, take_profit_triggered)';
COMMENT ON COLUMN positions.events.symbol IS 'Trading pair symbol for the position';
COMMENT ON COLUMN positions.events.details IS 'JSON details specific to the event type';

COMMIT;
