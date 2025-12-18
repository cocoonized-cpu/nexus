'use client';

import { useEffect, useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  RefreshCw,
  Search,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Filter,
  LineChart,
} from 'lucide-react';
import { getFundingRatesMatrixWithSource, getExchanges } from '@/lib/api';
import { cn } from '@/lib/utils';
import { DataSourceToggle, DataSource } from '@/components/funding-rates/data-source-toggle';

interface Exchange {
  slug: string;
  name: string;
  has_credentials?: boolean;
  enabled?: boolean;
}

interface FundingRow {
  ticker: string;
  symbol: string;
  rates: Record<string, number>;
  max_spread: number;
}

interface MatrixData {
  exchanges: Exchange[];
  rows: FundingRow[];
}

type SortKey = 'ticker' | 'max_spread';
type SortDir = 'asc' | 'desc';

const ITEMS_PER_PAGE = 30;

function formatRate(rate: number | undefined): string {
  if (rate === undefined || rate === null) return '-';
  return `${rate >= 0 ? '' : ''}${rate.toFixed(4)}%`;
}

function getRateColor(rate: number | undefined): string {
  if (rate === undefined || rate === null) return 'text-muted-foreground';
  if (rate > 0.01) return 'text-green-500 font-medium';
  if (rate > 0) return 'text-green-400';
  if (rate < -0.01) return 'text-red-500 font-medium';
  if (rate < 0) return 'text-red-400';
  return 'text-muted-foreground';
}

function getRateBgColor(rate: number | undefined): string {
  if (rate === undefined || rate === null) return '';
  if (rate > 0.05) return 'bg-green-500/20';
  if (rate > 0.02) return 'bg-green-500/10';
  if (rate < -0.05) return 'bg-red-500/20';
  if (rate < -0.02) return 'bg-red-500/10';
  return '';
}

export default function FundingRatesPage() {
  const [data, setData] = useState<MatrixData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('max_spread');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [selectedExchanges, setSelectedExchanges] = useState<Set<string>>(new Set());
  const [dataSource, setDataSource] = useState<DataSource>('exchanges');
  const [showConnectedOnly, setShowConnectedOnly] = useState(false);

  // Fetch connected exchanges
  const { data: exchangesData } = useQuery({
    queryKey: ['exchanges'],
    queryFn: () => getExchanges() as Promise<{ data?: Exchange[] }>,
  });

  // Normalize exchange slug to match funding rates matrix format
  // Config API returns "binance_futures" but funding matrix uses "binance"
  const normalizeSlug = (slug: string): string => {
    return slug
      .replace('_futures', '')
      .replace('_perp', '')
      .replace('ex_futures', 'x')  // okex_futures -> okx
      .toLowerCase();
  };

  const connectedExchanges = useMemo(() => {
    return (exchangesData?.data || [])
      .filter(e => e.has_credentials && e.enabled)
      .map(e => ({ ...e, slug: normalizeSlug(e.slug) }));
  }, [exchangesData?.data]);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        // Pass data source to filter funding rates by source
        const response = await getFundingRatesMatrixWithSource(dataSource);
        const matrixData = (response as { data: MatrixData }).data;
        setData(matrixData);
        // Initialize with all exchanges selected
        if (matrixData?.exchanges && selectedExchanges.size === 0) {
          setSelectedExchanges(new Set(matrixData.exchanges.map(e => e.slug)));
        }
        setLastUpdated(new Date());
      } catch (error) {
        console.error('Failed to fetch funding rates:', error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    const interval = setInterval(fetchData, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [dataSource]); // Re-fetch when data source changes

  // Filter exchanges based on selection and connected filter
  const filteredExchanges = useMemo(() => {
    if (!data?.exchanges) return [];
    let exchanges = data.exchanges;

    // Filter by connected exchanges if enabled
    if (showConnectedOnly && connectedExchanges.length > 0) {
      const connectedSlugs = new Set(connectedExchanges.map(e => e.slug));
      exchanges = exchanges.filter(e => connectedSlugs.has(e.slug));
    }

    // Filter by selected exchanges
    if (selectedExchanges.size > 0) {
      exchanges = exchanges.filter(e => selectedExchanges.has(e.slug));
    }

    return exchanges;
  }, [data?.exchanges, selectedExchanges, showConnectedOnly, connectedExchanges]);

  const toggleExchange = (slug: string) => {
    const newSet = new Set(selectedExchanges);
    if (newSet.has(slug)) {
      newSet.delete(slug);
    } else {
      newSet.add(slug);
    }
    setSelectedExchanges(newSet);
  };

  const selectAllExchanges = () => {
    if (data?.exchanges) {
      setSelectedExchanges(new Set(data.exchanges.map(e => e.slug)));
    }
  };

  const clearExchangeSelection = () => {
    setSelectedExchanges(new Set());
  };

  const filteredAndSortedRows = useMemo(() => {
    if (!data?.rows) return [];

    let filtered = data.rows;

    // Filter by search term
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (row) =>
          row.ticker.toLowerCase().includes(term) ||
          row.symbol.toLowerCase().includes(term)
      );
    }

    // Filter rows to only show coins that have rates from visible exchanges
    // This ensures that when "Show Connected Only" is checked, we also filter rows
    if (filteredExchanges.length > 0 && filteredExchanges.length < (data?.exchanges?.length || 0)) {
      const visibleExchangeSlugs = new Set(filteredExchanges.map(e => e.slug));
      filtered = filtered.filter((row) => {
        // Check if this row has at least one rate from a visible exchange
        return Object.keys(row.rates).some(slug => visibleExchangeSlugs.has(slug));
      });
    }

    // Sort
    return [...filtered].sort((a, b) => {
      let comparison = 0;
      if (sortKey === 'ticker') {
        comparison = a.ticker.localeCompare(b.ticker);
      } else if (sortKey === 'max_spread') {
        comparison = a.max_spread - b.max_spread;
      }
      return sortDir === 'asc' ? comparison : -comparison;
    });
  }, [data?.rows, data?.exchanges?.length, searchTerm, sortKey, sortDir, filteredExchanges]);

  const totalPages = Math.ceil(filteredAndSortedRows.length / ITEMS_PER_PAGE);
  const paginatedRows = filteredAndSortedRows.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir(key === 'max_spread' ? 'desc' : 'asc');
    }
  };

  // Calculate stats
  const stats = useMemo(() => {
    if (!data?.rows) return { totalCoins: 0, highestSpread: 0, avgSpread: 0 };
    const spreads = data.rows.map((r) => r.max_spread);
    return {
      totalCoins: data.rows.length,
      highestSpread: Math.max(...spreads, 0),
      avgSpread: spreads.length > 0 ? spreads.reduce((a, b) => a + b, 0) / spreads.length : 0,
    };
  }, [data?.rows]);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <LineChart className="h-8 w-8" />
              Funding Rates
            </h1>
            <p className="text-muted-foreground">
              Live funding rates across all exchanges
            </p>
          </div>
          <div className="flex items-center gap-4">
            {lastUpdated && (
              <span className="text-sm text-muted-foreground">
                Updated: {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setLoading(true)}
            >
              <RefreshCw className={cn('h-4 w-4 mr-2', loading && 'animate-spin')} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Data Source Toggle */}
        <Card>
          <CardContent className="py-4">
            <DataSourceToggle
              value={dataSource}
              onChange={setDataSource}
              showConnectedOnly={showConnectedOnly}
              onShowConnectedOnlyChange={setShowConnectedOnly}
              connectedExchangeCount={connectedExchanges.length}
              totalExchangeCount={data?.exchanges?.length || 0}
            />
          </CardContent>
        </Card>

        {/* Stats */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Total Coins</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalCoins}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Highest Spread</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-500">
                {stats.highestSpread.toFixed(4)}%
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Average Spread</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.avgSpread.toFixed(4)}%</div>
            </CardContent>
          </Card>
        </div>

        {/* Search and Filters */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search coins..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="pl-9"
            />
          </div>

          {/* Exchange Filter Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="h-10">
                <Filter className="h-4 w-4 mr-2" />
                Exchanges ({selectedExchanges.size}/{data?.exchanges?.length || 0})
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <div className="flex gap-2 px-2 py-1.5">
                <Button variant="ghost" size="sm" onClick={selectAllExchanges} className="flex-1 h-8">
                  Select All
                </Button>
                <Button variant="ghost" size="sm" onClick={clearExchangeSelection} className="flex-1 h-8">
                  Clear
                </Button>
              </div>
              <DropdownMenuSeparator />
              {data?.exchanges?.map((exchange) => (
                <DropdownMenuCheckboxItem
                  key={exchange.slug}
                  checked={selectedExchanges.has(exchange.slug)}
                  onCheckedChange={() => toggleExchange(exchange.slug)}
                >
                  {exchange.name}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Badge variant="outline" className="h-10 px-4">
            {filteredAndSortedRows.length} coins
          </Badge>
        </div>

        {/* Funding Rates Matrix */}
        <Card>
          <CardHeader>
            <CardTitle>Funding Rates Matrix</CardTitle>
            <CardDescription>
              Coins (rows) x Exchanges (columns) - rates shown as % per funding interval
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card z-10">
                  <tr className="border-b">
                    <th
                      className="text-left py-3 px-4 font-medium cursor-pointer hover:bg-muted/50 sticky left-0 bg-card z-20"
                      onClick={() => toggleSort('ticker')}
                    >
                      <div className="flex items-center gap-1">
                        Coins
                        <ArrowUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th
                      className="text-right py-3 px-4 font-medium cursor-pointer hover:bg-muted/50 min-w-[100px]"
                      onClick={() => toggleSort('max_spread')}
                    >
                      <div className="flex items-center justify-end gap-1">
                        Max Spread
                        <ArrowUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    {filteredExchanges.map((exchange) => (
                      <th
                        key={exchange.slug}
                        className="text-center py-3 px-2 font-medium min-w-[80px]"
                      >
                        <div className="truncate" title={exchange.name}>
                          {exchange.name.replace(' (Futures)', '').replace(' Futures', '')}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedRows.map((row) => (
                    <tr key={row.ticker} className="border-b hover:bg-muted/50">
                      <td className="py-2 px-4 sticky left-0 bg-card z-10">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{row.ticker}</span>
                        </div>
                      </td>
                      <td className="text-right py-2 px-4">
                        <span className={cn(
                          'font-mono',
                          row.max_spread > 0.1 ? 'text-green-500 font-bold' :
                          row.max_spread > 0.05 ? 'text-green-400' :
                          'text-muted-foreground'
                        )}>
                          {row.max_spread.toFixed(4)}%
                        </span>
                      </td>
                      {filteredExchanges.map((exchange) => {
                        const rate = row.rates[exchange.slug];
                        return (
                          <td
                            key={exchange.slug}
                            className={cn(
                              'text-center py-2 px-2 font-mono text-xs',
                              getRateColor(rate),
                              getRateBgColor(rate)
                            )}
                          >
                            {formatRate(rate)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>

              {paginatedRows.length === 0 && (
                <div className="py-12 text-center text-muted-foreground">
                  {loading ? (
                    <div className="flex items-center justify-center gap-2">
                      <RefreshCw className="h-5 w-5 animate-spin" />
                      Loading funding rates...
                    </div>
                  ) : searchTerm ? (
                    `No coins found matching "${searchTerm}"`
                  ) : (
                    'No funding rate data available. Data will appear once the data collector service is running.'
                  )}
                </div>
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t">
                <div className="text-sm text-muted-foreground">
                  Showing {(currentPage - 1) * ITEMS_PER_PAGE + 1} to{' '}
                  {Math.min(currentPage * ITEMS_PER_PAGE, filteredAndSortedRows.length)} of{' '}
                  {filteredAndSortedRows.length} coins
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="p-2 rounded hover:bg-muted disabled:opacity-50"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <div className="flex items-center gap-1">
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      let pageNum;
                      if (totalPages <= 5) {
                        pageNum = i + 1;
                      } else if (currentPage <= 3) {
                        pageNum = i + 1;
                      } else if (currentPage >= totalPages - 2) {
                        pageNum = totalPages - 4 + i;
                      } else {
                        pageNum = currentPage - 2 + i;
                      }
                      return (
                        <button
                          key={pageNum}
                          onClick={() => setCurrentPage(pageNum)}
                          className={cn(
                            'w-8 h-8 rounded text-sm',
                            currentPage === pageNum
                              ? 'bg-primary text-primary-foreground'
                              : 'hover:bg-muted'
                          )}
                        >
                          {pageNum}
                        </button>
                      );
                    })}
                  </div>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="p-2 rounded hover:bg-muted disabled:opacity-50"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Legend */}
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center justify-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded bg-green-500/20" />
                <span>Strong Positive (&gt;0.02%)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-green-400">0.0100%</span>
                <span>Positive</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">-</span>
                <span>No Data</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-red-400">-0.0100%</span>
                <span>Negative</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded bg-red-500/20" />
                <span>Strong Negative (&lt;-0.02%)</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
