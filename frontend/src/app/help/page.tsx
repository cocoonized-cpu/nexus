'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  BookOpen,
  Workflow,
  Calculator,
  Map,
  Rocket,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react';
import { BotFlowChart } from '@/components/help/bot-flow-chart';
import { KPIDictionary } from '@/components/help/kpi-dictionary';
import { PageGuide } from '@/components/help/page-guide';

const GETTING_STARTED_STEPS = [
  {
    step: 1,
    title: 'Configure Exchanges',
    description: 'Add your exchange API keys in Settings to connect to trading platforms.',
    path: '/settings',
  },
  {
    step: 2,
    title: 'Review Funding Rates',
    description: 'Check the Funding Rates page to see current rates across all connected exchanges.',
    path: '/funding-rates',
  },
  {
    step: 3,
    title: 'Explore Opportunities',
    description: 'View detected arbitrage opportunities and their UOS scores on the Opportunities page.',
    path: '/opportunities',
  },
  {
    step: 4,
    title: 'Start in Paper Mode',
    description: 'Use the Situation Room to start the bot in Paper mode for risk-free testing.',
    path: '/situation-room',
  },
  {
    step: 5,
    title: 'Monitor Positions',
    description: 'Track your positions and funding collected on the Positions page.',
    path: '/positions',
  },
  {
    step: 6,
    title: 'Analyze Performance',
    description: 'Review your returns and metrics on the Performance page.',
    path: '/performance',
  },
];

export default function HelpPage() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <BookOpen className="h-8 w-8" />
            Help Center
          </h1>
          <p className="text-muted-foreground mt-1">
            Learn how to use NEXUS and understand all metrics and features
          </p>
        </div>

        {/* Navigation Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
            <TabsTrigger value="overview" className="gap-2">
              <Rocket className="h-4 w-4" />
              <span className="hidden sm:inline">Getting Started</span>
              <span className="sm:hidden">Start</span>
            </TabsTrigger>
            <TabsTrigger value="how-it-works" className="gap-2">
              <Workflow className="h-4 w-4" />
              <span className="hidden sm:inline">How It Works</span>
              <span className="sm:hidden">How</span>
            </TabsTrigger>
            <TabsTrigger value="pages" className="gap-2">
              <Map className="h-4 w-4" />
              <span className="hidden sm:inline">Page Guide</span>
              <span className="sm:hidden">Pages</span>
            </TabsTrigger>
            <TabsTrigger value="kpis" className="gap-2">
              <Calculator className="h-4 w-4" />
              <span className="hidden sm:inline">KPI Dictionary</span>
              <span className="sm:hidden">KPIs</span>
            </TabsTrigger>
          </TabsList>

          {/* Getting Started Tab */}
          <TabsContent value="overview" className="mt-6 space-y-6">
            {/* Welcome Card */}
            <Card className="bg-gradient-to-r from-blue-500/10 to-purple-500/10 border-blue-500/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Rocket className="h-5 w-5 text-blue-500" />
                  Welcome to NEXUS
                </CardTitle>
                <CardDescription>
                  Your automated funding rate arbitrage system
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm">
                  NEXUS automatically detects and executes funding rate arbitrage opportunities
                  across multiple cryptocurrency exchanges. By going long on one exchange and
                  short on another, you capture the funding rate differential while maintaining
                  a delta-neutral position.
                </p>
              </CardContent>
            </Card>

            {/* What is Funding Rate Arbitrage */}
            <Card>
              <CardHeader>
                <CardTitle>What is Funding Rate Arbitrage?</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Perpetual futures contracts use funding rates to keep prices aligned with spot markets.
                  When funding is positive, longs pay shorts. When negative, shorts pay longs.
                </p>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="p-4 rounded-lg border bg-green-500/5 border-green-500/20">
                    <div className="font-semibold text-green-500 mb-2">The Opportunity</div>
                    <p className="text-xs text-muted-foreground">
                      Different exchanges have different funding rates for the same asset.
                      This creates an arbitrage opportunity.
                    </p>
                  </div>
                  <div className="p-4 rounded-lg border bg-blue-500/5 border-blue-500/20">
                    <div className="font-semibold text-blue-500 mb-2">The Strategy</div>
                    <p className="text-xs text-muted-foreground">
                      Go long on the exchange paying you funding, short on the exchange where you pay.
                      Price moves cancel out.
                    </p>
                  </div>
                  <div className="p-4 rounded-lg border bg-purple-500/5 border-purple-500/20">
                    <div className="font-semibold text-purple-500 mb-2">The Profit</div>
                    <p className="text-xs text-muted-foreground">
                      Collect the funding rate differential every 8 hours while remaining market neutral.
                      Typical returns: 10-50% APR.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Quick Start Guide */}
            <Card>
              <CardHeader>
                <CardTitle>Quick Start Guide</CardTitle>
                <CardDescription>
                  Follow these steps to get started with NEXUS
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {GETTING_STARTED_STEPS.map((item, index) => (
                    <div key={item.step} className="flex items-start gap-4">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold">
                        {item.step}
                      </div>
                      <div className="flex-1 pt-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{item.title}</span>
                          <Badge variant="outline" className="text-xs font-mono">
                            {item.path}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {item.description}
                        </p>
                      </div>
                      {index < GETTING_STARTED_STEPS.length - 1 && (
                        <ArrowRight className="h-5 w-5 text-muted-foreground shrink-0 mt-1.5 hidden lg:block" />
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Key Concepts */}
            <Card>
              <CardHeader>
                <CardTitle>Key Concepts</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <div className="font-semibold flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      Delta Neutral
                    </div>
                    <p className="text-sm text-muted-foreground">
                      By holding equal long and short positions, price movements cancel out.
                      Your profit comes purely from funding payments.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="font-semibold flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      UOS Score
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Unified Opportunity Score (0-100) that evaluates opportunities based on
                      return potential, risk, execution quality, and timing.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="font-semibold flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      Funding Spread
                    </div>
                    <p className="text-sm text-muted-foreground">
                      The difference in funding rates between two exchanges. Higher spreads
                      mean more profitable opportunities.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="font-semibold flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      Position Legs
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Each arbitrage position has two legs: a Primary leg (receives funding)
                      and a Hedge leg (neutralizes directional risk).
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* How It Works Tab */}
          <TabsContent value="how-it-works" className="mt-6">
            <BotFlowChart />
          </TabsContent>

          {/* Page Guide Tab */}
          <TabsContent value="pages" className="mt-6">
            <PageGuide />
          </TabsContent>

          {/* KPI Dictionary Tab */}
          <TabsContent value="kpis" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calculator className="h-5 w-5" />
                  KPI Dictionary
                </CardTitle>
                <CardDescription>
                  Comprehensive guide to all metrics and KPIs used in NEXUS
                </CardDescription>
              </CardHeader>
              <CardContent>
                <KPIDictionary />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
