import { test, expect } from '@playwright/test';

const API_BASE = 'http://localhost:8000/api/v1';

test.describe('API Endpoints', () => {
  test.describe('Health API', () => {
    test('should return healthy status', async ({ request }) => {
      const response = await request.get(`${API_BASE}/health`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.status).toBe('healthy');
      expect(data.service).toBe('gateway');
    });

    test('should return ready status', async ({ request }) => {
      const response = await request.get(`${API_BASE}/health/ready`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.status).toMatch(/ready|degraded/);
      expect(data.checks).toBeDefined();
    });

    test('should return liveness status', async ({ request }) => {
      const response = await request.get(`${API_BASE}/health/live`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.status).toBe('alive');
    });
  });

  test.describe('Opportunities API', () => {
    test('should list opportunities', async ({ request }) => {
      const response = await request.get(`${API_BASE}/opportunities`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(Array.isArray(data.data)).toBeTruthy();
    });

    test('should filter opportunities by status', async ({ request }) => {
      const response = await request.get(`${API_BASE}/opportunities?status=detected`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should filter opportunities by limit', async ({ request }) => {
      const response = await request.get(`${API_BASE}/opportunities?limit=10`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.data.length).toBeLessThanOrEqual(10);
    });
  });

  test.describe('Positions API', () => {
    test('should list positions', async ({ request }) => {
      const response = await request.get(`${API_BASE}/positions`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(Array.isArray(data.data)).toBeTruthy();
    });

    test('should filter positions by status', async ({ request }) => {
      const response = await request.get(`${API_BASE}/positions?status=active`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });

  test.describe('Risk API', () => {
    test('should get risk limits', async ({ request }) => {
      const response = await request.get(`${API_BASE}/risk/limits`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.data).toBeDefined();
    });

    test('should get risk state', async ({ request }) => {
      const response = await request.get(`${API_BASE}/risk/state`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get risk alerts', async ({ request }) => {
      const response = await request.get(`${API_BASE}/risk/alerts`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });

  test.describe('Capital API', () => {
    test('should get capital summary', async ({ request }) => {
      const response = await request.get(`${API_BASE}/capital/summary`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.data).toBeDefined();
    });

    test('should get venue balances', async ({ request }) => {
      const response = await request.get(`${API_BASE}/capital/venues`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(Array.isArray(data.data)).toBeTruthy();
    });

    test('should get portfolio', async ({ request }) => {
      const response = await request.get(`${API_BASE}/capital/portfolio`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get portfolio history', async ({ request }) => {
      const response = await request.get(`${API_BASE}/capital/portfolio/history?days=30`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });

  test.describe('Config API', () => {
    test('should list exchanges', async ({ request }) => {
      const response = await request.get(`${API_BASE}/config/exchanges`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(Array.isArray(data.data)).toBeTruthy();
      expect(data.data.length).toBeGreaterThan(0);
    });

    test('should get system settings', async ({ request }) => {
      const response = await request.get(`${API_BASE}/config/settings`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get strategy parameters', async ({ request }) => {
      const response = await request.get(`${API_BASE}/config/strategy`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });

  test.describe('Funding API', () => {
    test('should get live funding matrix', async ({ request }) => {
      const response = await request.get(`${API_BASE}/funding/live/matrix`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get funding spreads', async ({ request }) => {
      const response = await request.get(`${API_BASE}/funding/live/spreads`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });

  test.describe('System API', () => {
    test('should get system status', async ({ request }) => {
      const response = await request.get(`${API_BASE}/system/status`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });

  test.describe('Analytics API', () => {
    test('should get daily PnL', async ({ request }) => {
      const response = await request.get(`${API_BASE}/analytics/daily`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get performance summary', async ({ request }) => {
      const response = await request.get(`${API_BASE}/analytics/summary?period=30d`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get funding history', async ({ request }) => {
      const response = await request.get(`${API_BASE}/analytics/funding`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    test('should get trade history', async ({ request }) => {
      const response = await request.get(`${API_BASE}/analytics/trades`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
    });
  });
});
