import { describe, it, expect } from 'vitest';

// Test the sort functions used in the Opportunities page
// These are the same sort functions defined in opportunities/page.tsx

interface Opportunity {
  id: string;
  symbol: string;
  funding_spread_pct?: number;
  gross_funding_rate?: number;
  net_apr?: number;
  estimated_net_apr?: number;
  uos_score: number;
  scores?: { total: number };
  uos_score_direct?: number;
  expires_at: string;
}

// Helper to get UOS score from various sources (same as in page)
function getUOSScore(opp: Opportunity): number {
  return opp.scores?.total || opp.uos_score_direct || opp.uos_score || 0;
}

// Sort functions matching the implementation
const sortFunctions = {
  symbol: (a: Opportunity, b: Opportunity) => a.symbol.localeCompare(b.symbol),
  spread: (a: Opportunity, b: Opportunity) => (a.funding_spread_pct || a.gross_funding_rate || 0) - (b.funding_spread_pct || b.gross_funding_rate || 0),
  net_apr: (a: Opportunity, b: Opportunity) => (a.net_apr || a.estimated_net_apr || 0) - (b.net_apr || b.estimated_net_apr || 0),
  uos_score: (a: Opportunity, b: Opportunity) => getUOSScore(a) - getUOSScore(b),
  expires: (a: Opportunity, b: Opportunity) => new Date(a.expires_at).getTime() - new Date(b.expires_at).getTime(),
};

const mockOpportunities: Opportunity[] = [
  {
    id: '1',
    symbol: 'BTC-PERP',
    funding_spread_pct: 0.05,
    net_apr: 50,
    uos_score: 85,
    expires_at: '2024-01-15T08:00:00Z',
  },
  {
    id: '2',
    symbol: 'ETH-PERP',
    funding_spread_pct: 0.03,
    net_apr: 30,
    uos_score: 75,
    expires_at: '2024-01-15T04:00:00Z',
  },
  {
    id: '3',
    symbol: 'SOL-PERP',
    funding_spread_pct: 0.08,
    net_apr: 80,
    uos_score: 90,
    expires_at: '2024-01-15T12:00:00Z',
  },
];

describe('Opportunities Sorting', () => {
  describe('sortFunctions.symbol', () => {
    it('should sort by symbol alphabetically', () => {
      const sorted = [...mockOpportunities].sort(sortFunctions.symbol);
      expect(sorted.map(o => o.symbol)).toEqual(['BTC-PERP', 'ETH-PERP', 'SOL-PERP']);
    });
  });

  describe('sortFunctions.spread', () => {
    it('should sort by spread ascending (default for sort function)', () => {
      const sorted = [...mockOpportunities].sort(sortFunctions.spread);
      expect(sorted.map(o => o.symbol)).toEqual(['ETH-PERP', 'BTC-PERP', 'SOL-PERP']);
    });

    it('should sort by spread descending (reversed)', () => {
      const sorted = [...mockOpportunities].sort(sortFunctions.spread).reverse();
      expect(sorted.map(o => o.symbol)).toEqual(['SOL-PERP', 'BTC-PERP', 'ETH-PERP']);
    });

    it('should use gross_funding_rate as fallback', () => {
      const oppWithGross: Opportunity[] = [
        { id: '1', symbol: 'A', gross_funding_rate: 0.02, uos_score: 80, expires_at: '2024-01-15T08:00:00Z' },
        { id: '2', symbol: 'B', funding_spread_pct: 0.01, uos_score: 70, expires_at: '2024-01-15T08:00:00Z' },
      ];
      const sorted = [...oppWithGross].sort(sortFunctions.spread);
      expect(sorted.map(o => o.symbol)).toEqual(['B', 'A']);
    });
  });

  describe('sortFunctions.net_apr', () => {
    it('should sort by net_apr ascending', () => {
      const sorted = [...mockOpportunities].sort(sortFunctions.net_apr);
      expect(sorted.map(o => o.symbol)).toEqual(['ETH-PERP', 'BTC-PERP', 'SOL-PERP']);
    });

    it('should use estimated_net_apr as fallback', () => {
      const oppWithEstimated: Opportunity[] = [
        { id: '1', symbol: 'A', estimated_net_apr: 40, uos_score: 80, expires_at: '2024-01-15T08:00:00Z' },
        { id: '2', symbol: 'B', net_apr: 20, uos_score: 70, expires_at: '2024-01-15T08:00:00Z' },
      ];
      const sorted = [...oppWithEstimated].sort(sortFunctions.net_apr);
      expect(sorted.map(o => o.symbol)).toEqual(['B', 'A']);
    });
  });

  describe('sortFunctions.uos_score', () => {
    it('should sort by UOS score ascending', () => {
      const sorted = [...mockOpportunities].sort(sortFunctions.uos_score);
      expect(sorted.map(o => o.symbol)).toEqual(['ETH-PERP', 'BTC-PERP', 'SOL-PERP']);
    });

    it('should handle scores from different sources', () => {
      const oppWithDifferentScores: Opportunity[] = [
        { id: '1', symbol: 'A', uos_score: 60, scores: { total: 90 }, expires_at: '2024-01-15T08:00:00Z' },
        { id: '2', symbol: 'B', uos_score: 80, uos_score_direct: 70, expires_at: '2024-01-15T08:00:00Z' },
        { id: '3', symbol: 'C', uos_score: 50, expires_at: '2024-01-15T08:00:00Z' },
      ];
      const sorted = [...oppWithDifferentScores].sort(sortFunctions.uos_score);
      // A uses scores.total=90, B uses uos_score_direct=70, C uses uos_score=50
      expect(sorted.map(o => o.symbol)).toEqual(['C', 'B', 'A']);
    });
  });

  describe('sortFunctions.expires', () => {
    it('should sort by expiration time ascending', () => {
      const sorted = [...mockOpportunities].sort(sortFunctions.expires);
      expect(sorted.map(o => o.symbol)).toEqual(['ETH-PERP', 'BTC-PERP', 'SOL-PERP']);
    });
  });

  describe('getUOSScore', () => {
    it('should prefer scores.total over other sources', () => {
      const opp: Opportunity = { id: '1', symbol: 'A', uos_score: 50, uos_score_direct: 60, scores: { total: 70 }, expires_at: '' };
      expect(getUOSScore(opp)).toBe(70);
    });

    it('should use uos_score_direct as second priority', () => {
      const opp: Opportunity = { id: '1', symbol: 'A', uos_score: 50, uos_score_direct: 60, expires_at: '' };
      expect(getUOSScore(opp)).toBe(60);
    });

    it('should fall back to uos_score', () => {
      const opp: Opportunity = { id: '1', symbol: 'A', uos_score: 50, expires_at: '' };
      expect(getUOSScore(opp)).toBe(50);
    });

    it('should return 0 when no score available', () => {
      const opp: Opportunity = { id: '1', symbol: 'A', uos_score: 0, expires_at: '' };
      expect(getUOSScore(opp)).toBe(0);
    });
  });
});

describe('Opportunities Filtering', () => {
  const allOpportunities: Opportunity[] = [
    { id: '1', symbol: 'BTC-PERP', uos_score: 85, expires_at: '2024-01-15T08:00:00Z' },
    { id: '2', symbol: 'ETH-PERP', uos_score: 75, expires_at: '2024-01-15T04:00:00Z' },
    { id: '3', symbol: 'SOL-PERP', uos_score: 65, expires_at: '2024-01-15T12:00:00Z' },
    { id: '4', symbol: 'BTCUSDT', uos_score: 55, expires_at: '2024-01-15T16:00:00Z' },
  ];

  it('should filter by symbol search (case insensitive)', () => {
    const searchTerm = 'btc';
    const filtered = allOpportunities.filter((opp) =>
      opp.symbol.toLowerCase().includes(searchTerm.toLowerCase())
    );
    expect(filtered.map(o => o.symbol)).toEqual(['BTC-PERP', 'BTCUSDT']);
  });

  it('should filter by minimum UOS score', () => {
    const minScore = 70;
    const filtered = allOpportunities.filter((opp) => getUOSScore(opp) >= minScore);
    expect(filtered.map(o => o.symbol)).toEqual(['BTC-PERP', 'ETH-PERP']);
  });

  it('should handle combined filters', () => {
    const searchTerm = 'perp';
    const minScore = 70;
    const filtered = allOpportunities.filter((opp) =>
      opp.symbol.toLowerCase().includes(searchTerm.toLowerCase()) &&
      getUOSScore(opp) >= minScore
    );
    expect(filtered.map(o => o.symbol)).toEqual(['BTC-PERP', 'ETH-PERP']);
  });
});
