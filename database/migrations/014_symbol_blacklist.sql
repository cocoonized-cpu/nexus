-- Migration 014: Symbol Blacklist
-- Purpose: Add blacklist functionality for symbols that should never be traded
-- This table stores symbols that the bot will exclude from opportunity detection and trading

-- Create the symbol blacklist table
CREATE TABLE IF NOT EXISTS config.symbol_blacklist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(50) NOT NULL,
    reason TEXT,
    blacklisted_by VARCHAR(100) DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol)
);

-- Create index for fast symbol lookup
CREATE INDEX IF NOT EXISTS idx_symbol_blacklist_symbol ON config.symbol_blacklist(symbol);
CREATE INDEX IF NOT EXISTS idx_symbol_blacklist_created_at ON config.symbol_blacklist(created_at DESC);

-- Add comment for documentation
COMMENT ON TABLE config.symbol_blacklist IS 'Symbols that are blacklisted from trading. The bot will never open positions on these symbols.';
COMMENT ON COLUMN config.symbol_blacklist.symbol IS 'The trading symbol (e.g., BTCUSDT, ETHUSDT)';
COMMENT ON COLUMN config.symbol_blacklist.reason IS 'Optional reason for blacklisting';
COMMENT ON COLUMN config.symbol_blacklist.blacklisted_by IS 'Who/what added this blacklist entry (user, system, etc.)';

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION config.update_blacklist_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update timestamp
DROP TRIGGER IF EXISTS trigger_update_blacklist_timestamp ON config.symbol_blacklist;
CREATE TRIGGER trigger_update_blacklist_timestamp
    BEFORE UPDATE ON config.symbol_blacklist
    FOR EACH ROW
    EXECUTE FUNCTION config.update_blacklist_timestamp();
