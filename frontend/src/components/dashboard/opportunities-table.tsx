'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getTopOpportunities, executeOpportunity } from '@/lib/api';
import { formatPercent, getScoreColor } from '@/lib/utils';
import { useWebSocket } from '@/lib/websocket';
import { ExecutionProgressModal } from '@/components/opportunities/execution-progress-modal';
import { Play } from 'lucide-react';

interface Opportunity {
  id: string;
  symbol: string;
  long_leg: { exchange: string; funding_rate: number };
  short_leg: { exchange: string; funding_rate: number };
  funding_spread_pct: number;
  estimated_net_apr: number;
  uos_score: number;
  status?: string;
  primary_exchange?: string;
  hedge_exchange?: string;
  primary_side?: string;
  hedge_side?: string;
  net_apr?: number;
  recommended_size_usd?: number;
}

export function OpportunitiesTable() {
  const { subscribe, lastMessage } = useWebSocket();
  const queryClient = useQueryClient();
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [showExecuteDialog, setShowExecuteDialog] = useState(false);

  const { data, refetch } = useQuery({
    queryKey: ['top-opportunities'],
    queryFn: () => getTopOpportunities(10) as Promise<{ data?: Opportunity[] }>,
  });

  useEffect(() => {
    subscribe('opportunities');
  }, [subscribe]);

  useEffect(() => {
    if (lastMessage?.event === 'opportunity.detected') {
      refetch();
    }
  }, [lastMessage, refetch]);

  const opportunities: Opportunity[] = data?.data || [];

  // Execute handler for the progress modal
  const handleExecuteOpportunity = async (id: string) => {
    try {
      // Use recommended size or default to $100
      const capital_usd = selectedOpportunity?.recommended_size_usd || 100;
      const result = await executeOpportunity(id, { capital_usd }) as {
        success?: boolean;
        message?: string;
        data?: {
          position_id: string;
          primary: { exchange: string; side: string; order_id?: string };
          hedge: { exchange: string; side: string; order_id?: string };
        };
      };
      // Invalidate queries after successful execution
      queryClient.invalidateQueries({ queryKey: ['top-opportunities'] });
      queryClient.invalidateQueries({ queryKey: ['opportunities'] });
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      return {
        success: true,
        message: result.message || 'Position opened successfully',
        data: result.data,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Execution failed';
      return {
        success: false,
        error: errorMessage,
      };
    }
  };

  const handleExecuteModalClose = () => {
    setShowExecuteDialog(false);
    setSelectedOpportunity(null);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Top Opportunities</CardTitle>
        <CardDescription>
          Highest scoring funding rate arbitrage opportunities
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {opportunities.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No opportunities detected
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-muted-foreground">
                    <th className="pb-3 font-medium">Symbol</th>
                    <th className="pb-3 font-medium">Long</th>
                    <th className="pb-3 font-medium">Short</th>
                    <th className="pb-3 font-medium">Spread</th>
                    <th className="pb-3 font-medium">APR</th>
                    <th className="pb-3 font-medium">Score</th>
                    <th className="pb-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {opportunities.map((opp) => (
                    <tr key={opp.id} className="border-b">
                      <td className="py-3 font-medium">{opp.symbol}</td>
                      <td className="py-3 text-sm">
                        <div>{opp.long_leg?.exchange}</div>
                        <div className="text-green-500 text-xs">
                          {formatPercent(opp.long_leg?.funding_rate * 100 || 0, 4)}
                        </div>
                      </td>
                      <td className="py-3 text-sm">
                        <div>{opp.short_leg?.exchange}</div>
                        <div className="text-red-500 text-xs">
                          {formatPercent(opp.short_leg?.funding_rate * 100 || 0, 4)}
                        </div>
                      </td>
                      <td className="py-3">
                        {formatPercent(opp.funding_spread_pct || 0, 4)}
                      </td>
                      <td className="py-3 text-green-500">
                        {formatPercent(opp.estimated_net_apr || 0, 1)}
                      </td>
                      <td className={`py-3 font-bold ${getScoreColor(opp.uos_score)}`}>
                        {opp.uos_score}
                      </td>
                      <td className="py-3">
                        <Button
                          size="sm"
                          onClick={() => {
                            setSelectedOpportunity(opp);
                            setShowExecuteDialog(true);
                          }}
                        >
                          <Play className="h-3 w-3 mr-1" />
                          Execute
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Execute Progress Modal */}
        <ExecutionProgressModal
          open={showExecuteDialog}
          onClose={handleExecuteModalClose}
          opportunity={selectedOpportunity ? {
            id: selectedOpportunity.id,
            symbol: selectedOpportunity.symbol,
            primary_exchange: selectedOpportunity.long_leg?.exchange || selectedOpportunity.primary_exchange || 'Unknown',
            hedge_exchange: selectedOpportunity.short_leg?.exchange || selectedOpportunity.hedge_exchange || 'Unknown',
            primary_side: selectedOpportunity.primary_side || 'long',
            hedge_side: selectedOpportunity.hedge_side || 'short',
            net_apr: selectedOpportunity.net_apr || selectedOpportunity.estimated_net_apr || 0,
            uos_score: selectedOpportunity.uos_score,
            recommended_size_usd: selectedOpportunity.recommended_size_usd || 100,
          } : null}
          onExecute={handleExecuteOpportunity}
        />
      </CardContent>
    </Card>
  );
}
