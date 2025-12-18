-- Migration: Add credential_fields and wallet_address support for exchanges
-- This migration adds support for exchange-specific credential requirements

-- Add new columns to config.exchanges
ALTER TABLE config.exchanges
ADD COLUMN IF NOT EXISTS wallet_address_encrypted BYTEA;

ALTER TABLE config.exchanges
ADD COLUMN IF NOT EXISTS credential_fields JSONB DEFAULT '["api_key", "api_secret"]'::jsonb;

-- Update credential_fields for each exchange based on their requirements
-- Most CEXes use api_key + api_secret
UPDATE config.exchanges
SET credential_fields = '["api_key", "api_secret"]'::jsonb
WHERE slug IN ('binance_futures', 'bybit_futures', 'gate_futures', 'mexc_futures', 'bingx_futures');

-- OKX, KuCoin, and Bitget require passphrase
UPDATE config.exchanges
SET credential_fields = '["api_key", "api_secret", "passphrase"]'::jsonb
WHERE slug IN ('okex_futures', 'kucoin_futures', 'bitget_futures');

-- DEXes (Hyperliquid, dYdX) require wallet address and private key
UPDATE config.exchanges
SET credential_fields = '["wallet_address", "api_secret"]'::jsonb,
    requires_on_chain = true
WHERE slug IN ('hyperliquid_futures', 'dydx_futures');

COMMIT;
