'use client';

import { useQuery } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Card,
  CardContent,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  PieChart,
  TrendingUp,
  TrendingDown,
  Wallet,
  DollarSign,
  Activity,
  Percent,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getPerformanceSummary, getCapitalSummary } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { PerformanceChart } from '@/components/performance/performance-chart';
import { BalanceOverview } from '@/components/performance/balance-overview';
import { FundingBreakdown } from '@/components/performance/funding-breakdown';
import { TradingHistory } from '@/components/performance/trading-history';
import { PerformanceAttribution } from '@/components/analytics/performance-attribution';

interface PerformanceSummary {
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  funding_pnl: number;
  trading_pnl: number;
  return_pct: number;
  win_rate: number;
  total_trades: number;
  avg_trade_duration_hours: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  best_day?: number;
  worst_day?: number;
}

interface CapitalSummary {
  total_capital: number;
  total_equity: number;
  available_capital: number;
  deployed_capital: number;
}

export default function PerformancePage() {
  const { data: summaryData, isLoading: isLoadingSummary } = useQuery({
    queryKey: ['performance-summary'],
    queryFn: () => getPerformanceSummary('30d') as Promise<{ data?: PerformanceSummary }>,
    refetchInterval: 60000,
  });

  const { data: capitalData, isLoading: isLoadingCapital } = useQuery({
    queryKey: ['capital-summary'],
    queryFn: () => getCapitalSummary() as Promise<{ data?: CapitalSummary }>,
    refetchInterval: 30000,
  });

  const summary = summaryData?.data;
  const capital = capitalData?.data;
  const isLoading = isLoadingSummary || isLoadingCapital;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <PieChart className="h-8 w-8" />
            Performance
          </h1>
          <p className="text-muted-foreground">
            Track your trading performance and financial metrics
          </p>
        </div>

        {/* Summary Cards */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-5">
            {/* Total Value */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Value</p>
                    <p className="text-2xl font-bold">
                      {formatCurrency(capital?.total_equity || 0)}
                    </p>
                  </div>
                  <Wallet className="h-8 w-8 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>

            {/* Net P&L */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Net P&L</p>
                    <p className={cn(
                      'text-2xl font-bold',
                      (summary?.total_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                    )}>
                      {formatCurrency(summary?.total_pnl || 0)}
                    </p>
                  </div>
                  {(summary?.total_pnl || 0) >= 0 ? (
                    <TrendingUp className="h-8 w-8 text-green-500" />
                  ) : (
                    <TrendingDown className="h-8 w-8 text-red-500" />
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Return % */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Return</p>
                    <p className={cn(
                      'text-2xl font-bold',
                      (summary?.return_pct || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                    )}>
                      {formatPercent(summary?.return_pct || 0, 2)}
                    </p>
                  </div>
                  <Percent className="h-8 w-8 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>

            {/* Win Rate */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Win Rate</p>
                    <p className={cn(
                      'text-2xl font-bold',
                      (summary?.win_rate || 0) >= 50 ? 'text-green-500' : 'text-yellow-500'
                    )}>
                      {formatPercent(summary?.win_rate || 0, 1)}
                    </p>
                  </div>
                  <Activity className="h-8 w-8 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>

            {/* Funding Earned */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Funding Earned</p>
                    <p className={cn(
                      'text-2xl font-bold',
                      (summary?.funding_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                    )}>
                      {formatCurrency(summary?.funding_pnl || 0)}
                    </p>
                  </div>
                  <DollarSign className="h-8 w-8 text-green-500" />
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Performance Chart */}
        <PerformanceChart />

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="attribution">Attribution</TabsTrigger>
            <TabsTrigger value="balances">Balances</TabsTrigger>
            <TabsTrigger value="trading">Trading</TabsTrigger>
            <TabsTrigger value="funding">Funding</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            {/* Overview Tab - P&L breakdown and key metrics */}
            <div className="grid gap-6 lg:grid-cols-2">
              {/* P&L Breakdown */}
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">P&L Breakdown</h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Funding P&L</span>
                      <span className={cn(
                        'font-medium',
                        (summary?.funding_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      )}>
                        {formatCurrency(summary?.funding_pnl || 0)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Trading P&L</span>
                      <span className={cn(
                        'font-medium',
                        (summary?.trading_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      )}>
                        {formatCurrency(summary?.trading_pnl || 0)}
                      </span>
                    </div>
                    <div className="h-px bg-border" />
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Realized P&L</span>
                      <span className={cn(
                        'font-medium',
                        (summary?.realized_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      )}>
                        {formatCurrency(summary?.realized_pnl || 0)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Unrealized P&L</span>
                      <span className={cn(
                        'font-medium',
                        (summary?.unrealized_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      )}>
                        {formatCurrency(summary?.unrealized_pnl || 0)}
                      </span>
                    </div>
                    <div className="h-px bg-border" />
                    <div className="flex items-center justify-between font-semibold">
                      <span>Total P&L</span>
                      <span className={cn(
                        (summary?.total_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      )}>
                        {formatCurrency(summary?.total_pnl || 0)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Key Metrics */}
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Key Metrics</h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Total Trades</span>
                      <span className="font-medium">{summary?.total_trades || 0}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Avg Trade Duration</span>
                      <span className="font-medium">
                        {summary?.avg_trade_duration_hours
                          ? `${Math.round(summary.avg_trade_duration_hours)}h`
                          : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Sharpe Ratio</span>
                      <span className={cn(
                        'font-medium',
                        (summary?.sharpe_ratio || 0) >= 1 ? 'text-green-500' : 'text-muted-foreground'
                      )}>
                        {summary?.sharpe_ratio?.toFixed(2) || '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Max Drawdown</span>
                      <span className="font-medium text-red-500">
                        {summary?.max_drawdown ? formatPercent(summary.max_drawdown, 2) : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Best Day</span>
                      <span className="font-medium text-green-500">
                        {summary?.best_day ? formatCurrency(summary.best_day) : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Worst Day</span>
                      <span className="font-medium text-red-500">
                        {summary?.worst_day ? formatCurrency(summary.worst_day) : '-'}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="attribution">
            <PerformanceAttribution />
          </TabsContent>

          <TabsContent value="balances">
            <BalanceOverview />
          </TabsContent>

          <TabsContent value="trading">
            <TradingHistory />
          </TabsContent>

          <TabsContent value="funding">
            <FundingBreakdown />
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
