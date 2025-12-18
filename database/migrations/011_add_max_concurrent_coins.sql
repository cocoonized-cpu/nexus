-- Migration: 011_add_max_concurrent_coins.sql
-- Description: Add max_concurrent_coins configuration for position limit control
-- Date: 2024-12-18

-- Add max_concurrent_coins to strategy_parameters table
ALTER TABLE config.strategy_parameters
ADD COLUMN IF NOT EXISTS max_concurrent_coins INTEGER DEFAULT 5;

-- Add comment for documentation
COMMENT ON COLUMN config.strategy_parameters.max_concurrent_coins IS
'Maximum number of coins (arbitrage positions) that can be active simultaneously. Each coin = 2 exchange positions (1 long + 1 short). Default: 5 coins = 10 total exchange positions.';

-- Update existing system_settings if max_allocations exists (for migration from old naming)
UPDATE config.system_settings
SET key = 'max_concurrent_coins',
    description = 'Maximum number of coins traded simultaneously (each coin = 2 positions)'
WHERE key = 'max_allocations';

-- Insert default value into system_settings if not exists
INSERT INTO config.system_settings (key, value, data_type, category, description)
VALUES (
    'max_concurrent_coins',
    '5'::jsonb,
    'integer',
    'capital',
    'Maximum number of coins traded simultaneously (each coin = 2 positions)'
)
ON CONFLICT (key) DO NOTHING;

-- Create table to track auto-unwind events for audit purposes
CREATE TABLE IF NOT EXISTS capital.auto_unwind_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    allocation_id UUID NOT NULL,
    position_id UUID,
    symbol VARCHAR(50) NOT NULL,
    reason VARCHAR(100) NOT NULL,
    weakness_score DECIMAL(10, 4),
    coins_before INTEGER NOT NULL,
    max_coins INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for querying recent events
CREATE INDEX IF NOT EXISTS idx_auto_unwind_events_created
    ON capital.auto_unwind_events(created_at DESC);

-- Index for querying by symbol
CREATE INDEX IF NOT EXISTS idx_auto_unwind_events_symbol
    ON capital.auto_unwind_events(symbol);
