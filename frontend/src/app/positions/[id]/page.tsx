'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PositionSpreadChart } from '@/components/positions/position-spread-chart';
import { ArrowLeft, ExternalLink, AlertCircle, Loader2 } from 'lucide-react';

// Types
interface PositionLeg {
  id: string;
  leg_type: string;
  exchange: string;
  symbol: string;
  market_type: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  notional_value_usd: number;
  unrealized_pnl: number;
  funding_pnl: number;
}

interface Position {
  id: string;
  opportunity_id: string | null;
  opportunity_type: string;
  symbol: string;
  base_asset: string;
  status: string;
  health_status: string;
  total_capital_deployed: number;
  funding_received: number;
  funding_paid: number;
  net_funding_pnl: number;
  unrealized_pnl: number;
  return_pct: number;
  delta_exposure_pct: number;
  max_margin_utilization: number;
  opened_at: string | null;
  funding_periods_collected: number;
  legs: PositionLeg[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchPosition(id: string): Promise<Position> {
  const response = await fetch(`${API_BASE}/api/v1/positions/${id}`);
  if (!response.ok) {
    throw new Error('Position not found');
  }
  const result = await response.json();
  const data = result.data;

  // Convert string values to numbers
  return {
    ...data,
    total_capital_deployed: parseFloat(data.total_capital_deployed) || 0,
    funding_received: parseFloat(data.funding_received) || 0,
    funding_paid: parseFloat(data.funding_paid) || 0,
    net_funding_pnl: parseFloat(data.net_funding_pnl) || 0,
    unrealized_pnl: parseFloat(data.unrealized_pnl) || 0,
    return_pct: parseFloat(data.return_pct) || 0,
    delta_exposure_pct: parseFloat(data.delta_exposure_pct) || 0,
    max_margin_utilization: parseFloat(data.max_margin_utilization) || 0,
    legs: data.legs.map((leg: PositionLeg) => ({
      ...leg,
      quantity: parseFloat(String(leg.quantity)) || 0,
      entry_price: parseFloat(String(leg.entry_price)) || 0,
      current_price: parseFloat(String(leg.current_price)) || 0,
      notional_value_usd: parseFloat(String(leg.notional_value_usd)) || 0,
      unrealized_pnl: parseFloat(String(leg.unrealized_pnl)) || 0,
      funding_pnl: parseFloat(String(leg.funding_pnl)) || 0,
    })),
  };
}

export default function PositionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const positionId = params.id as string;

  const [position, setPosition] = useState<Position | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (positionId) {
      fetchPosition(positionId)
        .then(setPosition)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    }
  }, [positionId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !position) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)] gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <h2 className="text-xl font-semibold">Position Not Found</h2>
        <p className="text-muted-foreground">{error || 'Unable to load position details'}</p>
        <Button onClick={() => router.push('/positions')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Positions
        </Button>
      </div>
    );
  }

  // Find long and short legs
  const longLeg = position.legs.find((leg) => leg.side === 'long');
  const shortLeg = position.legs.find((leg) => leg.side === 'short');

  // Status badge color
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'default';
      case 'opening':
        return 'secondary';
      case 'closing':
        return 'outline';
      case 'closed':
        return 'secondary';
      default:
        return 'destructive';
    }
  };

  // Health badge color
  const getHealthColor = (health: string) => {
    switch (health) {
      case 'healthy':
        return 'default';
      case 'attention':
        return 'secondary';
      case 'warning':
        return 'outline';
      case 'critical':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/positions">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold">{position.symbol}</h1>
            <p className="text-muted-foreground">{position.opportunity_type} Position</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={getStatusColor(position.status) as 'default' | 'secondary' | 'destructive' | 'outline'}>
            {position.status}
          </Badge>
          <Badge variant={getHealthColor(position.health_status) as 'default' | 'secondary' | 'destructive' | 'outline'}>
            {position.health_status}
          </Badge>
        </div>
      </div>

      {/* Spread Chart */}
      <PositionSpreadChart positionId={positionId} />

      {/* Position Legs */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Long Leg */}
        {longLeg && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Badge variant="default" className="bg-green-500">LONG</Badge>
                {longLeg.exchange.charAt(0).toUpperCase() + longLeg.exchange.slice(1)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Entry Price</span>
                  <p className="font-mono font-medium">${longLeg.entry_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Current Price</span>
                  <p className="font-mono font-medium">${longLeg.current_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Size</span>
                  <p className="font-mono font-medium">{longLeg.quantity.toFixed(6)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Notional</span>
                  <p className="font-mono font-medium">${longLeg.notional_value_usd.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Unrealized P&L</span>
                  <p className={`font-mono font-medium ${longLeg.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${longLeg.unrealized_pnl.toFixed(2)}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Funding P&L</span>
                  <p className={`font-mono font-medium ${longLeg.funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${longLeg.funding_pnl.toFixed(2)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Short Leg */}
        {shortLeg && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Badge variant="destructive">SHORT</Badge>
                {shortLeg.exchange.charAt(0).toUpperCase() + shortLeg.exchange.slice(1)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Entry Price</span>
                  <p className="font-mono font-medium">${shortLeg.entry_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Current Price</span>
                  <p className="font-mono font-medium">${shortLeg.current_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Size</span>
                  <p className="font-mono font-medium">{shortLeg.quantity.toFixed(6)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Notional</span>
                  <p className="font-mono font-medium">${shortLeg.notional_value_usd.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Unrealized P&L</span>
                  <p className={`font-mono font-medium ${shortLeg.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${shortLeg.unrealized_pnl.toFixed(2)}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Funding P&L</span>
                  <p className={`font-mono font-medium ${shortLeg.funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${shortLeg.funding_pnl.toFixed(2)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Summary Stats */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Position Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Total Capital</span>
              <p className="font-mono font-medium text-lg">${position.total_capital_deployed.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Net Funding P&L</span>
              <p className={`font-mono font-medium text-lg ${position.net_funding_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                ${position.net_funding_pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Return</span>
              <p className={`font-mono font-medium text-lg ${position.return_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {position.return_pct.toFixed(2)}%
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Funding Periods</span>
              <p className="font-mono font-medium text-lg">{position.funding_periods_collected}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Delta Exposure</span>
              <p className="font-mono font-medium">{position.delta_exposure_pct.toFixed(2)}%</p>
            </div>
            <div>
              <span className="text-muted-foreground">Margin Utilization</span>
              <p className="font-mono font-medium">{position.max_margin_utilization.toFixed(2)}%</p>
            </div>
            <div>
              <span className="text-muted-foreground">Opened At</span>
              <p className="font-mono font-medium">
                {position.opened_at
                  ? new Date(position.opened_at).toLocaleString()
                  : 'N/A'}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Position ID</span>
              <p className="font-mono text-xs text-muted-foreground truncate" title={position.id}>
                {position.id}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
