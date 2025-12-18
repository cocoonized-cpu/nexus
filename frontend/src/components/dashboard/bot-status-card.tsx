'use client';

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Activity,
  Square,
  Play,
  Clock,
  Radio,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getSystemStatus } from '@/lib/api';
import { useWebSocket } from '@/lib/websocket';
import Link from 'next/link';

interface SystemStatus {
  running?: boolean;
  is_running?: boolean;
  mode: string;
  start_time?: string;
  uptime_seconds?: number;
  version?: string;
}

const MODE_LABELS: Record<string, { label: string; color: string }> = {
  standard: { label: 'Standard', color: 'text-green-500' },
  discovery: { label: 'Discovery', color: 'text-blue-500' },
  conservative: { label: 'Conservative', color: 'text-yellow-500' },
  aggressive: { label: 'Aggressive', color: 'text-orange-500' },
  emergency: { label: 'Emergency', color: 'text-red-500' },
};

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours < 24) return `${hours}h ${mins}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

interface BotStatusCardProps {
  className?: string;
}

export function BotStatusCard({ className }: BotStatusCardProps) {
  const { subscribe, lastMessage } = useWebSocket();
  const [uptimeDisplay, setUptimeDisplay] = useState('');

  const { data: statusData, isLoading, refetch } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => getSystemStatus() as Promise<{ data?: SystemStatus }>,
    refetchInterval: 10000,
  });

  const rawStatus = statusData?.data;
  // Normalize the status - support both `running` and `is_running` field names
  const status = rawStatus ? {
    ...rawStatus,
    running: rawStatus.running ?? rawStatus.is_running ?? false,
  } : undefined;

  // Subscribe to WebSocket
  useEffect(() => {
    subscribe('system');
  }, [subscribe]);

  // Refetch on status changes
  useEffect(() => {
    if (lastMessage?.channel === 'system') {
      refetch();
    }
  }, [lastMessage, refetch]);

  // Update uptime counter
  useEffect(() => {
    if (!status?.running || !status.uptime_seconds) {
      setUptimeDisplay('');
      return;
    }

    let currentUptime = status.uptime_seconds;
    setUptimeDisplay(formatUptime(currentUptime));

    const interval = setInterval(() => {
      currentUptime += 1;
      setUptimeDisplay(formatUptime(currentUptime));
    }, 1000);

    return () => clearInterval(interval);
  }, [status?.running, status?.uptime_seconds]);

  const modeConfig = MODE_LABELS[status?.mode || 'standard'] || MODE_LABELS.standard;

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Radio className="h-4 w-4" />
          Bot Status
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Status */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    'h-10 w-10 rounded-full flex items-center justify-center',
                    status?.running
                      ? 'bg-green-500/10'
                      : 'bg-muted'
                  )}
                >
                  {status?.running ? (
                    <Activity className="h-5 w-5 text-green-500 animate-pulse" />
                  ) : (
                    <Square className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
                <div>
                  <p className={cn(
                    'font-semibold',
                    status?.running ? 'text-green-500' : 'text-muted-foreground'
                  )}>
                    {status?.running ? 'Running' : 'Stopped'}
                  </p>
                  {status?.running && uptimeDisplay && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {uptimeDisplay}
                    </div>
                  )}
                </div>
              </div>
              <Link href="/situation-room">
                <Button variant="outline" size="sm">
                  {status?.running ? 'Manage' : 'Start'}
                </Button>
              </Link>
            </div>

            {/* Mode */}
            <div className="flex items-center justify-between pt-2 border-t">
              <span className="text-sm text-muted-foreground">Mode</span>
              <Badge variant="outline" className={modeConfig.color}>
                {modeConfig.label}
              </Badge>
            </div>

            {/* Version */}
            {status?.version && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Version</span>
                <span className="text-sm font-mono">{status.version}</span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
