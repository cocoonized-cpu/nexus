'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPositions } from '@/lib/api';

// Types matching the API response
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

// Consolidated view structure for display
export interface ConsolidatedPosition {
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

interface ApiResponse {
  data?: Position[];
  meta?: {
    total: number;
    timestamp: string;
  };
}

export function useConsolidatedPositions() {
  // Fetch positions from API
  const {
    data: positionsData,
    isLoading,
    refetch,
    error,
  } = useQuery({
    queryKey: ['nexus-positions'],
    queryFn: () => getPositions() as Promise<ApiResponse>,
    refetchInterval: 10000,
  });

  // Transform positions to consolidated view
  const consolidatedPositions = useMemo<ConsolidatedPosition[]>(() => {
    const positions = positionsData?.data || [];

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
  }, [positionsData]);

  // Calculate summary stats
  const stats = useMemo(() => {
    const totalCapital = consolidatedPositions.reduce(
      (sum, p) => sum + p.totalCapital,
      0
    );
    const totalPnl = consolidatedPositions.reduce(
      (sum, p) => sum + p.netPnl,
      0
    );
    const totalFundingPnl = consolidatedPositions.reduce(
      (sum, p) => sum + p.netFundingPnl,
      0
    );

    return {
      positionCount: consolidatedPositions.length,
      totalCapital,
      totalPnl,
      totalFundingPnl,
      avgReturn:
        consolidatedPositions.length > 0
          ? consolidatedPositions.reduce((sum, p) => sum + p.returnPct, 0) /
            consolidatedPositions.length
          : 0,
    };
  }, [consolidatedPositions]);

  return {
    positions: consolidatedPositions,
    stats,
    isLoading,
    error,
    refetch,
  };
}
