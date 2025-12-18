'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useMutation, useQueryClient } from '@tanstack/react-query';
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  TrendingUp,
  TrendingDown,
  X,
  Loader2,
  RefreshCw,
  AlertTriangle,
  Ban,
  Eye,
  History,
  MoreHorizontal,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/utils';
import { closePosition } from '@/lib/api';
import { useToast } from '@/components/ui/use-toast';
import {
  useConsolidatedPositions,
  ConsolidatedPosition,
} from '@/hooks/use-consolidated-positions';
import { useRouter } from 'next/navigation';

const HEALTH_COLORS: Record<string, { bg: string; text: string }> = {
  healthy: { bg: 'bg-green-500/10', text: 'text-green-500' },
  warning: { bg: 'bg-yellow-500/10', text: 'text-yellow-500' },
  critical: { bg: 'bg-red-500/10', text: 'text-red-500' },
  unknown: { bg: 'bg-muted', text: 'text-muted-foreground' },
};

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  active: { bg: 'bg-green-500', text: 'text-white' },
  opening: { bg: 'bg-blue-500', text: 'text-white' },
  closing: { bg: 'bg-orange-500', text: 'text-white' },
  closed: { bg: 'bg-gray-500', text: 'text-white' },
};

export function ConsolidatedPositionsTable() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const { toast } = useToast();
  const { positions, stats, isLoading, refetch } = useConsolidatedPositions();
  const [closingPositionId, setClosingPositionId] = useState<string | null>(null);
  const [showCloseAllDialog, setShowCloseAllDialog] = useState(false);
  const [blacklistingSymbol, setBlacklistingSymbol] = useState<string | null>(null);

  // Blacklist symbol mutation
  const blacklistMutation = useMutation({
    mutationFn: async (symbol: string) => {
      const response = await fetch(`/api/v1/blacklist/${symbol}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Blacklisted from positions page' }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to blacklist symbol');
      }
      return response.json();
    },
    onSuccess: (data, symbol) => {
      toast({
        title: 'Symbol Blacklisted',
        description: `${symbol} has been added to the blacklist. No new positions will be opened for this symbol.`,
      });
      setBlacklistingSymbol(null);
    },
    onError: (error: Error, symbol) => {
      toast({
        title: 'Blacklist Failed',
        description: error.message || `Failed to blacklist ${symbol}`,
        variant: 'destructive',
      });
      setBlacklistingSymbol(null);
    },
  });

  const handleBlacklist = (symbol: string) => {
    setBlacklistingSymbol(symbol);
    blacklistMutation.mutate(symbol);
  };

  // Close position mutation
  const closeMutation = useMutation({
    mutationFn: (positionId: string) => closePosition(positionId, 'manual'),
    onSuccess: (data, positionId) => {
      queryClient.invalidateQueries({ queryKey: ['nexus-positions'] });
      queryClient.invalidateQueries({ queryKey: ['exchange-positions'] });
      toast({
        title: 'Position Closed',
        description: `Position closed successfully`,
      });
      setClosingPositionId(null);
    },
    onError: (error: Error, positionId) => {
      toast({
        title: 'Close Failed',
        description: error.message || 'Failed to close position',
        variant: 'destructive',
      });
      setClosingPositionId(null);
    },
  });

  // Close all positions mutation
  const closeAllMutation = useMutation({
    mutationFn: async () => {
      const activePositions = positions.filter((p) => p.status === 'active');
      const results = await Promise.allSettled(
        activePositions.map((p) => closePosition(p.positionId, 'manual_close_all'))
      );
      return results;
    },
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: ['nexus-positions'] });
      queryClient.invalidateQueries({ queryKey: ['exchange-positions'] });

      const succeeded = results.filter((r) => r.status === 'fulfilled').length;
      const failed = results.filter((r) => r.status === 'rejected').length;

      toast({
        title: 'Close All Complete',
        description:
          failed > 0
            ? `${succeeded} positions closed, ${failed} failed`
            : `All ${succeeded} positions closed successfully`,
        variant: failed > 0 ? 'destructive' : 'default',
      });
      setShowCloseAllDialog(false);
    },
    onError: (error: Error) => {
      toast({
        title: 'Close All Failed',
        description: error.message || 'Failed to close positions',
        variant: 'destructive',
      });
      setShowCloseAllDialog(false);
    },
  });

  const handleClose = (positionId: string) => {
    setClosingPositionId(positionId);
    closeMutation.mutate(positionId);
  };

  const activePositions = positions.filter((p) => p.status === 'active');

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>NEXUS Positions</CardTitle>
            <CardDescription>
              Arbitrage positions with paired long/short legs
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
            </Button>
            {activePositions.length > 0 && (
              <AlertDialog open={showCloseAllDialog} onOpenChange={setShowCloseAllDialog}>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    Close All ({activePositions.length})
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Close All Positions</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will close all {activePositions.length} active positions by placing
                      market orders on both legs. This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => closeAllMutation.mutate()}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      disabled={closeAllMutation.isPending}
                    >
                      {closeAllMutation.isPending ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Closing...
                        </>
                      ) : (
                        'Close All'
                      )}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Summary Stats */}
        <div className="grid gap-4 md:grid-cols-4 mb-6">
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Positions</div>
            <div className="text-2xl font-bold">{stats.positionCount}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Total Capital</div>
            <div className="text-2xl font-bold">{formatCurrency(stats.totalCapital)}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Funding P&L</div>
            <div
              className={cn(
                'text-2xl font-bold',
                stats.totalFundingPnl >= 0 ? 'text-green-500' : 'text-red-500'
              )}
            >
              {formatCurrency(stats.totalFundingPnl)}
            </div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Net P&L</div>
            <div
              className={cn(
                'text-2xl font-bold',
                stats.totalPnl >= 0 ? 'text-green-500' : 'text-red-500'
              )}
            >
              {formatCurrency(stats.totalPnl)}
            </div>
          </div>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : positions.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No NEXUS positions</p>
            <p className="text-sm mt-2">
              Execute opportunities to open arbitrage positions
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-left text-sm text-muted-foreground">
                  <th className="pb-3 font-medium">Symbol</th>
                  <th className="pb-3 font-medium">
                    <div className="flex items-center gap-1">
                      <TrendingUp className="h-3 w-3 text-green-500" />
                      Long Exchange
                    </div>
                  </th>
                  <th className="pb-3 font-medium text-right">Long Entry</th>
                  <th className="pb-3 font-medium text-right">Long Size</th>
                  <th className="pb-3 font-medium text-right">Long P&L</th>
                  <th className="pb-3 font-medium">
                    <div className="flex items-center gap-1">
                      <TrendingDown className="h-3 w-3 text-red-500" />
                      Short Exchange
                    </div>
                  </th>
                  <th className="pb-3 font-medium text-right">Short Entry</th>
                  <th className="pb-3 font-medium text-right">Short Size</th>
                  <th className="pb-3 font-medium text-right">Short P&L</th>
                  <th className="pb-3 font-medium text-right">Capital</th>
                  <th className="pb-3 font-medium text-right">Net P&L</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => {
                  const healthStyle = HEALTH_COLORS[position.healthStatus] || HEALTH_COLORS.unknown;
                  const statusStyle = STATUS_COLORS[position.status] || STATUS_COLORS.active;
                  const isClosing = closingPositionId === position.positionId;

                  return (
                    <tr key={position.positionId} className="border-b hover:bg-muted/50">
                      <td className="py-4">
                        <Link
                          href={`/positions/${position.positionId}`}
                          className="hover:underline"
                        >
                          <div className="font-medium text-primary">{position.symbol}</div>
                          <div className="text-xs text-muted-foreground">
                            {position.fundingPeriods} periods
                          </div>
                        </Link>
                      </td>

                      {/* Long Leg */}
                      <td className="py-4">
                        {position.longLeg ? (
                          <Badge variant="outline" className="bg-green-500/10 text-green-600">
                            {position.longLeg.exchange}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="py-4 text-right font-mono">
                        {position.longLeg
                          ? `$${position.longLeg.entryPrice.toFixed(2)}`
                          : '-'}
                      </td>
                      <td className="py-4 text-right font-mono">
                        {position.longLeg
                          ? position.longLeg.size.toFixed(4)
                          : '-'}
                      </td>
                      <td
                        className={cn(
                          'py-4 text-right font-medium',
                          position.longLeg?.pnl && position.longLeg.pnl >= 0
                            ? 'text-green-500'
                            : 'text-red-500'
                        )}
                      >
                        {position.longLeg
                          ? formatCurrency(position.longLeg.pnl)
                          : '-'}
                      </td>

                      {/* Short Leg */}
                      <td className="py-4">
                        {position.shortLeg ? (
                          <Badge variant="outline" className="bg-red-500/10 text-red-600">
                            {position.shortLeg.exchange}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="py-4 text-right font-mono">
                        {position.shortLeg
                          ? `$${position.shortLeg.entryPrice.toFixed(2)}`
                          : '-'}
                      </td>
                      <td className="py-4 text-right font-mono">
                        {position.shortLeg
                          ? position.shortLeg.size.toFixed(4)
                          : '-'}
                      </td>
                      <td
                        className={cn(
                          'py-4 text-right font-medium',
                          position.shortLeg?.pnl && position.shortLeg.pnl >= 0
                            ? 'text-green-500'
                            : 'text-red-500'
                        )}
                      >
                        {position.shortLeg
                          ? formatCurrency(position.shortLeg.pnl)
                          : '-'}
                      </td>

                      {/* Totals */}
                      <td className="py-4 text-right">
                        {formatCurrency(position.totalCapital)}
                      </td>
                      <td
                        className={cn(
                          'py-4 text-right font-bold',
                          position.netPnl >= 0 ? 'text-green-500' : 'text-red-500'
                        )}
                      >
                        {formatCurrency(position.netPnl)}
                      </td>

                      {/* Status */}
                      <td className="py-4">
                        <div className="flex items-center gap-2">
                          <Badge className={cn(statusStyle.bg, statusStyle.text)}>
                            {position.status}
                          </Badge>
                          {position.healthStatus !== 'healthy' && (
                            <Badge
                              variant="outline"
                              className={cn(healthStyle.bg, healthStyle.text)}
                            >
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              {position.healthStatus}
                            </Badge>
                          )}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-4 text-right">
                        <TooltipProvider>
                          <div className="flex items-center justify-end gap-1">
                            {/* Quick Action Buttons */}
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-8 w-8 p-0"
                                  onClick={() => router.push(`/positions/${position.positionId}`)}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>View Details</TooltipContent>
                            </Tooltip>

                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-8 w-8 p-0"
                                  onClick={() => router.push(`/positions/${position.positionId}/interactions`)}
                                >
                                  <History className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>View Interactions</TooltipContent>
                            </Tooltip>

                            {/* More Actions Dropdown */}
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button size="sm" variant="ghost" className="h-8 w-8 p-0">
                                  <MoreHorizontal className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem
                                  onClick={() => router.push(`/positions/${position.positionId}`)}
                                >
                                  <Eye className="h-4 w-4 mr-2" />
                                  View Details
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() => router.push(`/positions/${position.positionId}/interactions`)}
                                >
                                  <History className="h-4 w-4 mr-2" />
                                  View Interactions
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => handleBlacklist(position.symbol)}
                                  disabled={blacklistingSymbol === position.symbol}
                                  className="text-orange-600"
                                >
                                  {blacklistingSymbol === position.symbol ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                  ) : (
                                    <Ban className="h-4 w-4 mr-2" />
                                  )}
                                  Blacklist {position.symbol}
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>

                            {/* Close Button */}
                            {position.status === 'active' && (
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="destructive"
                                    disabled={isClosing}
                                    className="ml-1"
                                  >
                                    {isClosing ? (
                                      <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                      <>
                                        <X className="h-3 w-3 mr-1" />
                                        Close
                                      </>
                                    )}
                                  </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                  <AlertDialogHeader>
                                    <AlertDialogTitle>Close Position</AlertDialogTitle>
                                    <AlertDialogDescription>
                                      This will close the {position.symbol} position by placing market
                                      orders on both exchanges. Current P&L:{' '}
                                      <span
                                        className={cn(
                                          'font-bold',
                                          position.netPnl >= 0 ? 'text-green-500' : 'text-red-500'
                                        )}
                                      >
                                        {formatCurrency(position.netPnl)}
                                      </span>
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <AlertDialogFooter>
                                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                                    <AlertDialogAction
                                      onClick={() => handleClose(position.positionId)}
                                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                    >
                                      Confirm Close
                                    </AlertDialogAction>
                                  </AlertDialogFooter>
                                </AlertDialogContent>
                              </AlertDialog>
                            )}
                            {position.status === 'closing' && (
                              <Badge variant="secondary">
                                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                Closing...
                              </Badge>
                            )}
                          </div>
                        </TooltipProvider>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
