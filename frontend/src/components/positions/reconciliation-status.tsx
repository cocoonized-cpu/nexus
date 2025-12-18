'use client';

import { useEffect, useState } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  XCircle,
  AlertCircle,
  FileWarning,
  Server,
} from 'lucide-react';
import { useWebSocket } from '@/lib/websocket';
import { ReconciliationDiscrepancy } from '@/lib/api';

interface ReconciliationStatusProps {
  className?: string;
}

const severityConfig: Record<string, { icon: React.ReactNode; color: string; badge: string }> = {
  low: {
    icon: <AlertCircle className="h-4 w-4" />,
    color: 'text-blue-500',
    badge: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  },
  medium: {
    icon: <AlertTriangle className="h-4 w-4" />,
    color: 'text-yellow-500',
    badge: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  },
  high: {
    icon: <FileWarning className="h-4 w-4" />,
    color: 'text-orange-500',
    badge: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  },
  critical: {
    icon: <XCircle className="h-4 w-4" />,
    color: 'text-red-500',
    badge: 'bg-red-500/10 text-red-500 border-red-500/20',
  },
};

const discrepancyTypeLabels: Record<string, string> = {
  orphan_on_exchange: 'Orphan on Exchange',
  missing_on_exchange: 'Missing on Exchange',
  size_mismatch: 'Size Mismatch',
  price_mismatch: 'Price Mismatch',
  state_mismatch: 'State Mismatch',
};

export function ReconciliationStatus({ className }: ReconciliationStatusProps) {
  const { subscribe, lastMessage } = useWebSocket();
  const [lastReconciliation, setLastReconciliation] = useState<string | null>(null);
  const [discrepancies, setDiscrepancies] = useState<ReconciliationDiscrepancy[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    subscribe('reconciliation');
  }, [subscribe]);

  useEffect(() => {
    if (lastMessage?.channel === 'reconciliation') {
      const data = lastMessage.data as {
        last_report?: {
          completed_at: string;
          unresolved?: ReconciliationDiscrepancy[];
        };
        type?: string;
        message?: string;
      };
      if (data?.last_report) {
        setLastReconciliation(data.last_report.completed_at);
        // Extract unresolved discrepancies from report
        if (data.last_report.unresolved) {
          setDiscrepancies(data.last_report.unresolved);
        }
      }
      if (data?.type === 'reconciliation_discrepancies') {
        // Alert about new discrepancies
        console.log('Reconciliation alert:', data.message);
      }
    }
  }, [lastMessage]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    // Trigger reconciliation via API would go here
    // For now, just simulate a refresh
    setTimeout(() => setIsRefreshing(false), 2000);
  };

  const getTimeSince = (isoString: string | null) => {
    if (!isoString) return 'Never';
    const diff = Date.now() - new Date(isoString).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const criticalCount = discrepancies.filter(d => d.severity === 'critical').length;
  const highCount = discrepancies.filter(d => d.severity === 'high').length;
  const hasIssues = discrepancies.length > 0;

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5" />
              Position Reconciliation
            </CardTitle>
            <CardDescription>
              Sync status between database and exchanges
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Sync
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Status Overview */}
        <div className="flex items-center justify-between p-3 rounded-lg border bg-card/50 mb-4">
          <div className="flex items-center gap-3">
            {!hasIssues ? (
              <CheckCircle2 className="h-6 w-6 text-green-500" />
            ) : criticalCount > 0 ? (
              <XCircle className="h-6 w-6 text-red-500" />
            ) : (
              <AlertTriangle className="h-6 w-6 text-yellow-500" />
            )}
            <div>
              <div className="font-medium">
                {!hasIssues
                  ? 'All Positions Synced'
                  : `${discrepancies.length} Discrepancies Found`}
              </div>
              <div className="text-sm text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Last checked: {getTimeSince(lastReconciliation)}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            {criticalCount > 0 && (
              <Badge variant="outline" className={severityConfig.critical.badge}>
                {criticalCount} Critical
              </Badge>
            )}
            {highCount > 0 && (
              <Badge variant="outline" className={severityConfig.high.badge}>
                {highCount} High
              </Badge>
            )}
          </div>
        </div>

        {/* Discrepancy List */}
        {hasIssues && (
          <div className="space-y-3">
            <div className="text-sm font-medium text-muted-foreground">
              Pending Discrepancies
            </div>
            {discrepancies.slice(0, 5).map((discrepancy, index) => {
              const config = severityConfig[discrepancy.severity] || severityConfig.medium;
              return (
                <div
                  key={`${discrepancy.exchange}-${discrepancy.symbol}-${index}`}
                  className="flex items-start justify-between p-3 rounded-lg border bg-card/50"
                >
                  <div className="flex items-start gap-3">
                    <div className={config.color}>{config.icon}</div>
                    <div>
                      <div className="font-medium flex items-center gap-2">
                        {discrepancy.symbol}
                        <Badge variant="outline" className={config.badge}>
                          {discrepancy.severity}
                        </Badge>
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {discrepancyTypeLabels[discrepancy.type] || discrepancy.type}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        Exchange: {discrepancy.exchange}
                        {discrepancy.position_id && ` • Position: ${discrepancy.position_id.slice(0, 8)}...`}
                      </div>
                    </div>
                  </div>
                  <div className="text-right text-sm">
                    <div className="text-muted-foreground">
                      DB: {JSON.stringify(discrepancy.db_value)?.slice(0, 15) || 'null'}
                    </div>
                    <div className="text-muted-foreground">
                      Ex: {JSON.stringify(discrepancy.exchange_value)?.slice(0, 15) || 'null'}
                    </div>
                  </div>
                </div>
              );
            })}
            {discrepancies.length > 5 && (
              <div className="text-sm text-center text-muted-foreground">
                +{discrepancies.length - 5} more discrepancies
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!hasIssues && (
          <div className="text-center py-4 text-muted-foreground">
            <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-500" />
            <div>All positions are synchronized</div>
            <div className="text-sm">No discrepancies between database and exchanges</div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
