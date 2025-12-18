-- Migration: Add exchange positions and orders tracking tables
-- These tables store raw position and order data from exchanges

-- Exchange positions (raw data from exchanges)
CREATE TABLE IF NOT EXISTS positions.exchange_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'long' or 'short'
    size DECIMAL(28, 18) NOT NULL,
    notional_usd DECIMAL(18, 2) NOT NULL,
    entry_price DECIMAL(28, 18) NOT NULL,
    mark_price DECIMAL(28, 18) NOT NULL,
    unrealized_pnl DECIMAL(18, 6) DEFAULT 0,
    leverage DECIMAL(10, 4) DEFAULT 1,
    liquidation_price DECIMAL(28, 18),
    margin_mode VARCHAR(20) DEFAULT 'cross',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_exchange_position UNIQUE (exchange, symbol)
);

CREATE INDEX IF NOT EXISTS idx_exchange_positions_exchange ON positions.exchange_positions (exchange);
CREATE INDEX IF NOT EXISTS idx_exchange_positions_symbol ON positions.exchange_positions (symbol);

-- Exchange orders (raw data from exchanges)
CREATE TABLE IF NOT EXISTS positions.exchange_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange_order_id VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'buy' or 'sell'
    order_type VARCHAR(20) NOT NULL,  -- 'limit', 'market', etc.
    price DECIMAL(28, 18),
    amount DECIMAL(28, 18) NOT NULL,
    filled DECIMAL(28, 18) DEFAULT 0,
    remaining DECIMAL(28, 18),
    status VARCHAR(20) NOT NULL,  -- 'open', 'closed', 'canceled'
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_exchange_order UNIQUE (exchange, exchange_order_id)
);

CREATE INDEX IF NOT EXISTS idx_exchange_orders_exchange ON positions.exchange_orders (exchange);
CREATE INDEX IF NOT EXISTS idx_exchange_orders_status ON positions.exchange_orders (status);
CREATE INDEX IF NOT EXISTS idx_exchange_orders_symbol ON positions.exchange_orders (symbol);

-- Order history (for tracking filled orders)
CREATE TABLE IF NOT EXISTS positions.order_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange_order_id VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    price DECIMAL(28, 18),
    amount DECIMAL(28, 18) NOT NULL,
    filled DECIMAL(28, 18) NOT NULL,
    fee DECIMAL(18, 6) DEFAULT 0,
    fee_currency VARCHAR(20),
    status VARCHAR(20) NOT NULL,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_history_exchange ON positions.order_history (exchange);
CREATE INDEX IF NOT EXISTS idx_order_history_symbol ON positions.order_history (symbol);
CREATE INDEX IF NOT EXISTS idx_order_history_executed ON positions.order_history (executed_at);

COMMIT;
