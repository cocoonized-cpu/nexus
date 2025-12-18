'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  getExchanges,
  updateExchange,
  getSettings,
  updateSetting,
  getRiskLimits,
  updateRiskLimits,
  getStrategyParameters,
  updateStrategyParameters,
  getSpreadMonitoringSettings,
  updateSpreadMonitoringSettings,
  SpreadMonitoringSettings,
  getMaxConcurrentCoins,
  updateMaxConcurrentCoins,
  MaxConcurrentCoinsSettings,
} from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { useToast } from '@/components/ui/use-toast';
import {
  Settings,
  Key,
  Shield,
  Bell,
  Sliders,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  Save,
  Loader2,
  Cog,
  AlertCircle,
} from 'lucide-react';

interface Exchange {
  slug: string;
  display_name: string;
  exchange_type: string;
  tier: string;
  enabled: boolean;
  perp_maker_fee: number;
  perp_taker_fee: number;
  funding_interval_hours: number;
  supports_portfolio_margin: boolean;
  has_credentials: boolean;
  credential_fields: string[];
  requires_on_chain: boolean;
}

interface SystemSetting {
  key: string;
  value: unknown;
  description: string;
  updated_at: string;
}

// API returns string values for risk limits, but we normalize to numbers
interface RiskLimitsAPI {
  max_position_size_usd: number | string;
  max_position_size_pct: number | string;
  max_leverage: number | string;
  max_venue_exposure_pct: number | string;
  max_asset_exposure_pct: number | string;
  max_gross_exposure_pct: number | string;
  max_net_exposure_pct: number | string;
  max_drawdown_pct: number | string;
  max_var_pct: number | string;
  max_total_exposure_usd?: number | string;
  max_exchange_exposure_usd?: number | string;
}

interface RiskLimits {
  max_position_size_usd: number;
  max_position_size_pct: number;
  max_leverage: number;
  max_venue_exposure_pct: number;
  max_asset_exposure_pct: number;
  max_gross_exposure_pct: number;
  max_net_exposure_pct: number;
  max_drawdown_pct: number;
  max_var_pct: number;
  max_total_exposure_usd?: number;
  max_exchange_exposure_usd?: number;
}

interface StrategyParams {
  name: string;
  min_spread_pct: number;
  min_net_apr_pct: number;
  min_uos_score: number;
  min_volume_24h_usd: number;
  min_open_interest_usd: number;
  max_expected_slippage_pct: number;
  liquidity_multiple: number;
  return_score_weight: number;
  risk_score_weight: number;
  execution_score_weight: number;
  timing_score_weight: number;
  target_funding_rate_min: number;
  stop_loss_pct: number;
}

interface ExchangeCredentials {
  api_key: string;
  api_secret: string;
  passphrase: string;
  wallet_address: string;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [selectedExchange, setSelectedExchange] = useState<Exchange | null>(null);
  const [showCredentialDialog, setShowCredentialDialog] = useState(false);
  const [credentials, setCredentials] = useState<ExchangeCredentials>({
    api_key: '',
    api_secret: '',
    passphrase: '',
    wallet_address: '',
  });
  const [showSecrets, setShowSecrets] = useState(false);
  const [riskLimitChanges, setRiskLimitChanges] = useState<Partial<RiskLimits>>({});
  const [hasRiskChanges, setHasRiskChanges] = useState(false);
  const [strategyChanges, setStrategyChanges] = useState<Partial<StrategyParams>>({});
  const [hasStrategyChanges, setHasStrategyChanges] = useState(false);
  const [spreadMonitoringChanges, setSpreadMonitoringChanges] = useState<Partial<SpreadMonitoringSettings>>({});
  const [hasSpreadMonitoringChanges, setHasSpreadMonitoringChanges] = useState(false);
  const [maxCoinsValue, setMaxCoinsValue] = useState<number | null>(null);
  const [hasMaxCoinsChanges, setHasMaxCoinsChanges] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Queries
  const { data: exchangesData, isLoading: exchangesLoading } = useQuery({
    queryKey: ['exchanges'],
    queryFn: () => getExchanges() as Promise<{ data: Exchange[] }>,
  });

  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: () => getSettings() as Promise<{ data: SystemSetting[] }>,
  });

  const { data: riskLimitsData } = useQuery({
    queryKey: ['risk-limits'],
    queryFn: async () => {
      const response = await getRiskLimits() as { data: RiskLimitsAPI };
      // Transform string values to numbers
      const parseNum = (v: number | string | undefined): number => {
        if (typeof v === 'number') return v;
        if (typeof v === 'string') return parseFloat(v) || 0;
        return 0;
      };
      const data: RiskLimits = {
        max_position_size_usd: parseNum(response.data.max_position_size_usd),
        max_position_size_pct: parseNum(response.data.max_position_size_pct),
        max_leverage: parseNum(response.data.max_leverage),
        max_venue_exposure_pct: parseNum(response.data.max_venue_exposure_pct),
        max_asset_exposure_pct: parseNum(response.data.max_asset_exposure_pct),
        max_gross_exposure_pct: parseNum(response.data.max_gross_exposure_pct),
        max_net_exposure_pct: parseNum(response.data.max_net_exposure_pct),
        max_drawdown_pct: parseNum(response.data.max_drawdown_pct),
        max_var_pct: parseNum(response.data.max_var_pct),
        max_total_exposure_usd: parseNum(response.data.max_total_exposure_usd),
        max_exchange_exposure_usd: parseNum(response.data.max_exchange_exposure_usd),
      };
      return { data };
    },
  });

  const { data: strategyData } = useQuery({
    queryKey: ['strategy-params'],
    queryFn: () => getStrategyParameters() as Promise<{ data: StrategyParams }>,
  });

  const { data: spreadMonitoringData } = useQuery({
    queryKey: ['spread-monitoring-settings'],
    queryFn: () => getSpreadMonitoringSettings(),
  });

  const { data: maxCoinsData } = useQuery({
    queryKey: ['max-concurrent-coins'],
    queryFn: () => getMaxConcurrentCoins(),
  });

  const exchanges: Exchange[] = exchangesData?.data || [];
  const settings: SystemSetting[] = settingsData?.data || [];
  const riskLimits: RiskLimits = riskLimitsData?.data || {} as RiskLimits;
  const strategyParams: StrategyParams = strategyData?.data || {} as StrategyParams;
  const spreadMonitoring: SpreadMonitoringSettings = spreadMonitoringData || {
    spread_drawdown_exit_pct: 50,
    min_time_to_funding_exit_seconds: 1800,
  };

  // Helper to get setting value
  const getSettingValue = (key: string): unknown => {
    const setting = settings.find((s) => s.key === key);
    return setting?.value;
  };

  // Mutations
  const updateExchangeMutation = useMutation({
    mutationFn: ({ slug, data }: { slug: string; data: Record<string, unknown> }) =>
      updateExchange(slug, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['exchanges'] });
      setShowCredentialDialog(false);
      setCredentials({ api_key: '', api_secret: '', passphrase: '', wallet_address: '' });
      toast({
        title: 'Exchange Updated',
        description: `${variables.slug} configuration saved successfully.`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update exchange settings.',
        variant: 'destructive',
      });
    },
  });

  const updateSettingMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      updateSetting(key, value),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      toast({
        title: 'Setting Updated',
        description: `${variables.key.replace(/_/g, ' ')} has been updated.`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update setting.',
        variant: 'destructive',
      });
    },
  });

  const updateRiskLimitsMutation = useMutation({
    mutationFn: (limits: Record<string, number>) => updateRiskLimits(limits),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['risk-limits'] });
      setRiskLimitChanges({});
      setHasRiskChanges(false);
      toast({
        title: 'Risk Limits Updated',
        description: 'Risk limit changes saved successfully.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update risk limits.',
        variant: 'destructive',
      });
    },
  });

  const updateStrategyMutation = useMutation({
    mutationFn: (params: Record<string, unknown>) => updateStrategyParameters(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategy-params'] });
      setStrategyChanges({});
      setHasStrategyChanges(false);
      toast({
        title: 'Strategy Updated',
        description: 'Strategy parameters saved successfully.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update strategy parameters.',
        variant: 'destructive',
      });
    },
  });

  const updateSpreadMonitoringMutation = useMutation({
    mutationFn: (settings: SpreadMonitoringSettings) => updateSpreadMonitoringSettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spread-monitoring-settings'] });
      setSpreadMonitoringChanges({});
      setHasSpreadMonitoringChanges(false);
      toast({
        title: 'Spread Monitoring Updated',
        description: 'Spread monitoring settings saved successfully.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update spread monitoring settings.',
        variant: 'destructive',
      });
    },
  });

  const updateMaxCoinsMutation = useMutation({
    mutationFn: (value: number) => updateMaxConcurrentCoins(value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['max-concurrent-coins'] });
      setMaxCoinsValue(null);
      setHasMaxCoinsChanges(false);
      toast({
        title: 'Position Limit Updated',
        description: 'Maximum concurrent coins setting saved successfully.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update position limit.',
        variant: 'destructive',
      });
    },
  });

  const handleExchangeToggle = (exchange: Exchange) => {
    updateExchangeMutation.mutate({
      slug: exchange.slug,
      data: { enabled: !exchange.enabled },
    });
  };

  const handleCredentialsSave = () => {
    if (selectedExchange) {
      const data: Record<string, unknown> = {};
      if (credentials.api_key) data.api_key = credentials.api_key;
      if (credentials.api_secret) data.api_secret = credentials.api_secret;
      if (credentials.passphrase) data.passphrase = credentials.passphrase;
      if (credentials.wallet_address) data.wallet_address = credentials.wallet_address;

      updateExchangeMutation.mutate({
        slug: selectedExchange.slug,
        data,
      });
    }
  };

  // Helper to check if a credential field is required
  const isFieldRequired = (field: string): boolean => {
    if (!selectedExchange) return false;
    return selectedExchange.credential_fields?.includes(field) || false;
  };

  // Helper to get field label
  const getFieldLabel = (field: string): string => {
    const labels: Record<string, string> = {
      api_key: 'API Key',
      api_secret: 'API Secret / Private Key',
      passphrase: 'Passphrase',
      wallet_address: 'Wallet Address',
    };
    return labels[field] || field;
  };

  const handleSettingToggle = (key: string, currentValue: unknown) => {
    updateSettingMutation.mutate({
      key,
      value: !currentValue,
    });
  };

  const handleRiskLimitChange = (field: keyof RiskLimits, value: string) => {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      setRiskLimitChanges((prev) => ({ ...prev, [field]: numValue }));
      setHasRiskChanges(true);
    }
  };

  const handleSaveRiskLimits = () => {
    if (Object.keys(riskLimitChanges).length > 0) {
      updateRiskLimitsMutation.mutate(riskLimitChanges as Record<string, number>);
    }
  };

  const getMergedRiskLimit = (field: keyof RiskLimits): number => {
    // Check pending changes first (these are always numbers from user input)
    const pendingValue = riskLimitChanges[field];
    if (pendingValue !== undefined) {
      return pendingValue;
    }
    // Data is already transformed to numbers by the query
    return riskLimits[field] || 0;
  };

  const handleStrategyChange = (field: keyof StrategyParams, value: string) => {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      setStrategyChanges((prev) => ({ ...prev, [field]: numValue }));
      setHasStrategyChanges(true);
    }
  };

  const handleSaveStrategy = () => {
    if (Object.keys(strategyChanges).length > 0) {
      updateStrategyMutation.mutate(strategyChanges as Record<string, unknown>);
    }
  };

  const getMergedStrategy = (field: keyof StrategyParams): number => {
    return strategyChanges[field] !== undefined
      ? strategyChanges[field] as number
      : (strategyParams[field] as number) || 0;
  };

  // Spread monitoring handlers
  const handleSpreadMonitoringChange = (field: keyof SpreadMonitoringSettings, value: string) => {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      setSpreadMonitoringChanges((prev) => ({ ...prev, [field]: numValue }));
      setHasSpreadMonitoringChanges(true);
    }
  };

  const handleSaveSpreadMonitoring = () => {
    const merged = {
      spread_drawdown_exit_pct: spreadMonitoringChanges.spread_drawdown_exit_pct ?? spreadMonitoring.spread_drawdown_exit_pct,
      min_time_to_funding_exit_seconds: spreadMonitoringChanges.min_time_to_funding_exit_seconds ?? spreadMonitoring.min_time_to_funding_exit_seconds,
    };
    updateSpreadMonitoringMutation.mutate(merged);
  };

  const getMergedSpreadMonitoring = (field: keyof SpreadMonitoringSettings): number => {
    return spreadMonitoringChanges[field] !== undefined
      ? spreadMonitoringChanges[field]!
      : spreadMonitoring[field];
  };

  // Max Concurrent Coins handlers
  const handleMaxCoinsChange = (value: string) => {
    const numValue = parseInt(value, 10);
    if (!isNaN(numValue) && numValue >= 1 && numValue <= 20) {
      setMaxCoinsValue(numValue);
      setHasMaxCoinsChanges(true);
    }
  };

  const handleSaveMaxCoins = () => {
    if (maxCoinsValue !== null) {
      updateMaxCoinsMutation.mutate(maxCoinsValue);
    }
  };

  const getCurrentMaxCoins = (): number => {
    return maxCoinsValue !== null
      ? maxCoinsValue
      : (maxCoinsData?.max_concurrent_coins ?? 5);
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Settings className="h-8 w-8" />
              Settings
            </h1>
            <p className="text-muted-foreground">Configure NEXUS trading parameters and integrations</p>
          </div>
        </div>

        <Tabs defaultValue="exchanges" className="space-y-6">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="exchanges" className="flex items-center gap-2">
              <Key className="h-4 w-4" />
              Exchanges
            </TabsTrigger>
            <TabsTrigger value="trading" className="flex items-center gap-2">
              <Sliders className="h-4 w-4" />
              Trading
            </TabsTrigger>
            <TabsTrigger value="risk" className="flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Risk
            </TabsTrigger>
            <TabsTrigger value="notifications" className="flex items-center gap-2">
              <Bell className="h-4 w-4" />
              Notifications
            </TabsTrigger>
            <TabsTrigger value="system" className="flex items-center gap-2">
              <Cog className="h-4 w-4" />
              System
            </TabsTrigger>
          </TabsList>

          {/* Exchanges Tab */}
          <TabsContent value="exchanges">
            <Card>
              <CardHeader>
                <CardTitle>Exchange Connections</CardTitle>
                <CardDescription>
                  Configure API credentials for each exchange. Credentials are encrypted and stored securely.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {exchangesLoading ? (
                  <div className="text-center py-8 text-muted-foreground">Loading exchanges...</div>
                ) : (
                  <div className="space-y-4">
                    {exchanges.map((exchange) => (
                      <div
                        key={exchange.slug}
                        className="flex items-center justify-between p-4 border rounded-lg"
                      >
                        <div className="flex items-center gap-4">
                          <Switch
                            checked={exchange.enabled}
                            onCheckedChange={() => handleExchangeToggle(exchange)}
                          />
                          <div>
                            <div className="font-medium flex items-center gap-2">
                              {exchange.display_name}
                              <Badge variant="outline" className="text-xs">
                                {exchange.tier.replace('_', ' ')}
                              </Badge>
                              {exchange.exchange_type === 'dex' && (
                                <Badge variant="secondary" className="text-xs">DEX</Badge>
                              )}
                            </div>
                            <div className="text-sm text-muted-foreground flex items-center gap-2">
                              {exchange.has_credentials ? (
                                <>
                                  <CheckCircle2 className="h-3 w-3 text-green-500" />
                                  Credentials configured
                                </>
                              ) : (
                                <>
                                  <XCircle className="h-3 w-3 text-red-500" />
                                  No credentials
                                </>
                              )}
                              <span className="mx-2">|</span>
                              Maker: {(exchange.perp_maker_fee * 100).toFixed(3)}%
                              <span className="mx-1">/</span>
                              Taker: {(exchange.perp_taker_fee * 100).toFixed(3)}%
                            </div>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setSelectedExchange(exchange);
                              setShowCredentialDialog(true);
                            }}
                          >
                            {exchange.has_credentials ? 'Update' : 'Configure'}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Trading Tab */}
          <TabsContent value="trading">
            <div className="grid gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Trading Behavior</CardTitle>
                  <CardDescription>Configure how NEXUS detects and executes opportunities</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">Auto-Execute Opportunities</div>
                      <div className="text-sm text-muted-foreground">
                        Automatically execute opportunities above score threshold
                      </div>
                    </div>
                    <Switch
                      checked={getSettingValue('new_positions_enabled') === true}
                      onCheckedChange={() =>
                        handleSettingToggle('new_positions_enabled', getSettingValue('new_positions_enabled'))
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">Use ArbitrageScanner</div>
                      <div className="text-sm text-muted-foreground">
                        Enable secondary data source for validation
                      </div>
                    </div>
                    <Switch
                      checked={getSettingValue('arbitragescanner_enabled') === true}
                      onCheckedChange={() =>
                        handleSettingToggle('arbitragescanner_enabled', getSettingValue('arbitragescanner_enabled'))
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">Alerts Enabled</div>
                      <div className="text-sm text-muted-foreground">
                        Send notifications for important events
                      </div>
                    </div>
                    <Switch
                      checked={getSettingValue('alerts_enabled') === true}
                      onCheckedChange={() =>
                        handleSettingToggle('alerts_enabled', getSettingValue('alerts_enabled'))
                      }
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Max Concurrent Coins */}
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Position Limits</CardTitle>
                      <CardDescription>Control how many coins can be traded simultaneously</CardDescription>
                    </div>
                    {hasMaxCoinsChanges && (
                      <Button onClick={handleSaveMaxCoins} disabled={updateMaxCoinsMutation.isPending}>
                        {updateMaxCoinsMutation.isPending ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Save className="h-4 w-4 mr-2" />
                        )}
                        Save Changes
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="max_concurrent_coins">Max Concurrent Coins</Label>
                      <span className="text-sm text-muted-foreground">
                        {maxCoinsData?.current_coins ?? 0} / {getCurrentMaxCoins()} active
                        {maxCoinsData?.at_limit && (
                          <Badge variant="secondary" className="ml-2">At Limit</Badge>
                        )}
                      </span>
                    </div>
                    <Input
                      id="max_concurrent_coins"
                      type="number"
                      min="1"
                      max="20"
                      step="1"
                      value={getCurrentMaxCoins()}
                      onChange={(e) => handleMaxCoinsChange(e.target.value)}
                      className="w-full"
                    />
                    <div className="text-xs text-muted-foreground">
                      Maximum number of coins traded simultaneously (1-20). Each coin = 1 arbitrage position = 2 exchange positions (long + short).
                    </div>
                    {maxCoinsData?.at_limit && (
                      <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                        <p className="text-xs text-yellow-600 dark:text-yellow-400">
                          Position limit reached. New opportunities will be blocked until existing positions close.
                          Consider increasing the limit or closing underperforming positions.
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="mt-4 p-4 bg-muted rounded-lg">
                    <h4 className="font-medium text-sm mb-2">Auto-Unwind Behavior</h4>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li>• If active coins exceed the limit, weakest positions will auto-close</li>
                      <li>• Weakness is determined by net funding P&L, unrealized P&L, and hold time</li>
                      <li>• Both legs (long + short) are closed together</li>
                      <li>• Auto-unwind events are logged for audit purposes</li>
                    </ul>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Strategy Parameters</CardTitle>
                      <CardDescription>Current active strategy: {strategyParams.name || 'default'}</CardDescription>
                    </div>
                    {hasStrategyChanges && (
                      <Button onClick={handleSaveStrategy} disabled={updateStrategyMutation.isPending}>
                        {updateStrategyMutation.isPending ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Save className="h-4 w-4 mr-2" />
                        )}
                        Save Changes
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="min_net_apr_pct">Min Net APR (%)</Label>
                      <Input
                        id="min_net_apr_pct"
                        type="number"
                        step="1"
                        value={getMergedStrategy('min_net_apr_pct')}
                        onChange={(e) => handleStrategyChange('min_net_apr_pct', e.target.value)}
                      />
                      <div className="text-xs text-muted-foreground">
                        Minimum required net annual return
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="min_uos_score">Min UOS Score</Label>
                      <Input
                        id="min_uos_score"
                        type="number"
                        step="1"
                        value={getMergedStrategy('min_uos_score')}
                        onChange={(e) => handleStrategyChange('min_uos_score', e.target.value)}
                      />
                      <div className="text-xs text-muted-foreground">
                        Minimum Unified Opportunity Score (0-100)
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="min_volume_24h_usd">Min 24h Volume (USD)</Label>
                      <Input
                        id="min_volume_24h_usd"
                        type="number"
                        step="100000"
                        value={getMergedStrategy('min_volume_24h_usd')}
                        onChange={(e) => handleStrategyChange('min_volume_24h_usd', e.target.value)}
                      />
                      <div className="text-xs text-muted-foreground">
                        Minimum trading volume requirement
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="max_expected_slippage_pct">Max Slippage (%)</Label>
                      <Input
                        id="max_expected_slippage_pct"
                        type="number"
                        step="0.01"
                        value={getMergedStrategy('max_expected_slippage_pct')}
                        onChange={(e) => handleStrategyChange('max_expected_slippage_pct', e.target.value)}
                      />
                      <div className="text-xs text-muted-foreground">
                        Maximum acceptable slippage
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="stop_loss_pct">Stop Loss (%)</Label>
                      <Input
                        id="stop_loss_pct"
                        type="number"
                        step="0.1"
                        value={getMergedStrategy('stop_loss_pct')}
                        onChange={(e) => handleStrategyChange('stop_loss_pct', e.target.value)}
                      />
                      <div className="text-xs text-muted-foreground">
                        Position stop loss trigger
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="liquidity_multiple">Liquidity Multiple</Label>
                      <Input
                        id="liquidity_multiple"
                        type="number"
                        step="0.1"
                        value={getMergedStrategy('liquidity_multiple')}
                        onChange={(e) => handleStrategyChange('liquidity_multiple', e.target.value)}
                      />
                      <div className="text-xs text-muted-foreground">
                        Required order book depth vs position size
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Risk Tab */}
          <TabsContent value="risk">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Risk Limits</CardTitle>
                    <CardDescription>Configure position and portfolio risk parameters</CardDescription>
                  </div>
                  {hasRiskChanges && (
                    <Button onClick={handleSaveRiskLimits} disabled={updateRiskLimitsMutation.isPending}>
                      {updateRiskLimitsMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4 mr-2" />
                      )}
                      Save Changes
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-6 md:grid-cols-2">
                  {/* Position Limits */}
                  <div className="space-y-4">
                    <h3 className="font-semibold">Position Limits</h3>

                    <div className="space-y-2">
                      <Label htmlFor="max_position_size_usd">Max Position Size (USD)</Label>
                      <Input
                        id="max_position_size_usd"
                        type="number"
                        value={getMergedRiskLimit('max_position_size_usd')}
                        onChange={(e) => handleRiskLimitChange('max_position_size_usd', e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_position_size_pct">Max Position Size (%)</Label>
                      <Input
                        id="max_position_size_pct"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_position_size_pct')}
                        onChange={(e) => handleRiskLimitChange('max_position_size_pct', e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_leverage">Max Leverage</Label>
                      <Input
                        id="max_leverage"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_leverage')}
                        onChange={(e) => handleRiskLimitChange('max_leverage', e.target.value)}
                      />
                    </div>
                  </div>

                  {/* Concentration Limits */}
                  <div className="space-y-4">
                    <h3 className="font-semibold">Concentration Limits</h3>

                    <div className="space-y-2">
                      <Label htmlFor="max_venue_exposure_pct">Max Venue Exposure (%)</Label>
                      <Input
                        id="max_venue_exposure_pct"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_venue_exposure_pct')}
                        onChange={(e) => handleRiskLimitChange('max_venue_exposure_pct', e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_asset_exposure_pct">Max Asset Exposure (%)</Label>
                      <Input
                        id="max_asset_exposure_pct"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_asset_exposure_pct')}
                        onChange={(e) => handleRiskLimitChange('max_asset_exposure_pct', e.target.value)}
                      />
                    </div>
                  </div>

                  {/* Portfolio Limits */}
                  <div className="space-y-4">
                    <h3 className="font-semibold">Portfolio Limits</h3>

                    <div className="space-y-2">
                      <Label htmlFor="max_gross_exposure_pct">Max Gross Exposure (%)</Label>
                      <Input
                        id="max_gross_exposure_pct"
                        type="number"
                        step="1"
                        value={getMergedRiskLimit('max_gross_exposure_pct')}
                        onChange={(e) => handleRiskLimitChange('max_gross_exposure_pct', e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_net_exposure_pct">Max Net Exposure (%)</Label>
                      <Input
                        id="max_net_exposure_pct"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_net_exposure_pct')}
                        onChange={(e) => handleRiskLimitChange('max_net_exposure_pct', e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="max_drawdown_pct">Max Drawdown (%)</Label>
                      <Input
                        id="max_drawdown_pct"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_drawdown_pct')}
                        onChange={(e) => handleRiskLimitChange('max_drawdown_pct', e.target.value)}
                      />
                    </div>
                  </div>

                  {/* Risk Metrics */}
                  <div className="space-y-4">
                    <h3 className="font-semibold">Risk Metrics</h3>

                    <div className="space-y-2">
                      <Label htmlFor="max_var_pct">Max VaR (%)</Label>
                      <Input
                        id="max_var_pct"
                        type="number"
                        step="0.1"
                        value={getMergedRiskLimit('max_var_pct')}
                        onChange={(e) => handleRiskLimitChange('max_var_pct', e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Spread Monitoring Settings */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Spread Monitoring</CardTitle>
                    <CardDescription>
                      Configure automatic position exit thresholds based on spread deterioration
                    </CardDescription>
                  </div>
                  {hasSpreadMonitoringChanges && (
                    <Button onClick={handleSaveSpreadMonitoring} disabled={updateSpreadMonitoringMutation.isPending}>
                      {updateSpreadMonitoringMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4 mr-2" />
                      )}
                      Save Changes
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="spread_drawdown_exit_pct">Spread Drawdown Exit (%)</Label>
                    <Input
                      id="spread_drawdown_exit_pct"
                      type="number"
                      step="5"
                      min="10"
                      max="90"
                      value={getMergedSpreadMonitoring('spread_drawdown_exit_pct')}
                      onChange={(e) => handleSpreadMonitoringChange('spread_drawdown_exit_pct', e.target.value)}
                    />
                    <div className="text-xs text-muted-foreground">
                      Exit position when spread drops by this percentage from entry value (10-90%)
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="min_time_to_funding_exit_seconds">Funding Protection Window (seconds)</Label>
                    <Input
                      id="min_time_to_funding_exit_seconds"
                      type="number"
                      step="300"
                      min="0"
                      max="3600"
                      value={getMergedSpreadMonitoring('min_time_to_funding_exit_seconds')}
                      onChange={(e) => handleSpreadMonitoringChange('min_time_to_funding_exit_seconds', e.target.value)}
                    />
                    <div className="text-xs text-muted-foreground">
                      Don&apos;t auto-exit if funding payment is due within this window (0-3600s)
                    </div>
                  </div>
                </div>

                <div className="mt-4 p-4 bg-muted rounded-lg">
                  <h4 className="font-medium text-sm mb-2">How Spread Monitoring Works</h4>
                  <ul className="text-xs text-muted-foreground space-y-1">
                    <li>• Position spreads are monitored every 30 seconds</li>
                    <li>• Spread drawdown = (Entry Spread - Current Spread) / Entry Spread × 100</li>
                    <li>• Positions auto-exit when drawdown exceeds the configured threshold</li>
                    <li>• Exits are delayed if funding payment is imminent (within protection window)</li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Notifications Tab */}
          <TabsContent value="notifications">
            <Card>
              <CardHeader>
                <CardTitle>Alert Channels</CardTitle>
                <CardDescription>Configure where notifications are sent</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <div className="font-medium">Telegram Alerts</div>
                    <div className="text-sm text-muted-foreground">
                      Receive alerts via Telegram bot
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant="secondary">Coming Soon</Badge>
                    <Switch disabled />
                  </div>
                </div>

                <div className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <div className="font-medium">Discord Alerts</div>
                    <div className="text-sm text-muted-foreground">
                      Post alerts to Discord webhook
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant="secondary">Coming Soon</Badge>
                    <Switch disabled />
                  </div>
                </div>

                <div className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <div className="font-medium">Email Alerts</div>
                    <div className="text-sm text-muted-foreground">
                      Send critical alerts via email
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant="secondary">Coming Soon</Badge>
                    <Switch disabled />
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* System Tab */}
          <TabsContent value="system">
            <div className="grid gap-6">
              {/* Feature Status */}
              <Card>
                <CardHeader>
                  <CardTitle>Feature Status</CardTitle>
                  <CardDescription>
                    Implementation status of NEXUS features
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Funding Rate Collection</div>
                      <div className="text-sm text-muted-foreground">
                        Dual-source funding rate aggregation
                      </div>
                    </div>
                    <Badge variant="default" className="bg-green-500">Implemented</Badge>
                  </div>

                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Opportunity Detection</div>
                      <div className="text-sm text-muted-foreground">
                        UOS-based arbitrage opportunity scoring
                      </div>
                    </div>
                    <Badge variant="default" className="bg-green-500">Implemented</Badge>
                  </div>

                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Position Management</div>
                      <div className="text-sm text-muted-foreground">
                        Automated position monitoring and exit triggers
                      </div>
                    </div>
                    <Badge variant="default" className="bg-green-500">Implemented</Badge>
                  </div>

                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Auto-Execution</div>
                      <div className="text-sm text-muted-foreground">
                        Automatic trade execution based on UOS score
                      </div>
                    </div>
                    <Badge variant="default" className="bg-green-500">Implemented</Badge>
                  </div>

                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Backtesting Engine</div>
                      <div className="text-sm text-muted-foreground">
                        Historical strategy simulation
                      </div>
                    </div>
                    <Badge variant="secondary">Not Implemented</Badge>
                  </div>

                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Paper Trading Mode</div>
                      <div className="text-sm text-muted-foreground">
                        Simulated trading without real capital
                      </div>
                    </div>
                    <Badge variant="secondary">Not Implemented</Badge>
                  </div>

                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">Multi-User Support</div>
                      <div className="text-sm text-muted-foreground">
                        Multiple user accounts with permissions
                      </div>
                    </div>
                    <Badge variant="secondary">Not Implemented</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* System Information */}
              <Card>
                <CardHeader>
                  <CardTitle>System Information</CardTitle>
                  <CardDescription>
                    Version and configuration details
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Version</div>
                      <div className="font-medium">0.1.0-dev</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Environment</div>
                      <div className="font-medium">Development</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Database</div>
                      <div className="font-medium">PostgreSQL</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Message Broker</div>
                      <div className="font-medium">Redis Pub/Sub</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Danger Zone */}
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="text-destructive flex items-center gap-2">
                    <AlertCircle className="h-5 w-5" />
                    Danger Zone
                  </CardTitle>
                  <CardDescription>
                    Irreversible actions - use with caution
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between p-4 border border-destructive/50 rounded-lg">
                    <div>
                      <div className="font-medium">Reset All Positions</div>
                      <div className="text-sm text-muted-foreground">
                        Mark all positions as closed. Use for recovery scenarios.
                      </div>
                    </div>
                    <Button variant="destructive" disabled>
                      Reset Positions
                    </Button>
                  </div>

                  <div className="flex items-center justify-between p-4 border border-destructive/50 rounded-lg">
                    <div>
                      <div className="font-medium">Clear Symbol Blacklist</div>
                      <div className="text-sm text-muted-foreground">
                        Remove all entries from the symbol blacklist
                      </div>
                    </div>
                    <Button variant="destructive" disabled>
                      Clear Blacklist
                    </Button>
                  </div>

                  <div className="flex items-center justify-between p-4 border border-destructive/50 rounded-lg">
                    <div>
                      <div className="font-medium">Factory Reset</div>
                      <div className="text-sm text-muted-foreground">
                        Reset all settings to defaults (credentials preserved)
                      </div>
                    </div>
                    <Button variant="destructive" disabled>
                      Factory Reset
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>

        {/* Credential Dialog */}
        <Dialog open={showCredentialDialog} onOpenChange={setShowCredentialDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                Configure {selectedExchange?.display_name} Credentials
              </DialogTitle>
              <DialogDescription>
                {selectedExchange?.requires_on_chain
                  ? 'Enter your wallet credentials. They will be encrypted and stored securely.'
                  : 'Enter your API credentials. They will be encrypted and stored securely.'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {/* Wallet Address - for DEX/on-chain exchanges like Hyperliquid */}
              {isFieldRequired('wallet_address') && (
                <div className="space-y-2">
                  <Label htmlFor="wallet_address">{getFieldLabel('wallet_address')}</Label>
                  <div className="relative">
                    <Input
                      id="wallet_address"
                      type="text"
                      placeholder="0x..."
                      value={credentials.wallet_address}
                      onChange={(e) => setCredentials((prev) => ({ ...prev, wallet_address: e.target.value }))}
                    />
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Your Ethereum wallet address (EVM-compatible)
                  </div>
                </div>
              )}

              {/* API Key - for CEXes */}
              {isFieldRequired('api_key') && (
                <div className="space-y-2">
                  <Label htmlFor="api_key">{getFieldLabel('api_key')}</Label>
                  <div className="relative">
                    <Input
                      id="api_key"
                      type={showSecrets ? 'text' : 'password'}
                      placeholder="Enter API key"
                      value={credentials.api_key}
                      onChange={(e) => setCredentials((prev) => ({ ...prev, api_key: e.target.value }))}
                    />
                  </div>
                </div>
              )}

              {/* API Secret / Private Key */}
              {isFieldRequired('api_secret') && (
                <div className="space-y-2">
                  <Label htmlFor="api_secret">{getFieldLabel('api_secret')}</Label>
                  <div className="relative">
                    <Input
                      id="api_secret"
                      type={showSecrets ? 'text' : 'password'}
                      placeholder={selectedExchange?.requires_on_chain ? 'Enter private key' : 'Enter API secret'}
                      value={credentials.api_secret}
                      onChange={(e) => setCredentials((prev) => ({ ...prev, api_secret: e.target.value }))}
                    />
                  </div>
                  {selectedExchange?.requires_on_chain && (
                    <div className="text-xs text-muted-foreground">
                      Your wallet private key (never shared - only used for signing)
                    </div>
                  )}
                </div>
              )}

              {/* Passphrase - for exchanges like OKX */}
              {isFieldRequired('passphrase') && (
                <div className="space-y-2">
                  <Label htmlFor="passphrase">{getFieldLabel('passphrase')}</Label>
                  <div className="relative">
                    <Input
                      id="passphrase"
                      type={showSecrets ? 'text' : 'password'}
                      placeholder="Enter passphrase"
                      value={credentials.passphrase}
                      onChange={(e) => setCredentials((prev) => ({ ...prev, passphrase: e.target.value }))}
                    />
                  </div>
                  <div className="text-xs text-muted-foreground">
                    API passphrase set during API key creation
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowSecrets(!showSecrets)}
                >
                  {showSecrets ? (
                    <EyeOff className="h-4 w-4 mr-2" />
                  ) : (
                    <Eye className="h-4 w-4 mr-2" />
                  )}
                  {showSecrets ? 'Hide' : 'Show'} Credentials
                </Button>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCredentialDialog(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleCredentialsSave}
                disabled={
                  updateExchangeMutation.isPending ||
                  (isFieldRequired('api_key') && !credentials.api_key) ||
                  (isFieldRequired('api_secret') && !credentials.api_secret) ||
                  (isFieldRequired('wallet_address') && !credentials.wallet_address) ||
                  (isFieldRequired('passphrase') && !credentials.passphrase)
                }
              >
                {updateExchangeMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                Save Credentials
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
}
