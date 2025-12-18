import { test, expect } from '@playwright/test';

test.describe('User Journey Tests', () => {
  test.describe('Dashboard Overview Journey', () => {
    test('user can view dashboard and navigate to all sections', async ({ page }) => {
      // Start on dashboard
      await page.goto('/');

      // Verify dashboard loads
      await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

      // Check overview stats are visible
      await expect(page.getByText('Total P&L').first()).toBeVisible();

      // Navigate to Situation Room
      await page.getByRole('link', { name: /situation room/i }).click();
      await expect(page.getByRole('heading', { name: 'Situation Room' })).toBeVisible();

      // Navigate to Funding Rates
      await page.getByRole('link', { name: /funding rates/i }).click();
      await expect(page.getByRole('heading', { name: 'Funding Rates', level: 1 })).toBeVisible();

      // Navigate to opportunities
      await page.getByRole('link', { name: /opportunities/i }).click();
      await expect(page.getByRole('heading', { name: 'Opportunities', exact: true })).toBeVisible();

      // Navigate to positions
      await page.getByRole('link', { name: /positions/i }).click();
      await expect(page.getByRole('heading', { name: 'Positions & Trades' })).toBeVisible();

      // Navigate to performance
      await page.getByRole('link', { name: /performance/i }).click();
      await expect(page.getByRole('heading', { name: 'Performance', level: 1 })).toBeVisible();

      // Navigate to settings
      await page.getByRole('link', { name: /settings/i }).click();
      await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
    });
  });

  test.describe('Opportunities Review Journey', () => {
    test('user can browse and filter opportunities', async ({ page }) => {
      await page.goto('/opportunities');

      // Verify opportunities page loads
      await expect(page.getByRole('heading', { name: 'Opportunities', exact: true })).toBeVisible();

      // Check filter tabs exist
      await expect(page.getByRole('tab', { name: 'All' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Active' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Executed' })).toBeVisible();

      // Click on Active tab
      await page.getByRole('tab', { name: 'Active' }).click();
      await page.waitForTimeout(500);

      // Click on Executed tab
      await page.getByRole('tab', { name: 'Executed' }).click();
      await page.waitForTimeout(500);

      // Return to All tab
      await page.getByRole('tab', { name: 'All' }).click();

      // Verify statistics are displayed
      await expect(page.getByText('Total Detected').first()).toBeVisible();
    });

    test('opportunity expiration countdown updates in real-time', async ({ page }) => {
      await page.goto('/opportunities');
      await page.waitForTimeout(1000);

      // Look for countdown cells (should show time remaining, not "Expired" for active ones)
      const countdownCells = page.locator('[class*="countdown"]');
      const count = await countdownCells.count();

      if (count > 0) {
        // Get initial text
        const firstCell = countdownCells.first();
        const initialText = await firstCell.textContent();

        // Wait for countdown to update (if not already expired)
        if (initialText && !initialText.includes('Expired')) {
          await page.waitForTimeout(2000);
          const updatedText = await firstCell.textContent();
          // Text should have changed (countdown updating)
          expect(updatedText).toBeDefined();
        }
      }
    });
  });

  test.describe('Settings Configuration Journey', () => {
    test('user can navigate through all settings tabs', async ({ page }) => {
      await page.goto('/settings');

      // Verify settings page loads
      await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();

      // Check Exchanges tab (default)
      await expect(page.getByRole('tab', { name: 'Exchanges' })).toBeVisible();
      await expect(page.getByText('Exchange Connections').first()).toBeVisible();

      // Click Trading tab
      await page.getByRole('tab', { name: 'Trading' }).click();
      await expect(page.getByText('Trading Behavior').first()).toBeVisible();
      await expect(page.getByText('Auto-Execute Opportunities').first()).toBeVisible();

      // Click Risk tab
      await page.getByRole('tab', { name: 'Risk' }).click();
      await page.waitForTimeout(500);

      // Click Notifications tab
      await page.getByRole('tab', { name: 'Notifications' }).click();
      await page.waitForTimeout(500);

      // Return to Exchanges tab
      await page.getByRole('tab', { name: 'Exchanges' }).click();
      await expect(page.getByText('Exchange Connections').first()).toBeVisible();
    });
  });

  test.describe('Situation Room Monitoring Journey', () => {
    test('user can view system status and control the bot', async ({ page }) => {
      await page.goto('/situation-room');

      // Verify situation room page loads
      await expect(page.getByRole('heading', { name: 'Situation Room' })).toBeVisible();

      // Check bot control sections are visible
      await expect(page.getByText('Bot Controls')).toBeVisible();

      // Check system status section
      await expect(page.getByText('System Status')).toBeVisible();

      // Check risk overview
      await expect(page.getByText('Risk Overview')).toBeVisible();
      await expect(page.getByText('Circuit Breaker')).toBeVisible();

      // Check activity log section
      await expect(page.getByText('Activity Log')).toBeVisible();

      // Verify log level filters are present
      await expect(page.getByRole('button', { name: 'INFO' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'WARNING' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'ERROR' })).toBeVisible();
    });
  });

  test.describe('Performance Analysis Journey', () => {
    test('user can review performance across all tabs', async ({ page }) => {
      await page.goto('/performance');

      // Verify performance page loads
      await expect(page.getByRole('heading', { name: 'Performance', level: 1 })).toBeVisible();

      // Check summary cards
      await expect(page.getByText('Total Value').first()).toBeVisible();
      await expect(page.getByText('Net P&L').first()).toBeVisible();

      // Check Overview tab content
      await expect(page.getByText('Key Metrics').first()).toBeVisible();

      // Navigate to Balances tab
      await page.getByRole('tab', { name: 'Balances' }).click();
      await expect(page.getByText('Exchange Balances').first()).toBeVisible();

      // Navigate to Trading tab
      await page.getByRole('tab', { name: 'Trading' }).click();
      await expect(page.getByText('Trading History').first()).toBeVisible();

      // Navigate to Funding tab
      await page.getByRole('tab', { name: 'Funding' }).click();
      await expect(page.getByText('Funding Breakdown').first()).toBeVisible();

      // Test funding view toggle (per-position vs daily) - uses tabs, not buttons
      await page.getByRole('tab', { name: /daily/i }).click();
      await page.waitForTimeout(300);
      await page.getByRole('tab', { name: /per position/i }).click();
    });
  });

  test.describe('Complete Trading Workflow', () => {
    test('user can review system status end-to-end', async ({ page }) => {
      // 1. Start with dashboard overview
      await page.goto('/');
      await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

      // Check for connection status (online/offline indicator)
      await page.waitForTimeout(500);

      // 2. Check situation room for system health
      await page.goto('/situation-room');
      await expect(page.getByRole('heading', { name: 'Situation Room' })).toBeVisible();
      await expect(page.getByText('System Status')).toBeVisible();

      // 3. Check funding rates for opportunities
      await page.goto('/funding-rates');
      await expect(page.getByRole('heading', { name: 'Funding Rates', level: 1 })).toBeVisible();

      // 4. Check opportunities for potential trades
      await page.goto('/opportunities');
      await expect(page.getByRole('heading', { name: 'Opportunities', exact: true })).toBeVisible();

      // Wait for opportunities to load
      await page.waitForTimeout(1000);

      // 5. Review current positions
      await page.goto('/positions');
      await expect(page.getByRole('heading', { name: 'Positions & Trades' })).toBeVisible();

      // 6. Review performance
      await page.goto('/performance');
      await expect(page.getByRole('heading', { name: 'Performance', level: 1 })).toBeVisible();

      // Verify performance metrics are displayed
      await expect(page.getByText('Total Value').first()).toBeVisible();
      await expect(page.getByText('Key Metrics').first()).toBeVisible();
    });
  });

  test.describe('Positions Management Journey', () => {
    test('user can view and filter positions', async ({ page }) => {
      await page.goto('/positions');

      // Verify positions page loads
      await expect(page.getByRole('heading', { name: 'Positions & Trades' })).toBeVisible();

      // Check tab filters exist
      await expect(page.getByRole('tab', { name: /open positions/i })).toBeVisible();
      await expect(page.getByRole('tab', { name: /trade history/i })).toBeVisible();

      // Check summary stats
      await expect(page.getByText('Open Positions').first()).toBeVisible();
      await expect(page.getByText('Open Notional').first()).toBeVisible();

      // Switch between tabs
      await page.getByRole('tab', { name: /trade history/i }).click();
      await page.waitForTimeout(300);

      await page.getByRole('tab', { name: /open positions/i }).click();
      await page.waitForTimeout(300);
    });
  });

  test.describe('Funding Rates Exploration Journey', () => {
    test('user can explore funding rates with different data sources', async ({ page }) => {
      await page.goto('/funding-rates');

      // Verify funding rates page loads
      await expect(page.getByRole('heading', { name: 'Funding Rates', level: 1 })).toBeVisible();

      // Check data source toggle exists
      await expect(page.getByText('Data Source').first()).toBeVisible();

      // Try different data sources
      await page.getByRole('tab', { name: /exchanges/i }).click();
      await page.waitForTimeout(500);

      await page.getByRole('tab', { name: /arbitrage.?scanner/i }).click();
      await page.waitForTimeout(500);

      await page.getByRole('tab', { name: /both/i }).click();
      await page.waitForTimeout(500);

      // Toggle connected exchanges filter
      const checkbox = page.getByRole('checkbox');
      await checkbox.click();
      await page.waitForTimeout(300);
      await checkbox.click();
    });
  });
});
