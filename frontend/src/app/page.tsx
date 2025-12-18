'use client';

import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { PnLInsights } from '@/components/dashboard/pnl-insights';
import { BotStatusCard } from '@/components/dashboard/bot-status-card';
import { BotPerformanceMetrics } from '@/components/dashboard/bot-performance-metrics';
import { ActivePositionsPerformance } from '@/components/dashboard/active-positions-performance';
import { OpportunitiesTable } from '@/components/dashboard/opportunities-table';
import { LayoutDashboard } from 'lucide-react';

export default function DashboardPage() {
  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <LayoutDashboard className="h-8 w-8" />
            Dashboard
          </h1>
          <p className="text-muted-foreground">
            Overview of your trading bot performance
          </p>
        </div>

        {/* P&L Insights - 4 Cards */}
        <PnLInsights />

        {/* Bot Status & Performance Metrics */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <BotStatusCard />
          <BotPerformanceMetrics />
          <ActivePositionsPerformance className="lg:row-span-2" maxPositions={4} />

          {/* Top Opportunities Mini Table */}
          <div className="md:col-span-2 lg:col-span-2">
            <OpportunitiesTable />
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
