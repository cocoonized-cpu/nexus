'use client';

import { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle, Search } from 'lucide-react';
import { getOpportunities, getPositions, executeOpportunity } from '@/lib/api';
import { formatPercent, formatCurrency, getScoreColor, cn } from '@/lib/utils';
import { useWebSocket } from '@/lib/websocket';
import { useToast } from '@/components/ui/use-toast';
import { CountdownCell } from '@/components/opportunities/countdown-cell';
import { ExecutionProgressModal } from '@/components/opportunities/execution-progress-modal';
import { BotActionCell, BotAction } from '@/components/opportunities/bot-action-cell';
import {
  SortableTableHeader,
  useSortState,
  useSortedData,
  SortConfig,
} from '@/components/opportunities/sortable-table-header';
import {
  TrendingUp,
  TrendingDown,
  Play,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ExternalLink,
  ArrowRightLeft,
  Zap,
} from 'lucide-react';
import Link from 'next/link';

// Sort key type for opportunities
type OpportunitySortKey = 'symbol' | 'spread' | 'net_apr' | 'uos_score' | 'expires' | 'long_exchange' | 'short_exchange' | 'status';

interface OpportunityLeg {
  exchange: string;
  funding_rate: number;
  market_type?: string;
}

interface UOSScores {
  return_score: number;
  risk_score: number;
  execution_score: number;
  timing_score: number;
  total: number;
  quality?: string;
}

interface Opportunity {
  id: string;
  symbol: string;
  base_asset: string;
  opportunity_type: string;
  status: string;
  primary_exchange: string;
  primary_rate: number;
  primary_side: string;
  hedge_exchange: string;
  hedge_rate: number;
  hedge_side: string;
  gross_funding_rate?: number;
  gross_apr?: number;
  net_apr?: number;
  uos_score: number;
  uos_score_direct?: number;
  scores?: UOSScores;
  uos_breakdown?: UOSScores;
  return_score?: number;
  risk_score?: number;
  execution_score?: number;
  timing_score?: number;
  confidence?: string;
  recommended_size_usd?: number;
  minimum_hold_periods?: number;
  detected_at: string;
  expires_at: string;
  long_leg?: OpportunityLeg;
  short_leg?: OpportunityLeg;
  funding_spread_pct?: number;
  estimated_net_apr?: number;
  bot_action?: BotAction;
}

// Helper to get UOS score from various sources
function getUOSScore(opp: Opportunity): number {
  return opp.scores?.total || opp.uos_score_direct || opp.uos_score || 0;
}

interface Position {
  id: string;
  symbol: string;
  status: string;
  opportunity_id?: string;
  health_status: string;
  total_capital_deployed: number;
  funding_received: number;
  opened_at: string;
}

const STATUS_STYLES: Record<string, { color: string; label: string }> = {
  detected: { color: 'bg-blue-500', label: 'Detected' },
  validated: { color: 'bg-cyan-500', label: 'Validated' },
  scored: { color: 'bg-purple-500', label: 'Scored' },
  allocated: { color: 'bg-yellow-500', label: 'Allocated' },
  executing: { color: 'bg-orange-500', label: 'Executing' },
  executed: { color: 'bg-green-500', label: 'Executed' },
  expired: { color: 'bg-gray-500', label: 'Expired' },
  rejected: { color: 'bg-red-500', label: 'Rejected' },
};

const CONFIDENCE_STYLES: Record<string, { color: string }> = {
  high: { color: 'text-green-500' },
  medium: { color: 'text-yellow-500' },
  low: { color: 'text-red-500' },
  exceptional: { color: 'text-green-500' },
  good: { color: 'text-green-400' },
  fair: { color: 'text-yellow-500' },
  poor: { color: 'text-red-500' },
};

export default function OpportunitiesPage() {
  const queryClient = useQueryClient();
  const { subscribe, lastMessage } = useWebSocket();
  const { toast } = useToast();
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [showExecuteDialog, setShowExecuteDialog] = useState(false);
  const [filter, setFilter] = useState<'all' | 'active' | 'executed'>('all');

  // Sort and filter state
  const [sortConfig, handleSort] = useSortState<OpportunitySortKey>('spread', 'desc');
  const [exchangeFilter, setExchangeFilter] = useState<string>('all');
  const [minUosScore, setMinUosScore] = useState<number>(0);
  const [symbolSearch, setSymbolSearch] = useState<string>('');

  // Queries
  const { data: opportunitiesData, isLoading, refetch } = useQuery({
    queryKey: ['opportunities'],
    queryFn: () => getOpportunities() as Promise<{ data?: Opportunity[] }>,
    refetchInterval: 10000,
  });

  const { data: positionsData } = useQuery({
    queryKey: ['positions'],
    queryFn: () => getPositions() as Promise<{ data?: Position[] }>,
    refetchInterval: 10000,
  });

  const opportunities: Opportunity[] = opportunitiesData?.data || [];
  const positions: Position[] = positionsData?.data || [];

  // Create a map of opportunity IDs to positions for quick lookup
  const opportunityToPosition = new Map<string, Position>();
  positions.forEach((pos) => {
    if (pos.opportunity_id) {
      opportunityToPosition.set(pos.opportunity_id, pos);
    }
  });

  // Subscribe to WebSocket
  useEffect(() => {
    subscribe('opportunities');
  }, [subscribe]);

  useEffect(() => {
    if (lastMessage?.channel === 'opportunities') {
      refetch();
    }
  }, [lastMessage, refetch]);

  // Execute handler for the progress modal
  const handleExecuteOpportunity = async (id: string) => {
    try {
      // Use recommended size or default to $100
      const capital_usd = selectedOpportunity?.recommended_size_usd || 100;
      const result = await executeOpportunity(id, { capital_usd }) as {
        success?: boolean;
        message?: string;
        data?: {
          position_id: string;
          primary: { exchange: string; side: string; order_id?: string };
          hedge: { exchange: string; side: string; order_id?: string };
        };
      };
      // Invalidate queries after successful execution
      queryClient.invalidateQueries({ queryKey: ['opportunities'] });
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      return {
        success: true,
        message: result.message || 'Position opened successfully',
        data: result.data,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Execution failed';
      return {
        success: false,
        error: errorMessage,
      };
    }
  };

  // Handle modal close
  const handleExecuteModalClose = () => {
    setShowExecuteDialog(false);
    setSelectedOpportunity(null);
  };

  // Get unique exchanges for filter dropdown
  const availableExchanges = useMemo(() => {
    const exchanges = new Set<string>();
    opportunities.forEach((opp) => {
      const longEx = opp.long_leg?.exchange || opp.primary_exchange;
      const shortEx = opp.short_leg?.exchange || opp.hedge_exchange;
      if (longEx) exchanges.add(longEx);
      if (shortEx) exchanges.add(shortEx);
    });
    return Array.from(exchanges).sort();
  }, [opportunities]);

  // Sort functions for opportunities
  const sortFunctions: Record<OpportunitySortKey, (a: Opportunity, b: Opportunity) => number> = useMemo(() => ({
    symbol: (a, b) => a.symbol.localeCompare(b.symbol),
    spread: (a, b) => (a.funding_spread_pct || a.gross_funding_rate || 0) - (b.funding_spread_pct || b.gross_funding_rate || 0),
    net_apr: (a, b) => (a.net_apr || a.estimated_net_apr || 0) - (b.net_apr || b.estimated_net_apr || 0),
    uos_score: (a, b) => getUOSScore(a) - getUOSScore(b),
    expires: (a, b) => new Date(a.expires_at).getTime() - new Date(b.expires_at).getTime(),
    long_exchange: (a, b) => (a.long_leg?.exchange || a.primary_exchange || '').localeCompare(b.long_leg?.exchange || b.primary_exchange || ''),
    short_exchange: (a, b) => (a.short_leg?.exchange || a.hedge_exchange || '').localeCompare(b.short_leg?.exchange || b.hedge_exchange || ''),
    status: (a, b) => a.status.localeCompare(b.status),
  }), []);

  // Filter opportunities
  const filteredOpportunities = useMemo(() => {
    return opportunities.filter((opp) => {
      // Status filter (tabs)
      if (filter === 'active') {
        if (!['detected', 'validated', 'scored', 'allocated', 'executing'].includes(opp.status)) return false;
      }
      if (filter === 'executed') {
        if (opp.status !== 'executed') return false;
      }

      // Exchange filter
      if (exchangeFilter !== 'all') {
        const longEx = opp.long_leg?.exchange || opp.primary_exchange;
        const shortEx = opp.short_leg?.exchange || opp.hedge_exchange;
        if (longEx !== exchangeFilter && shortEx !== exchangeFilter) return false;
      }

      // Min UOS score filter
      if (minUosScore > 0 && getUOSScore(opp) < minUosScore) return false;

      // Symbol search filter
      if (symbolSearch) {
        const search = symbolSearch.toLowerCase();
        if (!opp.symbol.toLowerCase().includes(search) && !opp.base_asset?.toLowerCase().includes(search)) {
          return false;
        }
      }

      return true;
    });
  }, [opportunities, filter, exchangeFilter, minUosScore, symbolSearch]);

  // Sort the filtered opportunities
  const sortedOpportunities = useSortedData(filteredOpportunities, sortConfig, sortFunctions);

  // Statistics
  const stats = {
    total: opportunities.length,
    active: opportunities.filter((o) => ['detected', 'validated', 'scored', 'allocated', 'executing', 'active'].includes(o.status)).length,
    executed: opportunities.filter((o) => o.status === 'executed').length,
    avgScore: opportunities.length > 0
      ? Math.round(opportunities.reduce((sum, o) => sum + getUOSScore(o), 0) / opportunities.length)
      : 0,
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Opportunities</h1>
            <p className="text-muted-foreground">Real-time arbitrage opportunity detection</p>
          </div>
          <Button onClick={() => refetch()} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>

        {/* Statistics Cards */}
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Detected</p>
                  <p className="text-2xl font-bold">{stats.total}</p>
                </div>
                <TrendingUp className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Active</p>
                  <p className="text-2xl font-bold text-blue-500">{stats.active}</p>
                </div>
                <Zap className="h-8 w-8 text-blue-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Executed</p>
                  <p className="text-2xl font-bold text-green-500">{stats.executed}</p>
                </div>
                <CheckCircle2 className="h-8 w-8 text-green-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Avg UOS Score</p>
                  <p className={`text-2xl font-bold ${getScoreColor(stats.avgScore)}`}>
                    {stats.avgScore}
                  </p>
                </div>
                <ArrowRightLeft className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Opportunities Table */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Detected Opportunities</CardTitle>
                <CardDescription>
                  Funding rate arbitrage opportunities across exchanges
                </CardDescription>
              </div>
              <Tabs value={filter} onValueChange={(v) => setFilter(v as 'all' | 'active' | 'executed')}>
                <TabsList>
                  <TabsTrigger value="all">All</TabsTrigger>
                  <TabsTrigger value="active">Active</TabsTrigger>
                  <TabsTrigger value="executed">Executed</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </CardHeader>
          <CardContent>
            {/* Filter Controls */}
            <div className="flex flex-wrap gap-4 mb-6 pb-4 border-b">
              {/* Symbol Search */}
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search symbol..."
                    value={symbolSearch}
                    onChange={(e) => setSymbolSearch(e.target.value)}
                    className="pl-9 w-48"
                  />
                </div>
              </div>

              {/* Exchange Filter */}
              <div className="flex items-center gap-2">
                <Label className="text-sm text-muted-foreground">Exchange:</Label>
                <Select value={exchangeFilter} onValueChange={setExchangeFilter}>
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Exchanges</SelectItem>
                    {availableExchanges.map((ex) => (
                      <SelectItem key={ex} value={ex}>
                        {ex}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Min UOS Score */}
              <div className="flex items-center gap-2">
                <Label className="text-sm text-muted-foreground">Min UOS:</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={minUosScore || ''}
                  onChange={(e) => setMinUosScore(parseInt(e.target.value) || 0)}
                  placeholder="0"
                  className="w-20"
                />
              </div>

              {/* Results count */}
              <div className="flex items-center ml-auto text-sm text-muted-foreground">
                Showing {sortedOpportunities.length} of {opportunities.length} opportunities
              </div>
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : sortedOpportunities.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No opportunities found
              </div>
            ) : (
              <div className="overflow-x-auto">
                <TooltipProvider>
                <table className="w-full">
                  <thead>
                    <tr className="border-b text-left text-sm text-muted-foreground">
                      <SortableTableHeader
                        label="Symbol"
                        sortKey="symbol"
                        currentSort={sortConfig}
                        onSort={handleSort}
                      />
                      <SortableTableHeader
                        label="Long Exchange"
                        sortKey="long_exchange"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="Exchange where you open a long position to earn positive funding rates"
                      />
                      <SortableTableHeader
                        label="Short Exchange"
                        sortKey="short_exchange"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="Exchange where you open a short position as a hedge against price movement"
                      />
                      <SortableTableHeader
                        label="Spread"
                        sortKey="spread"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="The funding rate differential between long and short exchanges. Higher spreads indicate more profitable opportunities."
                      />
                      <SortableTableHeader
                        label="Net APR"
                        sortKey="net_apr"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="Annualized return after fees and slippage. This is the expected profit rate if the position is held for a full year."
                      />
                      <SortableTableHeader
                        label="UOS Score"
                        sortKey="uos_score"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="Unified Opportunity Score (0-100). Combines return potential, risk metrics, execution feasibility, and timing factors. Higher is better."
                      />
                      <SortableTableHeader
                        label="Status"
                        sortKey="status"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="Current status of the opportunity in the execution pipeline"
                      />
                      <SortableTableHeader
                        label="Expires"
                        sortKey="expires"
                        currentSort={sortConfig}
                        onSort={handleSort}
                        tooltip="Time until this opportunity expires. Opportunities are recalculated each funding cycle."
                      />
                      <th className="pb-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedOpportunities.map((opp) => {
                      const statusStyle = STATUS_STYLES[opp.status] || STATUS_STYLES.detected;
                      const linkedPosition = opportunityToPosition.get(opp.id);

                      // Extract exchange names from nested structure or flat fields
                      const longExchange = opp.long_leg?.exchange || opp.primary_exchange || 'N/A';
                      const shortExchange = opp.short_leg?.exchange || opp.hedge_exchange || 'N/A';
                      const longRate = opp.long_leg?.funding_rate || opp.primary_rate || 0;
                      const shortRate = opp.short_leg?.funding_rate || opp.hedge_rate || 0;

                      return (
                        <tr
                          key={opp.id}
                          className={cn(
                            'border-b hover:bg-muted/50',
                            opp.status === 'executing' && 'bg-orange-500/5'
                          )}
                        >
                          <td className="py-4">
                            <Link
                              href={`/funding-rates?symbol=${opp.symbol}`}
                              className="hover:underline"
                            >
                              <div className="font-medium text-primary">{opp.symbol}</div>
                              <div className="text-xs text-muted-foreground">{opp.base_asset}</div>
                            </Link>
                          </td>
                          <td className="py-4">
                            <div className="flex items-center gap-1">
                              <TrendingUp className="h-3 w-3 text-green-500" />
                              {longExchange}
                            </div>
                            <div className="text-xs text-green-500">
                              {formatPercent(longRate * 100, 4)}
                            </div>
                          </td>
                          <td className="py-4">
                            <div className="flex items-center gap-1">
                              <TrendingDown className="h-3 w-3 text-red-500" />
                              {shortExchange}
                            </div>
                            <div className="text-xs text-red-500">
                              {formatPercent(shortRate * 100, 4)}
                            </div>
                          </td>
                          <td className="py-4">
                            <span className="font-medium">
                              {formatPercent(opp.funding_spread_pct || opp.gross_funding_rate || 0, 4)}
                            </span>
                          </td>
                          <td className="py-4">
                            <span className="font-medium text-green-500">
                              {formatPercent(opp.net_apr || opp.estimated_net_apr || 0, 1)}
                            </span>
                          </td>
                          <td className="py-4">
                            <div className="flex items-center gap-2">
                              <span className={`font-bold ${getScoreColor(getUOSScore(opp))}`}>
                                {getUOSScore(opp)}
                              </span>
                              {(opp.scores?.quality || opp.confidence) && (
                                <span className={`text-xs ${CONFIDENCE_STYLES[opp.scores?.quality || opp.confidence || 'medium']?.color || ''}`}>
                                  {opp.scores?.quality || opp.confidence}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-4">
                            <div className="flex items-center gap-2">
                              <Badge
                                variant="outline"
                                className={`${statusStyle.color} text-white border-none`}
                              >
                                {statusStyle.label}
                              </Badge>
                              {linkedPosition && (
                                <Badge variant="secondary" className="text-xs">
                                  In Position
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="py-4">
                            <CountdownCell expiresAt={opp.expires_at} />
                          </td>
                          <td className="py-4">
                            <div className="flex gap-2">
                              {!linkedPosition && opp.status !== 'executed' && opp.status !== 'expired' && (
                                <Button
                                  size="sm"
                                  onClick={() => {
                                    setSelectedOpportunity(opp);
                                    setShowExecuteDialog(true);
                                  }}
                                >
                                  <Play className="h-3 w-3 mr-1" />
                                  Execute
                                </Button>
                              )}
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setSelectedOpportunity(opp)}
                              >
                                Details
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                </TooltipProvider>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Execute Progress Modal */}
        <ExecutionProgressModal
          open={showExecuteDialog}
          onClose={handleExecuteModalClose}
          opportunity={selectedOpportunity ? {
            id: selectedOpportunity.id,
            symbol: selectedOpportunity.symbol,
            primary_exchange: selectedOpportunity.long_leg?.exchange || selectedOpportunity.primary_exchange || 'Unknown',
            hedge_exchange: selectedOpportunity.short_leg?.exchange || selectedOpportunity.hedge_exchange || 'Unknown',
            primary_side: selectedOpportunity.primary_side || 'long',
            hedge_side: selectedOpportunity.hedge_side || 'short',
            net_apr: selectedOpportunity.net_apr || selectedOpportunity.estimated_net_apr || 0,
            uos_score: getUOSScore(selectedOpportunity),
            recommended_size_usd: selectedOpportunity.recommended_size_usd || 100,
          } : null}
          onExecute={handleExecuteOpportunity}
        />

        {/* Details Dialog */}
        {selectedOpportunity && !showExecuteDialog && (
          <Dialog open={!!selectedOpportunity} onOpenChange={() => setSelectedOpportunity(null)}>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Opportunity Details</DialogTitle>
                <DialogDescription>
                  {selectedOpportunity.symbol} - {selectedOpportunity.opportunity_type}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-6 py-4">
                {/* Score Breakdown */}
                <div>
                  <h3 className="font-semibold mb-3">
                    Score Breakdown (UOS: {getUOSScore(selectedOpportunity)})
                    {selectedOpportunity.scores?.quality && (
                      <span className={`ml-2 text-sm ${CONFIDENCE_STYLES[selectedOpportunity.scores.quality]?.color || ''}`}>
                        {selectedOpportunity.scores.quality}
                      </span>
                    )}
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Return Score (max 30)</span>
                        <span>{selectedOpportunity.scores?.return_score || selectedOpportunity.return_score || 0}</span>
                      </div>
                      <Progress value={(selectedOpportunity.scores?.return_score || selectedOpportunity.return_score || 0) * 100 / 30} className="h-2" />
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Risk Score (max 30)</span>
                        <span>{selectedOpportunity.scores?.risk_score || selectedOpportunity.risk_score || 0}</span>
                      </div>
                      <Progress value={(selectedOpportunity.scores?.risk_score || selectedOpportunity.risk_score || 0) * 100 / 30} className="h-2" />
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Execution Score (max 25)</span>
                        <span>{selectedOpportunity.scores?.execution_score || selectedOpportunity.execution_score || 0}</span>
                      </div>
                      <Progress value={(selectedOpportunity.scores?.execution_score || selectedOpportunity.execution_score || 0) * 100 / 25} className="h-2" />
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Timing Score (max 15)</span>
                        <span>{selectedOpportunity.scores?.timing_score || selectedOpportunity.timing_score || 0}</span>
                      </div>
                      <Progress value={(selectedOpportunity.scores?.timing_score || selectedOpportunity.timing_score || 0) * 100 / 15} className="h-2" />
                    </div>
                  </div>
                </div>

                {/* Trade Details */}
                <div>
                  <h3 className="font-semibold mb-3">Trade Setup</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="p-4 rounded-lg border bg-green-500/5">
                      <div className="flex items-center gap-2 mb-2">
                        <TrendingUp className="h-4 w-4 text-green-500" />
                        <span className="font-medium">Long Position</span>
                      </div>
                      <div className="space-y-1 text-muted-foreground">
                        <div>Exchange: {selectedOpportunity.long_leg?.exchange || selectedOpportunity.primary_exchange || 'N/A'}</div>
                        <div>Rate: {formatPercent(
                          (selectedOpportunity.long_leg?.funding_rate || selectedOpportunity.primary_rate || 0) * 100,
                          4
                        )}</div>
                      </div>
                    </div>
                    <div className="p-4 rounded-lg border bg-red-500/5">
                      <div className="flex items-center gap-2 mb-2">
                        <TrendingDown className="h-4 w-4 text-red-500" />
                        <span className="font-medium">Short Position</span>
                      </div>
                      <div className="space-y-1 text-muted-foreground">
                        <div>Exchange: {selectedOpportunity.short_leg?.exchange || selectedOpportunity.hedge_exchange || 'N/A'}</div>
                        <div>Rate: {formatPercent(
                          (selectedOpportunity.short_leg?.funding_rate || selectedOpportunity.hedge_rate || 0) * 100,
                          4
                        )}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Timing */}
                <div>
                  <h3 className="font-semibold mb-3">Timing</h3>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <div className="text-muted-foreground">Detected</div>
                      <div>{new Date(selectedOpportunity.detected_at).toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Expires</div>
                      <div>{new Date(selectedOpportunity.expires_at).toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Min Hold</div>
                      <div>{selectedOpportunity.minimum_hold_periods || 2} periods</div>
                    </div>
                  </div>
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setSelectedOpportunity(null)}>
                  Close
                </Button>
                {['detected', 'validated', 'scored'].includes(selectedOpportunity.status) && (
                  <Button onClick={() => setShowExecuteDialog(true)}>
                    <Play className="h-4 w-4 mr-2" />
                    Execute
                  </Button>
                )}
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>
    </DashboardLayout>
  );
}
