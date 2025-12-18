'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { getRiskState, getRiskLimits } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { useWebSocket } from '@/lib/websocket';
import { AlertTriangle, Shield, ShieldAlert, ShieldCheck } from 'lucide-react';

interface RiskState {
  circuit_breaker_active?: boolean;
  total_exposure_usd?: number | string;
  current_drawdown_pct?: number | string;
}

interface RiskLimits {
  max_total_exposure_usd?: number | string;
  max_position_size_usd?: number | string;
  max_exchange_exposure_usd?: number | string;
  max_drawdown_pct?: number | string;
}

export function RiskIndicators() {
  const { subscribe, lastMessage } = useWebSocket();

  const { data: riskState, refetch: refetchState } = useQuery({
    queryKey: ['risk-state'],
    queryFn: () => getRiskState() as Promise<{ data?: RiskState }>,
  });

  const { data: riskLimits } = useQuery({
    queryKey: ['risk-limits'],
    queryFn: () => getRiskLimits() as Promise<{ data?: RiskLimits }>,
  });

  useEffect(() => {
    subscribe('risk');
  }, [subscribe]);

  useEffect(() => {
    if (lastMessage?.channel === 'risk') {
      refetchState();
    }
  }, [lastMessage, refetchState]);

  const state: RiskState = riskState?.data || {};
  const limits: RiskLimits = riskLimits?.data || {};

  // Helper to safely parse numeric values (API may return strings)
  const parseNum = (value: unknown): number => {
    if (typeof value === 'number') return value;
    if (typeof value === 'string') return parseFloat(value) || 0;
    return 0;
  };

  // Safely extract numeric values with defaults
  const totalExposure = parseNum(state.total_exposure_usd);
  const maxExposure = parseNum(limits.max_total_exposure_usd);
  const currentDrawdown = parseNum(state.current_drawdown_pct);
  const maxDrawdown = parseNum(limits.max_drawdown_pct);

  const exposureUtilization =
    maxExposure > 0
      ? (totalExposure / maxExposure) * 100
      : 0;

  const drawdownUtilization =
    maxDrawdown > 0
      ? (currentDrawdown / maxDrawdown) * 100
      : 0;

  const getStatusIcon = () => {
    if (state.circuit_breaker_active) {
      return <ShieldAlert className="h-6 w-6 text-red-500" />;
    }
    if (drawdownUtilization > 80 || exposureUtilization > 80) {
      return <AlertTriangle className="h-6 w-6 text-yellow-500" />;
    }
    return <ShieldCheck className="h-6 w-6 text-green-500" />;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Risk Status</CardTitle>
            <CardDescription>Current risk metrics and limits</CardDescription>
          </div>
          {getStatusIcon()}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {state.circuit_breaker_active && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
            <div className="flex items-center gap-2 text-red-500">
              <ShieldAlert className="h-5 w-5" />
              <span className="font-semibold">Circuit Breaker Active</span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              All new trades are halted. Manual intervention required.
            </p>
          </div>
        )}

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Total Exposure</span>
            <span>
              {formatCurrency(totalExposure)} /{' '}
              {formatCurrency(maxExposure)}
            </span>
          </div>
          <Progress value={exposureUtilization} className="h-2" />
          <div className="text-xs text-muted-foreground text-right">
            {exposureUtilization.toFixed(1)}% utilized
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Current Drawdown</span>
            <span>
              {formatPercent(currentDrawdown)} /{' '}
              {formatPercent(maxDrawdown)}
            </span>
          </div>
          <Progress
            value={drawdownUtilization}
            className={`h-2 ${drawdownUtilization > 80 ? '[&>div]:bg-red-500' : ''}`}
          />
          <div className="text-xs text-muted-foreground text-right">
            {drawdownUtilization.toFixed(1)}% of limit
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-4 border-t">
          <div>
            <div className="text-sm text-muted-foreground">Max Position</div>
            <div className="font-medium">
              {formatCurrency(parseNum(limits.max_position_size_usd))}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Max Per Exchange</div>
            <div className="font-medium">
              {formatCurrency(parseNum(limits.max_exchange_exposure_usd))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
