'use client';

import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
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
  ArrowLeft,
  Loader2,
  RefreshCw,
  Clock,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  DollarSign,
  RotateCcw,
  Eye,
  Zap,
  History,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWebSocket } from '@/lib/websocket';
import { useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Interaction {
  id: string;
  position_id: string;
  opportunity_id: string | null;
  symbol: string;
  timestamp: string;
  interaction_type: string;
  worker_service: string;
  decision: string | null;
  narrative: string;
  metrics: Record<string, unknown>;
}

const INTERACTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  position_opened: CheckCircle2,
  health_check: Activity,
  health_changed: AlertTriangle,
  funding_check: DollarSign,
  funding_collected: DollarSign,
  spread_update: TrendingUp,
  rebalance_check: RotateCcw,
  rebalance_triggered: RotateCcw,
  exit_evaluation: Eye,
  exit_triggered: XCircle,
  position_closed: XCircle,
};

const INTERACTION_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  position_opened: { bg: 'bg-green-500/10', text: 'text-green-500', border: 'border-green-500/30' },
  health_check: { bg: 'bg-blue-500/10', text: 'text-blue-500', border: 'border-blue-500/30' },
  health_changed: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/30' },
  funding_check: { bg: 'bg-cyan-500/10', text: 'text-cyan-500', border: 'border-cyan-500/30' },
  funding_collected: { bg: 'bg-green-500/10', text: 'text-green-500', border: 'border-green-500/30' },
  spread_update: { bg: 'bg-purple-500/10', text: 'text-purple-500', border: 'border-purple-500/30' },
  rebalance_check: { bg: 'bg-orange-500/10', text: 'text-orange-500', border: 'border-orange-500/30' },
  rebalance_triggered: { bg: 'bg-orange-500/10', text: 'text-orange-500', border: 'border-orange-500/30' },
  exit_evaluation: { bg: 'bg-gray-500/10', text: 'text-gray-500', border: 'border-gray-500/30' },
  exit_triggered: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/30' },
  position_closed: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/30' },
};

const DECISION_BADGES: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string }> = {
  kept_open: { variant: 'secondary', label: 'Kept Open' },
  triggered_exit: { variant: 'destructive', label: 'Exit Triggered' },
  rebalanced: { variant: 'default', label: 'Rebalanced' },
  skipped: { variant: 'outline', label: 'Skipped' },
  escalated: { variant: 'destructive', label: 'Escalated' },
  degraded: { variant: 'destructive', label: 'Degraded' },
  recovered: { variant: 'default', label: 'Recovered' },
};

const INTERACTION_TYPES = [
  { value: 'all', label: 'All Types' },
  { value: 'position_opened', label: 'Position Opened' },
  { value: 'health_check', label: 'Health Check' },
  { value: 'health_changed', label: 'Health Changed' },
  { value: 'funding_check', label: 'Funding Check' },
  { value: 'funding_collected', label: 'Funding Collected' },
  { value: 'spread_update', label: 'Spread Update' },
  { value: 'rebalance_check', label: 'Rebalance Check' },
  { value: 'rebalance_triggered', label: 'Rebalance Triggered' },
  { value: 'exit_evaluation', label: 'Exit Evaluation' },
  { value: 'exit_triggered', label: 'Exit Triggered' },
  { value: 'position_closed', label: 'Position Closed' },
];

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatRelativeTime(ts: string): string {
  const now = Date.now();
  const then = new Date(ts).getTime();
  const diff = now - then;

  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

export default function PositionInteractionsPage() {
  const params = useParams();
  const router = useRouter();
  const positionId = params.id as string;
  const { subscribe, lastMessage } = useWebSocket();
  const [typeFilter, setTypeFilter] = useState<string>('all');

  // Fetch position details for header
  const { data: positionData } = useQuery({
    queryKey: ['position-basic', positionId],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/v1/positions/${positionId}`);
      if (!response.ok) throw new Error('Failed to fetch position');
      return response.json();
    },
    enabled: !!positionId,
  });

  // Fetch interactions
  const { data: interactionsData, isLoading, refetch } = useQuery({
    queryKey: ['position-interactions', positionId, typeFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (typeFilter !== 'all') {
        params.set('interaction_type', typeFilter);
      }
      params.set('limit', '200');
      const response = await fetch(
        `${API_BASE}/api/v1/positions/${positionId}/interactions?${params.toString()}`
      );
      if (!response.ok) throw new Error('Failed to fetch interactions');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!positionId,
  });

  const position = positionData?.data;
  const interactions: Interaction[] = interactionsData?.data || [];

  // Subscribe to WebSocket updates
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

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href={`/positions/${positionId}`}>
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Position
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <History className="h-6 w-6" />
              Interaction Timeline
            </h1>
            <p className="text-muted-foreground">
              {position?.symbol || 'Loading...'} - Bot decision history
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Type Filter */}
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by type" />
            </SelectTrigger>
            <SelectContent>
              {INTERACTION_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Timeline */}
      <Card>
        <CardHeader>
          <CardTitle>Bot Interactions</CardTitle>
          <CardDescription>
            Chronological log of all bot decisions and actions for this position
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : interactions.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <History className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No interactions recorded yet</p>
              <p className="text-sm mt-1">
                Interactions will appear as the bot monitors this position
              </p>
            </div>
          ) : (
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-6 top-0 bottom-0 w-px bg-border" />

              <div className="space-y-4">
                {interactions.map((interaction, idx) => {
                  const Icon = INTERACTION_ICONS[interaction.interaction_type] || Activity;
                  const colors = INTERACTION_COLORS[interaction.interaction_type] || {
                    bg: 'bg-gray-500/10',
                    text: 'text-gray-500',
                    border: 'border-gray-500/30',
                  };
                  const decision = interaction.decision
                    ? DECISION_BADGES[interaction.decision]
                    : null;

                  return (
                    <div key={interaction.id} className="relative flex gap-4">
                      {/* Timeline dot */}
                      <div
                        className={cn(
                          'relative z-10 flex h-12 w-12 items-center justify-center rounded-full border-2',
                          colors.bg,
                          colors.border
                        )}
                      >
                        <Icon className={cn('h-5 w-5', colors.text)} />
                      </div>

                      {/* Content */}
                      <div className="flex-1 pt-1">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-medium capitalize">
                                {interaction.interaction_type.replace(/_/g, ' ')}
                              </span>
                              {decision && (
                                <Badge variant={decision.variant}>{decision.label}</Badge>
                              )}
                              <Badge variant="outline" className="text-xs">
                                {interaction.worker_service}
                              </Badge>
                            </div>
                            <p className="mt-1 text-sm">{interaction.narrative}</p>

                            {/* Metrics */}
                            {Object.keys(interaction.metrics).length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {Object.entries(interaction.metrics).map(([key, value]) => (
                                  <div
                                    key={key}
                                    className="text-xs bg-muted px-2 py-1 rounded"
                                  >
                                    <span className="text-muted-foreground">{key}: </span>
                                    <span className="font-mono">
                                      {typeof value === 'number'
                                        ? value.toFixed(4)
                                        : String(value)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          {/* Timestamp */}
                          <div className="text-right shrink-0">
                            <p className="text-sm text-muted-foreground">
                              {formatRelativeTime(interaction.timestamp)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {formatTimestamp(interaction.timestamp)}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Summary Stats */}
      {interactions.length > 0 && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Total Interactions</span>
              </div>
              <p className="text-2xl font-bold mt-1">{interactions.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Funding Collections</span>
              </div>
              <p className="text-2xl font-bold mt-1">
                {interactions.filter((i) => i.interaction_type === 'funding_collected').length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Health Changes</span>
              </div>
              <p className="text-2xl font-bold mt-1">
                {interactions.filter((i) => i.interaction_type === 'health_changed').length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <RotateCcw className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Rebalances</span>
              </div>
              <p className="text-2xl font-bold mt-1">
                {interactions.filter((i) => i.interaction_type === 'rebalance_triggered').length}
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
