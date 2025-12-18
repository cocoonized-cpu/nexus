'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Terminal,
  Pause,
  Play,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';

interface LogEntry {
  timestamp: string;
  service: string;
  level: string;
  message: string;
  container: string;
  details?: Record<string, unknown>;
}

interface SystemLogPanelProps {
  className?: string;
  maxHeight?: string;
}

const SERVICES = [
  { value: 'all', label: 'All Services' },
  { value: 'gateway', label: 'Gateway' },
  { value: 'opportunity-detector', label: 'Opportunity Detector' },
  { value: 'position-manager', label: 'Position Manager' },
  { value: 'execution-engine', label: 'Execution Engine' },
  { value: 'funding-aggregator', label: 'Funding Aggregator' },
  { value: 'data-collector', label: 'Data Collector' },
  { value: 'risk-manager', label: 'Risk Manager' },
  { value: 'capital-allocator', label: 'Capital Allocator' },
];

const LEVELS = [
  { value: 'all', label: 'All Levels' },
  { value: 'error', label: 'Error' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
  { value: 'debug', label: 'Debug' },
];

const LEVEL_COLORS: Record<string, string> = {
  error: 'text-red-500 bg-red-500/10',
  warning: 'text-yellow-500 bg-yellow-500/10',
  info: 'text-blue-500 bg-blue-500/10',
  debug: 'text-gray-500 bg-gray-500/10',
};

const SERVICE_COLORS: Record<string, string> = {
  gateway: 'text-purple-500',
  'opportunity-detector': 'text-green-500',
  'position-manager': 'text-blue-500',
  'execution-engine': 'text-orange-500',
  'funding-aggregator': 'text-cyan-500',
  'data-collector': 'text-pink-500',
  'risk-manager': 'text-red-500',
  'capital-allocator': 'text-yellow-500',
};

export function SystemLogPanel({ className, maxHeight = '400px' }: SystemLogPanelProps) {
  const [selectedService, setSelectedService] = useState<string>('all');
  const [selectedLevel, setSelectedLevel] = useState<string>('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Fetch logs from API
  const { data: logsData, isLoading, refetch } = useQuery({
    queryKey: ['system-logs', selectedService, selectedLevel],
    queryFn: async () => {
      const services = selectedService === 'all'
        ? 'gateway,opportunity-detector,position-manager,execution-engine,funding-aggregator'
        : selectedService;
      const url = `/api/v1/system/logs/aggregate?tail=100&services=${services}${selectedLevel !== 'all' ? `&level=${selectedLevel}` : ''}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch logs');
      return response.json();
    },
    refetchInterval: autoScroll ? 5000 : false,
  });

  const logs: LogEntry[] = logsData?.data || [];

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const formatTimestamp = (ts: string) => {
    try {
      const date = new Date(ts);
      return date.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return ts.slice(11, 19);
    }
  };

  const toggleAutoScroll = useCallback(() => {
    setAutoScroll((prev) => !prev);
  }, []);

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Terminal className="h-5 w-5" />
              System Logs
            </CardTitle>
            <CardDescription>
              Real-time Docker container logs
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {/* Service Filter */}
            <Select value={selectedService} onValueChange={setSelectedService}>
              <SelectTrigger className="w-[160px] h-8 text-xs">
                <SelectValue placeholder="Service" />
              </SelectTrigger>
              <SelectContent>
                {SERVICES.map((svc) => (
                  <SelectItem key={svc.value} value={svc.value}>
                    {svc.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Level Filter */}
            <Select value={selectedLevel} onValueChange={setSelectedLevel}>
              <SelectTrigger className="w-[120px] h-8 text-xs">
                <SelectValue placeholder="Level" />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((lvl) => (
                  <SelectItem key={lvl.value} value={lvl.value}>
                    {lvl.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Auto-scroll toggle */}
            <Button
              variant="outline"
              size="sm"
              onClick={toggleAutoScroll}
              className={cn(
                'h-8 w-8 p-0',
                autoScroll && 'bg-green-500/10 text-green-500'
              )}
              title={autoScroll ? 'Pause auto-scroll' : 'Resume auto-scroll'}
            >
              {autoScroll ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4" />
              )}
            </Button>

            {/* Refresh */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="h-8 w-8 p-0"
              title="Refresh logs"
            >
              <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
            </Button>

            {/* Expand/Collapse */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="h-8 w-8 p-0"
              title={expanded ? 'Collapse' : 'Expand'}
            >
              {expanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div
          ref={logContainerRef}
          className="font-mono text-xs bg-black/90 rounded-md p-3 overflow-y-auto transition-all duration-200"
          style={{ maxHeight: expanded ? '600px' : maxHeight }}
        >
          {isLoading && logs.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading logs...
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              No logs available. Check if Docker is running.
            </div>
          ) : (
            <div className="space-y-1">
              {logs.map((log, index) => (
                <div
                  key={`${log.timestamp}-${index}`}
                  className="flex items-start gap-2 hover:bg-white/5 py-0.5 px-1 rounded"
                >
                  {/* Timestamp */}
                  <span className="text-gray-500 shrink-0">
                    {formatTimestamp(log.timestamp)}
                  </span>

                  {/* Service */}
                  <span
                    className={cn(
                      'shrink-0 w-24 truncate',
                      SERVICE_COLORS[log.service] || 'text-gray-400'
                    )}
                  >
                    [{log.service}]
                  </span>

                  {/* Level */}
                  <Badge
                    variant="outline"
                    className={cn(
                      'shrink-0 h-5 text-[10px] px-1',
                      LEVEL_COLORS[log.level] || 'text-gray-400'
                    )}
                  >
                    {log.level.toUpperCase()}
                  </Badge>

                  {/* Message */}
                  <span
                    className={cn(
                      'flex-1 break-words',
                      log.level === 'error' && 'text-red-400',
                      log.level === 'warning' && 'text-yellow-400',
                      log.level === 'info' && 'text-gray-200',
                      log.level === 'debug' && 'text-gray-500'
                    )}
                  >
                    {log.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Status Bar */}
        <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
          <span>{logs.length} log entries</span>
          <div className="flex items-center gap-2">
            {autoScroll && (
              <Badge variant="outline" className="text-[10px] text-green-500 border-green-500/50">
                Auto-updating
              </Badge>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
