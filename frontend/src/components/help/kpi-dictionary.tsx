'use client';

import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Search,
  TrendingUp,
  Wallet,
  BarChart3,
  Star,
  Shield,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  KPI_DEFINITIONS,
  KPI_CATEGORIES,
  getKPIsByCategory,
  searchKPIs,
  type KPIDefinition,
} from '@/lib/kpi-definitions';

const CATEGORY_ICONS = {
  funding: TrendingUp,
  position: Wallet,
  performance: BarChart3,
  uos: Star,
  risk: Shield,
  execution: Zap,
} as const;

const CATEGORY_COLORS = {
  funding: 'bg-green-500/10 text-green-500 border-green-500/20',
  position: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  performance: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  uos: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  risk: 'bg-red-500/10 text-red-500 border-red-500/20',
  execution: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
} as const;

function KPICard({ kpi }: { kpi: KPIDefinition }) {
  const CategoryIcon = CATEGORY_ICONS[kpi.category];

  return (
    <AccordionItem value={kpi.id} className="border rounded-lg px-4 mb-2">
      <AccordionTrigger className="hover:no-underline py-4">
        <div className="flex items-center gap-3 text-left">
          <div className={cn('p-2 rounded-lg', CATEGORY_COLORS[kpi.category])}>
            <CategoryIcon className="h-4 w-4" />
          </div>
          <div>
            <div className="font-medium">{kpi.name}</div>
            {kpi.shortName && (
              <div className="text-xs text-muted-foreground">({kpi.shortName})</div>
            )}
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-4 pt-2 pb-4">
          <p className="text-sm text-muted-foreground">{kpi.description}</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            {kpi.formula && (
              <div className="space-y-1">
                <div className="font-medium text-xs uppercase text-muted-foreground">
                  Formula
                </div>
                <div className="font-mono text-xs bg-muted p-2 rounded">
                  {kpi.formula}
                </div>
              </div>
            )}

            {kpi.unit && (
              <div className="space-y-1">
                <div className="font-medium text-xs uppercase text-muted-foreground">
                  Unit
                </div>
                <div>{kpi.unit}</div>
              </div>
            )}

            {kpi.range && (
              <div className="space-y-1">
                <div className="font-medium text-xs uppercase text-muted-foreground">
                  Typical Range
                </div>
                <div>{kpi.range}</div>
              </div>
            )}

            {kpi.example && (
              <div className="space-y-1">
                <div className="font-medium text-xs uppercase text-muted-foreground">
                  Example
                </div>
                <div className="text-muted-foreground">{kpi.example}</div>
              </div>
            )}
          </div>

          {kpi.location && kpi.location.length > 0 && (
            <div className="space-y-2">
              <div className="font-medium text-xs uppercase text-muted-foreground">
                Where to find it
              </div>
              <div className="flex flex-wrap gap-2">
                {kpi.location.map((loc) => (
                  <Badge key={loc} variant="secondary" className="text-xs">
                    {loc}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

interface KPIDictionaryProps {
  className?: string;
}

export function KPIDictionary({ className }: KPIDictionaryProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('all');

  const filteredKPIs = useMemo(() => {
    let results = KPI_DEFINITIONS;

    if (searchQuery) {
      results = searchKPIs(searchQuery);
    }

    if (activeCategory !== 'all') {
      results = results.filter((kpi) => kpi.category === activeCategory);
    }

    return results;
  }, [searchQuery, activeCategory]);

  const categories = Object.entries(KPI_CATEGORIES);

  return (
    <div className={cn('space-y-6', className)}>
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search metrics..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Category Tabs */}
      <Tabs value={activeCategory} onValueChange={setActiveCategory}>
        <TabsList className="flex flex-wrap h-auto gap-1 bg-transparent p-0">
          <TabsTrigger
            value="all"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            All ({KPI_DEFINITIONS.length})
          </TabsTrigger>
          {categories.map(([key, cat]) => {
            const Icon = CATEGORY_ICONS[key as keyof typeof CATEGORY_ICONS];
            const count = getKPIsByCategory(key as KPIDefinition['category']).length;
            return (
              <TabsTrigger
                key={key}
                value={key}
                className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                <Icon className="h-3 w-3 mr-1" />
                {cat.name.replace(' Metrics', '').replace(' Components', '')} ({count})
              </TabsTrigger>
            );
          })}
        </TabsList>

        <TabsContent value={activeCategory} className="mt-6">
          {/* Category Description */}
          {activeCategory !== 'all' && (
            <div className="mb-4 p-4 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2">
                {(() => {
                  const Icon = CATEGORY_ICONS[activeCategory as keyof typeof CATEGORY_ICONS];
                  return Icon && <Icon className="h-5 w-5" />;
                })()}
                <h3 className="font-semibold">
                  {KPI_CATEGORIES[activeCategory as keyof typeof KPI_CATEGORIES]?.name}
                </h3>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {KPI_CATEGORIES[activeCategory as keyof typeof KPI_CATEGORIES]?.description}
              </p>
            </div>
          )}

          {/* KPI List */}
          {filteredKPIs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No metrics found matching your search
            </div>
          ) : (
            <Accordion type="multiple" className="space-y-2">
              {filteredKPIs.map((kpi) => (
                <KPICard key={kpi.id} kpi={kpi} />
              ))}
            </Accordion>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
