'use client';

import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Activity,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Zap,
  Eye,
  EyeOff,
  Calculator,
  Brain,
  ArrowRightLeft
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ActivityEntry {
  id: string;
  timestamp: Date;
  type: 'metric' | 'decision' | 'action' | 'alert' | 'info';
  category: string;
  message: string;
  details?: Record<string, any>;
}

const categoryIcons: Record<string, React.ElementType> = {
  'funding': TrendingUp,
  'opportunity': Zap,
  'risk': AlertTriangle,
  'execution': ArrowRightLeft,
  'calculation': Calculator,
  'decision': Brain,
  'system': Activity,
};

const typeColors: Record<string, string> = {
  'metric': 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  'decision': 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  'action': 'bg-green-500/10 text-green-500 border-green-500/20',
  'alert': 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  'info': 'bg-gray-500/10 text-gray-500 border-gray-500/20',
};

export function ActivityLog() {
  const [enabled, setEnabled] = useState(false);
  const [activities, setActivities] = useState<ActivityEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enabled) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    // Connect to WebSocket for real-time updates
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Subscribe to all activity channels
      ws.send(JSON.stringify({ action: 'subscribe', channel: 'system' }));
      ws.send(JSON.stringify({ action: 'subscribe', channel: 'opportunities' }));
      ws.send(JSON.stringify({ action: 'subscribe', channel: 'risk' }));
      ws.send(JSON.stringify({ action: 'subscribe', channel: 'funding_rates' }));

      addActivity({
        type: 'info',
        category: 'system',
        message: 'Connected to real-time activity feed',
      });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      addActivity({
        type: 'alert',
        category: 'system',
        message: 'Disconnected from real-time feed',
      });
    };

    ws.onerror = () => {
      setConnected(false);
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [enabled]);

  const addActivity = (entry: Omit<ActivityEntry, 'id' | 'timestamp'>) => {
    const newEntry: ActivityEntry = {
      ...entry,
      id: Math.random().toString(36).substr(2, 9),
      timestamp: new Date(),
    };
    setActivities(prev => [newEntry, ...prev].slice(0, 100)); // Keep last 100 entries
  };

  const handleWebSocketMessage = (data: any) => {
    const { event, channel, data: eventData } = data;

    if (event === 'subscribed') {
      addActivity({
        type: 'info',
        category: 'system',
        message: `Subscribed to ${channel} updates`,
      });
      return;
    }

    // Handle activity events from services (format: {type, service, level, message, details})
    if (channel === 'system' && eventData?.service) {
      // Map service level to activity type
      const levelToType: Record<string, 'metric' | 'decision' | 'action' | 'alert' | 'info'> = {
        'info': 'info',
        'warning': 'alert',
        'error': 'alert',
        'debug': 'info',
      };

      // Map event type to category
      const typeToCategory: Record<string, string> = {
        'position_health_changed': 'risk',
        'health_check_complete': 'system',
        'exit_triggered': 'execution',
        'funding_collected': 'funding',
        'positions_adopted': 'system',
        'position_opened': 'execution',
        'position_closed': 'execution',
        'opportunity_detected': 'opportunity',
        'opportunity_scored': 'opportunity',
      };

      addActivity({
        type: levelToType[eventData.level] || 'info',
        category: typeToCategory[eventData.type] || eventData.service || 'system',
        message: eventData.message || eventData.type || 'Activity event',
        details: eventData.details,
      });
      return;
    }

    // Map other WebSocket events to activity entries
    switch (channel) {
      case 'funding_rates':
        addActivity({
          type: 'metric',
          category: 'funding',
          message: `Funding rate update received`,
          details: eventData,
        });
        break;
      case 'opportunities':
        addActivity({
          type: 'decision',
          category: 'opportunity',
          message: `Opportunity ${event}: ${eventData?.symbol || 'Unknown'}`,
          details: eventData,
        });
        break;
      case 'risk':
        addActivity({
          type: 'alert',
          category: 'risk',
          message: `Risk event: ${event}`,
          details: eventData,
        });
        break;
      case 'system':
        addActivity({
          type: 'info',
          category: 'system',
          message: eventData?.message || event,
          details: eventData,
        });
        break;
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Activity Log
            </CardTitle>
            <CardDescription>
              Real-time bot activity, metrics, and decisions
            </CardDescription>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant={connected ? 'default' : 'secondary'} className="gap-1">
              <span className={cn(
                'h-2 w-2 rounded-full',
                connected ? 'bg-green-500 animate-pulse' : 'bg-gray-500'
              )} />
              {connected ? 'Live' : 'Offline'}
            </Badge>
            <div className="flex items-center gap-2">
              {enabled ? (
                <Eye className="h-4 w-4 text-muted-foreground" />
              ) : (
                <EyeOff className="h-4 w-4 text-muted-foreground" />
              )}
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {!enabled ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <EyeOff className="h-12 w-12 text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">
              Enable the activity log to see real-time bot operations
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              View every metric calculation, decision, and action
            </p>
          </div>
        ) : (
          <div className="h-[400px] overflow-y-auto pr-4" ref={scrollRef}>
            <div className="space-y-2">
              {activities.length === 0 ? (
                <div className="flex items-center justify-center py-8">
                  <p className="text-sm text-muted-foreground">
                    Waiting for activity...
                  </p>
                </div>
              ) : (
                activities.map((entry) => {
                  const Icon = categoryIcons[entry.category] || Activity;
                  return (
                    <div
                      key={entry.id}
                      className={cn(
                        'flex items-start gap-3 p-3 rounded-lg border',
                        typeColors[entry.type]
                      )}
                    >
                      <Icon className="h-4 w-4 mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline" className="text-xs">
                            {entry.category}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatTime(entry.timestamp)}
                          </span>
                        </div>
                        <p className="text-sm">{entry.message}</p>
                        {entry.details && (
                          <details className="mt-2">
                            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                              View details
                            </summary>
                            <pre className="mt-1 text-xs bg-background/50 p-2 rounded overflow-x-auto">
                              {JSON.stringify(entry.details, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
