'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/card';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Percent,
  Calendar,
  Activity,
  Loader2,
  HelpCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getRealtimePnL } from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { getKPIById } from '@/lib/kpi-definitions';

interface RealtimePnL {
  total_pnl: number;
  today_pnl: number;
  unrealized_pnl: number;
  roi: number;
  active_positions: number;
  today_closed_trades: number;
  capital_deployed: number;
}

interface PnLInsightsProps {
  className?: string;
}

export function PnLInsights({ className }: PnLInsightsProps) {
  const { data: realtimeData, isLoading, error } = useQuery({
    queryKey: ['realtime-pnl'],
    queryFn: () => getRealtimePnL() as Promise<{ data?: RealtimePnL }>,
    refetchInterval: 10000, // Refresh every 10 seconds for real-time updates
  });

  const data = realtimeData?.data;
  const hasError = !!error;

  // Use real-time data from positions
  const totalPnl = data?.total_pnl || 0;
  const todayPnl = data?.today_pnl || 0;
  const unrealizedPnl = data?.unrealized_pnl || 0;
  const roi = data?.roi || 0;

  const cards = [
    {
      title: 'Total P&L',
      value: totalPnl,
      format: 'currency' as const,
      icon: DollarSign,
      description: 'All-time profit/loss',
      kpiId: 'total_pnl',
    },
    {
      title: "Today's P&L",
      value: todayPnl,
      format: 'currency' as const,
      icon: Calendar,
      description: '24h change',
      kpiId: 'funding_today',
    },
    {
      title: 'Unrealized P&L',
      value: unrealizedPnl,
      format: 'currency' as const,
      icon: Activity,
      description: 'Open positions',
      kpiId: 'unrealized_pnl',
    },
    {
      title: 'ROI',
      value: roi,
      format: 'percent' as const,
      icon: Percent,
      description: 'Return on investment',
      kpiId: 'roi',
    },
  ];

  if (hasError) {
    return (
      <div className={cn('grid gap-4 md:grid-cols-4', className)}>
        <Card className="col-span-4">
          <CardContent className="pt-6">
            <div className="text-center text-red-500 py-4">
              <p className="font-medium">Failed to load P&L data</p>
              <p className="text-sm text-muted-foreground mt-1">
                {error?.message || 'Unknown error'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className={cn('grid gap-4 md:grid-cols-4', className)}>
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className={cn('grid gap-4 md:grid-cols-4', className)}>
        {cards.map((card) => {
          const isPositive = card.value >= 0;
          const Icon = card.icon;
          const kpiDef = getKPIById(card.kpiId);

          return (
            <Card key={card.title}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-1">
                      <p className="text-sm font-medium text-muted-foreground">
                        {card.title}
                      </p>
                      {kpiDef && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/60 cursor-help hover:text-muted-foreground transition-colors" />
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-sm">
                            <div className="space-y-2">
                              <p className="font-semibold">{kpiDef.name}</p>
                              <p className="text-sm">{kpiDef.description}</p>
                              {kpiDef.formula && (
                                <p className="text-xs text-muted-foreground">
                                  <span className="font-medium">Formula:</span> {kpiDef.formula}
                                </p>
                              )}
                              {kpiDef.range && (
                                <p className="text-xs text-muted-foreground">
                                  <span className="font-medium">Range:</span> {kpiDef.range}
                                </p>
                              )}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                    <p className={cn(
                      'text-2xl font-bold',
                      isPositive ? 'text-green-500' : 'text-red-500'
                    )}>
                      {card.format === 'currency'
                        ? formatCurrency(card.value)
                        : formatPercent(card.value, 2)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {card.description}
                    </p>
                  </div>
                  <div className={cn(
                    'h-10 w-10 rounded-full flex items-center justify-center',
                    isPositive ? 'bg-green-500/10' : 'bg-red-500/10'
                  )}>
                    {isPositive ? (
                      <TrendingUp className={cn('h-5 w-5', isPositive ? 'text-green-500' : 'text-red-500')} />
                    ) : (
                      <TrendingDown className="h-5 w-5 text-red-500" />
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
