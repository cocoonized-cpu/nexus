-- Migration: Initialize system state for trading
-- This ensures the system is properly configured to execute trades

-- First, ensure config schema exists
CREATE SCHEMA IF NOT EXISTS config;

-- Create system_settings table if it doesn't exist
CREATE TABLE IF NOT EXISTS config.system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    data_type VARCHAR(20) DEFAULT 'string',
    category VARCHAR(50) DEFAULT 'system',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create trigger for updated_at
CREATE OR REPLACE FUNCTION config.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_system_settings_updated_at ON config.system_settings;
CREATE TRIGGER update_system_settings_updated_at
    BEFORE UPDATE ON config.system_settings
    FOR EACH ROW
    EXECUTE FUNCTION config.update_updated_at_column();

-- Initialize system state settings for trading
INSERT INTO config.system_settings (key, value, data_type, category, description) VALUES
    ('system_running', 'true', 'boolean', 'system', 'Whether the trading system is running'),
    ('new_positions_enabled', 'true', 'boolean', 'system', 'Allow opening new positions'),
    ('system_mode', '"standard"', 'string', 'system', 'Operating mode: standard, aggressive, conservative, discovery, emergency'),
    ('auto_execute', 'true', 'boolean', 'capital', 'Auto-execute high quality opportunities without manual approval'),
    ('circuit_breaker_active', 'false', 'boolean', 'risk', 'Emergency circuit breaker state'),
    ('min_allocation_usd', '100', 'decimal', 'capital', 'Minimum capital allocation per position'),
    ('max_allocation_usd', '10000', 'decimal', 'capital', 'Maximum capital allocation per position'),
    ('min_uos_score', '65', 'integer', 'capital', 'Minimum UOS score to consider opportunity'),
    ('high_quality_threshold', '75', 'integer', 'capital', 'UOS score threshold for auto-execution'),
    ('max_allocations', '10', 'integer', 'capital', 'Maximum concurrent positions'),
    ('reserve_percentage', '0.20', 'decimal', 'capital', 'Percentage of capital to keep in reserve')
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_system_settings_category ON config.system_settings(category);

COMMENT ON TABLE config.system_settings IS 'System configuration settings stored as key-value pairs';
COMMENT ON COLUMN config.system_settings.key IS 'Unique setting identifier';
COMMENT ON COLUMN config.system_settings.value IS 'Setting value as JSON (allows any type)';
COMMENT ON COLUMN config.system_settings.data_type IS 'Data type hint: string, boolean, integer, decimal, json';
COMMENT ON COLUMN config.system_settings.category IS 'Setting category for grouping: system, capital, risk, etc.';

COMMIT;
