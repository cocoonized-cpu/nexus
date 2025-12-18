'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Database,
  Search,
  Calculator,
  CheckCircle,
  Coins,
  Target,
  ArrowRight,
  ArrowDown,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Zap,
  Clock,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface FlowStep {
  id: string;
  number: number;
  title: string;
  description: string;
  details: string[];
  icon: React.ReactNode;
  color: string;
}

const FLOW_STEPS: FlowStep[] = [
  {
    id: 'collect',
    number: 1,
    title: 'Data Collection',
    description: 'Fetch funding rates from all connected exchanges',
    details: [
      'Connect to exchange APIs (Binance, Bybit, Hyperliquid, OKX, etc.)',
      'Retrieve current funding rates for all perpetual contracts',
      'Collect order book data for liquidity analysis',
      'Update every 10-30 seconds',
    ],
    icon: <Database className="h-5 w-5" />,
    color: 'bg-blue-500',
  },
  {
    id: 'detect',
    number: 2,
    title: 'Opportunity Detection',
    description: 'Identify funding rate differentials between exchanges',
    details: [
      'Compare funding rates across exchange pairs',
      'Calculate funding spreads (difference between exchanges)',
      'Filter by minimum spread threshold',
      'Identify which exchange to long and which to short',
    ],
    icon: <Search className="h-5 w-5" />,
    color: 'bg-purple-500',
  },
  {
    id: 'score',
    number: 3,
    title: 'UOS Scoring',
    description: 'Score each opportunity using the Unified Opportunity Score',
    details: [
      'Return Score (0-30): Expected profitability from funding spread',
      'Risk Score (0-30): Volatility, liquidity, and exchange reliability',
      'Execution Score (0-25): Order book depth and expected slippage',
      'Timing Score (0-15): Optimal entry based on funding schedule',
      'Combined UOS: 0-100 (higher is better)',
    ],
    icon: <Calculator className="h-5 w-5" />,
    color: 'bg-yellow-500',
  },
  {
    id: 'validate',
    number: 4,
    title: 'Validation & Filtering',
    description: 'Apply risk filters and validate opportunity quality',
    details: [
      'Check minimum UOS threshold (configurable, typically 60+)',
      'Verify sufficient liquidity on both exchanges',
      'Ensure within position limits and risk parameters',
      'Confirm margin availability',
    ],
    icon: <CheckCircle className="h-5 w-5" />,
    color: 'bg-green-500',
  },
  {
    id: 'allocate',
    number: 5,
    title: 'Capital Allocation',
    description: 'Determine position size based on capital and risk limits',
    details: [
      'Calculate optimal position size based on UOS score',
      'Apply maximum position size limits',
      'Consider existing positions and capital utilization',
      'Allocate margin to both exchanges',
    ],
    icon: <Coins className="h-5 w-5" />,
    color: 'bg-orange-500',
  },
  {
    id: 'execute',
    number: 6,
    title: 'Order Execution',
    description: 'Open positions on both exchanges simultaneously',
    details: [
      'Place LONG order on exchange with lower/negative funding rate',
      'Place SHORT order on exchange with higher/positive funding rate',
      'Use market orders for immediate execution',
      'Verify fills and calculate actual entry prices',
    ],
    icon: <Zap className="h-5 w-5" />,
    color: 'bg-red-500',
  },
  {
    id: 'manage',
    number: 7,
    title: 'Position Management',
    description: 'Monitor positions and collect funding payments',
    details: [
      'Track delta exposure (should be near zero)',
      'Collect funding payments every 8 hours',
      'Monitor position health and margin levels',
      'Rebalance if delta exceeds threshold',
    ],
    icon: <Target className="h-5 w-5" />,
    color: 'bg-cyan-500',
  },
  {
    id: 'exit',
    number: 8,
    title: 'Exit Optimization',
    description: 'Close positions at optimal time to maximize profit',
    details: [
      'Monitor when funding spread narrows or reverses',
      'Calculate if continued holding is profitable',
      'Close both legs simultaneously',
      'Record P&L and reset for next opportunity',
    ],
    icon: <RefreshCw className="h-5 w-5" />,
    color: 'bg-indigo-500',
  },
];

function StepCard({ step, isExpanded, onToggle }: { step: FlowStep; isExpanded: boolean; onToggle: () => void }) {
  return (
    <div
      className={cn(
        'border rounded-lg p-4 cursor-pointer transition-all',
        isExpanded ? 'ring-2 ring-primary' : 'hover:border-primary/50'
      )}
      onClick={onToggle}
    >
      <div className="flex items-start gap-3">
        <div className={cn('p-2 rounded-lg text-white shrink-0', step.color)}>
          {step.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              Step {step.number}
            </Badge>
            <h3 className="font-semibold">{step.title}</h3>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{step.description}</p>

          {isExpanded && (
            <ul className="mt-3 space-y-1.5 text-sm">
              {step.details.map((detail, i) => (
                <li key={i} className="flex items-start gap-2">
                  <ArrowRight className="h-3 w-3 mt-1 text-muted-foreground shrink-0" />
                  <span>{detail}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

interface BotFlowChartProps {
  className?: string;
}

export function BotFlowChart({ className }: BotFlowChartProps) {
  const [expandedStep, setExpandedStep] = useState<string | null>(null);

  return (
    <div className={cn('space-y-8', className)}>
      {/* Overview Diagram */}
      <Card>
        <CardHeader>
          <CardTitle>Arbitrage Strategy Overview</CardTitle>
          <CardDescription>
            How NEXUS captures funding rate differentials between exchanges
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row items-center justify-center gap-4 p-4 bg-muted/30 rounded-lg">
            {/* Exchange A */}
            <div className="flex flex-col items-center gap-2 p-4 border rounded-lg bg-background">
              <div className="font-semibold">Exchange A</div>
              <div className="text-xs text-muted-foreground">Funding: -0.01%</div>
              <Badge className="bg-green-500">
                <TrendingUp className="h-3 w-3 mr-1" />
                LONG
              </Badge>
              <div className="text-xs text-green-500">Receive funding</div>
            </div>

            {/* Arrow */}
            <div className="flex flex-col items-center gap-1">
              <div className="text-2xl font-bold text-primary">+</div>
              <ArrowRight className="h-6 w-6 text-muted-foreground hidden md:block" />
              <ArrowDown className="h-6 w-6 text-muted-foreground md:hidden" />
            </div>

            {/* Exchange B */}
            <div className="flex flex-col items-center gap-2 p-4 border rounded-lg bg-background">
              <div className="font-semibold">Exchange B</div>
              <div className="text-xs text-muted-foreground">Funding: +0.03%</div>
              <Badge className="bg-red-500">
                <TrendingDown className="h-3 w-3 mr-1" />
                SHORT
              </Badge>
              <div className="text-xs text-green-500">Receive funding</div>
            </div>

            {/* Equals */}
            <div className="flex flex-col items-center gap-1">
              <div className="text-2xl font-bold text-muted-foreground">=</div>
            </div>

            {/* Result */}
            <div className="flex flex-col items-center gap-2 p-4 border-2 border-green-500 rounded-lg bg-green-500/5">
              <div className="font-semibold text-green-500">Net Profit</div>
              <div className="text-xs text-muted-foreground">Spread: 0.04%</div>
              <div className="text-lg font-bold text-green-500">~14.6% APR</div>
              <div className="text-xs text-muted-foreground">Delta neutral</div>
            </div>
          </div>

          <div className="mt-4 p-4 bg-blue-500/5 border border-blue-500/20 rounded-lg">
            <div className="flex items-start gap-2">
              <Zap className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
              <div className="text-sm">
                <strong>Key Insight:</strong> By being long on one exchange and short on the other for the same asset,
                price movements cancel out (delta neutral). Profit comes purely from the funding rate differential
                paid every 8 hours.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Decision Flow */}
      <Card>
        <CardHeader>
          <CardTitle>Decision Flow</CardTitle>
          <CardDescription>
            How the bot decides to enter and exit positions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-2">
            {/* Entry Decision */}
            <div className="flex items-center gap-4 p-4 border rounded-lg w-full max-w-md">
              <div className="p-2 rounded-full bg-blue-500/10">
                <Search className="h-5 w-5 text-blue-500" />
              </div>
              <div className="flex-1">
                <div className="font-medium">Opportunity Detected</div>
                <div className="text-xs text-muted-foreground">Funding spread exceeds threshold</div>
              </div>
            </div>

            <ArrowDown className="h-5 w-5 text-muted-foreground" />

            <div className="flex items-center gap-4 p-4 border rounded-lg w-full max-w-md">
              <div className="p-2 rounded-full bg-yellow-500/10">
                <Calculator className="h-5 w-5 text-yellow-500" />
              </div>
              <div className="flex-1">
                <div className="font-medium">UOS Score Check</div>
                <div className="text-xs text-muted-foreground">Score must be above threshold (e.g., 60+)</div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="flex flex-col items-center gap-2">
                <Badge className="bg-green-500">
                  <CheckCircle className="h-3 w-3 mr-1" />
                  Pass
                </Badge>
                <ArrowDown className="h-5 w-5 text-green-500" />
              </div>
              <div className="flex flex-col items-center gap-2">
                <Badge variant="destructive">
                  <XCircle className="h-3 w-3 mr-1" />
                  Fail
                </Badge>
                <ArrowDown className="h-5 w-5 text-red-500" />
              </div>
            </div>

            <div className="flex items-center gap-4 w-full max-w-lg">
              <div className="flex-1 p-4 border border-green-500/50 rounded-lg bg-green-500/5">
                <div className="font-medium text-green-500">Execute Trade</div>
                <div className="text-xs text-muted-foreground">Open long + short positions</div>
              </div>
              <div className="flex-1 p-4 border border-red-500/50 rounded-lg bg-red-500/5">
                <div className="font-medium text-red-500">Skip</div>
                <div className="text-xs text-muted-foreground">Wait for better opportunity</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Step by Step Process */}
      <Card>
        <CardHeader>
          <CardTitle>Step-by-Step Process</CardTitle>
          <CardDescription>
            Click on any step to see more details
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2">
            {FLOW_STEPS.map((step) => (
              <StepCard
                key={step.id}
                step={step}
                isExpanded={expandedStep === step.id}
                onToggle={() => setExpandedStep(expandedStep === step.id ? null : step.id)}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Timing Diagram */}
      <Card>
        <CardHeader>
          <CardTitle>Funding Payment Timeline</CardTitle>
          <CardDescription>
            When funding payments are collected
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative">
            {/* Timeline */}
            <div className="flex items-center justify-between py-8">
              <div className="absolute left-0 right-0 h-1 bg-muted top-1/2 -translate-y-1/2" />

              {['00:00', '08:00', '16:00', '00:00'].map((time, i) => (
                <div key={i} className="relative z-10 flex flex-col items-center">
                  <div className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center',
                    i < 3 ? 'bg-green-500 text-white' : 'bg-muted'
                  )}>
                    <Clock className="h-4 w-4" />
                  </div>
                  <div className="mt-2 text-xs font-medium">{time} UTC</div>
                  {i < 3 && (
                    <div className="mt-1 text-xs text-green-500">+Funding</div>
                  )}
                </div>
              ))}
            </div>

            <div className="mt-4 text-sm text-muted-foreground text-center">
              Funding payments settle every 8 hours (3x per day) on most exchanges
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
