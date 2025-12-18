'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { getValueAtRisk } from '@/lib/api';
import { formatPercent } from '@/lib/utils';
import {
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  Info,
  BarChart3,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function VaRMetrics() {
  const { data: varData, isLoading } = useQuery({
    queryKey: ['var-metrics'],
    queryFn: () => getValueAtRisk(0.95),
    refetchInterval: 60000, // Refresh every minute
  });

  const data = varData?.data;

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          Calculating VaR metrics...
        </CardContent>
      </Card>
    );
  }

  if (!data || data.sample_size === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Value at Risk
          </CardTitle>
          <CardDescription>
            Risk metrics based on historical returns
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center text-muted-foreground py-4">
          <Info className="h-8 w-8 mx-auto mb-2" />
          <div>Insufficient historical data</div>
          <div className="text-sm">Complete at least 10 trades to calculate VaR</div>
        </CardContent>
      </Card>
    );
  }

  const getVaRRiskLevel = (var_pct: number) => {
    if (var_pct > 10) return { level: 'High', color: 'text-red-500', bg: 'bg-red-500/10' };
    if (var_pct > 5) return { level: 'Medium', color: 'text-yellow-500', bg: 'bg-yellow-500/10' };
    return { level: 'Low', color: 'text-green-500', bg: 'bg-green-500/10' };
  };

  const riskLevel = getVaRRiskLevel(data.var);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Value at Risk
            </CardTitle>
            <CardDescription>
              Risk metrics based on {data.sample_size} historical trades
            </CardDescription>
          </div>
          <Badge variant="outline" className={riskLevel.bg}>
            {riskLevel.level} Risk
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Main VaR Metrics */}
        <div className="grid grid-cols-2 gap-4">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="p-4 rounded-lg border bg-card/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-muted-foreground">VaR (95%)</span>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </div>
                  <div className={`text-2xl font-bold ${riskLevel.color}`}>
                    {formatPercent(data.var)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    5% chance of exceeding this loss
                  </div>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>Value at Risk: The maximum expected loss at 95% confidence</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="p-4 rounded-lg border bg-card/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-muted-foreground">CVaR (95%)</span>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </div>
                  <div className="text-2xl font-bold text-orange-500">
                    {formatPercent(data.cvar)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Expected loss in worst 5% of cases
                  </div>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>Conditional VaR: Average loss when VaR is breached</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* VaR 99 */}
        <div className="p-4 rounded-lg border bg-card/50">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              <span className="text-sm font-medium">Extreme Scenario (VaR 99%)</span>
            </div>
            <span className="text-lg font-bold text-red-500">
              {formatPercent(data.var_99)}
            </span>
          </div>
          <Progress
            value={Math.min(data.var_99, 30) / 30 * 100}
            className="h-2 [&>div]:bg-red-500"
          />
          <div className="text-xs text-muted-foreground mt-1">
            1% probability of this loss or worse
          </div>
        </div>

        {/* Return Statistics */}
        <div className="space-y-2">
          <div className="text-sm font-medium">Return Distribution</div>
          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-lg border bg-card/50 text-center">
              <div className="text-xs text-muted-foreground mb-1">Best Trade</div>
              <div className="flex items-center justify-center gap-1">
                <TrendingUp className="h-4 w-4 text-green-500" />
                <span className="font-bold text-green-500">
                  +{formatPercent(data.best_return)}
                </span>
              </div>
            </div>
            <div className="p-3 rounded-lg border bg-card/50 text-center">
              <div className="text-xs text-muted-foreground mb-1">Average</div>
              <div className={`font-bold ${data.avg_return >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {data.avg_return >= 0 ? '+' : ''}{formatPercent(data.avg_return)}
              </div>
            </div>
            <div className="p-3 rounded-lg border bg-card/50 text-center">
              <div className="text-xs text-muted-foreground mb-1">Worst Trade</div>
              <div className="flex items-center justify-center gap-1">
                <TrendingDown className="h-4 w-4 text-red-500" />
                <span className="font-bold text-red-500">
                  {formatPercent(data.worst_return)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Risk Assessment */}
        <div className={`p-3 rounded-lg ${riskLevel.bg}`}>
          <div className="text-sm">
            <span className="font-medium">Risk Assessment: </span>
            {data.var < 3 ? (
              <span>Portfolio shows low volatility with controlled downside risk.</span>
            ) : data.var < 7 ? (
              <span>Moderate risk level. Consider position sizing adjustments if exceeding 5%.</span>
            ) : (
              <span>Elevated risk. Review position sizes and consider reducing exposure.</span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
