'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Trophy,
  Clock,
  Activity,
  DollarSign,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getPerformanceSummary } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

interface PerformanceSummary {
  win_rate?: number | string;
  total_trades?: number;
  trades_count?: number;
  avg_trade_duration_hours?: number;
  avg_hold_hours?: number | string;
  funding_pnl?: number;
  today_pnl?: number;
}

interface BotPerformanceMetricsProps {
  className?: string;
}

export function BotPerformanceMetrics({ className }: BotPerformanceMetricsProps) {
  const { data: summaryData, isLoading } = useQuery({
    queryKey: ['performance-summary'],
    queryFn: () => getPerformanceSummary('30d') as Promise<{ data?: PerformanceSummary }>,
    refetchInterval: 60000,
  });

  const rawSummary = summaryData?.data;

  // Normalize field names from API response
  const winRate = parseFloat(String(rawSummary?.win_rate || 0));
  const totalTrades = rawSummary?.total_trades ?? rawSummary?.trades_count ?? 0;
  const avgHoldHours = parseFloat(String(rawSummary?.avg_trade_duration_hours ?? rawSummary?.avg_hold_hours ?? 0));

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Activity className="h-4 w-4" />
          Performance Metrics
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Win Rate */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Trophy className={cn(
                    'h-4 w-4',
                    winRate >= 50 ? 'text-green-500' : 'text-muted-foreground'
                  )} />
                  <span className="text-sm">Win Rate</span>
                </div>
                <span className={cn(
                  'font-semibold',
                  winRate >= 50 ? 'text-green-500' : 'text-yellow-500'
                )}>
                  {formatPercent(winRate, 1)}
                </span>
              </div>
              <Progress
                value={winRate}
                className={cn(
                  'h-2',
                  winRate >= 50 ? '' : '[&>div]:bg-yellow-500'
                )}
              />
            </div>

            {/* Total Trades */}
            <div className="flex items-center justify-between py-2 border-t">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Total Trades</span>
              </div>
              <span className="font-semibold">{totalTrades}</span>
            </div>

            {/* Avg Duration */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Avg Duration</span>
              </div>
              <span className="font-semibold">
                {avgHoldHours > 0 ? `${Math.round(avgHoldHours)}h` : '-'}
              </span>
            </div>

            {/* Funding Earned Today */}
            <div className="flex items-center justify-between pt-2 border-t">
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-green-500" />
                <span className="text-sm text-muted-foreground">Funding Today</span>
              </div>
              <span className={cn(
                'font-semibold',
                (rawSummary?.today_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
              )}>
                {formatCurrency(rawSummary?.today_pnl || 0)}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
