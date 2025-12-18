-- Migration: Add missing columns to positions table

-- Add missing columns to positions.active
ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS unrealized_pnl DECIMAL(18, 6) DEFAULT 0;
ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS realized_pnl_funding DECIMAL(18, 6) DEFAULT 0;
ALTER TABLE positions.active ADD COLUMN IF NOT EXISTS realized_pnl_price DECIMAL(18, 6) DEFAULT 0;

-- Add missing columns to positions.legs
ALTER TABLE positions.legs ADD COLUMN IF NOT EXISTS unrealized_pnl DECIMAL(18, 6) DEFAULT 0;
ALTER TABLE positions.legs ADD COLUMN IF NOT EXISTS realized_pnl DECIMAL(18, 6) DEFAULT 0;
ALTER TABLE positions.legs ADD COLUMN IF NOT EXISTS mark_price DECIMAL(28, 18);
ALTER TABLE positions.legs ADD COLUMN IF NOT EXISTS avg_entry_price DECIMAL(28, 18);

COMMIT;
