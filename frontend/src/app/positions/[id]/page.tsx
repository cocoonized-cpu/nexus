'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { PositionSpreadChart } from '@/components/positions/position-spread-chart';
import {
  ArrowLeft,
  ExternalLink,
  AlertCircle,
  Loader2,
  History,
  Ban,
  RefreshCw,
  HelpCircle,
  Clock,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import { useWebSocket } from '@/lib/websocket';
import { useToast } from '@/components/ui/use-toast';
import { cn } from '@/lib/utils';
import { formatCurrency, formatPercent } from '@/lib/utils';

// Types
interface PositionLeg {
  id: string;
  leg_type: string;
  exchange: string;
  symbol: string;
  market_type: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  notional_value_usd: number;
  unrealized_pnl: number;
  funding_pnl: number;
}

interface Position {
  id: string;
  opportunity_id: string | null;
  opportunity_type: string;
  symbol: string;
  base_asset: string;
  status: string;
  health_status: string;
  total_capital_deployed: number;
  funding_received: number;
  funding_paid: number;
  net_funding_pnl: number;
  unrealized_pnl: number;
  return_pct: number;
  delta_exposure_pct: number;
  max_margin_utilization: number;
  opened_at: string | null;
  funding_periods_collected: number;
  legs: PositionLeg[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const HEALTH_CONFIG: Record<string, { bg: string; text: string; icon: React.ComponentType<{ className?: string }> }> = {
  healthy: { bg: 'bg-green-500/10', text: 'text-green-500', icon: CheckCircle2 },
  attention: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', icon: AlertTriangle },
  warning: { bg: 'bg-orange-500/10', text: 'text-orange-500', icon: AlertTriangle },
  critical: { bg: 'bg-red-500/10', text: 'text-red-500', icon: XCircle },
  unknown: { bg: 'bg-gray-500/10', text: 'text-gray-500', icon: Activity },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return `${days}d ${hours}h`;
}

async function fetchPosition(id: string): Promise<Position> {
  const response = await fetch(`${API_BASE}/api/v1/positions/${id}`);
  if (!response.ok) {
    throw new Error('Position not found');
  }
  const result = await response.json();
  const data = result.data;

  // Convert string values to numbers
  return {
    ...data,
    total_capital_deployed: parseFloat(data.total_capital_deployed) || 0,
    funding_received: parseFloat(data.funding_received) || 0,
    funding_paid: parseFloat(data.funding_paid) || 0,
    net_funding_pnl: parseFloat(data.net_funding_pnl) || 0,
    unrealized_pnl: parseFloat(data.unrealized_pnl) || 0,
    return_pct: parseFloat(data.return_pct) || 0,
    delta_exposure_pct: parseFloat(data.delta_exposure_pct) || 0,
    max_margin_utilization: parseFloat(data.max_margin_utilization) || 0,
    legs: data.legs.map((leg: PositionLeg) => ({
      ...leg,
      quantity: parseFloat(String(leg.quantity)) || 0,
      entry_price: parseFloat(String(leg.entry_price)) || 0,
      current_price: parseFloat(String(leg.current_price)) || 0,
      notional_value_usd: parseFloat(String(leg.notional_value_usd)) || 0,
      unrealized_pnl: parseFloat(String(leg.unrealized_pnl)) || 0,
      funding_pnl: parseFloat(String(leg.funding_pnl)) || 0,
    })),
  };
}

export default function PositionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const positionId = params.id as string;
  const queryClient = useQueryClient();
  const { subscribe, lastMessage } = useWebSocket();
  const { toast } = useToast();
  const [showForecast, setShowForecast] = useState(false);

  // Real-time data fetching with React Query
  const { data: position, isLoading, error, refetch } = useQuery({
    queryKey: ['position-detail', positionId],
    queryFn: () => fetchPosition(positionId),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
    enabled: !!positionId,
  });

  // Subscribe to WebSocket updates for this position
  useEffect(() => {
    if (positionId) {
      subscribe(`positions:${positionId}`);
    }
  }, [subscribe, positionId]);

  // Refetch on WebSocket updates
  useEffect(() => {
    if (lastMessage?.channel === `positions:${positionId}`) {
      refetch();
    }
  }, [lastMessage, positionId, refetch]);

  // Blacklist mutation
  const blacklistMutation = useMutation({
    mutationFn: async (symbol: string) => {
      const response = await fetch(`${API_BASE}/api/v1/blacklist/${symbol}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Blacklisted from position details page' }),
      });
      if (!response.ok) throw new Error('Failed to blacklist symbol');
      return response.json();
    },
    onSuccess: () => {
      toast({
        title: 'Symbol Blacklisted',
        description: `${position?.symbol} has been added to the blacklist.`,
      });
      router.push('/positions');
    },
    onError: (error: Error) => {
      toast({
        title: 'Blacklist Failed',
        description: error.message,
        variant: 'destructive',
      });
    },
  });

  // Calculate hold duration
  const holdDuration = position?.opened_at
    ? Math.floor((Date.now() - new Date(position.opened_at).getTime()) / 1000)
    : 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !position) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)] gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <h2 className="text-xl font-semibold">Position Not Found</h2>
        <p className="text-muted-foreground">{error instanceof Error ? error.message : 'Unable to load position details'}</p>
        <Button onClick={() => router.push('/positions')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Positions
        </Button>
      </div>
    );
  }

  // Find long and short legs
  const longLeg = position.legs.find((leg) => leg.side === 'long');
  const shortLeg = position.legs.find((leg) => leg.side === 'short');

  // Status badge color
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'default';
      case 'opening':
        return 'secondary';
      case 'closing':
        return 'outline';
      case 'closed':
        return 'secondary';
      default:
        return 'destructive';
    }
  };

  // Health badge color
  const getHealthColor = (health: string) => {
    switch (health) {
      case 'healthy':
        return 'default';
      case 'attention':
        return 'secondary';
      case 'warning':
        return 'outline';
      case 'critical':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  const healthConfig = HEALTH_CONFIG[position.health_status] || HEALTH_CONFIG.unknown;
  const HealthIcon = healthConfig.icon;

  return (
    <TooltipProvider>
      <div className="container mx-auto py-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/positions">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-3">
                {position.symbol}
                <Badge
                  variant="outline"
                  className={cn('gap-1', healthConfig.bg, healthConfig.text)}
                >
                  <HealthIcon className="h-3 w-3" />
                  {position.health_status}
                </Badge>
              </h1>
              <p className="text-muted-foreground">{position.opportunity_type} Position</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Link href={`/positions/${positionId}/interactions`}>
              <Button variant="outline" size="sm">
                <History className="h-4 w-4 mr-2" />
                Interactions
              </Button>
            </Link>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => blacklistMutation.mutate(position.symbol)}
              disabled={blacklistMutation.isPending}
            >
              {blacklistMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Ban className="h-4 w-4 mr-2" />
              )}
              Blacklist
            </Button>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid gap-4 md:grid-cols-4">
          {/* Capital Allocated */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1">
                    <p className="text-sm font-medium text-muted-foreground">Capital Deployed</p>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/60 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent>
                        Total capital allocated to this position
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <p className="text-2xl font-bold">
                    ${position.total_capital_deployed.toLocaleString()}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Net Funding P&L */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1">
                    <p className="text-sm font-medium text-muted-foreground">Net Funding P&L</p>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/60 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent>
                        Total funding payments received minus paid
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <p className={cn(
                    'text-2xl font-bold',
                    position.net_funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'
                  )}>
                    ${position.net_funding_pnl.toFixed(2)}
                  </p>
                </div>
                <div className={cn(
                  'h-10 w-10 rounded-full flex items-center justify-center',
                  position.net_funding_pnl >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'
                )}>
                  <Activity className={cn(
                    'h-5 w-5',
                    position.net_funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'
                  )} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Unrealized P&L */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1">
                    <p className="text-sm font-medium text-muted-foreground">Unrealized P&L</p>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/60 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent>
                        Current profit/loss from price movements
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <p className={cn(
                    'text-2xl font-bold',
                    position.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'
                  )}>
                    ${position.unrealized_pnl.toFixed(2)}
                  </p>
                </div>
                <div className={cn(
                  'h-10 w-10 rounded-full flex items-center justify-center',
                  position.unrealized_pnl >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'
                )}>
                  {position.unrealized_pnl >= 0 ? (
                    <TrendingUp className="h-5 w-5 text-green-500" />
                  ) : (
                    <TrendingDown className="h-5 w-5 text-red-500" />
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Hold Duration */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1">
                    <p className="text-sm font-medium text-muted-foreground">Hold Duration</p>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/60 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent>
                        Time since position was opened ({position.funding_periods_collected} funding periods)
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <p className="text-2xl font-bold">
                    {formatDuration(holdDuration)}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-purple-500/10 flex items-center justify-center">
                  <Clock className="h-5 w-5 text-purple-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

      {/* Spread Chart */}
      <PositionSpreadChart positionId={positionId} />

      {/* Position Legs */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Long Leg */}
        {longLeg && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Badge variant="default" className="bg-green-500">LONG</Badge>
                {longLeg.exchange.charAt(0).toUpperCase() + longLeg.exchange.slice(1)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Entry Price</span>
                  <p className="font-mono font-medium">${longLeg.entry_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Current Price</span>
                  <p className="font-mono font-medium">${longLeg.current_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Size</span>
                  <p className="font-mono font-medium">{longLeg.quantity.toFixed(6)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Notional</span>
                  <p className="font-mono font-medium">${longLeg.notional_value_usd.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Unrealized P&L</span>
                  <p className={`font-mono font-medium ${longLeg.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${longLeg.unrealized_pnl.toFixed(2)}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Funding P&L</span>
                  <p className={`font-mono font-medium ${longLeg.funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${longLeg.funding_pnl.toFixed(2)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Short Leg */}
        {shortLeg && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Badge variant="destructive">SHORT</Badge>
                {shortLeg.exchange.charAt(0).toUpperCase() + shortLeg.exchange.slice(1)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Entry Price</span>
                  <p className="font-mono font-medium">${shortLeg.entry_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Current Price</span>
                  <p className="font-mono font-medium">${shortLeg.current_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Size</span>
                  <p className="font-mono font-medium">{shortLeg.quantity.toFixed(6)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Notional</span>
                  <p className="font-mono font-medium">${shortLeg.notional_value_usd.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Unrealized P&L</span>
                  <p className={`font-mono font-medium ${shortLeg.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${shortLeg.unrealized_pnl.toFixed(2)}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Funding P&L</span>
                  <p className={`font-mono font-medium ${shortLeg.funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${shortLeg.funding_pnl.toFixed(2)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Summary Stats */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Position Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Total Capital</span>
              <p className="font-mono font-medium text-lg">${position.total_capital_deployed.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Net Funding P&L</span>
              <p className={`font-mono font-medium text-lg ${position.net_funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                ${position.net_funding_pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Return</span>
              <p className={`font-mono font-medium text-lg ${position.return_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {position.return_pct.toFixed(2)}%
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Funding Periods</span>
              <p className="font-mono font-medium text-lg">{position.funding_periods_collected}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Delta Exposure</span>
              <p className="font-mono font-medium">{position.delta_exposure_pct.toFixed(2)}%</p>
            </div>
            <div>
              <span className="text-muted-foreground">Margin Utilization</span>
              <p className="font-mono font-medium">{position.max_margin_utilization.toFixed(2)}%</p>
            </div>
            <div>
              <span className="text-muted-foreground">Opened At</span>
              <p className="font-mono font-medium">
                {position.opened_at
                  ? new Date(position.opened_at).toLocaleString()
                  : 'N/A'}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Position ID</span>
              <p className="font-mono text-xs text-muted-foreground truncate" title={position.id}>
                {position.id}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
      </div>
    </TooltipProvider>
  );
}
