import { describe, it, expect } from 'vitest';

// Test the consolidated positions transformation logic
// This mirrors the hook's logic for transforming positions

interface PositionLeg {
  id: string;
  leg_type: 'primary' | 'hedge';
  exchange: string;
  symbol: string;
  market_type: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  notional_value_usd: number;
  unrealized_pnl: number;
  funding_pnl: number;
}

interface Position {
  id: string;
  opportunity_id?: string;
  opportunity_type: string;
  symbol: string;
  base_asset: string;
  status: string;
  health_status: string;
  total_capital_deployed: number;
  funding_received: number;
  funding_paid: number;
  net_funding_pnl: number;
  unrealized_pnl: number;
  return_pct: number;
  delta_exposure_pct: number;
  max_margin_utilization: number;
  opened_at?: string;
  funding_periods_collected: number;
  legs: PositionLeg[];
}

interface ConsolidatedPosition {
  symbol: string;
  positionId: string;
  status: string;
  healthStatus: string;
  longLeg?: {
    exchange: string;
    entryPrice: number;
    currentPrice: number;
    size: number;
    notional: number;
    pnl: number;
    fundingPnl: number;
  };
  shortLeg?: {
    exchange: string;
    entryPrice: number;
    currentPrice: number;
    size: number;
    notional: number;
    pnl: number;
    fundingPnl: number;
  };
  totalCapital: number;
  netFundingPnl: number;
  netPnl: number;
  returnPct: number;
  fundingPeriods: number;
  openedAt?: string;
}

// Transformation function matching the hook's implementation
function transformPositions(positions: Position[]): ConsolidatedPosition[] {
  return positions.map((pos): ConsolidatedPosition => {
    // Find long and short legs
    const longLeg = pos.legs?.find(
      (leg) => leg.side === 'long' || leg.side === 'buy'
    );
    const shortLeg = pos.legs?.find(
      (leg) => leg.side === 'short' || leg.side === 'sell'
    );

    // Calculate total P&L from legs
    const legPnl = pos.legs?.reduce((sum, leg) => sum + (leg.unrealized_pnl || 0), 0) || 0;
    const legFundingPnl = pos.legs?.reduce((sum, leg) => sum + (leg.funding_pnl || 0), 0) || 0;

    return {
      symbol: pos.symbol,
      positionId: pos.id,
      status: pos.status,
      healthStatus: pos.health_status,
      longLeg: longLeg
        ? {
            exchange: longLeg.exchange,
            entryPrice: Number(longLeg.entry_price),
            currentPrice: Number(longLeg.current_price),
            size: Number(longLeg.quantity),
            notional: Number(longLeg.notional_value_usd),
            pnl: Number(longLeg.unrealized_pnl),
            fundingPnl: Number(longLeg.funding_pnl),
          }
        : undefined,
      shortLeg: shortLeg
        ? {
            exchange: shortLeg.exchange,
            entryPrice: Number(shortLeg.entry_price),
            currentPrice: Number(shortLeg.current_price),
            size: Number(shortLeg.quantity),
            notional: Number(shortLeg.notional_value_usd),
            pnl: Number(shortLeg.unrealized_pnl),
            fundingPnl: Number(shortLeg.funding_pnl),
          }
        : undefined,
      totalCapital: Number(pos.total_capital_deployed),
      netFundingPnl: Number(pos.net_funding_pnl) || legFundingPnl,
      netPnl: Number(pos.unrealized_pnl) || legPnl,
      returnPct: Number(pos.return_pct),
      fundingPeriods: pos.funding_periods_collected,
      openedAt: pos.opened_at,
    };
  });
}

describe('Consolidated Positions Transformation', () => {
  const mockPosition: Position = {
    id: 'pos-123',
    opportunity_id: 'opp-456',
    opportunity_type: 'funding_rate',
    symbol: 'BTC-PERP',
    base_asset: 'BTC',
    status: 'active',
    health_status: 'healthy',
    total_capital_deployed: 1000,
    funding_received: 5.5,
    funding_paid: 1.2,
    net_funding_pnl: 4.3,
    unrealized_pnl: 12.5,
    return_pct: 1.25,
    delta_exposure_pct: 0.5,
    max_margin_utilization: 25,
    opened_at: '2024-01-15T10:00:00Z',
    funding_periods_collected: 3,
    legs: [
      {
        id: 'leg-1',
        leg_type: 'primary',
        exchange: 'binance',
        symbol: 'BTCUSDT',
        market_type: 'perpetual',
        side: 'long',
        quantity: 0.1,
        entry_price: 42000,
        current_price: 42500,
        notional_value_usd: 4250,
        unrealized_pnl: 50,
        funding_pnl: 3.2,
      },
      {
        id: 'leg-2',
        leg_type: 'hedge',
        exchange: 'bybit',
        symbol: 'BTCUSDT',
        market_type: 'perpetual',
        side: 'short',
        quantity: 0.1,
        entry_price: 42100,
        current_price: 42500,
        notional_value_usd: 4250,
        unrealized_pnl: -40,
        funding_pnl: 1.1,
      },
    ],
  };

  it('should correctly transform a position with both legs', () => {
    const result = transformPositions([mockPosition]);
    expect(result.length).toBe(1);

    const consolidated = result[0];
    expect(consolidated.symbol).toBe('BTC-PERP');
    expect(consolidated.positionId).toBe('pos-123');
    expect(consolidated.status).toBe('active');
    expect(consolidated.healthStatus).toBe('healthy');
    expect(consolidated.totalCapital).toBe(1000);
    expect(consolidated.fundingPeriods).toBe(3);
  });

  it('should correctly identify long leg', () => {
    const result = transformPositions([mockPosition]);
    const consolidated = result[0];

    expect(consolidated.longLeg).toBeDefined();
    expect(consolidated.longLeg?.exchange).toBe('binance');
    expect(consolidated.longLeg?.entryPrice).toBe(42000);
    expect(consolidated.longLeg?.size).toBe(0.1);
    expect(consolidated.longLeg?.pnl).toBe(50);
  });

  it('should correctly identify short leg', () => {
    const result = transformPositions([mockPosition]);
    const consolidated = result[0];

    expect(consolidated.shortLeg).toBeDefined();
    expect(consolidated.shortLeg?.exchange).toBe('bybit');
    expect(consolidated.shortLeg?.entryPrice).toBe(42100);
    expect(consolidated.shortLeg?.size).toBe(0.1);
    expect(consolidated.shortLeg?.pnl).toBe(-40);
  });

  it('should handle positions with buy/sell sides instead of long/short', () => {
    const positionWithBuySell: Position = {
      ...mockPosition,
      legs: [
        { ...mockPosition.legs[0], side: 'buy' },
        { ...mockPosition.legs[1], side: 'sell' },
      ],
    };

    const result = transformPositions([positionWithBuySell]);
    const consolidated = result[0];

    expect(consolidated.longLeg).toBeDefined();
    expect(consolidated.shortLeg).toBeDefined();
  });

  it('should handle positions with only one leg', () => {
    const singleLegPosition: Position = {
      ...mockPosition,
      legs: [mockPosition.legs[0]], // Only long leg
    };

    const result = transformPositions([singleLegPosition]);
    const consolidated = result[0];

    expect(consolidated.longLeg).toBeDefined();
    expect(consolidated.shortLeg).toBeUndefined();
  });

  it('should handle positions with no legs', () => {
    const noLegPosition: Position = {
      ...mockPosition,
      legs: [],
    };

    const result = transformPositions([noLegPosition]);
    const consolidated = result[0];

    expect(consolidated.longLeg).toBeUndefined();
    expect(consolidated.shortLeg).toBeUndefined();
    expect(consolidated.netPnl).toBe(12.5); // Uses position-level unrealized_pnl
  });

  it('should calculate leg P&L sum when position-level is zero', () => {
    const positionWithZeroPnl: Position = {
      ...mockPosition,
      unrealized_pnl: 0, // Force to use leg calculations
    };

    const result = transformPositions([positionWithZeroPnl]);
    const consolidated = result[0];

    // Sum of leg unrealized_pnl: 50 + (-40) = 10
    expect(consolidated.netPnl).toBe(10);
  });
});

describe('Consolidated Positions Stats Calculation', () => {
  function calculateStats(positions: ConsolidatedPosition[]) {
    const totalCapital = positions.reduce((sum, p) => sum + p.totalCapital, 0);
    const totalPnl = positions.reduce((sum, p) => sum + p.netPnl, 0);
    const totalFundingPnl = positions.reduce((sum, p) => sum + p.netFundingPnl, 0);
    const avgReturn = positions.length > 0
      ? positions.reduce((sum, p) => sum + p.returnPct, 0) / positions.length
      : 0;

    return {
      positionCount: positions.length,
      totalCapital,
      totalPnl,
      totalFundingPnl,
      avgReturn,
    };
  }

  const mockConsolidated: ConsolidatedPosition[] = [
    {
      symbol: 'BTC-PERP',
      positionId: '1',
      status: 'active',
      healthStatus: 'healthy',
      totalCapital: 1000,
      netFundingPnl: 5,
      netPnl: 10,
      returnPct: 1.0,
      fundingPeriods: 3,
    },
    {
      symbol: 'ETH-PERP',
      positionId: '2',
      status: 'active',
      healthStatus: 'healthy',
      totalCapital: 500,
      netFundingPnl: 2,
      netPnl: -3,
      returnPct: -0.6,
      fundingPeriods: 2,
    },
    {
      symbol: 'SOL-PERP',
      positionId: '3',
      status: 'active',
      healthStatus: 'warning',
      totalCapital: 200,
      netFundingPnl: 1,
      netPnl: 5,
      returnPct: 2.5,
      fundingPeriods: 1,
    },
  ];

  it('should calculate total position count', () => {
    const stats = calculateStats(mockConsolidated);
    expect(stats.positionCount).toBe(3);
  });

  it('should calculate total capital', () => {
    const stats = calculateStats(mockConsolidated);
    expect(stats.totalCapital).toBe(1700); // 1000 + 500 + 200
  });

  it('should calculate total P&L', () => {
    const stats = calculateStats(mockConsolidated);
    expect(stats.totalPnl).toBe(12); // 10 + (-3) + 5
  });

  it('should calculate total funding P&L', () => {
    const stats = calculateStats(mockConsolidated);
    expect(stats.totalFundingPnl).toBe(8); // 5 + 2 + 1
  });

  it('should calculate average return', () => {
    const stats = calculateStats(mockConsolidated);
    // (1.0 + (-0.6) + 2.5) / 3 = 2.9 / 3 = ~0.967
    expect(stats.avgReturn).toBeCloseTo(0.967, 2);
  });

  it('should handle empty positions array', () => {
    const stats = calculateStats([]);
    expect(stats.positionCount).toBe(0);
    expect(stats.totalCapital).toBe(0);
    expect(stats.totalPnl).toBe(0);
    expect(stats.totalFundingPnl).toBe(0);
    expect(stats.avgReturn).toBe(0);
  });
});
