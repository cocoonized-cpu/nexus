# Overview

This document provides comprehensive specifications for building NEXUS (Neural EXchange Unified Strategy), a sophisticated funding rate arbitrage system. Follow these instructions to implement a production-grade system.

**Important:** Read the accompanying whitepaper (NEXUS_Whitepaper.md) for conceptual understanding before implementing.

---

# ⚠️ CRITICAL: Dual-Source Funding Rate Architecture

## Funding Rate Data Strategy

NEXUS employs a **dual-source architecture** for funding rate data to ensure maximum accuracy, reliability, and coverage:

### PRIMARY SOURCE: Direct Exchange APIs
```
Sources: Binance, Bybit, OKX, Hyperliquid, dYdX, Gate, KuCoin, Bitget, etc.
Refresh: Every 5-10 seconds per exchange
Purpose: Authoritative, real-time funding rates directly from source
Advantages:
  - Most accurate and up-to-date data
  - No third-party dependency
  - Full control over refresh timing
  - Access to additional exchange-specific data
```

### SECONDARY SOURCE: ArbitrageScanner API
```
Funding Rates:
  URL: https://screener.arbitragescanner.io/api/funding-table
  Refresh: Every 5 seconds
  Purpose: Cross-validation, gap filling, opportunity discovery

Exchange Registry:
  URL: https://api.arbitragescanner.io/exchanges
  Refresh: Every 1 hour
  Purpose: Master list of supported exchanges and their capabilities
```

### Why Dual-Source Matters:

1. **Accuracy**: Exchange APIs provide authoritative data; ArbitrageScanner validates
2. **Reliability**: If one exchange API fails, ArbitrageScanner provides backup
3. **Coverage**: ArbitrageScanner may cover exchanges not directly integrated
4. **Discovery**: ArbitrageScanner's `maxSpread` enables quick opportunity scanning
5. **Validation**: Cross-reference both sources to detect anomalies

### Data Reconciliation Strategy:

```
For each symbol on each exchange:
  1. Fetch rate from exchange API (PRIMARY)
  2. Fetch rate from ArbitrageScanner (SECONDARY)
  3. Compare values:
     - If match (within tolerance): Use exchange API value ✓
     - If mismatch: Log discrepancy, use exchange API value, flag for review
     - If exchange API fails: Fall back to ArbitrageScanner value
     - If ArbitrageScanner has data exchange doesn't: Include with "unverified" flag
```

### Implementation Priority:

1. **FIRST:** Implement exchange API providers (Binance, Bybit, OKX, Hyperliquid)
2. **SECOND:** Implement `ArbitrageScannerClient` class
3. **THIRD:** Build `FundingRateAggregator` that merges both sources
4. **FOURTH:** Add reconciliation and anomaly detection
5. **THEN:** Build opportunity detection on unified data


# 1. Project Structure

Create the following directory structure:

```
nexus/
├── config/
│   ├── default.yaml           # Default configuration
│   ├── exchanges.yaml         # Exchange-specific settings
│   ├── arbitragescanner.yaml  # ArbitrageScanner API settings
│   └── strategies.yaml        # Strategy parameters
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine.py          # Main orchestration engine
│   │   ├── state_manager.py   # Global state management
│   │   └── event_bus.py       # Event pub/sub system
│   ├── data/
│   │   ├── __init__.py
│   │   ├── collector.py       # Data collection orchestrator
│   │   ├── normalizer.py      # Data normalization
│   │   ├── cache.py           # Data caching layer
│   │   ├── arbitragescanner/  # PRIMARY DATA SOURCE
│   │   │   ├── __init__.py
│   │   │   ├── client.py      # ArbitrageScanner API client
│   │   │   ├── models.py      # ArbitrageScanner data models
│   │   │   ├── parser.py      # Response parsing and normalization
│   │   │   └── websocket.py   # WebSocket connection (if available)
│   │   └── providers/         # SECONDARY: Exchange-specific (for execution)
│   │       ├── __init__.py
│   │       ├── base.py        # Abstract provider interface
│   │       ├── binance.py     # Binance data provider
│   │       ├── bybit.py       # Bybit data provider
│   │       ├── okx.py         # OKX data provider
│   │       ├── hyperliquid.py # Hyperliquid data provider
│   │       └── ...            # Other exchange providers
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── scanner.py         # Opportunity scanner
│   │   ├── constructor.py     # Opportunity constructor
│   │   ├── scorer.py          # UOS scoring engine
│   │   └── predictor.py       # Funding rate predictor
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── engine.py          # Execution orchestrator
│   │   ├── timing.py          # Timing optimizer
│   │   ├── router.py          # Smart order router
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── base.py        # Abstract execution handler
│   │       ├── binance.py     # Binance execution
│   │       ├── bybit.py       # Bybit execution
│   │       └── ...            # Other exchange handlers
│   ├── positions/
│   │   ├── __init__.py
│   │   ├── manager.py         # Position lifecycle manager
│   │   ├── monitor.py         # Position health monitor
│   │   ├── rebalancer.py      # Position rebalancing logic
│   │   └── models.py          # Position data models
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── manager.py         # Risk management orchestrator
│   │   ├── calculator.py      # Risk metric calculations
│   │   ├── limits.py          # Limit checking and enforcement
│   │   └── protocols.py       # Emergency protocols
│   ├── capital/
│   │   ├── __init__.py
│   │   ├── allocator.py       # Capital allocation engine
│   │   ├── optimizer.py       # Allocation optimization
│   │   └── pools.py           # Capital pool management
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── performance.py     # Performance calculations
│   │   ├── attribution.py     # Return/risk attribution
│   │   └── reporting.py       # Report generation
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── manager.py         # Alert management
│   │   ├── channels/
│   │   │   ├── __init__.py
│   │   │   ├── telegram.py    # Telegram notifications
│   │   │   ├── discord.py     # Discord notifications
│   │   │   └── email.py       # Email notifications
│   │   └── templates.py       # Alert message templates
│   └── utils/
│       ├── __init__.py
│       ├── logging.py         # Logging configuration
│       ├── helpers.py         # Utility functions
│       └── constants.py       # System constants
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── scripts/
│   ├── setup.py               # Initial setup script
│   └── backtest.py            # Backtesting script
├── logs/
├── data/
├── main.py                    # Application entry point
├── requirements.txt
└── README.md
```

---

# 2. Core Data Models

## 2.1 ArbitrageScanner Data Models (PRIMARY SOURCE)

### ArbitrageScannerConfig
```
Purpose: Configuration for ArbitrageScanner API connection

Fields:
  - funding_table_url: string = "https://screener.arbitragescanner.io/api/funding-table"
  - exchanges_url: string = "https://api.arbitragescanner.io/exchanges"
  - refresh_interval_seconds: integer = 5
  - stale_threshold_seconds: integer = 30
  - timeout_seconds: integer = 10
  - retry_attempts: integer = 3
  - retry_delay_seconds: integer = 1
```

### ArbitrageScannerExchange
```
Purpose: Represents an exchange from the ArbitrageScanner registry

Fields:
  - slug: string (unique identifier, e.g., "binance_futures")
  - title: string (display name, e.g., "Binance (Futures)")
  - enabled_futures: boolean
  - enabled_funding_rates: boolean
  - enabled_spot: boolean
  - ref_trading_pair_url: string (URL template for trading)
  - chain: string (blockchain if DEX, empty for CEX)
  
Methods:
  - get_trading_url(symbol): Returns formatted trading URL
  - is_dex(): Returns true if chain is non-empty
```

### ArbitrageScannerFundingRate
```
Purpose: Represents a single funding rate entry from ArbitrageScanner

Fields:
  - exchange: string (exchange slug)
  - rate: decimal (funding rate as percentage, e.g., 0.01 = 0.01%)
  - next_funding_time: datetime (converted from Unix ms timestamp)
  - ticker: string (base asset, e.g., "BTC")
  - symbol: string (trading pair, e.g., "BTCUSDT")
  
Computed Properties:
  - rate_annualized: decimal (rate * 3 * 365 for 8hr funding)
  - time_to_next_funding: timedelta
  - is_positive: boolean (rate > 0)
```

### ArbitrageScannerToken
```
Purpose: Represents a token with all its funding rates across exchanges

Fields:
  - slug: string (token identifier, e.g., "bitcoin")
  - symbol: string (trading pair, e.g., "BTCUSDT")
  - ticker: string (base asset, e.g., "BTC")
  - token_id: integer
  - max_spread: decimal (pre-calculated maximum spread opportunity)
  - rates: list[ArbitrageScannerFundingRate]
  - fetched_at: datetime
  
Computed Properties:
  - exchanges_count: integer (len of rates)
  - highest_rate: ArbitrageScannerFundingRate
  - lowest_rate: ArbitrageScannerFundingRate
  - spread: decimal (highest_rate.rate - lowest_rate.rate)
  - has_arbitrage_opportunity: boolean (spread > threshold)

Methods:
  - get_rate_for_exchange(exchange_slug): Returns rate or None
  - get_positive_funding_exchanges(): Returns list of exchanges with positive rates
  - get_negative_funding_exchanges(): Returns list of exchanges with negative rates
  - get_best_long_exchange(): Exchange with lowest/most negative rate
  - get_best_short_exchange(): Exchange with highest/most positive rate
```

### ArbitrageScannerSnapshot
```
Purpose: Complete snapshot of all funding data at a point in time

Fields:
  - tokens: dict[symbol, ArbitrageScannerToken]
  - exchanges: dict[slug, ArbitrageScannerExchange]
  - fetched_at: datetime
  - is_stale: boolean (computed based on age)
  
Methods:
  - get_token(symbol): Returns token or None
  - get_opportunities_above_threshold(min_spread): Returns filtered tokens
  - get_top_opportunities(n): Returns top N by max_spread
  - get_tokens_for_exchange(exchange_slug): Returns tokens tradeable on exchange
```

## 2.2 Market Data Models (Secondary - From Exchange APIs)

### FundingRateData
```
Purpose: Represents funding rate information for a single asset on a single venue

Fields:
  - venue: string (exchange identifier)
  - symbol: string (unified symbol format, e.g., "BTC/USDT")
  - base_asset: string (e.g., "BTC")
  - quote_asset: string (e.g., "USDT")
  - current_funding_rate: decimal (as percentage, e.g., 0.01 for 0.01%)
  - predicted_funding_rate: decimal (optional, from prediction model)
  - funding_interval_hours: integer (8, 4, or 1)
  - next_funding_time: datetime (UTC)
  - time_to_next_funding_seconds: integer
  - historical_rates: array of (timestamp, rate) tuples (last N periods)
  - timestamp: datetime (when data was fetched)

Constraints:
  - current_funding_rate must be within valid range (-3% to +3%)
  - funding_interval_hours must be one of [1, 4, 8]
  - next_funding_time must be in the future
```

### PriceData
```
Purpose: Represents price information for spot and perpetual markets

Fields:
  - venue: string
  - symbol: string
  - market_type: enum (SPOT, PERPETUAL)
  - bid_price: decimal
  - ask_price: decimal
  - mid_price: decimal (computed: (bid + ask) / 2)
  - spread: decimal (computed: (ask - bid) / mid)
  - mark_price: decimal (for perpetuals only)
  - index_price: decimal (for perpetuals only)
  - last_price: decimal
  - timestamp: datetime

Constraints:
  - bid_price < ask_price
  - All prices must be positive
  - spread should typically be < 1% (flag if exceeded)
```

### LiquidityData
```
Purpose: Represents order book depth and trading activity

Fields:
  - venue: string
  - symbol: string
  - market_type: enum (SPOT, PERPETUAL)
  - bid_depth: array of (price, quantity) tuples (top N levels)
  - ask_depth: array of (price, quantity) tuples (top N levels)
  - cumulative_bid_depth_usd: decimal (total USD value on bid side)
  - cumulative_ask_depth_usd: decimal (total USD value on ask side)
  - open_interest: decimal (for perpetuals, in contracts)
  - open_interest_usd: decimal (open interest in USD terms)
  - volume_24h: decimal
  - volume_24h_usd: decimal
  - timestamp: datetime

Methods:
  - get_depth_at_size(size_usd): Returns expected slippage for given order size
  - get_executable_size(max_slippage): Returns max size executable within slippage limit
```

### VenueFeeData
```
Purpose: Represents fee structure for a venue

Fields:
  - venue: string
  - spot_maker_fee: decimal (as percentage)
  - spot_taker_fee: decimal
  - perp_maker_fee: decimal
  - perp_taker_fee: decimal
  - withdrawal_fees: dict (asset -> fee amount)
  - borrowing_rate: decimal (for margin trading, if applicable)
  - funding_fee_rate: decimal (exchange's cut of funding, if any)
  - vip_level: string (user's fee tier)
  - timestamp: datetime (last updated)
```

## 2.2 Opportunity Models

### OpportunityLeg
```
Purpose: Represents one side of an arbitrage opportunity

Fields:
  - venue: string
  - symbol: string
  - market_type: enum (SPOT, PERPETUAL)
  - side: enum (LONG, SHORT)
  - funding_rate: decimal (0 for spot)
  - receives_funding: boolean
  - current_price: decimal
  - available_liquidity_usd: decimal
  - estimated_slippage: decimal (for target size)
  - fee_rate: decimal (taker fee assumed)
```

### Opportunity
```
Purpose: Represents a complete arbitrage opportunity

Fields:
  - id: string (unique identifier)
  - opportunity_type: enum (SPOT_PERP, CROSS_EXCHANGE_PERP, CEX_DEX, TRIANGULAR, TEMPORAL)
  - base_asset: string
  - primary_leg: OpportunityLeg (the leg that receives funding)
  - hedge_leg: OpportunityLeg (the leg that hedges delta)
  - additional_legs: array of OpportunityLeg (for complex strategies)
  
  Calculated Metrics:
  - gross_funding_rate: decimal (rate received - rate paid)
  - gross_apr: decimal (annualized gross return)
  - total_entry_cost: decimal (fees + estimated slippage)
  - total_exit_cost: decimal (estimated)
  - net_apr: decimal (after all costs)
  - basis: decimal (price difference between legs)
  - basis_risk: decimal (historical basis volatility)
  
  Scoring:
  - uos_score: integer (0-100, Unified Opportunity Score)
  - return_score: integer (0-40)
  - risk_score: integer (0-30)
  - execution_score: integer (0-20)
  - timing_score: integer (0-10)
  
  Metadata:
  - detected_at: datetime
  - expires_at: datetime (when opportunity is stale)
  - confidence: decimal (0-1)
  - recommended_size_usd: decimal
  - minimum_hold_periods: integer
  
Methods:
  - calculate_scores(): Computes all scoring components
  - estimate_profit(size_usd, hold_periods): Projects P&L
  - validate(): Checks all constraints are met
```

## 2.3 Position Models

### PositionLeg
```
Purpose: Represents one leg of an active position

Fields:
  - id: string
  - venue: string
  - symbol: string
  - market_type: enum (SPOT, PERPETUAL)
  - side: enum (LONG, SHORT)
  - entry_price: decimal
  - current_price: decimal
  - quantity: decimal (in base asset)
  - notional_value_usd: decimal
  - unrealized_pnl: decimal
  - margin_used: decimal (for perpetual)
  - liquidation_price: decimal (for perpetual, null for spot)
  - entry_timestamp: datetime
  - entry_order_ids: array of string

Computed Properties:
  - price_pnl: (current_price - entry_price) * quantity * side_multiplier
  - margin_utilization: margin_used / available_margin
  - distance_to_liquidation: abs(current_price - liquidation_price) / current_price
```

### Position
```
Purpose: Represents a complete arbitrage position

Fields:
  - id: string (unique identifier)
  - opportunity_id: string (reference to original opportunity)
  - opportunity_type: enum
  - base_asset: string
  - status: enum (PENDING, OPENING, ACTIVE, CLOSING, CLOSED, FAILED, EMERGENCY_CLOSE)
  
  Legs:
  - primary_leg: PositionLeg
  - hedge_leg: PositionLeg
  - additional_legs: array of PositionLeg
  
  Financial:
  - total_capital_deployed: decimal
  - entry_costs_paid: decimal
  - funding_received: decimal
  - funding_paid: decimal
  - net_funding_pnl: decimal
  - price_pnl: decimal (sum across legs)
  - total_unrealized_pnl: decimal
  - realized_pnl: decimal (if closed)
  
  Risk Metrics:
  - net_delta: decimal (should be ~0)
  - delta_exposure_pct: decimal (|net_delta| / notional)
  - max_margin_utilization: decimal (highest across legs)
  - min_liquidation_distance: decimal (lowest across legs)
  - health_status: enum (HEALTHY, ATTENTION, WARNING, CRITICAL)
  
  Timing:
  - opened_at: datetime
  - last_funding_collected: datetime
  - funding_periods_collected: integer
  - estimated_remaining_hold: integer (periods)
  - exit_deadline: datetime (max hold time)
  
  Exit Criteria:
  - target_funding_rate_min: decimal
  - stop_loss_threshold: decimal
  - take_profit_threshold: decimal
  
Methods:
  - calculate_health(): Updates all risk metrics and health_status
  - should_exit(): Evaluates all exit triggers, returns (bool, reason)
  - estimate_exit_cost(): Projects costs to close position
```

## 2.4 Capital Models

### CapitalPool
```
Purpose: Represents a segment of total capital

Fields:
  - pool_type: enum (RESERVE, ACTIVE, PENDING, TRANSIT)
  - total_value_usd: decimal
  - allocations: dict (venue -> amount)
  - min_required: decimal (minimum pool size)
  - max_allowed: decimal (maximum pool size)
  
Methods:
  - allocate(venue, amount): Move capital to specific venue allocation
  - deallocate(venue, amount): Remove capital from venue allocation
  - get_available(venue): Returns available capital at venue
```

### CapitalState
```
Purpose: Global view of capital across all pools and venues

Fields:
  - total_capital_usd: decimal
  - reserve_pool: CapitalPool
  - active_pool: CapitalPool
  - pending_pool: CapitalPool
  - transit_pool: CapitalPool
  
  Per-Venue Tracking:
  - venue_balances: dict (venue -> {asset -> balance})
  - venue_available: dict (venue -> available_usd)
  - venue_margin_used: dict (venue -> margin_used)
  - venue_exposure: dict (venue -> total_exposure_usd)
  
  Constraints Tracking:
  - total_utilization: decimal (active / total)
  - venue_utilization: dict (venue -> exposure / limit)
  - asset_exposure: dict (asset -> exposure_usd)
  
Methods:
  - refresh(): Sync with actual exchange balances
  - get_allocatable(venue, risk_budget): Returns max allocatable to opportunity
  - reserve_for_opportunity(opportunity, amount): Move to pending pool
  - confirm_allocation(position): Move from pending to active
  - release_allocation(position): Return capital to available
```

## 2.5 Risk Models

### RiskLimits
```
Purpose: Defines all risk constraints

Fields:
  Position Limits:
  - max_position_size_usd: decimal
  - max_position_size_pct: decimal (of total capital)
  - max_leverage: decimal
  
  Concentration Limits:
  - max_venue_exposure_pct: decimal
  - max_asset_exposure_pct: decimal
  - max_correlated_exposure_pct: decimal
  
  Portfolio Limits:
  - max_gross_exposure_pct: decimal
  - max_net_exposure_pct: decimal
  - max_drawdown_pct: decimal
  - max_var_pct: decimal (VaR limit)
  
  Position Health Limits:
  - max_delta_exposure_pct: decimal
  - min_liquidation_distance_pct: decimal
  - max_margin_utilization_pct: decimal
  
Methods:
  - check_position_allowed(opportunity, size): Returns (allowed, violations)
  - check_portfolio_health(portfolio): Returns (healthy, violations)
  - get_adjusted_limits(regime): Returns regime-adjusted limits
```

### RiskState
```
Purpose: Current risk exposure and metrics

Fields:
  Portfolio Metrics:
  - total_exposure_usd: decimal
  - gross_exposure_pct: decimal
  - net_exposure_pct: decimal
  - portfolio_delta: decimal
  - portfolio_var: decimal
  - current_drawdown_pct: decimal
  - peak_equity: decimal
  - current_equity: decimal
  
  Exposure Breakdowns:
  - venue_exposures: dict (venue -> exposure_usd)
  - asset_exposures: dict (asset -> exposure_usd)
  - strategy_exposures: dict (strategy_type -> exposure_usd)
  
  Risk Budget:
  - var_budget_used: decimal
  - var_budget_remaining: decimal
  - drawdown_budget_remaining: decimal
  
  Health Summary:
  - positions_healthy: integer
  - positions_attention: integer
  - positions_warning: integer
  - positions_critical: integer
  
Methods:
  - update(): Recalculate all metrics from current positions
  - can_add_risk(additional_var): Check if risk budget allows
  - get_risk_contribution(position): Calculate position's risk contribution
```

---

# 3. Module Specifications

## 3.1 Data Collection Module

### FundingRateAggregator Class (CORE - Merges Both Sources)
```
Purpose: Aggregates funding rates from BOTH exchange APIs (primary) and ArbitrageScanner (secondary)

Architecture:
  PRIMARY:   Individual Exchange APIs (most accurate, authoritative)
  SECONDARY: ArbitrageScanner API (validation, gap filling, discovery)

Key Methods:

  initialize():
    - Initialize all exchange providers (PRIMARY)
    - Initialize ArbitrageScannerClient (SECONDARY)
    - Start parallel refresh loops for both sources
    - Initialize reconciliation engine

  collect_all_funding_rates() -> UnifiedFundingSnapshot:
    """
    Fetches funding rates from BOTH sources simultaneously and merges them.
    Exchange APIs take precedence; ArbitrageScanner fills gaps and validates.
    """
    Steps:
    1. Parallel fetch from all exchange APIs
    2. Parallel fetch from ArbitrageScanner
    3. Merge data with exchange APIs as authoritative
    4. Flag discrepancies for review
    5. Fill gaps with ArbitrageScanner data (marked as "secondary_source")
    6. Return unified snapshot

  reconcile_sources(exchange_data, arbitragescanner_data) -> ReconciliationResult:
    """
    Compares data from both sources and handles discrepancies.
    """
    For each symbol/exchange pair:
      exchange_rate = exchange_data.get(symbol, exchange)
      arb_rate = arbitragescanner_data.get(symbol, exchange)
      
      if both exist:
        if abs(exchange_rate - arb_rate) < tolerance:
          result.matched.append(...)
        else:
          result.discrepancies.append(...)
          log_warning(f"Rate mismatch: {symbol} on {exchange}")
      elif only exchange_rate:
        result.exchange_only.append(...)
      elif only arb_rate:
        result.arbitragescanner_only.append(...)  # Gap fill opportunity
    
    return result

  get_unified_rate(symbol, exchange) -> FundingRateData:
    """
    Returns the best available rate with source information.
    """
    exchange_rate = self.exchange_cache.get(symbol, exchange)
    arb_rate = self.arbitragescanner_cache.get(symbol, exchange)
    
    if exchange_rate:
      return FundingRateData(
        rate=exchange_rate,
        source="exchange_api",
        validated_by="arbitragescanner" if arb_rate else None,
        discrepancy=abs(exchange_rate - arb_rate) if arb_rate else None
      )
    elif arb_rate:
      return FundingRateData(
        rate=arb_rate,
        source="arbitragescanner",
        validated_by=None,
        is_fallback=True
      )
    else:
      return None

Configuration:
  exchange_refresh_interval_seconds: 5
  arbitragescanner_refresh_interval_seconds: 5
  discrepancy_tolerance_pct: 0.05  # 0.05% tolerance
  log_all_discrepancies: true
  use_arbitragescanner_for_discovery: true
```

### ExchangeFundingProvider Interface (PRIMARY SOURCE)
```
Purpose: Fetches funding rates directly from exchange APIs

Required Methods:

  get_funding_rate(symbol) -> FundingRateData:
    - Fetch current funding rate from exchange API
    - Include predicted next rate if available
    - Include time to next funding

  get_all_funding_rates() -> dict[symbol, FundingRateData]:
    - Fetch all perpetual funding rates
    - Return normalized data

  get_funding_rate_history(symbol, periods) -> list[FundingRateData]:
    - Fetch historical funding rates
    - Used for volatility calculations

Exchange-Specific Implementations:

  BinanceFundingProvider:
    Endpoint: GET /fapi/v1/premiumIndex
    Returns: lastFundingRate, nextFundingTime, markPrice
    
  BybitFundingProvider:
    Endpoint: GET /v5/market/tickers?category=linear
    Returns: fundingRate, nextFundingTime
    
  OKXFundingProvider:
    Endpoint: GET /api/v5/public/funding-rate
    Returns: fundingRate, nextFundingTime
    
  HyperliquidFundingProvider:
    Endpoint: POST /info (with {"type": "metaAndAssetCtxs"})
    Returns: funding rate in asset contexts
    Note: 1-hour funding interval
    
  DYDXFundingProvider:
    Endpoint: GET /v4/perpetualMarkets
    Returns: nextFundingRate
    Note: 1-hour funding interval
    
  GateFundingProvider:
    Endpoint: GET /api/v4/futures/usdt/contracts
    Returns: funding_rate, funding_next_apply
    
  KuCoinFundingProvider:
    Endpoint: GET /api/v1/contract/{symbol}
    Returns: fundingFeeRate, nextFundingRateTime
    
  BitgetFundingProvider:
    Endpoint: GET /api/mix/v1/market/current-fundRate
    Returns: fundingRate
```

### ArbitrageScannerClient Class (SECONDARY SOURCE)
```
Purpose: Client for ArbitrageScanner API - secondary source for validation and gap filling

Endpoints:
  - Funding Table: https://screener.arbitragescanner.io/api/funding-table
  - Exchange List: https://api.arbitragescanner.io/exchanges

Key Methods:

  fetch_funding_table() -> ArbitrageScannerSnapshot:
    """
    Fetches ALL funding rates across ALL exchanges in a single API call.
    Used for:
    1. Validating exchange API data
    2. Filling gaps for exchanges not directly integrated
    3. Quick opportunity discovery via maxSpread
    """
    Steps:
    1. HTTP GET to funding-table endpoint
    2. Parse JSON response
    3. Convert to ArbitrageScannerToken objects
    4. Build ArbitrageScannerSnapshot
    5. Return snapshot

  fetch_exchanges() -> dict[slug, ArbitrageScannerExchange]:
    """
    Fetches the master list of all supported exchanges.
    """

  get_opportunities_by_spread(min_spread) -> list[ArbitrageScannerToken]:
    """
    Quick scan using ArbitrageScanner's pre-calculated maxSpread.
    Useful for rapid opportunity discovery before detailed analysis.
    """

  get_rate_for_validation(symbol, exchange) -> decimal:
    """
    Get ArbitrageScanner's rate for cross-validation with exchange API.
    """

Configuration:
  funding_table_url: "https://screener.arbitragescanner.io/api/funding-table"
  exchanges_url: "https://api.arbitragescanner.io/exchanges"
  refresh_interval_seconds: 5
  timeout_seconds: 10
  retry_attempts: 3

Usage in Dual-Source Architecture:
  - Validates exchange API data
  - Fills gaps for non-integrated exchanges
  - Provides maxSpread for quick opportunity scanning
  - Acts as fallback if exchange API fails
```

### DataCollector Class
```
Purpose: Orchestrates all data collection including dual-source funding rates

Components:
  - FundingRateAggregator (dual-source funding rates)
  - Exchange providers (prices, liquidity, account data)

Key Methods:

  initialize():
    - Initialize FundingRateAggregator (handles both sources)
    - Initialize exchange providers for price/liquidity data
    - Verify all API connectivity
    - Initialize data cache

  collect_funding_rates() -> UnifiedFundingSnapshot:
    """
    Delegates to FundingRateAggregator which merges both sources.
    """
    return self.funding_aggregator.collect_all_funding_rates()

  collect_prices() -> dict[venue, dict[symbol, PriceData]]:
    - Parallel fetch from exchange providers
    - Calculate derived metrics (basis, spread)
    - Return aggregated data

  collect_liquidity() -> dict[venue, dict[symbol, LiquidityData]]:
    - Fetch order book snapshots from exchange providers
    - Calculate depth metrics
    - Return aggregated data

  get_unified_market_data(symbol) -> UnifiedMarketData:
    - Funding rates from FundingRateAggregator (dual-source)
    - Prices and liquidity from exchange providers
    - Combine into unified view

Data Flow:
  Exchange APIs ──┐
                  ├──► FundingRateAggregator ──► Unified Funding Data
  ArbitrageScanner ─┘
```

### DataProvider Interface (For Prices/Liquidity/Execution)
```
Purpose: Standard interface for exchange data providers (non-funding data)

Required Methods:
  
  connect():
    - Establish API connection
    - Authenticate if required
    - Return connection status

  get_prices(symbols: list, market_types: list) -> dict[symbol, PriceData]:
    - Fetch bid/ask/last prices
    - Include mark price for perpetuals

  get_order_book(symbol, market_type, depth) -> OrderBookData:
    - Fetch order book to specified depth

  get_open_interest(symbol) -> decimal:
    - Fetch current open interest

  get_fee_structure() -> VenueFeeData:
    - Fetch current fee rates for user's tier

  get_account_balance() -> dict[asset, Balance]:
    - Fetch account balances

  get_positions() -> list[Position]:
    - Fetch open positions

  health_check() -> bool:
    - Verify API is responsive
    - Return true if healthy
```

## 3.2 Opportunity Detection Module

### OpportunityScanner Class
```
Purpose: Continuously scan for arbitrage opportunities using dual-source funding data

Data Sources:
  PRIMARY:   Exchange API funding rates (via FundingRateAggregator)
  SECONDARY: ArbitrageScanner API (for discovery and validation)

Key Methods:

  scan() -> list[Opportunity]:
    """
    Main scanning loop using unified funding data from both sources.
    """
    Steps:
    1. Get unified funding snapshot from FundingRateAggregator
    2. Quick scan: Use ArbitrageScanner maxSpread to identify candidates
    3. Deep scan: Validate candidates using exchange API data
    4. For each validated opportunity:
       a. Get authoritative rates from exchange APIs
       b. Validate against ArbitrageScanner data
       c. Fetch supplementary data (prices, liquidity)
       d. Construct Opportunity objects
       e. Validate viability (liquidity, fees, etc.)
    5. Return list of viable opportunities

  quick_discovery_scan() -> list[OpportunityCandidate]:
    """
    Ultra-fast scan using ArbitrageScanner's pre-calculated maxSpread.
    Used to identify CANDIDATES for deeper analysis.
    """
    Steps:
    1. Get ArbitrageScanner snapshot
    2. Filter tokens where maxSpread >= min_threshold
    3. Return candidates for detailed validation
    
    Note: These are candidates only - must be validated against exchange APIs

  deep_validation_scan(candidates: list) -> list[Opportunity]:
    """
    Validates candidates using authoritative exchange API data.
    """
    For each candidate:
    1. Fetch rates from exchange APIs (PRIMARY source)
    2. Compare with ArbitrageScanner rates
    3. If rates match (within tolerance):
       - High confidence opportunity
    4. If rates differ:
       - Use exchange API rate (authoritative)
       - Flag discrepancy for logging
    5. Calculate net returns using exchange API rates
    6. Return validated opportunities

  filter_eligible_assets(unified_snapshot) -> list[symbol]:
    Criteria:
    - Has rates from at least 2 exchanges (via exchange APIs)
    - Spread >= min_spread_threshold
    - Not in blacklist
    - Exchanges are enabled in system config

  construct_opportunities(symbol, unified_data) -> list[Opportunity]:
    """
    Construct opportunities using exchange API rates as authoritative.
    """
    For symbol with rates on exchanges A, B, C:
    1. Get authoritative rates from exchange APIs
    2. Sort rates by value (lowest to highest)
    3. Generate pair combinations
    4. For each pair:
       a. Calculate gross spread using exchange API rates
       b. Cross-validate against ArbitrageScanner (log if different)
       c. Estimate fees
       d. Calculate net expected return
       e. Filter by min_net_return threshold
    5. Return valid opportunities

  reconcile_opportunity_data(exchange_data, arb_data) -> ReconciliationResult:
    """
    Ensures opportunity is valid across both data sources.
    """
    - If exchange APIs confirm opportunity: HIGH confidence
    - If only ArbitrageScanner shows opportunity: MEDIUM confidence (needs verification)
    - If sources disagree significantly: Flag for manual review

Example Scan Flow:
  1. ArbitrageScanner quick scan identifies FOLKS with maxSpread=0.152
  2. Scanner fetches FOLKS rates from exchange APIs:
     - KuCoin API: -0.2730 (actual)
     - Bitget API: -0.1210 (actual)
  3. Compare with ArbitrageScanner:
     - KuCoin ArbitrageScanner: -0.2725 ✓ (matches within tolerance)
     - Bitget ArbitrageScanner: -0.1205 ✓ (matches within tolerance)
  4. Construct opportunity using exchange API rates (authoritative)
  5. Calculate spread: 0.152 (15.2% per period)
  6. Fetch prices/liquidity from exchange APIs
  7. Return validated HIGH confidence opportunity
```

### OpportunityScorer Class (UOS Engine)
```
Purpose: Calculate Unified Opportunity Scores

Key Methods:

  score(opportunity) -> ScoredOpportunity:
    Calculate all score components and total UOS

  calculate_return_score(opportunity) -> integer (0-40):
    Inputs:
    - Net APR
    - Funding rate autocorrelation (persistence)
    - Historical win rate for similar opportunities
    
    Logic:
    - base_score = min(20, net_apr / benchmark_apr * 10)
    - persistence_bonus = autocorrelation * 10 (if positive)
    - history_bonus = win_rate * 10
    - return min(40, base_score + persistence_bonus + history_bonus)

  calculate_risk_score(opportunity) -> integer (0-30):
    Inputs:
    - Funding rate volatility (std dev of historical rates)
    - Basis volatility
    - Estimated liquidation buffer
    - Venue reliability score
    
    Logic:
    - stability_score = (1 - normalized_funding_vol) * 10
    - basis_score = (1 - normalized_basis_vol) * 10
    - liquidation_score = min(10, liquidation_buffer * 2)
    - return stability_score + basis_score + liquidation_score

  calculate_execution_score(opportunity) -> integer (0-20):
    Inputs:
    - Available liquidity vs. target size
    - Expected slippage
    - Venue uptime/reliability
    
    Logic:
    - liquidity_score = min(10, liquidity_ratio * 5)
    - slippage_score = (1 - expected_slippage / max_slippage) * 5
    - reliability_score = venue_uptime * 5
    - return sum of above

  calculate_timing_score(opportunity) -> integer (0-10):
    Inputs:
    - Time to next funding
    - Funding rate trend
    - Market regime alignment
    
    Logic:
    - Optimal: 1-2 hours before funding, stable/rising rate
    - Score decreases as timing becomes suboptimal
```

### FundingPredictor Class
```
Purpose: Predict future funding rates

Key Methods:

  predict(symbol, venue, horizon_periods) -> PredictionResult:
    Output:
    - predicted_rate: decimal
    - confidence: decimal (0-1)
    - direction_change_probability: decimal
    - expected_persistence: integer (periods rate stays favorable)

  Features to consider:
    Market Features:
    - Recent funding rate momentum
    - Open interest changes
    - Long/short ratio changes
    - Basis momentum
    - Price momentum
    
    Cross-Market Features:
    - Funding rates on other venues
    - Stablecoin lending rates
    
    Temporal Features:
    - Time of day
    - Day of week

  Implementation Options:
    - Simple: Exponential moving average + mean reversion
    - Intermediate: Linear regression on features
    - Advanced: Gradient boosting or neural network

  Training/Calibration:
    - Use historical funding rate data
    - Retrain periodically (weekly)
    - Track prediction accuracy
```

## 3.3 Execution Module

### ExecutionEngine Class
```
Purpose: Execute trades to open and close positions

Key Methods:

  open_position(opportunity, size_usd) -> Position:
    Steps:
    1. Validate opportunity still valid (prices haven't moved)
    2. Calculate exact quantities for each leg
    3. Generate execution plan
    4. Execute legs (timing optimizer decides order)
    5. Confirm fills
    6. Create and return Position object
    
    Failure Handling:
    - If any leg fails after others succeed, execute emergency hedge
    - Log all failures for analysis

  close_position(position) -> ClosedPosition:
    Steps:
    1. Generate close orders for all legs
    2. Execute in optimal order (close hedge first if basis favorable)
    3. Confirm all fills
    4. Calculate final P&L
    5. Return closed position details

  execute_leg(leg, order_params) -> ExecutionResult:
    Steps:
    1. Select optimal venue handler
    2. Determine order type (limit vs. market)
    3. Split order if size exceeds threshold
    4. Submit order(s)
    5. Monitor fills
    6. Return execution result
```

### ExecutionTimingOptimizer Class
```
Purpose: Determine optimal timing for order execution

Key Methods:

  get_entry_timing(opportunity) -> TimingRecommendation:
    Output:
    - recommended_action: EXECUTE_NOW | WAIT | SKIP
    - optimal_window_start: datetime
    - optimal_window_end: datetime
    - urgency_score: decimal (0-1)
    - reasoning: string
    
    Logic:
    - Best: 1-2 hours before funding settlement
    - Good: 2-4 hours before
    - Avoid: Immediately after settlement

  get_exit_timing(position) -> TimingRecommendation:
    Output:
    - recommended_action: CLOSE_NOW | WAIT | URGENT_CLOSE
    - optimal_window_start: datetime
    - optimal_window_end: datetime
    - reasoning: string
    
    Logic:
    - Prefer: After collecting funding, when basis is favorable
    - Avoid: During funding settlement, low liquidity periods
    - Urgent: If risk triggers active

  assess_current_conditions(symbol, venue) -> MarketConditions:
    Output:
    - liquidity_quality: HIGH | MEDIUM | LOW
    - volatility_level: HIGH | MEDIUM | LOW
    - spread_quality: TIGHT | NORMAL | WIDE
    - recommendation: GOOD_TO_TRADE | CAUTION | AVOID
```

### SmartOrderRouter Class
```
Purpose: Optimize order routing and execution

Key Methods:

  plan_execution(opportunity, size_usd) -> ExecutionPlan:
    Output:
    - orders: list of OrderSpec (venue, symbol, side, size, type, timing)
    - estimated_cost: decimal
    - estimated_slippage: decimal
    - execution_sequence: ordered list

  split_order(total_size, liquidity_profile) -> list[OrderChunk]:
    Logic:
    - If size <= good_liquidity_threshold: single order
    - Else: split into chunks with time spacing
    - Adjust chunk sizes based on order book depth

  select_order_type(conditions) -> OrderType:
    Logic:
    - If urgent and liquidity good: MARKET
    - If not urgent and spread tight: LIMIT at mid
    - If spread wide: LIMIT at favorable side
```

## 3.4 Position Management Module

### PositionManager Class
```
Purpose: Manage position lifecycle

Key Methods:

  create_position(opportunity, execution_result) -> Position:
    - Initialize Position object with execution data
    - Set initial health metrics
    - Register with monitoring

  update_position(position_id, market_data):
    - Update current prices
    - Recalculate P&L
    - Update risk metrics
    - Update health status

  check_exit_triggers(position) -> (should_exit: bool, reason: string):
    Trigger checks:
    1. Funding rate below threshold
    2. Funding rate reversed
    3. Predicted funding unfavorable
    4. Risk limit breached
    5. Maximum hold time reached
    6. Better opportunity available (reallocation)
    
  initiate_close(position, reason):
    - Update status to CLOSING
    - Generate close orders
    - Hand off to execution engine

  handle_emergency_close(position, trigger):
    - Immediately update status to EMERGENCY_CLOSE
    - Execute market orders to close all legs
    - Alert operators
    - Log incident
```

### PositionMonitor Class
```
Purpose: Continuously monitor position health

Key Methods:

  run_monitoring_cycle():
    For each active position:
    1. Fetch latest market data
    2. Update position metrics
    3. Classify health status
    4. Check exit triggers
    5. Generate alerts if needed
    6. Queue actions for position manager

  calculate_health_status(position) -> HealthStatus:
    Criteria:
    HEALTHY:
    - Delta exposure < 1%
    - Margin utilization < 50%
    - Liquidation distance > 30%
    
    ATTENTION:
    - Delta exposure < 3%
    - Margin utilization < 70%
    - Liquidation distance > 20%
    
    WARNING:
    - Delta exposure < 5%
    - Margin utilization < 85%
    - Liquidation distance > 10%
    
    CRITICAL: Any metric exceeds WARNING thresholds

  monitor_funding_collection(position):
    - Track funding payments received
    - Update cumulative funding P&L
    - Alert if payment missed or unexpected
```

### PositionRebalancer Class
```
Purpose: Rebalance positions to maintain health

Key Methods:

  check_rebalance_needed(position) -> (needed: bool, type: string):
    Types:
    - DELTA: Net delta exceeds tolerance
    - MARGIN: Margin utilization too high
    - SIZE: Position size needs adjustment

  execute_delta_rebalance(position):
    Steps:
    1. Calculate required adjustment
    2. Determine which leg to adjust
    3. Execute adjustment order
    4. Verify new delta within tolerance

  execute_margin_rebalance(position):
    Options:
    1. Transfer additional margin
    2. Reduce position size
    3. Close unprofitable portion
    
    Selection based on:
    - Available capital
    - Opportunity cost
    - Current P&L
```

## 3.5 Risk Management Module

### RiskManager Class
```
Purpose: Enforce risk limits and manage risk state

Key Methods:

  initialize():
    - Load risk limits from configuration
    - Initialize risk state
    - Start monitoring

  check_new_position(opportunity, size_usd) -> RiskCheckResult:
    Checks:
    1. Position size within limits
    2. Venue exposure would remain within limits
    3. Asset exposure would remain within limits
    4. Portfolio VaR would remain within limits
    5. Drawdown budget sufficient
    
    Output:
    - approved: boolean
    - max_approved_size: decimal (if partially approved)
    - violations: list of violated limits
    - adjusted_limits: any regime-adjusted limits applied

  update_risk_state():
    - Recalculate all portfolio metrics
    - Update exposure tracking
    - Check for limit breaches
    - Trigger alerts/actions if needed

  get_risk_adjusted_limits() -> RiskLimits:
    - Apply regime-based adjustments
    - Apply drawdown-based adjustments
    - Return current effective limits
```

### RiskCalculator Class
```
Purpose: Calculate risk metrics

Key Methods:

  calculate_position_var(position) -> decimal:
    Parametric VaR:
    var = notional * volatility * z_score * sqrt(horizon)
    
    Inputs:
    - Position notional value
    - Asset volatility (historical)
    - Confidence level (95% -> z = 1.645)
    - Holding period

  calculate_portfolio_var(positions) -> decimal:
    Portfolio VaR with correlations:
    var = sqrt(weights' * covariance_matrix * weights) * z_score
    
    Inputs:
    - Position weights
    - Asset covariance matrix
    - Confidence level

  calculate_liquidation_distance(leg) -> decimal:
    distance = abs(current_price - liquidation_price) / current_price
    
  calculate_margin_utilization(leg) -> decimal:
    utilization = margin_used / margin_available

  calculate_delta_exposure(position) -> decimal:
    Sum of deltas across all legs (should be ~0 for hedged position)
```

### EmergencyProtocols Class
```
Purpose: Handle emergency situations

Protocols:

  flash_crash_protocol(trigger_data):
    Activation: Price moves > 10% in < 5 minutes
    Actions:
    1. Pause all new orders
    2. Check all positions for liquidation risk
    3. Add margin or reduce size for at-risk positions
    4. Alert operators
    5. Wait for stability before resuming

  exchange_failure_protocol(venue, failure_type):
    Actions:
    1. Mark venue as degraded
    2. Stop new positions on venue
    3. If positions exist:
       - Monitor via backup data if available
       - Prepare cross-venue hedges
    4. Alert operators

  max_drawdown_protocol():
    Activation: Drawdown exceeds limit
    Actions:
    1. Halt all new positions immediately
    2. Begin systematic position reduction
    3. Prioritize closing riskiest positions
    4. Alert operators
    5. Require manual reset to resume

  funding_anomaly_protocol(symbol, venue, anomaly_data):
    Actions:
    1. Verify data accuracy across sources
    2. If confirmed anomaly:
       - Reassess affected positions
       - Close if anomaly adverse
       - Potentially exploit if favorable (with caution)
```

## 3.6 Capital Allocation Module

### CapitalAllocator Class
```
Purpose: Determine optimal capital allocation

Key Methods:

  allocate_to_opportunity(opportunity, risk_state) -> AllocationResult:
    Steps:
    1. Get base allocation from scoring
    2. Apply volatility adjustment
    3. Apply constraint limits
    4. Reserve capital in pending pool
    
    Output:
    - allocated_amount_usd: decimal
    - venue_allocations: dict (how much to deploy where)
    - reasoning: string

  get_base_allocation(opportunity) -> decimal:
    Based on UOS score:
    - Score >= 80: base_size * 1.5
    - Score >= 60: base_size * 1.0
    - Score >= 40: base_size * 0.5
    - Score < 40: base_size * 0.25

  apply_volatility_adjustment(base_size, current_vol) -> decimal:
    vol_factor = baseline_volatility / current_volatility
    return base_size * vol_factor

  apply_constraints(size, opportunity, risk_state) -> decimal:
    Reduce to satisfy:
    - Max position size
    - Remaining venue capacity
    - Remaining asset capacity
    - Remaining risk budget
    - Available liquidity

  evaluate_reallocation(current_positions, new_opportunity) -> ReallocationPlan:
    If capital is limiting factor and new opportunity is better:
    1. Identify position(s) to close
    2. Calculate switching cost
    3. Calculate net benefit
    4. If benefit > threshold, recommend reallocation
```

### CapitalOptimizer Class
```
Purpose: Optimize capital distribution across venues

Key Methods:

  optimize_venue_distribution(opportunities, constraints) -> Distribution:
    Objective: Maximize expected return given constraints
    
    Constraints:
    - Total capital limit
    - Per-venue limits
    - Risk budget
    
    Output:
    - venue_allocations: dict (venue -> amount)
    - opportunity_allocations: dict (opp_id -> amount)
    - expected_portfolio_return: decimal

  calculate_margin_efficiency(venues) -> dict:
    For each venue, calculate:
    - Effective capital (considering portfolio margin)
    - Margin offset benefits from hedged positions
    - Return margin efficiency score

  recommend_capital_transfers() -> list[TransferRecommendation]:
    Based on:
    - Opportunity distribution across venues
    - Current capital distribution
    - Transfer costs
    
    Recommend transfers if benefit > cost
```

## 3.7 Analytics Module

### PerformanceTracker Class
```
Purpose: Track and calculate performance metrics

Key Methods:

  record_funding_payment(position_id, amount, timestamp):
    - Log funding payment
    - Update cumulative funding P&L

  record_trade(position_id, trade_details):
    - Log trade execution
    - Update costs incurred

  calculate_return_metrics(period) -> ReturnMetrics:
    Output:
    - gross_funding_return: decimal
    - net_return: decimal
    - annualized_return: decimal
    - return_on_capital: decimal

  calculate_risk_metrics(period) -> RiskMetrics:
    Output:
    - max_drawdown: decimal
    - sharpe_ratio: decimal
    - sortino_ratio: decimal
    - calmar_ratio: decimal
    - win_rate: decimal

  calculate_efficiency_metrics() -> EfficiencyMetrics:
    Output:
    - capital_utilization: decimal
    - opportunity_capture_rate: decimal
    - execution_quality: decimal
    - hold_time_efficiency: decimal
```

### AttributionAnalyzer Class
```
Purpose: Decompose returns and risk by source

Key Methods:

  attribute_returns(period) -> ReturnAttribution:
    Decompose into:
    - funding_component: Pure funding payments
    - basis_component: P&L from price divergence
    - execution_component: Slippage and timing costs
    - fee_component: Trading fees
    - borrowing_component: Interest costs
    - residual: Unexplained

  attribute_risk(period) -> RiskAttribution:
    For each position:
    - var_contribution: Marginal VaR
    - drawdown_contribution: P&L during drawdown
    - correlation_contribution: Covariance effects
```

### ReportGenerator Class
```
Purpose: Generate performance reports

Key Methods:

  generate_daily_report() -> Report:
    Contents:
    - Period P&L summary
    - Positions opened/closed
    - Risk events
    - Capital utilization
    - Top opportunities

  generate_weekly_report() -> Report:
    Contents:
    - Performance vs benchmarks
    - Attribution analysis
    - Risk analysis
    - Strategy performance breakdown
    - Recommendations

  generate_monthly_report() -> Report:
    Contents:
    - Comprehensive performance review
    - Strategy effectiveness
    - Market regime analysis
    - System metrics
    - Forward projections
```

---

# 4. Workflow Specifications

## 4.1 Main Event Loop

```
NEXUS Main Loop (runs continuously):

1. DATA_COLLECTION_CYCLE (every 10 seconds):
   - Collect funding rates from all venues
   - Collect prices (spot and perpetual)
   - Collect liquidity data
   - Update data cache
   - Check for data anomalies

2. OPPORTUNITY_SCAN_CYCLE (every 30 seconds):
   - Run opportunity scanner
   - Score all opportunities
   - Update opportunity queue
   - Trigger allocation for high-scoring opportunities

3. POSITION_MONITORING_CYCLE (every 10 seconds):
   - Update all position metrics
   - Check health status
   - Check exit triggers
   - Queue necessary actions

4. RISK_CHECK_CYCLE (every 30 seconds):
   - Update portfolio risk metrics
   - Check all limits
   - Trigger alerts if needed
   - Adjust dynamic limits

5. EXECUTION_CYCLE (event-driven):
   - Process pending opportunity allocations
   - Process pending position closes
   - Handle execution results

6. FUNDING_SETTLEMENT_CYCLE (at settlement times):
   - Verify funding payments received
   - Update position P&L
   - Log discrepancies
```

## 4.2 New Opportunity Workflow

```
OPPORTUNITY -> POSITION WORKFLOW:

1. DETECTION:
   Scanner identifies opportunity with UOS >= threshold

2. SCORING:
   UOS Engine calculates full score
   
3. VALIDATION:
   - Verify data freshness
   - Verify opportunity still valid (prices haven't moved)

4. RISK CHECK:
   Risk Manager checks:
   - Position size allowed
   - Portfolio limits not breached
   - Risk budget available

5. CAPITAL ALLOCATION:
   Capital Allocator determines:
   - Amount to allocate
   - Venue distribution
   - Reserves capital in pending pool

6. TIMING CHECK:
   Timing Optimizer determines:
   - Execute now or wait
   - If wait, schedule for optimal window

7. EXECUTION:
   Execution Engine:
   - Plans execution (order types, splitting, sequence)
   - Executes all legs
   - Handles failures

8. POSITION CREATION:
   Position Manager:
   - Creates Position object
   - Registers for monitoring
   - Confirms capital allocation

9. MONITORING:
   Position enters active monitoring
```

## 4.3 Position Exit Workflow

```
EXIT DECISION -> CLOSED POSITION WORKFLOW:

1. TRIGGER DETECTION:
   Monitor detects exit trigger:
   - Funding rate unfavorable
   - Risk limit breached
   - Maximum hold time
   - Better opportunity (reallocation)
   - Manual request

2. EXIT DECISION:
   Position Manager evaluates:
   - Urgency of exit
   - Current market conditions
   - Expected costs

3. TIMING OPTIMIZATION:
   Timing Optimizer determines:
   - Exit now or wait
   - Optimal window if waiting
   - Emergency override if risk-triggered

4. EXECUTION PLANNING:
   Order Router plans:
   - Close sequence (which leg first)
   - Order types
   - Size splitting if needed

5. EXECUTION:
   Execution Engine:
   - Executes close orders
   - Handles partial fills
   - Confirms full closure

6. FINALIZATION:
   Position Manager:
   - Calculates final P&L
   - Updates position status to CLOSED
   - Releases capital allocation
   - Logs position history

7. ANALYTICS:
   Performance Tracker:
   - Records final metrics
   - Updates strategy statistics
```

## 4.4 Risk Event Workflow

```
RISK EVENT HANDLING:

1. DETECTION:
   Risk Manager detects:
   - Position health WARNING/CRITICAL
   - Portfolio limit breach
   - Market anomaly

2. CLASSIFICATION:
   Determine severity:
   - LOW: Log and monitor
   - MEDIUM: Alert and prepare response
   - HIGH: Immediate action required
   - CRITICAL: Emergency protocol

3. RESPONSE (by severity):
   
   LOW:
   - Log event
   - Increase monitoring frequency
   - No immediate action

   MEDIUM:
   - Generate alert
   - Prepare contingency orders
   - Notify operators if configured

   HIGH:
   - Execute risk reduction
   - Reduce position sizes
   - Add margin where possible
   - Alert operators

   CRITICAL:
   - Activate emergency protocol
   - Halt new activity
   - Begin systematic closure
   - Require operator intervention

4. RESOLUTION:
   - Verify risk within limits
   - Update risk state
   - Log incident for analysis
   - Resume normal operation (or await manual reset)
```

---

# 5. Business Logic Rules

## 5.1 Opportunity Eligibility Rules

```
RULE: Asset must meet minimum trading thresholds
  - 24h volume >= $1,000,000
  - Open interest >= $500,000 (for perpetuals)
  - Not on asset blacklist

RULE: Venue must be operational
  - API responding within timeout
  - No known outages
  - Not in degraded mode

RULE: Opportunity must be profitable after costs
  - Net APR > minimum_apr_threshold (default: 10%)
  - Expected profit > expected_costs * min_profit_ratio

RULE: Liquidity must support target size
  - Available liquidity > target_size * liquidity_multiple (default: 3x)
  - Expected slippage < max_slippage (default: 0.1%)

RULE: Spread must be acceptable
  - Spot spread < max_spread_threshold (default: 0.1%)
  - Perpetual spread < max_spread_threshold
```

## 5.2 Position Sizing Rules

```
RULE: Never exceed maximum position size
  - position_size <= max_position_size_usd
  - position_size <= max_position_pct * total_capital

RULE: Score-based sizing
  - UOS >= 80: Allow up to 150% of base size
  - UOS >= 60: Allow up to 100% of base size
  - UOS >= 40: Allow up to 50% of base size
  - UOS < 40: Allow up to 25% of base size

RULE: Volatility-adjusted sizing
  - Higher volatility -> smaller positions
  - vol_factor = baseline_vol / current_vol
  - adjusted_size = base_size * vol_factor

RULE: Respect concentration limits
  - Single venue exposure <= max_venue_pct * total_capital
  - Single asset exposure <= max_asset_pct * total_capital
```

## 5.3 Exit Trigger Rules

```
RULE: Exit on funding rate deterioration
  - current_rate < min_profitable_rate for N periods
  - OR predicted_rate < min_profitable_rate with confidence > threshold

RULE: Exit on funding rate reversal
  - Rate changes sign (positive -> negative or vice versa)
  - AND rate persists in wrong direction for M periods
  - EXCEPTION: If predicted to reverse back within K periods

RULE: Exit on risk triggers
  - Delta exposure > max_delta_tolerance -> IMMEDIATE
  - Margin utilization > critical_threshold -> IMMEDIATE
  - Liquidation distance < emergency_threshold -> IMMEDIATE

RULE: Exit on time limits
  - Position age > max_hold_duration -> Exit when convenient
  - EXCEPTION: Extend if funding rate exceptionally favorable

RULE: Exit for reallocation
  - Better opportunity available
  - AND benefit > switching_cost
  - AND capital is limiting factor
```

## 5.4 Risk Limit Rules

```
RULE: Hard limits are inviolable
  - Never exceed max_drawdown_pct
  - Never exceed max_leverage
  - Never exceed max_venue_exposure

RULE: Soft limits trigger warnings
  - Approach within 80% of hard limit -> Warning
  - Approach within 90% of hard limit -> Reduce exposure

RULE: Dynamic limit adjustment
  - High volatility detected: Reduce all limits by 30%
  - Recent drawdown > 50% of limit: Reduce new position sizes 25%
  - Recent drawdown > 75% of limit: Halt new positions

RULE: Correlation limits
  - Correlated positions (r > 0.7) count as single exposure
  - Adjust concentration limits accordingly
```

## 5.5 Execution Rules

```
RULE: Both legs must succeed or position is unwound
  - If primary leg fills but hedge fails -> Immediately close primary
  - If hedge fills but primary fails -> Immediately close hedge
  - Log as execution failure

RULE: Maximum execution time
  - Order must fill within max_execution_time (default: 5 minutes)
  - If not filled, cancel and reassess

RULE: Slippage protection
  - Abort if actual slippage > 2x expected
  - Alert if actual slippage > 1.5x expected

RULE: Order type selection
  - Market order: If urgent and slippage acceptable
  - Limit order: If not urgent and spread wide
  - Default: Start with limit, convert to market if not filling
```

---

# 7. API Requirements

## 7.0 Dual-Source Funding Rate APIs

NEXUS uses a dual-source architecture for funding rates:
- **PRIMARY:** Direct exchange APIs (authoritative)
- **SECONDARY:** ArbitrageScanner API (validation & gap filling)

### 7.0.1 Exchange Funding Rate APIs (PRIMARY SOURCE)

Each exchange requires implementation of funding rate fetching:

#### Binance Futures
```
Endpoint: GET https://fapi.binance.com/fapi/v1/premiumIndex
Parameters: symbol (optional, omit for all)
Response:
  {
    "symbol": "BTCUSDT",
    "markPrice": "50000.00",
    "lastFundingRate": "0.00010000",  // 0.01%
    "nextFundingTime": 1765929600000,
    "interestRate": "0.00010000"
  }

Implementation:
  def get_binance_funding_rates():
      response = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex")
      return {item['symbol']: float(item['lastFundingRate']) * 100 
              for item in response.json()}
```

#### Bybit Futures
```
Endpoint: GET https://api.bybit.com/v5/market/tickers
Parameters: category=linear
Response:
  {
    "result": {
      "list": [
        {
          "symbol": "BTCUSDT",
          "fundingRate": "0.0001",
          "nextFundingTime": "1765929600000"
        }
      ]
    }
  }

Implementation:
  def get_bybit_funding_rates():
      response = requests.get("https://api.bybit.com/v5/market/tickers?category=linear")
      return {item['symbol']: float(item['fundingRate']) * 100 
              for item in response.json()['result']['list']}
```

#### OKX Futures
```
Endpoint: GET https://www.okx.com/api/v5/public/funding-rate
Parameters: instId (e.g., BTC-USDT-SWAP)
Response:
  {
    "data": [
      {
        "instId": "BTC-USDT-SWAP",
        "fundingRate": "0.0001",
        "nextFundingTime": "1765929600000"
      }
    ]
  }
```

#### Hyperliquid (DEX)
```
Endpoint: POST https://api.hyperliquid.xyz/info
Body: {"type": "metaAndAssetCtxs"}
Response: Contains funding rates in asset contexts
Note: 1-hour funding interval
```

#### dYdX v4 (DEX)
```
Endpoint: GET https://indexer.dydx.trade/v4/perpetualMarkets
Response: Contains nextFundingRate for each market
Note: 1-hour funding interval
```

#### Gate.io Futures
```
Endpoint: GET https://api.gateio.ws/api/v4/futures/usdt/contracts
Response:
  [
    {
      "name": "BTC_USDT",
      "funding_rate": "0.0001",
      "funding_next_apply": 1765929600
    }
  ]
```

#### KuCoin Futures
```
Endpoint: GET https://api-futures.kucoin.com/api/v1/contracts/active
Response:
  {
    "data": [
      {
        "symbol": "XBTUSDTM",
        "fundingFeeRate": 0.0001,
        "nextFundingRateTime": 1765929600000
      }
    ]
  }
```

#### Bitget Futures
```
Endpoint: GET https://api.bitget.com/api/mix/v1/market/contracts
Parameters: productType=umcbl
Response: Contains current funding rates
```

### 7.0.2 ArbitrageScanner API (SECONDARY SOURCE)

Used for validation, gap filling, and quick opportunity discovery.

#### Funding Table Endpoint
```
URL: https://screener.arbitragescanner.io/api/funding-table
Method: GET
Purpose: 
  - Validate exchange API data
  - Fill gaps for non-integrated exchanges
  - Quick opportunity discovery via maxSpread

Response Structure:
  [
    {
      "slug": "bitcoin",
      "symbol": "BTCUSDT",
      "ticker": "BTC",
      "tokenId": 1,
      "maxSpread": 0.0234,  // Pre-calculated opportunity size
      "rates": [
        {
          "exchange": "binance_futures",
          "rate": 0.01,
          "nextFundingTime": 1765929600000,
          "ticker": "BTC",
          "symbol": "BTCUSDT"
        },
        // ... rates from all exchanges
      ]
    },
    // ... all tokens
  ]

Implementation:
  def fetch_arbitragescanner_rates():
      response = requests.get(
          "https://screener.arbitragescanner.io/api/funding-table",
          timeout=10
      )
      return response.json()
```

#### Exchanges Endpoint
```
URL: https://api.arbitragescanner.io/exchanges
Method: GET
Purpose: Master list of supported exchanges

Implementation:
  def fetch_exchange_registry():
      response = requests.get(
          "https://api.arbitragescanner.io/exchanges",
          timeout=10
      )
      data = response.json()
      return {
          ex['slug']: ex 
          for ex in data['rows'] 
          if ex.get('enabled_funding_rates', False)
      }
```

### 7.0.3 Data Reconciliation Implementation

```python
class FundingRateReconciler:
    def __init__(self, tolerance_pct=0.05):
        self.tolerance = tolerance_pct / 100
    
    def reconcile(self, exchange_rates: dict, arb_rates: dict) -> dict:
        """
        Merge data from both sources with exchange APIs as authoritative.
        """
        unified = {}
        discrepancies = []
        
        # All symbols from both sources
        all_symbols = set(exchange_rates.keys()) | set(arb_rates.keys())
        
        for symbol in all_symbols:
            ex_rate = exchange_rates.get(symbol)
            arb_rate = arb_rates.get(symbol)
            
            if ex_rate is not None and arb_rate is not None:
                # Both sources have data - use exchange, validate with arb
                diff = abs(ex_rate - arb_rate)
                if diff > self.tolerance:
                    discrepancies.append({
                        'symbol': symbol,
                        'exchange_rate': ex_rate,
                        'arb_rate': arb_rate,
                        'diff': diff
                    })
                unified[symbol] = {
                    'rate': ex_rate,  # PRIMARY
                    'source': 'exchange_api',
                    'validated': diff <= self.tolerance,
                    'arb_rate': arb_rate
                }
            elif ex_rate is not None:
                # Only exchange has data
                unified[symbol] = {
                    'rate': ex_rate,
                    'source': 'exchange_api',
                    'validated': False
                }
            elif arb_rate is not None:
                # Only ArbitrageScanner has data (gap fill)
                unified[symbol] = {
                    'rate': arb_rate,
                    'source': 'arbitragescanner',
                    'is_fallback': True
                }
        
        return {'rates': unified, 'discrepancies': discrepancies}
```

## 7.1 Required Exchange API Capabilities

For each supported exchange, implement the following capabilities.

### Market Data (Public)
```
# REQUIRED - Funding rates (PRIMARY source)
get_funding_rate(symbol) -> FundingRateData
get_all_funding_rates() -> dict[symbol, FundingRateData]
get_funding_rate_history(symbol, periods) -> list[FundingRateData]

# REQUIRED - Price and liquidity data
get_ticker(symbol) -> TickerData
get_order_book(symbol, depth) -> OrderBookData
get_open_interest(symbol) -> decimal
```

### Account Data (Private)
```
get_balance() -> dict[asset, Balance]
get_positions() -> list[PositionData]
get_margin_info() -> MarginInfo
get_fee_rates() -> FeeRates
```

### Trading (Private)
```
create_order(symbol, side, type, amount, price) -> OrderResult
cancel_order(order_id) -> CancelResult
get_order_status(order_id) -> OrderStatus
get_open_orders() -> list[Order]
```

### Account Management (Private)
```
transfer_funds(from_account, to_account, amount, asset) -> TransferResult
get_deposit_address(asset) -> Address
withdraw(asset, amount, address) -> WithdrawResult
```

## 7.2 Internal API Endpoints (for monitoring/control)

```
GET /api/status
  Returns system status, mode, health

GET /api/positions
  Returns all active positions

GET /api/positions/{id}
  Returns specific position details

GET /api/opportunities
  Returns current opportunity queue

GET /api/risk
  Returns current risk state

GET /api/capital
  Returns capital allocation state

GET /api/performance
  Returns performance metrics

POST /api/mode
  Body: { "mode": "conservative" | "standard" | "aggressive" | "emergency" }
  Changes operational mode

POST /api/positions/{id}/close
  Initiates position close

POST /api/emergency/shutdown
  Triggers emergency shutdown

GET /api/health
  Returns system health check
```

---

# 8. Event System

## 8.1 Event Types

```
MARKET_DATA Events:
  - FUNDING_RATE_UPDATE: New funding rate data available
  - PRICE_UPDATE: Price data updated
  - LIQUIDITY_UPDATE: Order book data updated
  - DATA_STALE: Data exceeded max age

OPPORTUNITY Events:
  - OPPORTUNITY_DETECTED: New opportunity identified
  - OPPORTUNITY_SCORED: Opportunity scored and ranked
  - OPPORTUNITY_EXPIRED: Opportunity no longer valid
  - OPPORTUNITY_ALLOCATED: Capital allocated to opportunity

POSITION Events:
  - POSITION_OPENING: Position being opened
  - POSITION_OPENED: Position successfully opened
  - POSITION_OPEN_FAILED: Position opening failed
  - POSITION_UPDATED: Position metrics updated
  - POSITION_HEALTH_CHANGED: Health status changed
  - POSITION_EXIT_TRIGGERED: Exit condition detected
  - POSITION_CLOSING: Position being closed
  - POSITION_CLOSED: Position successfully closed
  - POSITION_EMERGENCY_CLOSE: Emergency close initiated
  - FUNDING_COLLECTED: Funding payment received

RISK Events:
  - RISK_STATE_UPDATED: Risk metrics updated
  - RISK_LIMIT_WARNING: Approaching limit
  - RISK_LIMIT_BREACH: Limit exceeded
  - RISK_REGIME_CHANGED: Market regime changed

CAPITAL Events:
  - CAPITAL_ALLOCATED: Capital reserved for opportunity
  - CAPITAL_DEPLOYED: Capital deployed to position
  - CAPITAL_RELEASED: Capital returned from position
  - CAPITAL_TRANSFER: Cross-venue transfer

SYSTEM Events:
  - SYSTEM_STARTED: System initialized
  - SYSTEM_MODE_CHANGED: Operational mode changed
  - SYSTEM_ERROR: System error occurred
  - VENUE_DEGRADED: Exchange marked degraded
  - VENUE_RESTORED: Exchange restored to normal
```

## 8.2 Event Handlers

```
Each module subscribes to relevant events:

DataCollector:
  - Publishes: FUNDING_RATE_UPDATE, PRICE_UPDATE, LIQUIDITY_UPDATE, DATA_STALE

OpportunityScanner:
  - Subscribes: FUNDING_RATE_UPDATE, PRICE_UPDATE
  - Publishes: OPPORTUNITY_DETECTED

OpportunityScorer:
  - Subscribes: OPPORTUNITY_DETECTED
  - Publishes: OPPORTUNITY_SCORED

CapitalAllocator:
  - Subscribes: OPPORTUNITY_SCORED
  - Publishes: OPPORTUNITY_ALLOCATED, CAPITAL_ALLOCATED

ExecutionEngine:
  - Subscribes: OPPORTUNITY_ALLOCATED, POSITION_EXIT_TRIGGERED
  - Publishes: POSITION_OPENING, POSITION_OPENED, POSITION_OPEN_FAILED, POSITION_CLOSING, POSITION_CLOSED

PositionManager:
  - Subscribes: POSITION_OPENED, POSITION_CLOSED
  - Publishes: POSITION_UPDATED, POSITION_HEALTH_CHANGED, POSITION_EXIT_TRIGGERED

RiskManager:
  - Subscribes: POSITION_UPDATED, CAPITAL_DEPLOYED
  - Publishes: RISK_STATE_UPDATED, RISK_LIMIT_WARNING, RISK_LIMIT_BREACH

AlertManager:
  - Subscribes: All events requiring notification
  - Sends alerts through configured channels
```

---

# 9. State Management

## 9.1 State Persistence

```
The following state must be persisted (survives restarts):

Positions:
  - All active positions with full details
  - Position history (last 30 days)
  - Execution records

Capital:
  - Current allocation state
  - Pending allocations
  - Transfer history

Risk:
  - Current drawdown state
  - Peak equity (for drawdown calculation)
  - Limit breach history

Configuration:
  - Current operational mode
  - Any runtime parameter overrides

Analytics:
  - Performance history
  - Trade logs
  - Funding payment logs

Storage Options:
  - SQLite for simple deployment
  - PostgreSQL for production
  - Redis for caching layer
```

## 9.2 State Recovery

```
On system startup:

1. Load persisted state
2. Verify exchange connectivity
3. Reconcile positions with exchanges:
   - Fetch actual positions from all venues
   - Compare with persisted state
   - Alert on discrepancies
   - Update state to match reality
4. Verify capital state:
   - Fetch balances from all venues
   - Reconcile with tracked state
   - Update allocations
5. Resume monitoring:
   - Re-register all active positions
   - Resume normal event loop
```

## 9.3 State Reconciliation

```
Periodic reconciliation (every 5 minutes):

1. Fetch actual positions from exchanges
2. Compare with internal state:
   - Position exists in system but not exchange: Mark as externally closed
   - Position exists in exchange but not system: Alert, may need manual import
   - Size mismatch: Log discrepancy, consider if significant
3. Fetch actual balances
4. Compare with tracked state
5. Update internal state to match reality
6. Log all discrepancies for investigation
```

---

# 10. Testing Requirements

## 10.1 Unit Tests

```
Each module requires unit tests covering:

Data Providers:
  - API response parsing
  - Error handling
  - Rate limiting behavior
  - Data normalization

Opportunity Detection:
  - Eligibility filtering
  - Opportunity construction
  - Score calculation
  - Edge cases (missing data, extreme values)

Execution:
  - Order generation
  - Timing logic
  - Failure handling
  - Slippage calculation

Position Management:
  - Lifecycle transitions
  - Health calculation
  - Exit trigger evaluation
  - Rebalancing logic

Risk Management:
  - Limit checking
  - Metric calculations
  - Emergency protocol triggers

Capital Allocation:
  - Sizing logic
  - Constraint application
  - Reallocation decisions
```

## 10.2 Integration Tests

```
Integration tests for workflows:

Opportunity -> Position workflow:
  - Mock exchange responses
  - Verify complete flow
  - Verify state updates

Position monitoring workflow:
  - Simulate market data changes
  - Verify health status updates
  - Verify exit trigger detection

Risk event workflow:
  - Simulate risk limit approach
  - Verify alerts generated
  - Verify position adjustments

Cross-venue operations:
  - Verify multi-venue opportunity handling
  - Verify capital transfer logic
```

## 10.3 Simulation Testing

```
Before live deployment:

Paper Trading Mode:
  - Run system in discovery mode with real data
  - Log all would-be trades
  - Calculate hypothetical P&L
  - Verify system behavior matches expectations

Historical Backtesting:
  - Replay historical funding rate data
  - Execute strategy on historical data
  - Analyze performance
  - Identify parameter sensitivities

Stress Testing:
  - Simulate flash crash scenarios
  - Simulate exchange outages
  - Simulate extreme funding rates
  - Verify emergency protocols work correctly
```

---

# Implementation Priority

## Phase 1: Foundation
1. Project structure and configuration
2. Data models
3. Event system
4. Data providers (start with Binance)
5. Basic logging and monitoring

## Phase 2: Core Logic
1. Opportunity scanner
2. UOS scoring engine
3. Risk manager (basic limits)
4. Capital allocator (simple sizing)

## Phase 3: Execution
1. Execution engine
2. Position manager
3. Position monitor
4. Basic alerts

## Phase 4: Advanced Features
1. Predictive funding model
2. Timing optimizer
3. Smart order routing
4. Advanced risk management
5. Cross-venue operations

## Phase 5: Production Readiness
1. Full test coverage
2. State persistence
3. Recovery procedures
4. Performance analytics
5. Comprehensive alerting
6. Documentation

---

# Notes for Implementation
1. **Start Simple**: Begin with Type A (single-venue spot-perp) arbitrage before implementing complex cross-venue strategies.
2. **Data First**: Ensure data collection is rock-solid before building trading logic. Bad data leads to bad trades.
3. **Risk First**: Implement risk limits early. Never allow a trade that could exceed limits.
4. **Logging**: Log everything. You will need detailed logs to debug issues and improve the system.
5. **Gradual Rollout**: Start in discovery mode, then conservative mode with small sizes, before scaling up.
6. **Exchange Differences**: Each exchange has quirks. Document them and handle them explicitly.
7. **Time Zones**: All times should be in UTC internally. Convert for display only.
8. **Decimal Precision**: Use appropriate decimal precision for financial calculations. Never use floating point for money.
9. **Idempotency**: Make operations idempotent where possible. Retries should be safe.
10. **Graceful Degradation**: The system should continue operating (perhaps in reduced capacity) even if some components fail.
