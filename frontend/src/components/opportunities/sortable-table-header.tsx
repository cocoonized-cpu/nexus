'use client';

import { useState, useMemo } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle } from 'lucide-react';

export type SortDirection = 'asc' | 'desc' | null;

export interface SortConfig<T extends string = string> {
  key: T;
  direction: SortDirection;
}

interface SortableTableHeaderProps<T extends string = string> {
  label: string;
  sortKey: T;
  currentSort: SortConfig<T>;
  onSort: (key: T) => void;
  tooltip?: string;
  className?: string;
}

export function SortableTableHeader<T extends string = string>({
  label,
  sortKey,
  currentSort,
  onSort,
  tooltip,
  className,
}: SortableTableHeaderProps<T>) {
  const isActive = currentSort.key === sortKey;
  const direction = isActive ? currentSort.direction : null;

  const SortIcon = () => {
    if (!isActive || !direction) {
      return <ArrowUpDown className="h-3 w-3 opacity-50" />;
    }
    return direction === 'asc' ? (
      <ArrowUp className="h-3 w-3" />
    ) : (
      <ArrowDown className="h-3 w-3" />
    );
  };

  return (
    <th className={cn('pb-3 font-medium', className)}>
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8 data-[state=open]:bg-accent"
        onClick={() => onSort(sortKey)}
      >
        <span className="flex items-center gap-1">
          {label}
          {tooltip && (
            <Tooltip>
              <TooltipTrigger asChild>
                <HelpCircle className="h-3 w-3 opacity-50" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                {tooltip}
              </TooltipContent>
            </Tooltip>
          )}
        </span>
        <SortIcon />
      </Button>
    </th>
  );
}

/**
 * Hook to manage sort state
 */
export function useSortState<T extends string>(
  defaultKey: T,
  defaultDirection: SortDirection = null
): [SortConfig<T>, (key: T) => void] {
  const [sort, setSort] = useState<SortConfig<T>>({
    key: defaultKey,
    direction: defaultDirection,
  });

  const handleSort = (key: T) => {
    setSort((prev) => {
      if (prev.key !== key) {
        return { key, direction: 'desc' };
      }
      // Cycle: null -> desc -> asc -> null
      const nextDirection: SortDirection =
        prev.direction === null
          ? 'desc'
          : prev.direction === 'desc'
          ? 'asc'
          : null;
      return { key, direction: nextDirection };
    });
  };

  return [sort, handleSort];
}

/**
 * Hook to sort an array based on sort config
 */
export function useSortedData<T, K extends string>(
  data: T[],
  sortConfig: SortConfig<K>,
  sortFunctions: Record<K, (a: T, b: T) => number>
): T[] {
  return useMemo(() => {
    if (!sortConfig.direction) return data;

    const sortFn = sortFunctions[sortConfig.key];
    if (!sortFn) return data;

    const sorted = [...data].sort(sortFn);
    return sortConfig.direction === 'asc' ? sorted : sorted.reverse();
  }, [data, sortConfig, sortFunctions]);
}
