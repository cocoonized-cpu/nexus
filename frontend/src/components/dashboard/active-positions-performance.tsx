'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw,
  Loader2,
  ExternalLink,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getPositions } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { useWebSocket } from '@/lib/websocket';
import Link from 'next/link';

interface Position {
  id: string;
  symbol: string;
  status: string;
  primary_exchange: string;
  hedge_exchange: string;
  total_capital_deployed: number;
  unrealized_pnl: number;
  funding_received: number;
  health_status: string;
  opened_at: string;
}

const HEALTH_COLORS: Record<string, string> = {
  healthy: 'text-green-500 bg-green-500/10',
  warning: 'text-yellow-500 bg-yellow-500/10',
  critical: 'text-red-500 bg-red-500/10',
  unknown: 'text-muted-foreground bg-muted',
};

interface ActivePositionsPerformanceProps {
  className?: string;
  maxPositions?: number;
}

export function ActivePositionsPerformance({
  className,
  maxPositions = 5,
}: ActivePositionsPerformanceProps) {
  const { subscribe, lastMessage } = useWebSocket();

  const { data: positionsData, isLoading, refetch } = useQuery({
    queryKey: ['positions', 'active'],
    queryFn: () => getPositions('active') as Promise<{ data?: Position[] }>,
    refetchInterval: 10000,
  });

  // Subscribe to WebSocket
  useEffect(() => {
    subscribe('positions');
  }, [subscribe]);

  // Refetch on position changes
  useEffect(() => {
    if (lastMessage?.channel === 'positions') {
      refetch();
    }
  }, [lastMessage, refetch]);

  const positions = (positionsData?.data || []).slice(0, maxPositions);

  // Calculate totals
  const totalDeployed = positions.reduce((sum, p) => sum + p.total_capital_deployed, 0);
  const totalUnrealizedPnL = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
  const totalFunding = positions.reduce((sum, p) => sum + p.funding_received, 0);

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Active Positions
            </CardTitle>
            <CardDescription>Real-time position performance</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Link href="/positions">
              <Button variant="outline" size="sm">
                <ExternalLink className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : positions.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No active positions
          </div>
        ) : (
          <div className="space-y-4">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-4 p-3 rounded-lg bg-muted/50">
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Deployed</p>
                <p className="font-semibold">{formatCurrency(totalDeployed)}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Unrealized</p>
                <p className={cn(
                  'font-semibold',
                  totalUnrealizedPnL >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatCurrency(totalUnrealizedPnL)}
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Funding</p>
                <p className={cn(
                  'font-semibold',
                  totalFunding >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatCurrency(totalFunding)}
                </p>
              </div>
            </div>

            {/* Positions List */}
            <div className="space-y-2">
              {positions.map((position) => {
                const returnPct = position.total_capital_deployed > 0
                  ? (position.unrealized_pnl / position.total_capital_deployed) * 100
                  : 0;
                const isPositive = position.unrealized_pnl >= 0;

                return (
                  <div
                    key={position.id}
                    className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {/* P&L Indicator */}
                      <div
                        className={cn(
                          'h-8 w-8 rounded-full flex items-center justify-center',
                          isPositive ? 'bg-green-500/10' : 'bg-red-500/10'
                        )}
                      >
                        {isPositive ? (
                          <TrendingUp className="h-4 w-4 text-green-500" />
                        ) : (
                          <TrendingDown className="h-4 w-4 text-red-500" />
                        )}
                      </div>

                      {/* Symbol and Exchanges */}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{position.symbol}</span>
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-[10px] px-1 h-4',
                              HEALTH_COLORS[position.health_status] || HEALTH_COLORS.unknown
                            )}
                          >
                            {position.health_status}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {position.primary_exchange} / {position.hedge_exchange}
                        </p>
                      </div>
                    </div>

                    {/* P&L */}
                    <div className="text-right">
                      <p className={cn(
                        'font-semibold',
                        isPositive ? 'text-green-500' : 'text-red-500'
                      )}>
                        {formatCurrency(position.unrealized_pnl)}
                      </p>
                      <p className={cn(
                        'text-xs',
                        isPositive ? 'text-green-500' : 'text-red-500'
                      )}>
                        {isPositive ? '+' : ''}{formatPercent(returnPct, 2)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* View All Link */}
            {(positionsData?.data?.length || 0) > maxPositions && (
              <Link href="/positions">
                <Button variant="ghost" className="w-full text-muted-foreground">
                  View all {positionsData?.data?.length} positions
                </Button>
              </Link>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
