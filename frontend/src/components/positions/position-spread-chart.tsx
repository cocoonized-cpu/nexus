'use client';

import { useState, useEffect } from 'react';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getPositionSpreadHistory, SpreadHistoryResponse } from '@/lib/api';
import { TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react';

interface PositionSpreadChartProps {
  positionId: string;
  initialData?: SpreadHistoryResponse;
}

const TIME_RANGES = [
  { label: '1H', hours: 1 },
  { label: '4H', hours: 4 },
  { label: '24H', hours: 24 },
  { label: '7D', hours: 168 },
];

export function PositionSpreadChart({ positionId, initialData }: PositionSpreadChartProps) {
  const [data, setData] = useState<SpreadHistoryResponse | null>(initialData || null);
  const [selectedRange, setSelectedRange] = useState(24);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async (hours: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getPositionSpreadHistory(positionId, hours);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load spread history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!initialData) {
      fetchData(selectedRange);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionId]);

  const handleRangeChange = (hours: number) => {
    setSelectedRange(hours);
    fetchData(hours);
  };

  // Format chart data
  const chartData = data?.snapshots.map((snapshot) => ({
    time: new Date(snapshot.timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    }),
    fullTime: new Date(snapshot.timestamp).toLocaleString(),
    spread: snapshot.spread * 100, // Convert to percentage
    longRate: snapshot.long_rate ? snapshot.long_rate * 100 : null,
    shortRate: snapshot.short_rate ? snapshot.short_rate * 100 : null,
    price: snapshot.price,
  })) || [];

  // Entry spread reference line
  const entrySpread = data?.initial_spread ? data.initial_spread * 100 : null;

  // Trend icon
  const TrendIcon = data?.spread_trend === 'rising'
    ? TrendingUp
    : data?.spread_trend === 'falling'
      ? TrendingDown
      : Minus;

  const trendColor = data?.spread_trend === 'rising'
    ? 'text-green-500'
    : data?.spread_trend === 'falling'
      ? 'text-red-500'
      : 'text-gray-500';

  // Drawdown badge color
  const getDrawdownColor = (pct: number | null) => {
    if (pct === null) return 'default';
    if (pct >= 50) return 'destructive';
    if (pct >= 30) return 'warning';
    return 'secondary';
  };

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Funding Spread Chart</CardTitle>
          <div className="flex items-center gap-2">
            {/* Time range selector */}
            <div className="flex gap-1">
              {TIME_RANGES.map(({ label, hours }) => (
                <Button
                  key={hours}
                  variant={selectedRange === hours ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleRangeChange(hours)}
                  disabled={loading}
                >
                  {label}
                </Button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fetchData(selectedRange)}
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Metrics row */}
        {data && (
          <div className="flex flex-wrap items-center gap-4 mt-2 text-sm">
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Entry:</span>
              <span className="font-mono font-medium">
                {data.initial_spread !== null
                  ? `${(data.initial_spread * 100).toFixed(4)}%`
                  : '-'}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Current:</span>
              <span className="font-mono font-medium">
                {data.current_spread !== null
                  ? `${(data.current_spread * 100).toFixed(4)}%`
                  : '-'}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Drawdown:</span>
              <Badge variant={getDrawdownColor(data.spread_drawdown_pct) as 'default' | 'secondary' | 'destructive' | 'outline'}>
                {data.spread_drawdown_pct !== null
                  ? `${data.spread_drawdown_pct.toFixed(1)}%`
                  : '-'}
              </Badge>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Trend:</span>
              <TrendIcon className={`h-4 w-4 ${trendColor}`} />
              <span className={`capitalize ${trendColor}`}>{data.spread_trend}</span>
            </div>
          </div>
        )}
      </CardHeader>

      <CardContent>
        {error ? (
          <div className="h-[400px] flex items-center justify-center text-destructive">
            {error}
          </div>
        ) : chartData.length === 0 ? (
          <div className="h-[400px] flex items-center justify-center text-muted-foreground">
            {loading ? 'Loading...' : 'No spread data available'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 12 }}
                tickLine={false}
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 12 }}
                tickLine={false}
                tickFormatter={(value) => `${value.toFixed(3)}%`}
                domain={['auto', 'auto']}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 12 }}
                tickLine={false}
                tickFormatter={(value) => `${value.toFixed(3)}%`}
                domain={['auto', 'auto']}
                hide={true}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload || payload.length === 0) return null;
                  const item = payload[0].payload;
                  return (
                    <div className="bg-background border rounded-lg shadow-lg p-3 text-sm">
                      <div className="font-medium mb-2">{item.fullTime}</div>
                      <div className="space-y-1">
                        <div className="flex justify-between gap-4">
                          <span className="text-muted-foreground">Spread:</span>
                          <span className="font-mono text-green-500">{item.spread?.toFixed(4)}%</span>
                        </div>
                        <div className="flex justify-between gap-4">
                          <span className="text-muted-foreground">Long Rate:</span>
                          <span className="font-mono text-blue-500">{item.longRate?.toFixed(4) ?? '-'}%</span>
                        </div>
                        <div className="flex justify-between gap-4">
                          <span className="text-muted-foreground">Short Rate:</span>
                          <span className="font-mono text-orange-500">{item.shortRate?.toFixed(4) ?? '-'}%</span>
                        </div>
                        {item.price && (
                          <div className="flex justify-between gap-4">
                            <span className="text-muted-foreground">Price:</span>
                            <span className="font-mono">${item.price.toLocaleString()}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                }}
              />
              <Legend />

              {/* Entry spread reference line */}
              {entrySpread !== null && (
                <ReferenceLine
                  yAxisId="left"
                  y={entrySpread}
                  stroke="#888"
                  strokeDasharray="5 5"
                  label={{
                    value: `Entry: ${entrySpread.toFixed(4)}%`,
                    position: 'right',
                    fontSize: 11,
                    fill: '#888',
                  }}
                />
              )}

              {/* Spread area (main focus) */}
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="spread"
                name="Spread"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.2}
                strokeWidth={2}
              />

              {/* Long funding rate line */}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="longRate"
                name="Long Rate"
                stroke="#3b82f6"
                strokeWidth={1.5}
                dot={false}
                connectNulls
              />

              {/* Short funding rate line */}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="shortRate"
                name="Short Rate"
                stroke="#f97316"
                strokeWidth={1.5}
                dot={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
