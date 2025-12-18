'use client';

import { useState } from 'react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  RefreshCw,
  Loader2,
  Activity,
  TrendingUp,
  TrendingDown,
  Trophy,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getPositions } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

interface Position {
  id: string;
  symbol: string;
  status: string;
  primary_exchange: string;
  hedge_exchange: string;
  total_capital_deployed: number;
  realized_pnl: number;
  unrealized_pnl: number;
  funding_received: number;
  opened_at: string;
  closed_at?: string;
  health_status: string;
  close_reason?: string;
}

interface TradingHistoryProps {
  className?: string;
}

export function TradingHistory({ className }: TradingHistoryProps) {
  const [filter, setFilter] = useState<'all' | 'active' | 'closed'>('all');

  const { data: positionsData, isLoading, refetch } = useQuery({
    queryKey: ['positions'],
    queryFn: () => getPositions() as Promise<{ data?: Position[] }>,
    refetchInterval: 30000,
  });

  const positions = positionsData?.data || [];

  // Filter positions
  const filteredPositions = positions.filter((p) => {
    if (filter === 'active') return p.status === 'active';
    if (filter === 'closed') return p.status === 'closed';
    return true;
  });

  // Calculate statistics
  const closedPositions = positions.filter((p) => p.status === 'closed');
  const profitablePositions = closedPositions.filter((p) => p.realized_pnl > 0);
  const winRate = closedPositions.length > 0
    ? (profitablePositions.length / closedPositions.length) * 100
    : 0;

  const totalRealizedPnL = closedPositions.reduce((sum, p) => sum + p.realized_pnl, 0);
  const bestTrade = closedPositions.reduce((best, p) =>
    p.realized_pnl > (best?.realized_pnl || -Infinity) ? p : best
  , closedPositions[0]);
  const worstTrade = closedPositions.reduce((worst, p) =>
    p.realized_pnl < (worst?.realized_pnl || Infinity) ? p : worst
  , closedPositions[0]);

  const avgTradeReturn = closedPositions.length > 0
    ? closedPositions.reduce((sum, p) => {
        const returnPct = p.total_capital_deployed > 0
          ? (p.realized_pnl / p.total_capital_deployed) * 100
          : 0;
        return sum + returnPct;
      }, 0) / closedPositions.length
    : 0;

  return (
    <div className={cn('space-y-6', className)}>
      {/* Summary Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Win Rate</p>
                <p className={cn(
                  'text-2xl font-bold',
                  winRate >= 50 ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatPercent(winRate, 1)}
                </p>
              </div>
              <Trophy className={cn(
                'h-8 w-8',
                winRate >= 50 ? 'text-green-500' : 'text-muted-foreground'
              )} />
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {profitablePositions.length}/{closedPositions.length} profitable
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Realized P&L</p>
                <p className={cn(
                  'text-2xl font-bold',
                  totalRealizedPnL >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatCurrency(totalRealizedPnL)}
                </p>
              </div>
              {totalRealizedPnL >= 0 ? (
                <TrendingUp className="h-8 w-8 text-green-500" />
              ) : (
                <TrendingDown className="h-8 w-8 text-red-500" />
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Best Trade</p>
                <p className="text-2xl font-bold text-green-500">
                  {bestTrade ? formatCurrency(bestTrade.realized_pnl) : '-'}
                </p>
              </div>
              <TrendingUp className="h-8 w-8 text-green-500" />
            </div>
            {bestTrade && (
              <p className="text-xs text-muted-foreground mt-1">{bestTrade.symbol}</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Worst Trade</p>
                <p className="text-2xl font-bold text-red-500">
                  {worstTrade ? formatCurrency(worstTrade.realized_pnl) : '-'}
                </p>
              </div>
              <TrendingDown className="h-8 w-8 text-red-500" />
            </div>
            {worstTrade && (
              <p className="text-xs text-muted-foreground mt-1">{worstTrade.symbol}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Trading History Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                Trading History
              </CardTitle>
              <CardDescription>Historical and active positions</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
                <SelectTrigger className="w-[130px]">
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Trades</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="closed">Closed</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredPositions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No trades found
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-muted-foreground">
                    <th className="pb-3 font-medium">Symbol</th>
                    <th className="pb-3 font-medium">Exchanges</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium text-right">Capital</th>
                    <th className="pb-3 font-medium text-right">P&L</th>
                    <th className="pb-3 font-medium text-right">Return</th>
                    <th className="pb-3 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPositions
                    .sort((a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime())
                    .map((position) => {
                      const pnl = position.status === 'closed'
                        ? position.realized_pnl
                        : position.unrealized_pnl;
                      const returnPct = position.total_capital_deployed > 0
                        ? (pnl / position.total_capital_deployed) * 100
                        : 0;

                      return (
                        <tr key={position.id} className="border-b hover:bg-muted/50">
                          <td className="py-4">
                            <span className="font-medium">{position.symbol}</span>
                          </td>
                          <td className="py-4 text-sm text-muted-foreground">
                            {position.primary_exchange} / {position.hedge_exchange}
                          </td>
                          <td className="py-4">
                            <Badge
                              variant="outline"
                              className={cn(
                                position.status === 'active'
                                  ? 'text-green-500'
                                  : position.close_reason === 'profit_target'
                                  ? 'text-green-500'
                                  : position.close_reason === 'stop_loss'
                                  ? 'text-red-500'
                                  : 'text-muted-foreground'
                              )}
                            >
                              {position.status === 'active' ? 'Active' : position.close_reason || 'Closed'}
                            </Badge>
                          </td>
                          <td className="py-4 text-right">
                            {formatCurrency(position.total_capital_deployed)}
                          </td>
                          <td className={cn(
                            'py-4 text-right font-medium',
                            pnl >= 0 ? 'text-green-500' : 'text-red-500'
                          )}>
                            {formatCurrency(pnl)}
                          </td>
                          <td className={cn(
                            'py-4 text-right',
                            returnPct >= 0 ? 'text-green-500' : 'text-red-500'
                          )}>
                            {formatPercent(returnPct, 2)}
                          </td>
                          <td className="py-4 text-sm text-muted-foreground">
                            {new Date(position.opened_at).toLocaleDateString()}
                            {position.closed_at && (
                              <>
                                {' - '}
                                {new Date(position.closed_at).toLocaleDateString()}
                              </>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
