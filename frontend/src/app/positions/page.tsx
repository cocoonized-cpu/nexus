'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Loader2,
  DollarSign,
  Activity,
  Search,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Filter,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getExchangePositions, getTradeHistory } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ConsolidatedPositionsTable } from '@/components/positions/consolidated-positions-table';
import { ReconciliationStatus } from '@/components/positions/reconciliation-status';

interface ExchangePosition {
  id: string;
  exchange: string;
  symbol: string;
  side: string;
  size: number;
  notional_usd: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  leverage: number;
  liquidation_price?: number;
  margin_mode: string;
  updated_at?: string;
}

interface Trade {
  id: string;
  exchange_order_id: string;
  exchange: string;
  symbol: string;
  side: string;
  order_type: string;
  price: number;
  amount: number;
  filled: number;
  fee?: number;
  fee_currency?: string;
  status: string;
  executed_at?: string;
  created_at?: string;
}

type SortField = 'time' | 'exchange' | 'symbol' | 'side' | 'price' | 'amount' | 'value' | 'fee' | 'pnl' | 'notional';
type SortDirection = 'asc' | 'desc';

export default function PositionsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('nexus');

  // Filters
  const [exchangeFilter, setExchangeFilter] = useState<string>('all');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [sideFilter, setSideFilter] = useState<string>('all');

  // Sorting
  const [sortField, setSortField] = useState<SortField>('time');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Fetch exchange positions (open positions from exchanges)
  const { data: exchangePositionsData, isLoading: isLoadingExchange, refetch: refetchExchange } = useQuery({
    queryKey: ['exchange-positions'],
    queryFn: () => getExchangePositions() as Promise<{ data?: ExchangePosition[], meta?: { total_notional_usd?: number, total_unrealized_pnl?: number } }>,
    refetchInterval: 30000,
  });

  // Fetch trade history (closed trades from all exchanges) - increased limit
  const { data: tradeHistoryData, isLoading: isLoadingTrades, refetch: refetchTrades } = useQuery({
    queryKey: ['trade-history'],
    queryFn: () => getTradeHistory(undefined, undefined, 500) as Promise<{ data?: Trade[], meta?: { total_volume_usd?: number, total_fees?: number } }>,
    refetchInterval: 30000,
  });

  const exchangePositions = exchangePositionsData?.data || [];
  const trades = tradeHistoryData?.data || [];

  // Get unique exchanges for filter dropdown
  const availableExchanges = useMemo(() => {
    const positionExchanges = exchangePositions.map(p => p.exchange);
    const tradeExchanges = trades.map(t => t.exchange);
    const allExchanges = [...positionExchanges, ...tradeExchanges];
    const uniqueExchanges = allExchanges.filter((ex, idx) => allExchanges.indexOf(ex) === idx);
    return uniqueExchanges.sort();
  }, [exchangePositions, trades]);

  // Refresh data from database
  const handleRefresh = () => {
    refetchExchange();
    refetchTrades();
  };

  const isRefreshing = isLoadingExchange || isLoadingTrades;

  // Filter and sort positions
  const filteredPositions = useMemo(() => {
    let result = [...exchangePositions];

    if (exchangeFilter !== 'all') {
      result = result.filter(p => p.exchange === exchangeFilter);
    }
    if (symbolFilter) {
      result = result.filter(p => p.symbol.toLowerCase().includes(symbolFilter.toLowerCase()));
    }
    if (sideFilter !== 'all') {
      result = result.filter(p => p.side === sideFilter);
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'exchange':
          comparison = a.exchange.localeCompare(b.exchange);
          break;
        case 'symbol':
          comparison = a.symbol.localeCompare(b.symbol);
          break;
        case 'side':
          comparison = a.side.localeCompare(b.side);
          break;
        case 'notional':
          comparison = a.notional_usd - b.notional_usd;
          break;
        case 'pnl':
          comparison = a.unrealized_pnl - b.unrealized_pnl;
          break;
        default:
          comparison = 0;
      }
      return sortDirection === 'desc' ? -comparison : comparison;
    });

    return result;
  }, [exchangePositions, exchangeFilter, symbolFilter, sideFilter, sortField, sortDirection]);

  // Filter and sort trades
  const filteredTrades = useMemo(() => {
    let result = [...trades];

    if (exchangeFilter !== 'all') {
      result = result.filter(t => t.exchange === exchangeFilter);
    }
    if (symbolFilter) {
      result = result.filter(t => t.symbol.toLowerCase().includes(symbolFilter.toLowerCase()));
    }
    if (sideFilter !== 'all') {
      result = result.filter(t => t.side === sideFilter);
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      const priceA = parseFloat(String(a.price || 0));
      const priceB = parseFloat(String(b.price || 0));
      const filledA = parseFloat(String(a.filled || a.amount || 0));
      const filledB = parseFloat(String(b.filled || b.amount || 0));
      const feeA = parseFloat(String(a.fee || 0));
      const feeB = parseFloat(String(b.fee || 0));
      const timeA = a.executed_at ? new Date(a.executed_at).getTime() : a.created_at ? new Date(a.created_at).getTime() : 0;
      const timeB = b.executed_at ? new Date(b.executed_at).getTime() : b.created_at ? new Date(b.created_at).getTime() : 0;

      switch (sortField) {
        case 'time':
          comparison = timeA - timeB;
          break;
        case 'exchange':
          comparison = a.exchange.localeCompare(b.exchange);
          break;
        case 'symbol':
          comparison = a.symbol.localeCompare(b.symbol);
          break;
        case 'side':
          comparison = a.side.localeCompare(b.side);
          break;
        case 'price':
          comparison = priceA - priceB;
          break;
        case 'amount':
          comparison = filledA - filledB;
          break;
        case 'value':
          comparison = (filledA * priceA) - (filledB * priceB);
          break;
        case 'fee':
          comparison = feeA - feeB;
          break;
        default:
          comparison = timeA - timeB;
      }
      return sortDirection === 'desc' ? -comparison : comparison;
    });

    return result;
  }, [trades, exchangeFilter, symbolFilter, sideFilter, sortField, sortDirection]);

  // Calculate stats
  const stats = useMemo(() => {
    const openNotional = exchangePositions.reduce((sum, p) => sum + (p.notional_usd || 0), 0);
    const openPnL = exchangePositions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0);

    // Calculate trade volume and fees
    const tradeVolume = trades.reduce((sum, t) => {
      const price = parseFloat(String(t.price || 0));
      const filled = parseFloat(String(t.filled || t.amount || 0));
      return sum + (price * filled);
    }, 0);
    const totalFees = trades.reduce((sum, t) => sum + parseFloat(String(t.fee || 0)), 0);

    // Count by exchange
    const positionsByExchange = exchangePositions.reduce((acc, p) => {
      acc[p.exchange] = (acc[p.exchange] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const tradesByExchange = trades.reduce((acc, t) => {
      acc[t.exchange] = (acc[t.exchange] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      openPositions: exchangePositions.length,
      openNotional,
      openPnL,
      totalTrades: trades.length,
      tradeVolume,
      totalFees,
      positionsByExchange,
      tradesByExchange,
    };
  }, [exchangePositions, trades]);

  // Sort header component
  const SortHeader = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <th
      className="pb-3 font-medium cursor-pointer hover:text-foreground transition-colors"
      onClick={() => {
        if (sortField === field) {
          setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
        } else {
          setSortField(field);
          setSortDirection('desc');
        }
      }}
    >
      <div className="flex items-center gap-1">
        {children}
        {sortField === field ? (
          sortDirection === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </div>
    </th>
  );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Wallet className="h-8 w-8" />
              Positions & Trades
            </h1>
            <p className="text-muted-foreground">
              View all open positions and trade history across exchanges
            </p>
          </div>
          <Button variant="outline" onClick={handleRefresh} disabled={isRefreshing}>
            <RefreshCw className={cn('h-4 w-4 mr-2', isRefreshing && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        {/* Summary Stats */}
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Open Positions</p>
                  <p className="text-2xl font-bold">{stats.openPositions}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {Object.entries(stats.positionsByExchange).map(([ex, count]) => (
                      <span key={ex} className="mr-2">{ex.replace('_futures', '')}: {count}</span>
                    ))}
                  </p>
                </div>
                <Activity className="h-8 w-8 text-green-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Open Notional</p>
                  <p className="text-2xl font-bold">{formatCurrency(stats.openNotional)}</p>
                </div>
                <DollarSign className="h-8 w-8 text-muted-foreground" />
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
                    stats.openPnL >= 0 ? 'text-green-500' : 'text-red-500'
                  )}>
                    {formatCurrency(stats.openPnL)}
                  </p>
                </div>
                {stats.openPnL >= 0 ? (
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
                  <p className="text-sm font-medium text-muted-foreground">Total Trades</p>
                  <p className="text-2xl font-bold">{stats.totalTrades}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {Object.entries(stats.tradesByExchange).map(([ex, count]) => (
                      <span key={ex} className="mr-2">{ex.replace('_futures', '')}: {count}</span>
                    ))}
                  </p>
                </div>
                <Activity className="h-8 w-8 text-blue-500" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Filters:</span>
              </div>

              <Select value={exchangeFilter} onValueChange={setExchangeFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All Exchanges" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Exchanges</SelectItem>
                  {availableExchanges.map(ex => (
                    <SelectItem key={ex} value={ex}>
                      {ex.replace('_futures', '')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={sideFilter} onValueChange={setSideFilter}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="All Sides" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sides</SelectItem>
                  <SelectItem value="long">Long</SelectItem>
                  <SelectItem value="short">Short</SelectItem>
                  <SelectItem value="buy">Buy</SelectItem>
                  <SelectItem value="sell">Sell</SelectItem>
                </SelectContent>
              </Select>

              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search symbol..."
                  value={symbolFilter}
                  onChange={(e) => setSymbolFilter(e.target.value)}
                  className="pl-9 w-[200px]"
                />
              </div>

              {(exchangeFilter !== 'all' || sideFilter !== 'all' || symbolFilter) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setExchangeFilter('all');
                    setSideFilter('all');
                    setSymbolFilter('');
                  }}
                >
                  Clear Filters
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Tabs for NEXUS Positions, Exchange Positions, and Trade History */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3 max-w-xl">
            <TabsTrigger value="nexus">
              NEXUS Positions
            </TabsTrigger>
            <TabsTrigger value="open">
              Exchange ({filteredPositions.length})
            </TabsTrigger>
            <TabsTrigger value="history">
              Trade History ({filteredTrades.length})
            </TabsTrigger>
          </TabsList>

          {/* NEXUS Consolidated Positions Tab */}
          <TabsContent value="nexus">
            <div className="space-y-6">
              <ConsolidatedPositionsTable />
              <ReconciliationStatus />
            </div>
          </TabsContent>

          {/* Open Positions Tab */}
          <TabsContent value="open">
            <Card>
              <CardHeader>
                <CardTitle>Open Positions</CardTitle>
                <CardDescription>
                  Live positions from connected exchanges
                </CardDescription>
              </CardHeader>
              <CardContent>
                {isLoadingExchange ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : filteredPositions.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <p>No open positions</p>
                    <p className="text-sm mt-2">
                      {exchangePositions.length > 0
                        ? 'Try adjusting your filters'
                        : 'Positions are synced automatically from exchanges'}
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b text-left text-sm text-muted-foreground">
                          <SortHeader field="symbol">Symbol</SortHeader>
                          <SortHeader field="exchange">Exchange</SortHeader>
                          <SortHeader field="side">Side</SortHeader>
                          <th className="pb-3 font-medium text-right">Size</th>
                          <SortHeader field="notional">
                            <span className="text-right">Notional</span>
                          </SortHeader>
                          <th className="pb-3 font-medium text-right">Entry</th>
                          <th className="pb-3 font-medium text-right">Mark</th>
                          <SortHeader field="pnl">
                            <span className="text-right">P&L</span>
                          </SortHeader>
                          <th className="pb-3 font-medium text-right">Leverage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPositions.map((position) => {
                          const size = parseFloat(String(position.size || 0));
                          const entryPrice = parseFloat(String(position.entry_price || 0));
                          const markPrice = parseFloat(String(position.mark_price || 0));
                          const notional = parseFloat(String(position.notional_usd || 0));
                          const pnl = parseFloat(String(position.unrealized_pnl || 0));

                          return (
                            <tr key={position.id} className="border-b hover:bg-muted/50">
                              <td className="py-4">
                                <span className="font-medium">{position.symbol}</span>
                              </td>
                              <td className="py-4">
                                <Badge variant="outline" className="capitalize">
                                  {position.exchange.replace('_futures', '')}
                                </Badge>
                              </td>
                              <td className="py-4">
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    position.side === 'long'
                                      ? 'text-green-500 bg-green-500/10'
                                      : 'text-red-500 bg-red-500/10'
                                  )}
                                >
                                  {position.side}
                                </Badge>
                              </td>
                              <td className="py-4 text-right font-mono">
                                {size.toFixed(4)}
                              </td>
                              <td className="py-4 text-right">
                                {formatCurrency(notional)}
                              </td>
                              <td className="py-4 text-right font-mono">
                                ${entryPrice.toFixed(2)}
                              </td>
                              <td className="py-4 text-right font-mono">
                                ${markPrice.toFixed(2)}
                              </td>
                              <td className={cn(
                                'py-4 text-right font-medium',
                                pnl >= 0 ? 'text-green-500' : 'text-red-500'
                              )}>
                                {formatCurrency(pnl)}
                              </td>
                              <td className="py-4 text-right">
                                <Badge variant="secondary">
                                  {position.leverage}x
                                </Badge>
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
          </TabsContent>

          {/* Trade History Tab */}
          <TabsContent value="history">
            <Card>
              <CardHeader>
                <CardTitle>Trade History</CardTitle>
                <CardDescription>
                  Completed trades from all exchanges
                  {stats.tradeVolume > 0 && (
                    <span className="ml-2">
                      • Volume: {formatCurrency(stats.tradeVolume)}
                    </span>
                  )}
                  {stats.totalFees > 0 && (
                    <span className="ml-2">
                      • Fees: {formatCurrency(stats.totalFees)}
                    </span>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {isLoadingTrades ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : filteredTrades.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <p>No trade history</p>
                    <p className="text-sm mt-2">
                      {trades.length > 0
                        ? 'Try adjusting your filters'
                        : 'Trades will appear after syncing from exchanges'}
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b text-left text-sm text-muted-foreground">
                          <SortHeader field="time">Time</SortHeader>
                          <SortHeader field="exchange">Exchange</SortHeader>
                          <SortHeader field="symbol">Symbol</SortHeader>
                          <SortHeader field="side">Side</SortHeader>
                          <th className="pb-3 font-medium">Type</th>
                          <SortHeader field="price">
                            <span className="text-right">Price</span>
                          </SortHeader>
                          <SortHeader field="amount">
                            <span className="text-right">Amount</span>
                          </SortHeader>
                          <SortHeader field="value">
                            <span className="text-right">Value</span>
                          </SortHeader>
                          <SortHeader field="fee">
                            <span className="text-right">Fee</span>
                          </SortHeader>
                          <th className="pb-3 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredTrades.map((trade) => {
                          const price = parseFloat(String(trade.price || 0));
                          const filled = parseFloat(String(trade.filled || trade.amount || 0));
                          const fee = parseFloat(String(trade.fee || 0));
                          const value = filled * price;
                          const execTime = trade.executed_at ? new Date(trade.executed_at) : trade.created_at ? new Date(trade.created_at) : null;

                          return (
                            <tr key={trade.id} className="border-b hover:bg-muted/50">
                              <td className="py-4 text-sm text-muted-foreground">
                                {execTime ? (
                                  <div>
                                    <div>{execTime.toLocaleDateString()}</div>
                                    <div className="text-xs">{execTime.toLocaleTimeString()}</div>
                                  </div>
                                ) : '-'}
                              </td>
                              <td className="py-4">
                                <Badge variant="outline" className="capitalize">
                                  {trade.exchange.replace('_futures', '')}
                                </Badge>
                              </td>
                              <td className="py-4">
                                <span className="font-medium">{trade.symbol}</span>
                              </td>
                              <td className="py-4">
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    trade.side === 'buy'
                                      ? 'text-green-500 bg-green-500/10'
                                      : 'text-red-500 bg-red-500/10'
                                  )}
                                >
                                  {trade.side}
                                </Badge>
                              </td>
                              <td className="py-4 text-sm text-muted-foreground capitalize">
                                {trade.order_type || 'market'}
                              </td>
                              <td className="py-4 text-right font-mono">
                                ${price.toFixed(2)}
                              </td>
                              <td className="py-4 text-right font-mono">
                                {filled.toFixed(4)}
                              </td>
                              <td className="py-4 text-right">
                                {formatCurrency(value)}
                              </td>
                              <td className="py-4 text-right text-sm text-muted-foreground">
                                {fee > 0 ? (
                                  <span>
                                    {fee.toFixed(4)} {trade.fee_currency || ''}
                                  </span>
                                ) : '-'}
                              </td>
                              <td className="py-4">
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    trade.status === 'closed'
                                      ? 'text-green-500 bg-green-500/10'
                                      : trade.status === 'canceled' || trade.status === 'cancelled'
                                      ? 'text-red-500 bg-red-500/10'
                                      : 'text-yellow-500 bg-yellow-500/10'
                                  )}
                                >
                                  {trade.status}
                                </Badge>
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
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
