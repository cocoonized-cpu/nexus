import { describe, it, expect } from 'vitest';

// Test the filtering logic used in the Funding Rates page
// This tests the row filtering when "Show Connected Only" is enabled

interface FundingRate {
  rate: number;
  apr?: number;
  predicted?: number;
  next_funding_time?: string;
}

interface FundingRow {
  ticker: string;
  symbol: string;
  rates: Record<string, FundingRate | null>;
  max_spread: number;
}

interface Exchange {
  slug: string;
  name: string;
  status?: string;
}

describe('Funding Rates Row Filtering', () => {
  const mockExchanges: Exchange[] = [
    { slug: 'binance', name: 'Binance', status: 'connected' },
    { slug: 'bybit', name: 'Bybit', status: 'connected' },
    { slug: 'okx', name: 'OKX', status: 'disconnected' },
    { slug: 'gate', name: 'Gate', status: 'disconnected' },
  ];

  const mockRows: FundingRow[] = [
    {
      ticker: 'BTC',
      symbol: 'BTC-PERP',
      rates: {
        binance: { rate: 0.01 },
        bybit: { rate: 0.02 },
        okx: { rate: 0.015 },
        gate: null,
      },
      max_spread: 0.01,
    },
    {
      ticker: 'ETH',
      symbol: 'ETH-PERP',
      rates: {
        binance: null,
        bybit: null,
        okx: { rate: 0.025 },
        gate: { rate: 0.02 },
      },
      max_spread: 0.005,
    },
    {
      ticker: 'SOL',
      symbol: 'SOL-PERP',
      rates: {
        binance: { rate: 0.03 },
        bybit: null,
        okx: null,
        gate: null,
      },
      max_spread: 0.0,
    },
    {
      ticker: 'DOGE',
      symbol: 'DOGE-PERP',
      rates: {
        binance: null,
        bybit: null,
        okx: null,
        gate: null,
      },
      max_spread: 0.0,
    },
  ];

  // This is the filtering logic from funding-rates/page.tsx
  function filterRowsByVisibleExchanges(
    rows: FundingRow[],
    filteredExchanges: Exchange[],
    allExchangesCount: number
  ): FundingRow[] {
    // If all exchanges are shown, don't filter rows
    if (filteredExchanges.length === 0 || filteredExchanges.length >= allExchangesCount) {
      return rows;
    }

    const visibleExchangeSlugs = new Set(filteredExchanges.map(e => e.slug));

    return rows.filter((row) => {
      // Check if this row has at least one rate from a visible exchange
      return Object.keys(row.rates).some(slug => visibleExchangeSlugs.has(slug));
    });
  }

  describe('filterRowsByVisibleExchanges', () => {
    it('should return all rows when all exchanges are visible', () => {
      const filtered = filterRowsByVisibleExchanges(mockRows, mockExchanges, mockExchanges.length);
      expect(filtered.length).toBe(4);
    });

    it('should return all rows when no filter is applied (empty array)', () => {
      const filtered = filterRowsByVisibleExchanges(mockRows, [], mockExchanges.length);
      expect(filtered.length).toBe(4);
    });

    it('should filter rows when only some exchanges are visible', () => {
      // Only show connected exchanges (binance, bybit)
      const connectedExchanges = mockExchanges.filter(e => e.status === 'connected');
      const filtered = filterRowsByVisibleExchanges(mockRows, connectedExchanges, mockExchanges.length);

      // BTC has binance and bybit rates - should be included
      // ETH has only okx and gate rates - should be excluded
      // SOL has only binance rate - should be included
      // DOGE has no rates - should be excluded (no rates from visible exchanges)
      expect(filtered.map(r => r.ticker)).toEqual(['BTC', 'SOL']);
    });

    it('should filter rows when only disconnected exchanges are visible', () => {
      const disconnectedExchanges = mockExchanges.filter(e => e.status === 'disconnected');
      const filtered = filterRowsByVisibleExchanges(mockRows, disconnectedExchanges, mockExchanges.length);

      // Only ETH has okx/gate rates
      expect(filtered.map(r => r.ticker)).toEqual(['BTC', 'ETH']);
    });

    it('should correctly identify rows with rates from specific exchange', () => {
      // Only show binance
      const binanceOnly = mockExchanges.filter(e => e.slug === 'binance');
      const filtered = filterRowsByVisibleExchanges(mockRows, binanceOnly, mockExchanges.length);

      // BTC and SOL have binance rates
      expect(filtered.map(r => r.ticker)).toEqual(['BTC', 'SOL']);
    });

    it('should handle rows with null rates correctly', () => {
      // DOGE has all null rates, should never appear when filtering by specific exchanges
      const binanceOnly = mockExchanges.filter(e => e.slug === 'binance');
      const filtered = filterRowsByVisibleExchanges(mockRows, binanceOnly, mockExchanges.length);
      expect(filtered.map(r => r.ticker)).not.toContain('DOGE');
    });
  });

  describe('Search term filtering combined with exchange filtering', () => {
    function filterRowsBySearchAndExchanges(
      rows: FundingRow[],
      searchTerm: string,
      filteredExchanges: Exchange[],
      allExchangesCount: number
    ): FundingRow[] {
      let filtered = rows;

      // Apply search filter first
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        filtered = filtered.filter(
          (row) =>
            row.ticker.toLowerCase().includes(term) ||
            row.symbol.toLowerCase().includes(term)
        );
      }

      // Then apply exchange filter
      if (filteredExchanges.length > 0 && filteredExchanges.length < allExchangesCount) {
        const visibleExchangeSlugs = new Set(filteredExchanges.map(e => e.slug));
        filtered = filtered.filter((row) =>
          Object.keys(row.rates).some(slug => visibleExchangeSlugs.has(slug))
        );
      }

      return filtered;
    }

    it('should combine search and exchange filters', () => {
      const connectedExchanges = mockExchanges.filter(e => e.status === 'connected');
      const filtered = filterRowsBySearchAndExchanges(
        mockRows,
        'btc',
        connectedExchanges,
        mockExchanges.length
      );

      // Search for 'btc', only show connected exchanges
      // Only BTC row matches search and has connected exchange rates
      expect(filtered.map(r => r.ticker)).toEqual(['BTC']);
    });

    it('should return empty when search matches but no visible exchange rates', () => {
      const disconnectedExchanges = mockExchanges.filter(e => e.status === 'disconnected');
      const filtered = filterRowsBySearchAndExchanges(
        mockRows,
        'sol',
        disconnectedExchanges,
        mockExchanges.length
      );

      // SOL matches search but only has binance rate (connected, not in filter)
      expect(filtered.length).toBe(0);
    });
  });
});
