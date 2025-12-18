'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Play,
  Square,
  AlertOctagon,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Radio,
  Server,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  getSystemStatus,
  controlSystem,
  changeSystemMode,
  getServicesHealth,
  getAutoExecute,
  setAutoExecute,
} from '@/lib/api';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useWebSocket } from '@/lib/websocket';
import { useToast } from '@/components/ui/use-toast';
import { ActivityLogEnhanced } from '@/components/situation-room/activity-log-enhanced';
import { RiskOverviewPanel } from '@/components/situation-room/risk-overview-panel';
import { ServiceControlCard } from '@/components/situation-room/service-control-card';

interface SystemStatus {
  running?: boolean;
  is_running?: boolean;
  mode: string;
  start_time?: string;
  uptime_seconds?: number;
  version?: string;
}

interface ServiceHealth {
  name: string;
  display_name?: string;
  status: 'healthy' | 'unhealthy' | 'degraded' | 'unknown' | 'offline';
  last_heartbeat?: string;
  uptime_seconds?: number;
  critical?: boolean;
  details?: Record<string, unknown>;
}

const MODES = [
  { value: 'standard', label: 'Standard', description: 'Normal trading operations' },
  { value: 'discovery', label: 'Discovery', description: 'Observe only, no execution' },
  { value: 'conservative', label: 'Conservative', description: 'Reduced position sizes' },
  { value: 'aggressive', label: 'Aggressive', description: 'Increased position sizes' },
];

const SERVICE_DISPLAY_NAMES: Record<string, string> = {
  'data-collector': 'Data Collector',
  'funding-aggregator': 'Funding Aggregator',
  'opportunity-detector': 'Opportunity Detector',
  'execution-engine': 'Execution Engine',
  'position-manager': 'Position Manager',
  'risk-manager': 'Risk Manager',
  'capital-allocator': 'Capital Allocator',
  'analytics': 'Analytics',
  gateway: 'Gateway',
};

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

export default function SituationRoomPage() {
  const queryClient = useQueryClient();
  const { subscribe, lastMessage, isConnected } = useWebSocket();
  const { toast } = useToast();
  const [selectedMode, setSelectedMode] = useState<string>('');
  const [showEmergencyDialog, setShowEmergencyDialog] = useState(false);

  // Queries
  const { data: statusData, isLoading: isLoadingStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => getSystemStatus() as Promise<{ data?: SystemStatus }>,
    refetchInterval: 5000,
  });

  const { data: servicesData, isLoading: isLoadingServices, refetch: refetchServices } = useQuery({
    queryKey: ['services-health'],
    queryFn: () => getServicesHealth() as Promise<{ data?: ServiceHealth[] }>,
    refetchInterval: 10000,
  });

  const { data: autoExecuteData, refetch: refetchAutoExecute } = useQuery({
    queryKey: ['auto-execute'],
    queryFn: () => getAutoExecute() as Promise<{ data?: { auto_execute: boolean } }>,
    refetchInterval: 30000,
  });

  const autoExecute = autoExecuteData?.data?.auto_execute ?? true;

  const rawStatus = statusData?.data;
  // Normalize the status - support both `running` and `is_running` field names
  const status = rawStatus ? {
    ...rawStatus,
    running: rawStatus.running ?? rawStatus.is_running ?? false,
  } : undefined;
  const services = servicesData?.data || [];

  // Set initial mode from status
  useEffect(() => {
    if (status?.mode && !selectedMode) {
      setSelectedMode(status.mode);
    }
  }, [status?.mode, selectedMode]);

  // Subscribe to WebSocket
  useEffect(() => {
    subscribe('system');
  }, [subscribe]);

  // Refetch on status changes
  useEffect(() => {
    if (lastMessage?.channel === 'system') {
      refetchStatus();
      refetchServices();
    }
  }, [lastMessage, refetchStatus, refetchServices]);

  // Mutations
  const controlMutation = useMutation({
    mutationFn: ({ action, reason }: { action: 'start' | 'stop' | 'emergency_stop'; reason?: string }) =>
      controlSystem(action, reason),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['system-status'] });
      const actionText = variables.action === 'start' ? 'started' : variables.action === 'stop' ? 'stopped' : 'emergency stopped';
      toast({
        title: 'System Control',
        description: `System ${actionText} successfully`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Control Failed',
        description: error.message || 'Failed to control system',
        variant: 'destructive',
      });
    },
  });

  const modeMutation = useMutation({
    mutationFn: ({ mode, reason }: { mode: string; reason?: string }) =>
      changeSystemMode(mode, reason),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['system-status'] });
      toast({
        title: 'Mode Changed',
        description: `System mode changed to ${variables.mode}`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Mode Change Failed',
        description: error.message || 'Failed to change system mode',
        variant: 'destructive',
      });
    },
  });

  const autoExecuteMutation = useMutation({
    mutationFn: (enabled: boolean) => setAutoExecute(enabled),
    onSuccess: (data, enabled) => {
      queryClient.invalidateQueries({ queryKey: ['auto-execute'] });
      toast({
        title: 'Auto-Execute Updated',
        description: `Auto-execution ${enabled ? 'enabled' : 'disabled'}`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Auto-Execute Update Failed',
        description: error.message || 'Failed to update auto-execute setting',
        variant: 'destructive',
      });
      refetchAutoExecute();
    },
  });

  const handleModeChange = (mode: string) => {
    setSelectedMode(mode);
    modeMutation.mutate({ mode });
  };

  const handleAutoExecuteChange = (enabled: boolean) => {
    autoExecuteMutation.mutate(enabled);
  };

  const handleStart = () => {
    controlMutation.mutate({ action: 'start' });
  };

  const handleStop = () => {
    controlMutation.mutate({ action: 'stop' });
  };

  const handleEmergencyStop = () => {
    controlMutation.mutate({ action: 'emergency_stop', reason: 'Manual emergency stop from UI' });
    setShowEmergencyDialog(false);
  };

  const healthyServices = services.filter((s) => s.status === 'healthy').length;
  const totalServices = services.length;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Radio className="h-8 w-8" />
              Situation Room
            </h1>
            <p className="text-muted-foreground">
              Control, monitor, and configure your trading bot
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn(
                'gap-1',
                isConnected ? 'text-green-500' : 'text-red-500'
              )}
            >
              <div
                className={cn(
                  'h-2 w-2 rounded-full',
                  isConnected ? 'bg-green-500' : 'bg-red-500'
                )}
              />
              {isConnected ? 'Connected' : 'Disconnected'}
            </Badge>
          </div>
        </div>

        {/* Control Panel */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Bot Controls</CardTitle>
            <CardDescription>Start, stop, and configure the trading bot</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-4">
              {/* Status Indicator */}
              <div className="flex items-center gap-3 pr-4 border-r">
                <div
                  className={cn(
                    'h-12 w-12 rounded-full flex items-center justify-center',
                    status?.running
                      ? 'bg-green-500/10 text-green-500'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {status?.running ? (
                    <Activity className="h-6 w-6 animate-pulse" />
                  ) : (
                    <Square className="h-6 w-6" />
                  )}
                </div>
                <div>
                  <p className="font-semibold">
                    {status?.running ? 'Running' : 'Stopped'}
                  </p>
                  {status?.running && status.uptime_seconds && (
                    <p className="text-sm text-muted-foreground">
                      Uptime: {formatUptime(status.uptime_seconds)}
                    </p>
                  )}
                </div>
              </div>

              {/* Start/Stop Button */}
              <Button
                size="lg"
                variant={status?.running ? 'outline' : 'default'}
                onClick={status?.running ? handleStop : handleStart}
                disabled={controlMutation.isPending}
                className="min-w-[120px]"
              >
                {controlMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : status?.running ? (
                  <Square className="h-4 w-4 mr-2" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                {status?.running ? 'Stop' : 'Start'}
              </Button>

              {/* Mode Selector */}
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Mode:</span>
                <Select
                  value={selectedMode}
                  onValueChange={handleModeChange}
                  disabled={modeMutation.isPending}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Select mode" />
                  </SelectTrigger>
                  <SelectContent>
                    {MODES.map((mode) => (
                      <SelectItem key={mode.value} value={mode.value}>
                        <div>
                          <div>{mode.label}</div>
                          <div className="text-xs text-muted-foreground">
                            {mode.description}
                          </div>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Auto-Execute Toggle */}
              <div className="flex items-center gap-2 pl-4 border-l">
                <Switch
                  id="auto-execute"
                  checked={autoExecute}
                  onCheckedChange={handleAutoExecuteChange}
                  disabled={autoExecuteMutation.isPending || !status?.running}
                />
                <Label
                  htmlFor="auto-execute"
                  className={cn(
                    "text-sm font-medium cursor-pointer",
                    !status?.running && "text-muted-foreground"
                  )}
                >
                  Auto-Execute
                </Label>
                <span className="text-xs text-muted-foreground hidden sm:inline">
                  (UOS &ge; 75)
                </span>
                {/* Show override conditions */}
                {!status?.running && (
                  <Badge variant="outline" className="text-xs text-yellow-600 border-yellow-600">
                    System stopped
                  </Badge>
                )}
                {status?.running && status?.mode === 'discovery' && (
                  <Badge variant="outline" className="text-xs text-blue-600 border-blue-600">
                    Discovery mode
                  </Badge>
                )}
                {status?.running && status?.mode === 'maintenance' && (
                  <Badge variant="outline" className="text-xs text-orange-600 border-orange-600">
                    Maintenance
                  </Badge>
                )}
              </div>

              <div className="flex-1" />

              {/* Emergency Stop */}
              <AlertDialog open={showEmergencyDialog} onOpenChange={setShowEmergencyDialog}>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="lg">
                    <AlertOctagon className="h-4 w-4 mr-2" />
                    Emergency Stop
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Emergency Stop</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will immediately halt all trading operations and close any pending
                      orders. Active positions will remain open but no new actions will be taken.
                      Are you sure you want to proceed?
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleEmergencyStop}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Confirm Emergency Stop
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </CardContent>
        </Card>

        {/* System Status & Risk Overview */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Services Health */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Server className="h-5 w-5" />
                    System Status
                  </CardTitle>
                  <CardDescription>
                    {healthyServices}/{totalServices} services healthy
                  </CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={() => refetchServices()}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {isLoadingServices ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {services.map((service) => (
                    <ServiceControlCard
                      key={service.name}
                      service={service}
                      displayName={SERVICE_DISPLAY_NAMES[service.name] || service.name}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Risk Overview */}
          <RiskOverviewPanel />
        </div>

        {/* Activity Log */}
        <ActivityLogEnhanced maxHeight="500px" />
      </div>
    </DashboardLayout>
  );
}
