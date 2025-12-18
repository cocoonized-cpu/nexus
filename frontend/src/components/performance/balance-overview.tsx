'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { RefreshCw, Loader2, Wallet, TrendingUp, TrendingDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getExchangeBalances, getCapitalSummary } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

interface ExchangeBalanceAPI {
  venue: string;
  total_usd: string;
  margin_used: string;
  margin_available: string;
  margin_utilization_pct: string;
  unrealized_pnl: string;
}

interface ExchangeBalance {
  exchange: string;
  total_equity: number;
  available_balance: number;
  margin_used: number;
  unrealized_pnl: number;
}

interface CapitalSummaryAPI {
  total_capital_usd: string;
  available_capital_usd: string;
  deployed_capital_usd: string;
  pending_capital_usd: string;
  reserve_capital_usd: string;
  utilization_pct: string;
}

interface CapitalSummary {
  total_capital: number;
  total_equity: number;
  available_capital: number;
  deployed_capital: number;
  unrealized_pnl: number;
  realized_pnl: number;
}

interface BalanceOverviewProps {
  className?: string;
}

const EXCHANGE_COLORS: Record<string, string> = {
  binance: 'bg-yellow-500',
  bybit: 'bg-orange-500',
  okx: 'bg-blue-500',
  hyperliquid: 'bg-green-500',
  default: 'bg-gray-500',
};

export function BalanceOverview({ className }: BalanceOverviewProps) {
  const { data: balancesData, isLoading: isLoadingBalances, refetch: refetchBalances } = useQuery({
    queryKey: ['exchange-balances'],
    queryFn: async () => {
      const response = await getExchangeBalances() as { data?: ExchangeBalanceAPI[] };
      // Transform API response to component format
      const transformed: ExchangeBalance[] = (response.data || []).map((b) => ({
        exchange: b.venue.replace('_futures', '').replace('_spot', ''),
        total_equity: parseFloat(b.total_usd) || 0,
        available_balance: parseFloat(b.margin_available) || 0,
        margin_used: parseFloat(b.margin_used) || 0,
        unrealized_pnl: parseFloat(b.unrealized_pnl) || 0,
      }));
      return { data: transformed };
    },
    refetchInterval: 30000,
  });

  const { data: summaryData, isLoading: isLoadingSummary } = useQuery({
    queryKey: ['capital-summary'],
    queryFn: async () => {
      const response = await getCapitalSummary() as { data?: CapitalSummaryAPI };
      if (!response.data) return { data: undefined };
      const d = response.data;
      const transformed: CapitalSummary = {
        total_capital: parseFloat(d.total_capital_usd) || 0,
        total_equity: parseFloat(d.total_capital_usd) || 0,
        available_capital: parseFloat(d.available_capital_usd) || 0,
        deployed_capital: parseFloat(d.deployed_capital_usd) || 0,
        unrealized_pnl: 0,
        realized_pnl: 0,
      };
      return { data: transformed };
    },
    refetchInterval: 30000,
  });

  const balances = balancesData?.data || [];
  const summary = summaryData?.data;
  const isLoading = isLoadingBalances || isLoadingSummary;

  const totalValue = summary?.total_equity || balances.reduce((sum, b) => sum + b.total_equity, 0);
  const totalUnrealizedPnL = summary?.unrealized_pnl || balances.reduce((sum, b) => sum + b.unrealized_pnl, 0);

  return (
    <div className={cn('space-y-6', className)}>
      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Value</p>
                <p className="text-2xl font-bold">{formatCurrency(totalValue)}</p>
              </div>
              <Wallet className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Deployed</p>
                <p className="text-2xl font-bold">{formatCurrency(summary?.deployed_capital || 0)}</p>
              </div>
              <TrendingUp className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Available</p>
                <p className="text-2xl font-bold text-green-500">
                  {formatCurrency(summary?.available_capital || 0)}
                </p>
              </div>
              <Wallet className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Unrealized P&L</p>
                <p className={cn(
                  'text-2xl font-bold',
                  totalUnrealizedPnL >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {formatCurrency(totalUnrealizedPnL)}
                </p>
              </div>
              {totalUnrealizedPnL >= 0 ? (
                <TrendingUp className="h-8 w-8 text-green-500" />
              ) : (
                <TrendingDown className="h-8 w-8 text-red-500" />
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Exchange Balances */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Exchange Balances</CardTitle>
              <CardDescription>Capital distribution across connected exchanges</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetchBalances()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : balances.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No exchange balances found
            </div>
          ) : (
            <div className="space-y-6">
              {/* Distribution Bar */}
              <div className="space-y-2">
                <div className="flex h-4 rounded-full overflow-hidden">
                  {balances.map((balance) => {
                    const percentage = (balance.total_equity / totalValue) * 100;
                    const color = EXCHANGE_COLORS[balance.exchange.toLowerCase()] || EXCHANGE_COLORS.default;
                    return (
                      <div
                        key={balance.exchange}
                        className={cn('h-full', color)}
                        style={{ width: `${percentage}%` }}
                        title={`${balance.exchange}: ${formatPercent(percentage, 1)}`}
                      />
                    );
                  })}
                </div>
                <div className="flex flex-wrap gap-4 justify-center">
                  {balances.map((balance) => {
                    const color = EXCHANGE_COLORS[balance.exchange.toLowerCase()] || EXCHANGE_COLORS.default;
                    return (
                      <div key={balance.exchange} className="flex items-center gap-2">
                        <div className={cn('h-3 w-3 rounded', color)} />
                        <span className="text-sm text-muted-foreground capitalize">
                          {balance.exchange}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Exchange Details Table */}
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b text-left text-sm text-muted-foreground">
                      <th className="pb-3 font-medium">Exchange</th>
                      <th className="pb-3 font-medium text-right">Total Equity</th>
                      <th className="pb-3 font-medium text-right">Available</th>
                      <th className="pb-3 font-medium text-right">In Use</th>
                      <th className="pb-3 font-medium text-right">Unrealized P&L</th>
                      <th className="pb-3 font-medium text-right">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balances.map((balance) => {
                      const sharePercent = (balance.total_equity / totalValue) * 100;
                      const utilizationPercent = (balance.margin_used / balance.total_equity) * 100;

                      return (
                        <tr key={balance.exchange} className="border-b">
                          <td className="py-4">
                            <div className="flex items-center gap-2">
                              <div
                                className={cn(
                                  'h-2 w-2 rounded-full',
                                  EXCHANGE_COLORS[balance.exchange.toLowerCase()] || EXCHANGE_COLORS.default
                                )}
                              />
                              <span className="font-medium capitalize">{balance.exchange}</span>
                            </div>
                          </td>
                          <td className="py-4 text-right font-medium">
                            {formatCurrency(balance.total_equity)}
                          </td>
                          <td className="py-4 text-right text-green-500">
                            {formatCurrency(balance.available_balance)}
                          </td>
                          <td className="py-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <span>{formatCurrency(balance.margin_used)}</span>
                              <Badge variant="outline" className="text-xs">
                                {formatPercent(utilizationPercent, 0)}
                              </Badge>
                            </div>
                          </td>
                          <td className={cn(
                            'py-4 text-right',
                            balance.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'
                          )}>
                            {formatCurrency(balance.unrealized_pnl)}
                          </td>
                          <td className="py-4 text-right">
                            <Badge variant="secondary">
                              {formatPercent(sharePercent, 1)}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
