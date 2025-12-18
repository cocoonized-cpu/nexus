'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  AlertTriangle,
  Shield,
  TrendingDown,
  DollarSign,
  Activity,
  AlertCircle,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getRiskState, getRiskLimits, getRiskAlerts, emergencyHalt } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

interface RiskState {
  current_drawdown: number;
  max_drawdown_limit: number;
  gross_exposure: number;
  max_exposure_limit: number;
  circuit_breaker_active: boolean;
  active_positions_count: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
}

interface RiskAlert {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  type: string;
  message: string;
  acknowledged: boolean;
  created_at: string;
}

interface RiskOverviewPanelProps {
  className?: string;
  compact?: boolean;
}

const RISK_LEVEL_CONFIG = {
  low: { color: 'text-green-500', bgColor: 'bg-green-500', label: 'Low' },
  medium: { color: 'text-yellow-500', bgColor: 'bg-yellow-500', label: 'Medium' },
  high: { color: 'text-orange-500', bgColor: 'bg-orange-500', label: 'High' },
  critical: { color: 'text-red-500', bgColor: 'bg-red-500', label: 'Critical' },
};

export function RiskOverviewPanel({ className, compact = false }: RiskOverviewPanelProps) {
  const queryClient = useQueryClient();

  const { data: riskStateData, isLoading: isLoadingState } = useQuery({
    queryKey: ['risk-state'],
    queryFn: () => getRiskState() as Promise<{ data?: RiskState }>,
    refetchInterval: 5000,
  });

  const { data: alertsData } = useQuery({
    queryKey: ['risk-alerts', { acknowledged: false }],
    queryFn: () => getRiskAlerts(undefined, false) as Promise<{ data?: RiskAlert[] }>,
    refetchInterval: 10000,
  });

  const emergencyHaltMutation = useMutation({
    mutationFn: emergencyHalt,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['risk-state'] });
      queryClient.invalidateQueries({ queryKey: ['system-status'] });
    },
  });

  const riskState = riskStateData?.data;
  const alerts = alertsData?.data || [];
  const unacknowledgedAlerts = alerts.filter((a) => !a.acknowledged);

  if (isLoadingState) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const drawdownPercent = riskState
    ? (riskState.current_drawdown / riskState.max_drawdown_limit) * 100
    : 0;
  const exposurePercent = riskState
    ? (riskState.gross_exposure / riskState.max_exposure_limit) * 100
    : 0;

  const riskLevelConfig = riskState?.risk_level && RISK_LEVEL_CONFIG[riskState.risk_level]
    ? RISK_LEVEL_CONFIG[riskState.risk_level]
    : RISK_LEVEL_CONFIG.low;

  return (
    <Card className={className}>
      <CardHeader className={cn('pb-2', compact && 'py-3')}>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className={cn('flex items-center gap-2', compact && 'text-base')}>
              <Shield className="h-5 w-5" />
              Risk Overview
            </CardTitle>
            {!compact && (
              <CardDescription>Current exposure and risk metrics</CardDescription>
            )}
          </div>
          <Badge
            variant="outline"
            className={cn(
              'gap-1',
              riskLevelConfig.color
            )}
          >
            <div
              className={cn(
                'h-2 w-2 rounded-full',
                riskLevelConfig.bgColor
              )}
            />
            {riskLevelConfig.label} Risk
          </Badge>
        </div>
      </CardHeader>

      <CardContent className={cn('space-y-4', compact && 'py-2')}>
        {/* Circuit Breaker Status */}
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-2">
            {riskState?.circuit_breaker_active ? (
              <XCircle className="h-5 w-5 text-red-500" />
            ) : (
              <CheckCircle2 className="h-5 w-5 text-green-500" />
            )}
            <div>
              <p className="font-medium text-sm">Circuit Breaker</p>
              <p className="text-xs text-muted-foreground">
                {riskState?.circuit_breaker_active
                  ? 'Trading halted'
                  : 'Trading allowed'}
              </p>
            </div>
          </div>
          <Button
            variant={riskState?.circuit_breaker_active ? 'outline' : 'destructive'}
            size="sm"
            onClick={() => emergencyHaltMutation.mutate()}
            disabled={emergencyHaltMutation.isPending}
          >
            {riskState?.circuit_breaker_active ? 'Reset' : 'Emergency Stop'}
          </Button>
        </div>

        {/* Drawdown */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-muted-foreground" />
              <span>Current Drawdown</span>
            </div>
            <span className={cn(
              'font-medium',
              drawdownPercent > 75 ? 'text-red-500' :
              drawdownPercent > 50 ? 'text-yellow-500' :
              'text-green-500'
            )}>
              {formatPercent(drawdownPercent, 1)} of limit
            </span>
          </div>
          <Progress
            value={drawdownPercent}
            className={cn(
              'h-2',
              drawdownPercent > 75 ? '[&>div]:bg-red-500' :
              drawdownPercent > 50 ? '[&>div]:bg-yellow-500' :
              ''
            )}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{formatCurrency(riskState?.current_drawdown || 0)}</span>
            <span>Limit: {formatCurrency(riskState?.max_drawdown_limit || 0)}</span>
          </div>
        </div>

        {/* Exposure */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <span>Gross Exposure</span>
            </div>
            <span className={cn(
              'font-medium',
              exposurePercent > 90 ? 'text-red-500' :
              exposurePercent > 75 ? 'text-yellow-500' :
              'text-green-500'
            )}>
              {formatPercent(exposurePercent, 1)} of limit
            </span>
          </div>
          <Progress
            value={exposurePercent}
            className={cn(
              'h-2',
              exposurePercent > 90 ? '[&>div]:bg-red-500' :
              exposurePercent > 75 ? '[&>div]:bg-yellow-500' :
              ''
            )}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{formatCurrency(riskState?.gross_exposure || 0)}</span>
            <span>Limit: {formatCurrency(riskState?.max_exposure_limit || 0)}</span>
          </div>
        </div>

        {/* Active Positions */}
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">Active Positions</span>
          </div>
          <span className="font-medium">{riskState?.active_positions_count || 0}</span>
        </div>

        {/* Alerts */}
        {unacknowledgedAlerts.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="h-4 w-4 text-yellow-500" />
              <span>Active Alerts ({unacknowledgedAlerts.length})</span>
            </div>
            <div className="space-y-1">
              {unacknowledgedAlerts.slice(0, 3).map((alert) => (
                <div
                  key={alert.id}
                  className={cn(
                    'p-2 rounded text-xs',
                    alert.severity === 'critical'
                      ? 'bg-red-500/10 text-red-500'
                      : alert.severity === 'high'
                      ? 'bg-orange-500/10 text-orange-500'
                      : 'bg-yellow-500/10 text-yellow-500'
                  )}
                >
                  {alert.message}
                </div>
              ))}
              {unacknowledgedAlerts.length > 3 && (
                <p className="text-xs text-muted-foreground">
                  +{unacknowledgedAlerts.length - 3} more alerts
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
