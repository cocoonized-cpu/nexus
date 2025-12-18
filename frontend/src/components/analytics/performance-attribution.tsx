'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  getPerformanceAttribution,
  AttributionBreakdown,
} from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import {
  PieChart,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Building2,
  Coins,
  Target,
} from 'lucide-react';

const periodOptions = [
  { value: '7d', label: '7 Days' },
  { value: '30d', label: '30 Days' },
  { value: '90d', label: '90 Days' },
];

export function PerformanceAttribution() {
  const [period, setPeriod] = useState('30d');

  const { data: attributionData, isLoading } = useQuery({
    queryKey: ['performance-attribution', period],
    queryFn: () => getPerformanceAttribution(period),
  });

  const data = attributionData?.data;

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          Loading attribution data...
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          No attribution data available
        </CardContent>
      </Card>
    );
  }

  const { pnl_breakdown, exchange_attribution, symbol_attribution, uos_score_cohorts } = data;

  return (
    <div className="space-y-6">
      {/* Period Selector */}
      <div className="flex gap-2">
        {periodOptions.map((opt) => (
          <Button
            key={opt.value}
            variant={period === opt.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => setPeriod(opt.value)}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {/* P&L Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PieChart className="h-5 w-5" />
            P&L Breakdown
          </CardTitle>
          <CardDescription>
            Funding vs Price component analysis
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-6">
            <div className="p-4 rounded-lg border bg-card/50 text-center">
              <div className="text-sm text-muted-foreground mb-1">Total P&L</div>
              <div className={`text-3xl font-bold ${pnl_breakdown.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatCurrency(pnl_breakdown.total_pnl)}
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {pnl_breakdown.trade_count} trades
              </div>
            </div>

            <div className="p-4 rounded-lg border bg-card/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-muted-foreground">Funding P&L</span>
                <Badge variant="outline" className="bg-blue-500/10 text-blue-500">
                  {formatPercent(pnl_breakdown.funding_pct)}
                </Badge>
              </div>
              <div className={`text-2xl font-bold ${pnl_breakdown.funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatCurrency(pnl_breakdown.funding_pnl)}
              </div>
              <Progress
                value={Math.abs(pnl_breakdown.funding_pct)}
                className="mt-2 h-2 [&>div]:bg-blue-500"
              />
            </div>

            <div className="p-4 rounded-lg border bg-card/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-muted-foreground">Price P&L</span>
                <Badge variant="outline" className="bg-purple-500/10 text-purple-500">
                  {formatPercent(pnl_breakdown.price_pct)}
                </Badge>
              </div>
              <div className={`text-2xl font-bold ${pnl_breakdown.price_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatCurrency(pnl_breakdown.price_pnl)}
              </div>
              <Progress
                value={Math.abs(pnl_breakdown.price_pct)}
                className="mt-2 h-2 [&>div]:bg-purple-500"
              />
            </div>
          </div>

          {/* Analysis */}
          <div className="mt-4 p-3 rounded-lg bg-muted/50 text-sm">
            {pnl_breakdown.funding_pnl > 0 && pnl_breakdown.price_pnl > 0 ? (
              <span className="text-green-500">
                Both funding and price components positive - ideal performance
              </span>
            ) : pnl_breakdown.funding_pnl > 0 && pnl_breakdown.price_pnl < 0 ? (
              pnl_breakdown.funding_pnl > Math.abs(pnl_breakdown.price_pnl) ? (
                <span className="text-blue-500">
                  Funding profits offsetting price losses - strategy working as designed
                </span>
              ) : (
                <span className="text-orange-500">
                  Price losses exceeding funding gains - review hedging effectiveness
                </span>
              )
            ) : pnl_breakdown.funding_pnl < 0 && pnl_breakdown.price_pnl < 0 ? (
              <span className="text-red-500">
                Both components negative - urgent strategy review needed
              </span>
            ) : (
              <span className="text-muted-foreground">
                Mixed performance - continue monitoring
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Attribution Tabs */}
      <Tabs defaultValue="exchange" className="space-y-4">
        <TabsList>
          <TabsTrigger value="exchange" className="flex items-center gap-2">
            <Building2 className="h-4 w-4" />
            By Exchange
          </TabsTrigger>
          <TabsTrigger value="symbol" className="flex items-center gap-2">
            <Coins className="h-4 w-4" />
            By Symbol
          </TabsTrigger>
          <TabsTrigger value="uos" className="flex items-center gap-2">
            <Target className="h-4 w-4" />
            By UOS Score
          </TabsTrigger>
        </TabsList>

        {/* Exchange Attribution */}
        <TabsContent value="exchange">
          <Card>
            <CardHeader>
              <CardTitle>Exchange Attribution</CardTitle>
              <CardDescription>P&L contribution by exchange</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {exchange_attribution.length === 0 ? (
                  <div className="text-center text-muted-foreground py-4">
                    No exchange data available
                  </div>
                ) : (
                  exchange_attribution.map((item: AttributionBreakdown) => (
                    <div
                      key={item.exchange}
                      className="flex items-center justify-between p-3 rounded-lg border bg-card/50"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                          <Building2 className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <div className="font-medium capitalize">{item.exchange}</div>
                          <div className="text-sm text-muted-foreground">
                            {item.trade_count} trades • {formatPercent(item.win_rate)} win rate
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-lg font-bold ${item.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {formatCurrency(item.total_pnl)}
                        </div>
                        {item.total_pnl >= 0 ? (
                          <TrendingUp className="h-4 w-4 text-green-500 inline" />
                        ) : (
                          <TrendingDown className="h-4 w-4 text-red-500 inline" />
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Symbol Attribution */}
        <TabsContent value="symbol">
          <Card>
            <CardHeader>
              <CardTitle>Symbol Attribution</CardTitle>
              <CardDescription>Top performing symbols</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {symbol_attribution.length === 0 ? (
                  <div className="text-center text-muted-foreground py-4">
                    No symbol data available
                  </div>
                ) : (
                  symbol_attribution.map((item: AttributionBreakdown, index: number) => (
                    <div
                      key={item.symbol}
                      className="flex items-center justify-between p-3 rounded-lg border bg-card/50"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold">
                          {index + 1}
                        </div>
                        <div>
                          <div className="font-medium">{item.symbol}</div>
                          <div className="text-sm text-muted-foreground">
                            {item.trade_count} trades • {formatPercent(item.win_rate)} win rate
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-lg font-bold ${item.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {formatCurrency(item.total_pnl)}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* UOS Score Cohorts */}
        <TabsContent value="uos">
          <Card>
            <CardHeader>
              <CardTitle>UOS Score Cohort Analysis</CardTitle>
              <CardDescription>Performance by opportunity score range</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {uos_score_cohorts.length === 0 ? (
                  <div className="text-center text-muted-foreground py-4">
                    No cohort data available
                  </div>
                ) : (
                  uos_score_cohorts.map((cohort: AttributionBreakdown) => {
                    const isHighScore = cohort.cohort?.includes('High') || cohort.cohort?.includes('90');
                    return (
                      <div
                        key={cohort.cohort}
                        className={`p-4 rounded-lg border ${
                          isHighScore ? 'border-primary/50 bg-primary/5' : 'bg-card/50'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Badge variant={isHighScore ? 'default' : 'outline'}>
                              {cohort.cohort}
                            </Badge>
                            <span className="text-sm text-muted-foreground">
                              {cohort.trade_count} trades
                            </span>
                          </div>
                          <div className={`text-lg font-bold ${cohort.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {formatCurrency(cohort.total_pnl)}
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Win Rate:</span>{' '}
                            <span className={`font-medium ${cohort.win_rate >= 60 ? 'text-green-500' : cohort.win_rate >= 50 ? 'text-yellow-500' : 'text-red-500'}`}>
                              {formatPercent(cohort.win_rate)}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Avg P&L:</span>{' '}
                            <span className={`font-medium ${(cohort.avg_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              {formatCurrency(cohort.avg_pnl || 0)}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Share:</span>{' '}
                            <span className="font-medium">
                              {pnl_breakdown.total_pnl !== 0
                                ? formatPercent((cohort.total_pnl / Math.abs(pnl_breakdown.total_pnl)) * 100)
                                : '0%'}
                            </span>
                          </div>
                        </div>

                        <Progress
                          value={cohort.win_rate}
                          className={`mt-3 h-2 ${
                            cohort.win_rate >= 60
                              ? '[&>div]:bg-green-500'
                              : cohort.win_rate >= 50
                              ? '[&>div]:bg-yellow-500'
                              : '[&>div]:bg-red-500'
                          }`}
                        />
                      </div>
                    );
                  })
                )}
              </div>

              {/* Recommendation */}
              {uos_score_cohorts.length > 0 && (
                <div className="mt-4 p-3 rounded-lg bg-muted/50">
                  <div className="text-sm font-medium mb-1">Recommendation</div>
                  <div className="text-sm text-muted-foreground">
                    {(() => {
                      const bestCohort = uos_score_cohorts.reduce((best, current) =>
                        (current.win_rate > best.win_rate && current.trade_count >= 5) ? current : best
                      , uos_score_cohorts[0]);

                      if (bestCohort.cohort?.includes('High') || bestCohort.cohort?.includes('90')) {
                        return 'Focus on high UOS score opportunities (90+) for best risk-adjusted returns.';
                      } else if (bestCohort.cohort?.includes('Medium-High') || bestCohort.cohort?.includes('80')) {
                        return 'Consider opportunities with UOS score 80+ for optimal balance of volume and win rate.';
                      } else {
                        return 'Review scoring criteria - lower score opportunities are outperforming expectations.';
                      }
                    })()}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
