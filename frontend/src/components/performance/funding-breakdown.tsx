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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  RefreshCw,
  Loader2,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Calendar,
  Layers,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getPositions, getDailyPnL, DailyPnLData } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

type ViewMode = 'per-position' | 'daily';

interface Position {
  id: string;
  symbol: string;
  funding_received: number;
  funding_rate_avg: number;
  primary_exchange: string;
  hedge_exchange: string;
  opened_at: string;
  status: string;
  total_capital_deployed: number;
}

interface FundingBreakdownProps {
  className?: string;
}

export function FundingBreakdown({ className }: FundingBreakdownProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('per-position');

  const { data: positionsData, isLoading: isLoadingPositions, refetch: refetchPositions } = useQuery({
    queryKey: ['positions'],
    queryFn: () => getPositions() as Promise<{ data?: Position[] }>,
    refetchInterval: 30000,
  });

  const { data: dailyData, isLoading: isLoadingDaily, refetch: refetchDaily } = useQuery({
    queryKey: ['daily-pnl', 30],
    queryFn: () => getDailyPnL(30),
    refetchInterval: 60000,
  });

  const positions = positionsData?.data || [];
  const dailyFunding: DailyPnLData[] = dailyData?.data || [];

  const totalFundingReceived = positions.reduce((sum, p) => sum + p.funding_received, 0);
  const isLoading = viewMode === 'per-position' ? isLoadingPositions : isLoadingDaily;

  const handleRefetch = () => {
    if (viewMode === 'per-position') {
      refetchPositions();
    } else {
      refetchDaily();
    }
  };

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5" />
              Funding Breakdown
            </CardTitle>
            <CardDescription>
              {viewMode === 'per-position'
                ? 'Funding received per position'
                : 'Daily funding summary'}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
              <TabsList>
                <TabsTrigger value="per-position">
                  <Layers className="h-4 w-4 mr-1" />
                  Per Position
                </TabsTrigger>
                <TabsTrigger value="daily">
                  <Calendar className="h-4 w-4 mr-1" />
                  Daily
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <Button variant="outline" size="sm" onClick={handleRefetch}>
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
        ) : viewMode === 'per-position' ? (
          /* Per-Position View */
          <div className="space-y-4">
            {/* Summary */}
            <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50">
              <div>
                <p className="text-sm text-muted-foreground">Total Funding Received</p>
                <p className={cn(
                  'text-2xl font-bold',
                  totalFundingReceived >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatCurrency(totalFundingReceived)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Active Positions</p>
                <p className="text-xl font-semibold">{positions.filter(p => p.status === 'active').length}</p>
              </div>
            </div>

            {/* Positions Table */}
            {positions.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No positions with funding data
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b text-left text-sm text-muted-foreground">
                      <th className="pb-3 font-medium">Symbol</th>
                      <th className="pb-3 font-medium">Exchanges</th>
                      <th className="pb-3 font-medium text-right">Capital</th>
                      <th className="pb-3 font-medium text-right">Funding Received</th>
                      <th className="pb-3 font-medium text-right">Avg Rate</th>
                      <th className="pb-3 font-medium text-right">Yield</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions
                      .filter((p) => p.funding_received !== 0)
                      .sort((a, b) => b.funding_received - a.funding_received)
                      .map((position) => {
                        const yieldPercent = position.total_capital_deployed > 0
                          ? (position.funding_received / position.total_capital_deployed) * 100
                          : 0;

                        return (
                          <tr key={position.id} className="border-b hover:bg-muted/50">
                            <td className="py-4">
                              <span className="font-medium">{position.symbol}</span>
                              <Badge
                                variant="outline"
                                className={cn(
                                  'ml-2 text-xs',
                                  position.status === 'active' ? 'text-green-500' : 'text-muted-foreground'
                                )}
                              >
                                {position.status}
                              </Badge>
                            </td>
                            <td className="py-4 text-sm text-muted-foreground">
                              {position.primary_exchange} / {position.hedge_exchange}
                            </td>
                            <td className="py-4 text-right">
                              {formatCurrency(position.total_capital_deployed)}
                            </td>
                            <td className={cn(
                              'py-4 text-right font-medium',
                              position.funding_received >= 0 ? 'text-green-500' : 'text-red-500'
                            )}>
                              {formatCurrency(position.funding_received)}
                            </td>
                            <td className="py-4 text-right text-sm">
                              {formatPercent(position.funding_rate_avg * 100, 4)}
                            </td>
                            <td className={cn(
                              'py-4 text-right',
                              yieldPercent >= 0 ? 'text-green-500' : 'text-red-500'
                            )}>
                              {formatPercent(yieldPercent, 2)}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          /* Daily Summary View */
          <div className="space-y-4">
            {/* Summary */}
            <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50">
              <div>
                <p className="text-sm text-muted-foreground">30-Day Funding Total</p>
                <p className={cn(
                  'text-2xl font-bold',
                  dailyFunding.reduce((sum, d) => sum + d.funding_pnl, 0) >= 0
                    ? 'text-green-500'
                    : 'text-red-500'
                )}>
                  {formatCurrency(dailyFunding.reduce((sum, d) => sum + d.funding_pnl, 0))}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Avg Daily Funding</p>
                <p className="text-xl font-semibold">
                  {formatCurrency(
                    dailyFunding.length > 0
                      ? dailyFunding.reduce((sum, d) => sum + d.funding_pnl, 0) / dailyFunding.length
                      : 0
                  )}
                </p>
              </div>
            </div>

            {/* Daily Table */}
            {dailyFunding.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No daily funding data available
              </div>
            ) : (
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full">
                  <thead className="sticky top-0 bg-card">
                    <tr className="border-b text-left text-sm text-muted-foreground">
                      <th className="pb-3 font-medium">Date</th>
                      <th className="pb-3 font-medium text-right">Funding P&L</th>
                      <th className="pb-3 font-medium text-right">Cumulative</th>
                      <th className="pb-3 font-medium text-right">Positions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...dailyFunding].reverse().map((day) => (
                      <tr key={day.date} className="border-b hover:bg-muted/50">
                        <td className="py-3">
                          <span className="font-medium">
                            {new Date(day.date).toLocaleDateString('en-US', {
                              weekday: 'short',
                              month: 'short',
                              day: 'numeric',
                            })}
                          </span>
                        </td>
                        <td className="py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {day.funding_pnl >= 0 ? (
                              <TrendingUp className="h-3 w-3 text-green-500" />
                            ) : (
                              <TrendingDown className="h-3 w-3 text-red-500" />
                            )}
                            <span className={cn(
                              'font-medium',
                              day.funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'
                            )}>
                              {formatCurrency(day.funding_pnl)}
                            </span>
                          </div>
                        </td>
                        <td className={cn(
                          'py-3 text-right',
                          day.cumulative_funding >= 0 ? 'text-green-500' : 'text-red-500'
                        )}>
                          {formatCurrency(day.cumulative_funding)}
                        </td>
                        <td className="py-3 text-right text-muted-foreground">
                          {day.position_count || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
