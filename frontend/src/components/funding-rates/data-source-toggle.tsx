'use client';

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Database, Globe, Layers } from 'lucide-react';

export type DataSource = 'exchanges' | 'arbitrage-scanner' | 'both';

interface DataSourceToggleProps {
  value: DataSource;
  onChange: (value: DataSource) => void;
  showConnectedOnly: boolean;
  onShowConnectedOnlyChange: (value: boolean) => void;
  connectedExchangeCount?: number;
  totalExchangeCount?: number;
}

export function DataSourceToggle({
  value,
  onChange,
  showConnectedOnly,
  onShowConnectedOnlyChange,
  connectedExchangeCount = 0,
  totalExchangeCount = 0,
}: DataSourceToggleProps) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      {/* Data Source Tabs */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Data Source:</span>
        <Tabs value={value} onValueChange={(v) => onChange(v as DataSource)}>
          <TabsList>
            <TabsTrigger value="exchanges" className="gap-1">
              <Database className="h-3 w-3" />
              Exchanges
            </TabsTrigger>
            <TabsTrigger value="arbitrage-scanner" className="gap-1">
              <Globe className="h-3 w-3" />
              ArbitrageScanner
            </TabsTrigger>
            <TabsTrigger value="both" className="gap-1">
              <Layers className="h-3 w-3" />
              Both
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Connected Exchanges Filter */}
      <div className="flex items-center gap-2 pl-4 border-l">
        <Checkbox
          id="connected-only"
          checked={showConnectedOnly}
          onCheckedChange={(checked) => onShowConnectedOnlyChange(checked === true)}
        />
        <Label htmlFor="connected-only" className="text-sm cursor-pointer">
          Show only connected exchanges
        </Label>
        {showConnectedOnly && connectedExchangeCount > 0 && (
          <Badge variant="secondary" className="text-xs">
            {connectedExchangeCount}/{totalExchangeCount}
          </Badge>
        )}
      </div>
    </div>
  );
}
