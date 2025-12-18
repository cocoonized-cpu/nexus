'use client';

import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Shield, AlertTriangle, BarChart3, Activity } from 'lucide-react';
import { RiskIndicators } from '@/components/dashboard/risk-indicators';
import { StressTesting } from '@/components/risk/stress-testing';
import { VaRMetrics } from '@/components/risk/var-metrics';

export default function RiskPage() {
  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Shield className="h-8 w-8" />
            Risk Management
          </h1>
          <p className="text-muted-foreground">
            Monitor portfolio risk, run stress tests, and manage exposure limits
          </p>
        </div>

        {/* Risk Overview */}
        <div className="grid gap-6 lg:grid-cols-2">
          <RiskIndicators />
          <VaRMetrics />
        </div>

        {/* Detailed Risk Analysis */}
        <Tabs defaultValue="stress-testing" className="space-y-4">
          <TabsList>
            <TabsTrigger value="stress-testing" className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              Stress Testing
            </TabsTrigger>
            <TabsTrigger value="limits" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Limits & Thresholds
            </TabsTrigger>
            <TabsTrigger value="history" className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Risk History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="stress-testing">
            <StressTesting />
          </TabsContent>

          <TabsContent value="limits">
            <div className="text-center py-8 text-muted-foreground">
              Risk limits configuration coming soon
            </div>
          </TabsContent>

          <TabsContent value="history">
            <div className="text-center py-8 text-muted-foreground">
              Historical risk metrics coming soon
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
