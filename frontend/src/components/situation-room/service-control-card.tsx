'use client';

import { useState, useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  CheckCircle2,
  XCircle,
  Activity,
  RefreshCw,
  FileText,
  Loader2,
  AlertTriangle,
  Search,
  Filter,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { restartService, getServiceLogs } from '@/lib/api';
import { useToast } from '@/components/ui/use-toast';

type LogLevel = 'all' | 'error' | 'warning' | 'info' | 'debug';

interface ServiceHealth {
  name: string;
  display_name?: string;
  status: 'healthy' | 'unhealthy' | 'degraded' | 'unknown' | 'offline';
  last_heartbeat?: string;
  uptime_seconds?: number;
  critical?: boolean;
  details?: Record<string, unknown>;
}

interface ServiceControlCardProps {
  service: ServiceHealth;
  displayName: string;
}

export function ServiceControlCard({ service, displayName }: ServiceControlCardProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showLogsDialog, setShowLogsDialog] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);

  // Filter state
  const [logLevel, setLogLevel] = useState<LogLevel>('all');
  const [searchText, setSearchText] = useState('');
  const [lineCount, setLineCount] = useState<string>('100');

  // Restart mutation
  const restartMutation = useMutation({
    mutationFn: () => restartService(service.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services-health'] });
      toast({
        title: 'Service Restarting',
        description: `${displayName} is being restarted...`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Restart Failed',
        description: error.message || `Failed to restart ${displayName}`,
        variant: 'destructive',
      });
    },
  });

  // Fetch logs
  const fetchLogs = async (lines: number) => {
    setIsLoadingLogs(true);
    try {
      const response = await getServiceLogs(service.name, lines) as {
        data?: { lines: string[] };
      };
      setLogs(response.data?.lines || []);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch logs';
      toast({
        title: 'Error',
        description: errorMessage,
        variant: 'destructive',
      });
      setLogs([`Error fetching logs: ${errorMessage}`]);
    } finally {
      setIsLoadingLogs(false);
    }
  };

  const handleViewLogs = async () => {
    setShowLogsDialog(true);
    await fetchLogs(parseInt(lineCount, 10));
  };

  const handleRefreshLogs = async () => {
    await fetchLogs(parseInt(lineCount, 10));
  };

  // Filter logs based on level and search text
  const filteredLogs = useMemo(() => {
    return logs.filter((line) => {
      const lowerLine = line.toLowerCase();

      // Level filter
      if (logLevel !== 'all') {
        const hasError = lowerLine.includes('error') || lowerLine.includes('[error]');
        const hasWarning = lowerLine.includes('warn') || lowerLine.includes('[warn');
        const hasInfo = lowerLine.includes('info') || lowerLine.includes('[info]');
        const hasDebug = lowerLine.includes('debug') || lowerLine.includes('[debug]');

        switch (logLevel) {
          case 'error':
            if (!hasError) return false;
            break;
          case 'warning':
            if (!hasWarning) return false;
            break;
          case 'info':
            if (!hasInfo) return false;
            break;
          case 'debug':
            if (!hasDebug) return false;
            break;
        }
      }

      // Search filter
      if (searchText) {
        if (!lowerLine.includes(searchText.toLowerCase())) return false;
      }

      return true;
    });
  }, [logs, logLevel, searchText]);

  // Get log level from line for coloring
  const getLogLevelFromLine = (line: string): LogLevel => {
    const lowerLine = line.toLowerCase();
    if (lowerLine.includes('error') || lowerLine.includes('[error]')) return 'error';
    if (lowerLine.includes('warn') || lowerLine.includes('[warn')) return 'warning';
    if (lowerLine.includes('debug') || lowerLine.includes('[debug]')) return 'debug';
    if (lowerLine.includes('info') || lowerLine.includes('[info]')) return 'info';
    return 'all';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500/5 border-green-500/20';
      case 'degraded':
        return 'bg-yellow-500/5 border-yellow-500/20';
      case 'unhealthy':
      case 'offline':
        return 'bg-red-500/5 border-red-500/20';
      default:
        return 'bg-muted border-muted';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case 'degraded':
        return <Activity className="h-4 w-4 text-yellow-500" />;
      case 'unhealthy':
      case 'offline':
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'text-green-500';
      case 'degraded':
        return 'text-yellow-500';
      case 'unhealthy':
      case 'offline':
        return 'text-red-500';
      default:
        return 'text-muted-foreground';
    }
  };

  return (
    <TooltipProvider>
      <div
        className={cn(
          'flex items-center justify-between p-3 rounded-lg border',
          getStatusColor(service.status)
        )}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {getStatusIcon(service.status)}
          <div className="min-w-0">
            <span className="text-sm font-medium truncate block">{displayName}</span>
            {service.critical && (
              <span className="text-[10px] text-muted-foreground">Critical</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={cn('text-xs capitalize', getStatusBadgeColor(service.status))}
          >
            {service.status}
          </Badge>

          {/* Logs Button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={handleViewLogs}
              >
                <FileText className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>View Logs</TooltipContent>
          </Tooltip>

          {/* Restart Button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => restartMutation.mutate()}
                disabled={restartMutation.isPending}
              >
                {restartMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Restart Service</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Logs Dialog */}
      <Dialog open={showLogsDialog} onOpenChange={setShowLogsDialog}>
        <DialogContent className="max-w-5xl max-h-[85vh] w-[90vw]">
          <DialogHeader>
            <div className="flex items-center justify-between">
              <div>
                <DialogTitle>{displayName} Logs</DialogTitle>
                <DialogDescription>
                  Showing {filteredLogs.length} of {logs.length} log entries
                </DialogDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRefreshLogs}
                disabled={isLoadingLogs}
              >
                {isLoadingLogs ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Refresh
              </Button>
            </div>
          </DialogHeader>

          {/* Filters */}
          <div className="flex flex-wrap gap-3 items-center py-2 border-b">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search logs..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="pl-8 h-8 text-xs"
              />
            </div>

            {/* Log Level Filter */}
            <div className="flex items-center gap-2">
              <Filter className="h-3.5 w-3.5 text-muted-foreground" />
              <Select value={logLevel} onValueChange={(v) => setLogLevel(v as LogLevel)}>
                <SelectTrigger className="w-[120px] h-8 text-xs">
                  <SelectValue placeholder="Log Level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="error">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-red-500" />
                      Errors
                    </span>
                  </SelectItem>
                  <SelectItem value="warning">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-yellow-500" />
                      Warnings
                    </span>
                  </SelectItem>
                  <SelectItem value="info">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-500" />
                      Info
                    </span>
                  </SelectItem>
                  <SelectItem value="debug">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-gray-500" />
                      Debug
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Line Count */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Lines:</span>
              <Select value={lineCount} onValueChange={(v) => { setLineCount(v); fetchLogs(parseInt(v, 10)); }}>
                <SelectTrigger className="w-[80px] h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                  <SelectItem value="200">200</SelectItem>
                  <SelectItem value="500">500</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <ScrollArea className="h-[500px] rounded-md border bg-black/90 p-3">
            {isLoadingLogs ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : filteredLogs.length === 0 ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                {logs.length === 0 ? 'No logs available' : 'No logs match the current filters'}
              </div>
            ) : (
              <pre className="text-[11px] font-mono leading-relaxed">
                {filteredLogs.map((line, index) => {
                  const level = getLogLevelFromLine(line);
                  return (
                    <div
                      key={index}
                      className={cn(
                        'py-0.5 hover:bg-white/5 px-1 rounded',
                        level === 'error' && 'text-red-400',
                        level === 'warning' && 'text-yellow-400',
                        level === 'info' && 'text-blue-400',
                        level === 'debug' && 'text-gray-400',
                        level === 'all' && 'text-gray-300'
                      )}
                    >
                      {line}
                    </div>
                  );
                })}
              </pre>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}
