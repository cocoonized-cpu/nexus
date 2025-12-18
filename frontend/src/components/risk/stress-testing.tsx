'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  getStressTestScenarios,
  runStressTest,
  StressScenario,
  StressTestResult,
} from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import {
  AlertTriangle,
  Play,
  TrendingDown,
  Shield,
  Zap,
  Server,
  Activity,
} from 'lucide-react';

const severityColors: Record<string, string> = {
  mild: 'bg-green-500/10 text-green-500 border-green-500/20',
  moderate: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  severe: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  extreme: 'bg-red-500/10 text-red-500 border-red-500/20',
};

const typeIcons: Record<string, React.ReactNode> = {
  flash_crash: <TrendingDown className="h-4 w-4" />,
  funding_flip: <Activity className="h-4 w-4" />,
  exchange_outage: <Server className="h-4 w-4" />,
  liquidity_crisis: <AlertTriangle className="h-4 w-4" />,
  correlation_breakdown: <Zap className="h-4 w-4" />,
  combined: <Shield className="h-4 w-4" />,
};

export function StressTesting() {
  const [selectedScenario, setSelectedScenario] = useState<string>('');

  const { data: scenariosData } = useQuery({
    queryKey: ['stress-scenarios'],
    queryFn: getStressTestScenarios,
  });

  const stressTestMutation = useMutation({
    mutationFn: (scenarioName?: string) => runStressTest(scenarioName),
  });

  const scenarios = scenariosData?.data || [];
  const results = stressTestMutation.data?.data;

  const handleRunTest = () => {
    stressTestMutation.mutate(selectedScenario || undefined);
  };

  const getResultSeverityColor = (result: StressTestResult) => {
    const drawdown = Math.abs(result.max_drawdown_pct);
    if (drawdown > 20) return 'text-red-500';
    if (drawdown > 10) return 'text-orange-500';
    if (drawdown > 5) return 'text-yellow-500';
    return 'text-green-500';
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Stress Testing
          </CardTitle>
          <CardDescription>
            Simulate market scenarios to evaluate portfolio resilience
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <Select
              value={selectedScenario}
              onValueChange={setSelectedScenario}
            >
              <SelectTrigger className="w-[300px]">
                <SelectValue placeholder="All scenarios" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All scenarios</SelectItem>
                {scenarios.map((scenario: StressScenario) => (
                  <SelectItem key={scenario.key} value={scenario.key}>
                    <div className="flex items-center gap-2">
                      {typeIcons[scenario.type]}
                      <span>{scenario.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button
              onClick={handleRunTest}
              disabled={stressTestMutation.isPending}
            >
              <Play className="h-4 w-4 mr-2" />
              {stressTestMutation.isPending ? 'Running...' : 'Run Test'}
            </Button>
          </div>

          {/* Scenario list */}
          <div className="mt-6 grid gap-2">
            {scenarios.slice(0, 6).map((scenario: StressScenario) => (
              <div
                key={scenario.key}
                className="flex items-center justify-between p-2 rounded-lg border bg-card/50"
              >
                <div className="flex items-center gap-3">
                  {typeIcons[scenario.type]}
                  <div>
                    <div className="text-sm font-medium">{scenario.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {scenario.description}
                    </div>
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={severityColors[scenario.severity]}
                >
                  {scenario.severity}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Results Summary */}
      {results && (
        <Card>
          <CardHeader>
            <CardTitle>Test Results Summary</CardTitle>
            <CardDescription>
              {results.scenarios_run} scenarios evaluated
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4 mb-6">
              <div className="p-4 rounded-lg border bg-card/50">
                <div className="text-sm text-muted-foreground">Worst Case P&L</div>
                <div className={`text-2xl font-bold ${results.worst_case_pnl < 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {formatCurrency(results.worst_case_pnl)}
                </div>
              </div>
              <div className="p-4 rounded-lg border bg-card/50">
                <div className="text-sm text-muted-foreground">Max Drawdown</div>
                <div className="text-2xl font-bold text-orange-500">
                  {formatPercent(results.worst_case_drawdown_pct)}
                </div>
              </div>
              <div className="p-4 rounded-lg border bg-card/50">
                <div className="text-sm text-muted-foreground">Scenarios Run</div>
                <div className="text-2xl font-bold">
                  {results.scenarios_run}
                </div>
              </div>
              <div className="p-4 rounded-lg border bg-card/50">
                <div className="text-sm text-muted-foreground">Liquidation Risk</div>
                <div className={`text-2xl font-bold ${results.total_liquidation_risk > 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {results.total_liquidation_risk} positions
                </div>
              </div>
            </div>

            {/* Detailed Results */}
            <div className="space-y-4">
              {results.results.map((result: StressTestResult) => (
                <div
                  key={result.key}
                  className="p-4 rounded-lg border bg-card/50"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      {typeIcons[result.type]}
                      <div>
                        <div className="font-medium">{result.scenario}</div>
                        <Badge
                          variant="outline"
                          className={severityColors[result.severity]}
                        >
                          {result.severity}
                        </Badge>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-lg font-bold ${getResultSeverityColor(result)}`}>
                        {formatCurrency(result.projected_pnl)}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {formatPercent(result.projected_pnl_pct)} drawdown
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4 text-sm mb-3">
                    <div>
                      <span className="text-muted-foreground">Positions Affected:</span>{' '}
                      <span className="font-medium">{result.positions_affected}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Liquidations:</span>{' '}
                      <span className={`font-medium ${result.positions_liquidated > 0 ? 'text-red-500' : ''}`}>
                        {result.positions_liquidated}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Margin Calls:</span>{' '}
                      <span className={`font-medium ${result.margin_calls > 0 ? 'text-orange-500' : ''}`}>
                        {result.margin_calls}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <Progress
                      value={Math.min(Math.abs(result.max_drawdown_pct), 100)}
                      className={`h-2 ${
                        Math.abs(result.max_drawdown_pct) > 20
                          ? '[&>div]:bg-red-500'
                          : Math.abs(result.max_drawdown_pct) > 10
                          ? '[&>div]:bg-orange-500'
                          : '[&>div]:bg-yellow-500'
                      }`}
                    />
                  </div>

                  {result.recommendations.length > 0 && (
                    <div className="mt-3 pt-3 border-t">
                      <div className="text-sm font-medium mb-1">Recommendations:</div>
                      <ul className="text-sm text-muted-foreground space-y-1">
                        {result.recommendations.map((rec, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-primary">•</span>
                            {rec}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
