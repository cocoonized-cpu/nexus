'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RefreshCw, Loader2, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getDailyPnL, getPortfolioHistory } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

type TimeRange = '7d' | '30d' | '90d' | '1y';

interface DailyData {
  date: string;
  pnl: number;
  cumulative_pnl: number;
  funding_pnl: number;
  trading_pnl: number;
  portfolio_value?: number;
}

interface PerformanceChartProps {
  className?: string;
}

const TIME_RANGES: { value: TimeRange; label: string; days: number }[] = [
  { value: '7d', label: '7D', days: 7 },
  { value: '30d', label: '30D', days: 30 },
  { value: '90d', label: '90D', days: 90 },
  { value: '1y', label: '1Y', days: 365 },
];

export function PerformanceChart({ className }: PerformanceChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('30d');

  const days = TIME_RANGES.find((r) => r.value === timeRange)?.days || 30;

  const { data: pnlData, isLoading, refetch } = useQuery({
    queryKey: ['daily-pnl', days],
    queryFn: () => getDailyPnL(days) as Promise<{ data?: DailyData[] }>,
    refetchInterval: 60000,
  });

  const chartData = pnlData?.data || [];

  // Calculate chart dimensions and values
  const maxValue = Math.max(...chartData.map((d) => d.cumulative_pnl), 0);
  const minValue = Math.min(...chartData.map((d) => d.cumulative_pnl), 0);
  const range = maxValue - minValue || 1;

  const totalPnL = chartData.length > 0 ? chartData[chartData.length - 1].cumulative_pnl : 0;
  const isPositive = totalPnL >= 0;

  // Calculate period return
  const periodStart = chartData.length > 0 ? chartData[0].cumulative_pnl - chartData[0].pnl : 0;
  const periodReturn = periodStart !== 0 ? ((totalPnL - periodStart) / Math.abs(periodStart)) * 100 : 0;

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            Performance
            {isPositive ? (
              <TrendingUp className="h-5 w-5 text-green-500" />
            ) : (
              <TrendingDown className="h-5 w-5 text-red-500" />
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Tabs value={timeRange} onValueChange={(v) => setTimeRange(v as TimeRange)}>
              <TabsList>
                {TIME_RANGES.map((range) => (
                  <TabsTrigger key={range.value} value={range.value}>
                    {range.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center h-[300px]">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[300px] text-muted-foreground">
            No performance data available
          </div>
        ) : (
          <div className="space-y-4">
            {/* Summary */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Cumulative P&L</p>
                <p className={cn(
                  'text-2xl font-bold',
                  isPositive ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatCurrency(totalPnL)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Period Return</p>
                <p className={cn(
                  'text-lg font-semibold',
                  periodReturn >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {periodReturn >= 0 ? '+' : ''}{formatPercent(periodReturn, 2)}
                </p>
              </div>
            </div>

            {/* Chart */}
            <div className="h-[250px] relative">
              {/* Grid lines */}
              <div className="absolute inset-0 flex flex-col justify-between">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="border-t border-muted h-0" />
                ))}
              </div>

              {/* Y-axis labels */}
              <div className="absolute left-0 top-0 bottom-0 w-16 flex flex-col justify-between text-xs text-muted-foreground pr-2 text-right">
                <span>{formatCurrency(maxValue, 0)}</span>
                <span>{formatCurrency((maxValue + minValue) / 2, 0)}</span>
                <span>{formatCurrency(minValue, 0)}</span>
              </div>

              {/* Bars */}
              <div className="absolute left-16 right-0 top-0 bottom-8 flex items-end gap-[2px]">
                {chartData.map((day, index) => {
                  const height = Math.abs(day.pnl) / (range / 2) * 100;
                  const isPositiveDay = day.pnl >= 0;

                  return (
                    <div
                      key={day.date}
                      className="flex-1 flex flex-col items-center justify-end relative group"
                      style={{ minWidth: '4px' }}
                    >
                      {/* Tooltip */}
                      <div className="absolute bottom-full mb-2 bg-popover border rounded-lg shadow-lg p-2 text-xs opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none whitespace-nowrap">
                        <p className="font-medium">{new Date(day.date).toLocaleDateString()}</p>
                        <p className={isPositiveDay ? 'text-green-500' : 'text-red-500'}>
                          P&L: {formatCurrency(day.pnl)}
                        </p>
                        <p className="text-muted-foreground">
                          Cumulative: {formatCurrency(day.cumulative_pnl)}
                        </p>
                      </div>

                      {/* Bar */}
                      <div
                        className={cn(
                          'w-full rounded-t transition-all hover:opacity-80',
                          isPositiveDay ? 'bg-green-500' : 'bg-red-500'
                        )}
                        style={{ height: `${Math.max(height, 2)}%` }}
                      />
                    </div>
                  );
                })}
              </div>

              {/* Zero line if data spans positive and negative */}
              {minValue < 0 && maxValue > 0 && (
                <div
                  className="absolute left-16 right-0 border-t-2 border-muted-foreground/30"
                  style={{
                    bottom: `${8 + (Math.abs(minValue) / range) * 242}px`,
                  }}
                />
              )}
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded bg-green-500" />
                <span className="text-muted-foreground">Positive</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded bg-red-500" />
                <span className="text-muted-foreground">Negative</span>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
