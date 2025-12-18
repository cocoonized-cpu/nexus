'use client';

import { useQuery } from '@tanstack/react-query';
import { DollarSign, TrendingUp, Wallet, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';
import { getCapitalState, getPerformanceSummary, getRiskState } from '@/lib/api';

interface CapitalState {
  allocated_capital_usd?: number;
  utilization_pct?: number;
}

interface PerformanceData {
  total_pnl?: number;
  total_return_pct?: number;
  trades_count?: number;
}

interface RiskState {
  circuit_breaker_active?: boolean;
  current_drawdown_pct?: number;
}

export function OverviewStats() {
  const { data: capital } = useQuery({
    queryKey: ['capital-state'],
    queryFn: () => getCapitalState() as Promise<{ data?: CapitalState }>,
  });

  const { data: performance } = useQuery({
    queryKey: ['performance-summary'],
    queryFn: () => getPerformanceSummary('30d') as Promise<{ data?: PerformanceData }>,
  });

  const { data: risk } = useQuery({
    queryKey: ['risk-state'],
    queryFn: () => getRiskState() as Promise<{ data?: RiskState }>,
  });

  const stats = [
    {
      title: 'Total P&L',
      value: formatCurrency(performance?.data?.total_pnl || 0),
      change: formatPercent(performance?.data?.total_return_pct || 0),
      icon: DollarSign,
      changePositive: (performance?.data?.total_return_pct || 0) >= 0,
    },
    {
      title: 'Active Positions',
      value: String(performance?.data?.trades_count || 0),
      subtext: 'positions',
      icon: Wallet,
    },
    {
      title: 'Capital Deployed',
      value: formatCurrency(capital?.data?.allocated_capital_usd || 0),
      subtext: `${formatNumber(capital?.data?.utilization_pct, 1)}% utilized`,
      icon: TrendingUp,
    },
    {
      title: 'Risk Status',
      value: risk?.data?.circuit_breaker_active ? 'HALTED' : 'ACTIVE',
      subtext: `${formatNumber(risk?.data?.current_drawdown_pct, 2)}% drawdown`,
      icon: AlertTriangle,
      status: risk?.data?.circuit_breaker_active ? 'critical' : 'healthy',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
            <stat.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stat.value}</div>
            {stat.change && (
              <p
                className={`text-xs ${
                  stat.changePositive ? 'text-green-500' : 'text-red-500'
                }`}
              >
                {stat.change} from last period
              </p>
            )}
            {stat.subtext && (
              <p className="text-xs text-muted-foreground">{stat.subtext}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
