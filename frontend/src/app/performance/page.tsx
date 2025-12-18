'use client';

import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { PieChart } from 'lucide-react';
import { BalanceOverview } from '@/components/performance/balance-overview';
import { TradingHistory } from '@/components/performance/trading-history';
import { FundingBreakdown } from '@/components/performance/funding-breakdown';

export default function PerformancePage() {
  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <PieChart className="h-8 w-8" />
            Performance
          </h1>
          <p className="text-muted-foreground">
            Track exchange balances, trading performance, and funding earnings
          </p>
        </div>

        {/* Panel 1: Exchange Balances */}
        <BalanceOverview />

        {/* Panel 2: Trade Performance */}
        <TradingHistory />

        {/* Panel 3: Funding Performance */}
        <FundingBreakdown />
      </div>
    </DashboardLayout>
  );
}
