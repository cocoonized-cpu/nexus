'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { getPositions } from '@/lib/api';
import { formatCurrency, formatPercent, getHealthColor } from '@/lib/utils';
import { useWebSocket } from '@/lib/websocket';

interface Position {
  id: string;
  symbol: string;
  long_exchange: string;
  short_exchange: string;
  size_usd: number;
  funding_received: number;
  funding_paid: number;
  health: string;
  status: string;
}

export function PositionsSummary() {
  const { subscribe, lastMessage } = useWebSocket();

  const { data, refetch } = useQuery({
    queryKey: ['positions-active'],
    queryFn: () => getPositions('active') as Promise<{ data?: Position[] }>,
  });

  useEffect(() => {
    subscribe('positions');
  }, [subscribe]);

  useEffect(() => {
    if (
      lastMessage?.event === 'position.opened' ||
      lastMessage?.event === 'position.closed'
    ) {
      refetch();
    }
  }, [lastMessage, refetch]);

  const positions: Position[] = data?.data || [];
  const totalSize = positions.reduce((sum, p) => sum + (p.size_usd || 0), 0);
  const totalFunding = positions.reduce(
    (sum, p) => sum + ((p.funding_received || 0) - (p.funding_paid || 0)),
    0
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Active Positions</CardTitle>
        <CardDescription>
          {positions.length} positions | {formatCurrency(totalSize)} deployed
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {positions.length === 0 ? (
            <p className="text-center text-muted-foreground py-4">
              No active positions
            </p>
          ) : (
            <>
              <div className="space-y-3">
                {positions.slice(0, 5).map((position) => (
                  <div
                    key={position.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div>
                      <div className="font-medium">{position.symbol}</div>
                      <div className="text-xs text-muted-foreground">
                        {position.long_exchange} / {position.short_exchange}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-medium">
                        {formatCurrency(position.size_usd || 0)}
                      </div>
                      <div
                        className={`text-xs ${getHealthColor(position.health || 'healthy')}`}
                      >
                        {position.health || 'healthy'}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t pt-4">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Total Funding P&L</span>
                  <span
                    className={totalFunding >= 0 ? 'text-green-500' : 'text-red-500'}
                  >
                    {formatCurrency(totalFunding)}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
