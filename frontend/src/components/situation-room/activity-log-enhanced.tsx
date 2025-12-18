'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Toggle } from '@/components/ui/toggle';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Search,
  Filter,
  Pause,
  Play,
  ChevronDown,
  AlertCircle,
  AlertTriangle,
  Info,
  Bug,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getRecentEvents } from '@/lib/api';
import { useWebSocket } from '@/lib/websocket';

export type LogLevel = 'INFO' | 'WARNING' | 'DEBUG' | 'ERROR';
export type LogCategory = 'funding' | 'opportunity' | 'risk' | 'execution' | 'system' | 'position';

interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  category: LogCategory;
  source: string;
  message: string;
  details?: Record<string, unknown>;
}

// API response format (different from LogEntry)
interface APIEvent {
  source: string;
  event_type: string;
  resource: string;
  details?: Record<string, unknown>;
  timestamp: string;
}

// Map event_type to log level
function getLogLevel(eventType: string, source: string): LogLevel {
  if (eventType.includes('error') || eventType.includes('fail')) return 'ERROR';
  if (eventType.includes('warning') || eventType.includes('alert') || source === 'risk') return 'WARNING';
  if (eventType.includes('debug')) return 'DEBUG';
  return 'INFO';
}

// Map source to category
function getCategory(source: string, resource: string): LogCategory {
  if (source === 'opportunity') return 'opportunity';
  if (source === 'risk') return 'risk';
  if (source === 'execution') return 'execution';
  if (source === 'funding') return 'funding';
  if (source === 'position') return 'position';
  return 'system';
}

// Generate human-readable message
function generateMessage(eventType: string, resource: string, details?: Record<string, unknown>): string {
  const type = eventType.replace(/_/g, ' ');

  // Special cases for common events
  if (eventType === 'system_start') return 'System started';
  if (eventType === 'system_stop') return 'System stopped';
  if (eventType === 'mode_change') {
    const newMode = details?.new_mode || 'unknown';
    const prevMode = details?.previous_mode;
    return prevMode ? `Mode changed from ${prevMode} to ${newMode}` : `Mode changed to ${newMode}`;
  }
  if (eventType === 'opportunity_detected') {
    const score = details?.uos_score ? `(UOS: ${Number(details.uos_score).toFixed(1)})` : '';
    return `Opportunity detected: ${resource} ${score}`;
  }
  if (eventType.includes('alert')) {
    return details?.message ? String(details.message) : `${type} on ${resource}`;
  }

  // Position events
  if (eventType === 'position_opened') {
    const capital = details?.capital_deployed ? ` ($${Number(details.capital_deployed).toFixed(0)})` : '';
    return `Position opened: ${resource}${capital}`;
  }
  if (eventType === 'position_closed') {
    const pnl = details?.realized_pnl !== undefined
      ? ` PnL: $${Number(details.realized_pnl).toFixed(2)}`
      : '';
    const reason = details?.exit_reason ? ` (${details.exit_reason})` : '';
    return `Position closed: ${resource}${pnl}${reason}`;
  }
  if (eventType === 'funding_received') {
    const amount = details?.amount ? ` +$${Number(details.amount).toFixed(4)}` : '';
    return `Funding received: ${resource}${amount}`;
  }
  if (eventType === 'funding_paid') {
    const amount = details?.amount ? ` -$${Math.abs(Number(details.amount)).toFixed(4)}` : '';
    return `Funding paid: ${resource}${amount}`;
  }
  if (eventType === 'health_changed') {
    const oldHealth = details?.old_health || 'unknown';
    const newHealth = details?.new_health || 'unknown';
    return `Position health changed: ${resource} ${oldHealth} → ${newHealth}`;
  }
  if (eventType === 'rebalance_triggered') {
    return `Rebalance triggered: ${resource}`;
  }
  if (eventType === 'stop_loss_triggered') {
    const price = details?.trigger_price ? ` at $${Number(details.trigger_price).toFixed(2)}` : '';
    return `Stop loss triggered: ${resource}${price}`;
  }
  if (eventType === 'take_profit_triggered') {
    const pnl = details?.realized_pnl ? ` PnL: $${Number(details.realized_pnl).toFixed(2)}` : '';
    return `Take profit triggered: ${resource}${pnl}`;
  }

  return `${type}: ${resource}`;
}

// Transform API event to LogEntry
function transformEvent(event: APIEvent, index: number): LogEntry {
  return {
    id: `${event.timestamp}-${index}`,
    timestamp: event.timestamp,
    level: getLogLevel(event.event_type, event.source),
    category: getCategory(event.source, event.resource),
    source: event.source,
    message: generateMessage(event.event_type, event.resource, event.details),
    details: event.details,
  };
}

interface ActivityFilters {
  levels: Set<LogLevel>;
  categories: Set<LogCategory>;
  sources: Set<string>;
  searchTerm: string;
}

const LEVEL_CONFIG: Record<LogLevel, {
  color: string;
  bgColor: string;
  Icon: typeof Info;
}> = {
  INFO: {
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
    Icon: Info,
  },
  WARNING: {
    color: 'text-yellow-500',
    bgColor: 'bg-yellow-500/10',
    Icon: AlertTriangle,
  },
  DEBUG: {
    color: 'text-gray-500',
    bgColor: 'bg-gray-500/10',
    Icon: Bug,
  },
  ERROR: {
    color: 'text-red-500',
    bgColor: 'bg-red-500/10',
    Icon: AlertCircle,
  },
};

const CATEGORY_COLORS: Record<LogCategory, string> = {
  funding: 'bg-green-500',
  opportunity: 'bg-purple-500',
  risk: 'bg-red-500',
  execution: 'bg-orange-500',
  system: 'bg-blue-500',
  position: 'bg-cyan-500',
};

const ALL_LEVELS: LogLevel[] = ['INFO', 'WARNING', 'DEBUG', 'ERROR'];
const ALL_CATEGORIES: LogCategory[] = ['funding', 'opportunity', 'risk', 'execution', 'system', 'position'];

interface ActivityLogEnhancedProps {
  maxHeight?: string;
  className?: string;
}

export function ActivityLogEnhanced({ maxHeight = '400px', className }: ActivityLogEnhancedProps) {
  const { subscribe, lastMessage } = useWebSocket();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<ActivityFilters>({
    levels: new Set<LogLevel>(['INFO', 'WARNING', 'ERROR']),
    categories: new Set<LogCategory>(ALL_CATEGORIES),
    sources: new Set<string>(),
    searchTerm: '',
  });

  // Fetch initial events
  const { data: eventsData, refetch } = useQuery({
    queryKey: ['events'],
    queryFn: () => getRecentEvents(100) as Promise<{ data?: APIEvent[] }>,
    refetchInterval: isPaused ? false : 5000,
  });

  // Transform API events to LogEntry format
  const events: LogEntry[] = useMemo(() => {
    const apiEvents = eventsData?.data || [];
    return apiEvents.map((event, index) => transformEvent(event, index));
  }, [eventsData]);

  // Extract unique sources from events
  const availableSources = useMemo(() => {
    const sources = new Set<string>();
    events.forEach((event) => sources.add(event.source));
    return Array.from(sources).sort();
  }, [events]);

  // Subscribe to WebSocket
  useEffect(() => {
    subscribe('system');
    subscribe('events');
  }, [subscribe]);

  // Refetch on new messages
  useEffect(() => {
    if (lastMessage?.channel === 'system' || lastMessage?.channel === 'events') {
      refetch();
    }
  }, [lastMessage, refetch]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (!isPaused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, isPaused]);

  // Filter events
  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      // Level filter
      if (!filters.levels.has(event.level)) return false;

      // Category filter
      if (!filters.categories.has(event.category)) return false;

      // Source filter (if any sources are selected)
      if (filters.sources.size > 0 && !filters.sources.has(event.source)) return false;

      // Search term
      if (filters.searchTerm) {
        const searchLower = filters.searchTerm.toLowerCase();
        return (
          event.message.toLowerCase().includes(searchLower) ||
          event.source.toLowerCase().includes(searchLower) ||
          event.category.toLowerCase().includes(searchLower)
        );
      }

      return true;
    });
  }, [events, filters]);

  // Toggle functions
  const toggleLevel = (level: LogLevel) => {
    setFilters((prev) => {
      const newLevels = new Set(prev.levels);
      if (newLevels.has(level)) {
        newLevels.delete(level);
      } else {
        newLevels.add(level);
      }
      return { ...prev, levels: newLevels };
    });
  };

  const toggleCategory = (category: LogCategory) => {
    setFilters((prev) => {
      const newCategories = new Set(prev.categories);
      if (newCategories.has(category)) {
        newCategories.delete(category);
      } else {
        newCategories.add(category);
      }
      return { ...prev, categories: newCategories };
    });
  };

  const toggleSource = (source: string) => {
    setFilters((prev) => {
      const newSources = new Set(prev.sources);
      if (newSources.has(source)) {
        newSources.delete(source);
      } else {
        newSources.add(source);
      }
      return { ...prev, sources: newSources };
    });
  };

  const toggleEntryExpanded = (id: string) => {
    setExpandedEntries((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Activity Log</CardTitle>
            <CardDescription>Real-time system events and notifications</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsPaused(!isPaused)}
            >
              {isPaused ? (
                <>
                  <Play className="h-4 w-4 mr-1" />
                  Resume
                </>
              ) : (
                <>
                  <Pause className="h-4 w-4 mr-1" />
                  Pause
                </>
              )}
            </Button>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2 mt-4">
          {/* Level toggles */}
          <div className="flex items-center gap-1">
            {ALL_LEVELS.map((level) => {
              const config = LEVEL_CONFIG[level];
              return (
                <Toggle
                  key={level}
                  size="sm"
                  pressed={filters.levels.has(level)}
                  onPressedChange={() => toggleLevel(level)}
                  className={cn(
                    'gap-1 text-xs',
                    filters.levels.has(level) && config.bgColor
                  )}
                >
                  <config.Icon className={cn('h-3 w-3', config.color)} />
                  {level}
                </Toggle>
              );
            })}
          </div>

          <div className="h-4 w-px bg-border" />

          {/* Category dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <Filter className="h-4 w-4 mr-1" />
                Categories
                <ChevronDown className="h-3 w-3 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuLabel>Filter by Category</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {ALL_CATEGORIES.map((category) => (
                <DropdownMenuCheckboxItem
                  key={category}
                  checked={filters.categories.has(category)}
                  onCheckedChange={() => toggleCategory(category)}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        'h-2 w-2 rounded-full',
                        CATEGORY_COLORS[category]
                      )}
                    />
                    <span className="capitalize">{category}</span>
                  </div>
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Source dropdown */}
          {availableSources.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  Sources
                  {filters.sources.size > 0 && (
                    <Badge variant="secondary" className="ml-1 h-4 px-1 text-xs">
                      {filters.sources.size}
                    </Badge>
                  )}
                  <ChevronDown className="h-3 w-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuLabel>Filter by Source</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {availableSources.map((source) => (
                  <DropdownMenuCheckboxItem
                    key={source}
                    checked={filters.sources.has(source)}
                    onCheckedChange={() => toggleSource(source)}
                  >
                    {source}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <div className="flex-1" />

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search..."
              value={filters.searchTerm}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, searchTerm: e.target.value }))
              }
              className="h-8 w-[200px] pl-8"
            />
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <ScrollArea
          className="px-4"
          style={{ height: maxHeight }}
          ref={scrollRef}
        >
          <div className="space-y-1 py-2">
            {filteredEvents.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No events match the current filters
              </div>
            ) : (
              filteredEvents.map((event) => {
                const levelConfig = LEVEL_CONFIG[event.level];
                const isExpanded = expandedEntries.has(event.id);

                return (
                  <div
                    key={event.id}
                    className={cn(
                      'group rounded-lg px-3 py-2 hover:bg-muted/50 cursor-pointer transition-colors',
                      isExpanded && 'bg-muted/50'
                    )}
                    onClick={() => event.details && toggleEntryExpanded(event.id)}
                  >
                    <div className="flex items-start gap-3">
                      {/* Level icon */}
                      <div
                        className={cn(
                          'mt-0.5 rounded-full p-1',
                          levelConfig.bgColor
                        )}
                      >
                        <levelConfig.Icon
                          className={cn('h-3 w-3', levelConfig.color)}
                        />
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs text-muted-foreground font-mono">
                            {formatTimestamp(event.timestamp)}
                          </span>
                          <Badge
                            variant="outline"
                            className={cn(
                              'h-4 px-1.5 text-[10px] font-normal',
                              levelConfig.color
                            )}
                          >
                            {event.level}
                          </Badge>
                          <Badge
                            variant="outline"
                            className="h-4 px-1.5 text-[10px] font-normal capitalize"
                          >
                            <div
                              className={cn(
                                'h-1.5 w-1.5 rounded-full mr-1',
                                CATEGORY_COLORS[event.category]
                              )}
                            />
                            {event.category}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {event.source}
                          </span>
                        </div>
                        <p className="text-sm mt-1 break-words">{event.message}</p>

                        {/* Expanded details */}
                        {isExpanded && event.details && (
                          <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-x-auto">
                            {JSON.stringify(event.details, null, 2)}
                          </pre>
                        )}
                      </div>

                      {/* Expand indicator */}
                      {event.details && (
                        <ChevronDown
                          className={cn(
                            'h-4 w-4 text-muted-foreground transition-transform',
                            isExpanded && 'rotate-180'
                          )}
                        />
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
