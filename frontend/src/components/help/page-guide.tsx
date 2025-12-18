'use client';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  LayoutDashboard,
  Radio,
  TrendingUp,
  Target,
  Wallet,
  BarChart3,
  Settings,
  ArrowRight,
  Eye,
  Play,
  RefreshCw,
  Filter,
  Search,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface PageInfo {
  id: string;
  name: string;
  path: string;
  icon: React.ReactNode;
  color: string;
  description: string;
  features: {
    action: string;
    description: string;
    icon?: React.ReactNode;
  }[];
  keyMetrics?: string[];
}

const PAGES: PageInfo[] = [
  {
    id: 'dashboard',
    name: 'Dashboard',
    path: '/',
    icon: <LayoutDashboard className="h-5 w-5" />,
    color: 'bg-blue-500',
    description: 'Your portfolio overview and key performance indicators at a glance.',
    features: [
      {
        action: 'View Portfolio Summary',
        description: 'See total capital, active positions, and P&L',
        icon: <Eye className="h-4 w-4" />,
      },
      {
        action: 'Monitor Performance',
        description: 'Track daily/weekly/monthly returns and win rate',
        icon: <BarChart3 className="h-4 w-4" />,
      },
      {
        action: 'Quick Stats',
        description: 'View top opportunities and position health',
        icon: <TrendingUp className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['Total P&L', 'Win Rate', 'Active Positions', 'Capital Utilization'],
  },
  {
    id: 'situation-room',
    name: 'Situation Room',
    path: '/situation-room',
    icon: <Radio className="h-5 w-5" />,
    color: 'bg-red-500',
    description: 'Real-time monitoring and control center for the arbitrage bot.',
    features: [
      {
        action: 'Start/Stop Bot',
        description: 'Control the automated trading system',
        icon: <Play className="h-4 w-4" />,
      },
      {
        action: 'Monitor Activity',
        description: 'View real-time event log and system status',
        icon: <RefreshCw className="h-4 w-4" />,
      },
      {
        action: 'Change Modes',
        description: 'Switch between Paper, Shadow, and Live trading',
        icon: <Settings className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['Bot Status', 'Trading Mode', 'Position Health', 'System Events'],
  },
  {
    id: 'funding-rates',
    name: 'Funding Rates',
    path: '/funding-rates',
    icon: <TrendingUp className="h-5 w-5" />,
    color: 'bg-green-500',
    description: 'Compare funding rates across all connected exchanges in real-time.',
    features: [
      {
        action: 'Compare Rates',
        description: 'View funding rates side-by-side across exchanges',
        icon: <Eye className="h-4 w-4" />,
      },
      {
        action: 'Filter Assets',
        description: 'Search and filter by symbol or exchange',
        icon: <Filter className="h-4 w-4" />,
      },
      {
        action: 'Identify Spreads',
        description: 'Spot funding rate differentials for arbitrage',
        icon: <Search className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['Funding Rate', 'Funding Spread', 'Time to Next Funding', 'Rate History'],
  },
  {
    id: 'opportunities',
    name: 'Opportunities',
    path: '/opportunities',
    icon: <Target className="h-5 w-5" />,
    color: 'bg-purple-500',
    description: 'View and execute detected arbitrage opportunities.',
    features: [
      {
        action: 'View Opportunities',
        description: 'See all detected funding rate arbitrage opportunities',
        icon: <Eye className="h-4 w-4" />,
      },
      {
        action: 'Execute Trades',
        description: 'Manually execute high-scoring opportunities',
        icon: <Play className="h-4 w-4" />,
      },
      {
        action: 'Analyze Scores',
        description: 'Deep dive into UOS score breakdown',
        icon: <BarChart3 className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['UOS Score', 'Net APR', 'Funding Spread', 'Expires In'],
  },
  {
    id: 'positions',
    name: 'Positions & Trades',
    path: '/positions',
    icon: <Wallet className="h-5 w-5" />,
    color: 'bg-orange-500',
    description: 'Track all open and closed positions with full trade history.',
    features: [
      {
        action: 'View Open Positions',
        description: 'Monitor active arbitrage positions across exchanges',
        icon: <Eye className="h-4 w-4" />,
      },
      {
        action: 'Review Trade History',
        description: 'See all completed trades with P&L details',
        icon: <BarChart3 className="h-4 w-4" />,
      },
      {
        action: 'Analyze Performance',
        description: 'Track funding collected and position health',
        icon: <TrendingUp className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['Notional Value', 'Unrealized P&L', 'Funding Received', 'Delta Exposure'],
  },
  {
    id: 'performance',
    name: 'Performance',
    path: '/performance',
    icon: <BarChart3 className="h-5 w-5" />,
    color: 'bg-cyan-500',
    description: 'Detailed analytics and performance tracking over time.',
    features: [
      {
        action: 'View Returns',
        description: 'Track cumulative and daily returns with charts',
        icon: <TrendingUp className="h-4 w-4" />,
      },
      {
        action: 'Analyze Metrics',
        description: 'Review win rate, Sharpe ratio, and drawdowns',
        icon: <BarChart3 className="h-4 w-4" />,
      },
      {
        action: 'Export Reports',
        description: 'Download performance data for analysis',
        icon: <Settings className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['ROI', 'Win Rate', 'Sharpe Ratio', 'Max Drawdown'],
  },
  {
    id: 'settings',
    name: 'Settings',
    path: '/settings',
    icon: <Settings className="h-5 w-5" />,
    color: 'bg-gray-500',
    description: 'Configure exchanges, risk parameters, and system settings.',
    features: [
      {
        action: 'Exchange Configuration',
        description: 'Add API keys and configure exchange connections',
        icon: <Settings className="h-4 w-4" />,
      },
      {
        action: 'Risk Parameters',
        description: 'Set position limits, leverage, and risk thresholds',
        icon: <Filter className="h-4 w-4" />,
      },
      {
        action: 'Strategy Settings',
        description: 'Configure UOS thresholds and trading parameters',
        icon: <Target className="h-4 w-4" />,
      },
    ],
    keyMetrics: ['Connected Exchanges', 'Max Position Size', 'Leverage Limit', 'UOS Threshold'],
  },
];

interface PageCardProps {
  page: PageInfo;
}

function PageCard({ page }: PageCardProps) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className={cn('p-2 rounded-lg text-white', page.color)}>
            {page.icon}
          </div>
          <div>
            <CardTitle className="text-lg">{page.name}</CardTitle>
            <Badge variant="outline" className="mt-1 text-xs font-mono">
              {page.path}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{page.description}</p>

        <div className="space-y-2">
          <div className="text-xs font-medium uppercase text-muted-foreground">
            What you can do
          </div>
          {page.features.map((feature, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <ArrowRight className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <div>
                <span className="font-medium">{feature.action}</span>
                <span className="text-muted-foreground"> - {feature.description}</span>
              </div>
            </div>
          ))}
        </div>

        {page.keyMetrics && (
          <div className="space-y-2">
            <div className="text-xs font-medium uppercase text-muted-foreground">
              Key Metrics
            </div>
            <div className="flex flex-wrap gap-1">
              {page.keyMetrics.map((metric) => (
                <Badge key={metric} variant="secondary" className="text-xs">
                  {metric}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface PageGuideProps {
  className?: string;
}

export function PageGuide({ className }: PageGuideProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {/* Quick Navigation */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Navigation</CardTitle>
          <CardDescription>
            Jump to any page to learn what you can do there
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {PAGES.map((page) => (
              <a
                key={page.id}
                href={`#${page.id}`}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors',
                  'hover:bg-muted'
                )}
              >
                <div className={cn('p-1.5 rounded text-white', page.color)}>
                  {page.icon}
                </div>
                <span className="text-sm font-medium">{page.name}</span>
              </a>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Page Details */}
      <div className="grid gap-4 md:grid-cols-2">
        {PAGES.map((page) => (
          <div key={page.id} id={page.id}>
            <PageCard page={page} />
          </div>
        ))}
      </div>
    </div>
  );
}
