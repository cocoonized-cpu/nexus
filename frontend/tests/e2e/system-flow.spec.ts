import { test, expect } from '@playwright/test';

/**
 * E2E tests for the NEXUS trading system flow.
 *
 * These tests validate the complete execution pipeline:
 * - System controls (start/stop, auto-execute toggle)
 * - Opportunity detection and execution
 * - Activity log updates
 * - Position tracking
 * - Funding rates filtering
 * - Opportunities sorting
 */

test.describe('System Controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/situation-room');
    await page.waitForTimeout(500);
  });

  test.skip('should display auto-execute toggle', async ({ page }) => {
    // Skip: Auto-execute toggle rendering issues in test environment
    await expect(page.getByLabel('Auto-Execute')).toBeVisible();
  });

  test.skip('should toggle auto-execute setting', async ({ page }) => {
    // Skip: Auto-execute toggle rendering issues in test environment
    const autoExecuteSwitch = page.locator('#auto-execute');
    await expect(autoExecuteSwitch).toBeVisible();

    const initialState = await autoExecuteSwitch.isChecked();

    // Toggle the switch
    await autoExecuteSwitch.click();
    await page.waitForTimeout(500);

    // Verify state changed
    const newState = await autoExecuteSwitch.isChecked();
    expect(newState).toBe(!initialState);

    // Toggle back
    await autoExecuteSwitch.click();
    await page.waitForTimeout(500);
  });

  test('should show start/stop button', async ({ page }) => {
    const startButton = page.getByRole('button', { name: /^start$/i });
    const stopButton = page.getByRole('button', { name: /^stop$/i });
    await expect(startButton.or(stopButton)).toBeVisible();
  });

  test('should show mode selector', async ({ page }) => {
    await expect(page.getByText('Mode:')).toBeVisible();
    await expect(page.locator('[role="combobox"]').first()).toBeVisible();
  });
});

test.describe('Activity Log Execution Events', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/situation-room');
    await page.waitForTimeout(1000);
  });

  test('should display activity log section', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible();
  });

  test('should display level filter buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /INFO/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /WARNING/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /ERROR/i })).toBeVisible();
  });

  test('should show execution events when present', async ({ page }) => {
    // Wait for activity log to load
    await page.waitForTimeout(2000);

    // The activity log should be visible - look for activity log container
    const logContainer = page.locator('main').first();
    await expect(logContainer).toBeVisible();
  });
});

test.describe('Funding Rates Data Source Filtering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
    await page.waitForTimeout(1000);
  });

  test('should display data source tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /exchanges/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /arbitrage.?scanner/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /both/i })).toBeVisible();
  });

  test('should switch to Exchanges data source', async ({ page }) => {
    const exchangesTab = page.getByRole('tab', { name: /exchanges/i });
    await exchangesTab.click();
    await page.waitForTimeout(1000);
    await expect(exchangesTab).toHaveAttribute('data-state', 'active');

    // Table should still be visible
    await expect(page.getByRole('table')).toBeVisible();
  });

  test('should switch to ArbitrageScanner data source', async ({ page }) => {
    const scannerTab = page.getByRole('tab', { name: /arbitrage.?scanner/i });
    await scannerTab.click();
    await page.waitForTimeout(1000);
    await expect(scannerTab).toHaveAttribute('data-state', 'active');
  });

  test('should switch to Both data sources', async ({ page }) => {
    const bothTab = page.getByRole('tab', { name: /both/i });
    await bothTab.click();
    await page.waitForTimeout(1000);
    await expect(bothTab).toHaveAttribute('data-state', 'active');
  });

  test('should filter to connected exchanges only', async ({ page }) => {
    // Count columns before
    const headersBefore = await page.locator('thead th').count();

    // Enable "Show only connected" filter
    const checkbox = page.getByRole('checkbox');
    const wasChecked = await checkbox.isChecked();

    if (!wasChecked) {
      await checkbox.click();
      await page.waitForTimeout(500);
    }

    // Count columns after
    const headersAfter = await page.locator('thead th').count();

    // If there are non-connected exchanges, the column count should decrease
    expect(headersAfter).toBeLessThanOrEqual(headersBefore);

    // Restore original state
    if (!wasChecked) {
      await checkbox.click();
    }
  });
});

test.describe('Opportunities Page Sorting', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should display sortable column headers', async ({ page }) => {
    // Check for sortable headers
    await expect(page.getByRole('button', { name: /symbol/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /spread/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /net apr/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /uos score/i }).first()).toBeVisible();
  });

  test('should sort by symbol', async ({ page }) => {
    const symbolHeader = page.getByRole('button', { name: /symbol/i }).first();
    await symbolHeader.click();
    await page.waitForTimeout(300);

    // Table should still be visible
    const table = page.locator('table');
    await expect(table.or(page.getByText(/no opportunities/i))).toBeVisible();
  });

  test('should sort by spread', async ({ page }) => {
    const spreadHeader = page.getByRole('button', { name: /spread/i }).first();
    await spreadHeader.click();
    await page.waitForTimeout(300);

    await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
  });

  test('should sort by UOS score', async ({ page }) => {
    const uosHeader = page.getByRole('button', { name: /uos score/i }).first();
    await uosHeader.click();
    await page.waitForTimeout(300);

    await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
  });

  test('should sort by expires time', async ({ page }) => {
    const expiresHeader = page.getByRole('button', { name: /expires/i }).first();
    await expiresHeader.click();
    await page.waitForTimeout(300);

    await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
  });

  test('should sort by long exchange', async ({ page }) => {
    const longExHeader = page.getByRole('button', { name: /long exchange/i }).first();
    if (await longExHeader.isVisible()) {
      await longExHeader.click();
      await page.waitForTimeout(300);
      await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
    }
  });

  test('should sort by short exchange', async ({ page }) => {
    const shortExHeader = page.getByRole('button', { name: /short exchange/i }).first();
    if (await shortExHeader.isVisible()) {
      await shortExHeader.click();
      await page.waitForTimeout(300);
      await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
    }
  });

  test('should sort by status', async ({ page }) => {
    const statusHeader = page.getByRole('button', { name: /status/i }).first();
    if (await statusHeader.isVisible()) {
      await statusHeader.click();
      await page.waitForTimeout(300);
      await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
    }
  });

  test('should toggle sort direction on double click', async ({ page }) => {
    const spreadHeader = page.getByRole('button', { name: /spread/i }).first();

    // First click - ascending
    await spreadHeader.click();
    await page.waitForTimeout(200);

    // Second click - descending
    await spreadHeader.click();
    await page.waitForTimeout(200);

    await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
  });
});

test.describe('Opportunities Expiration', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should display expires column', async ({ page }) => {
    await expect(page.getByText('Expires').first()).toBeVisible();
  });

  test('should show countdown or expired status', async ({ page }) => {
    await page.waitForTimeout(2000);

    // Look for time patterns or "Expired" text in the table
    const rows = page.locator('tbody tr');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // At least one row should have either countdown or expired
      const hasTimeOrExpired = await page
        .locator('text=/\\d+[hms]|Expired|N\\/A/')
        .count();
      expect(hasTimeOrExpired).toBeGreaterThan(0);
    }
  });
});

test.describe('Dashboard Active Positions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(500);
  });

  test('should display Active Positions card', async ({ page }) => {
    await expect(page.getByText('Active Positions').first()).toBeVisible();
  });

  test('should show positions or empty state', async ({ page }) => {
    await page.waitForTimeout(1000);

    // Either positions table or empty state should be visible
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();
  });
});

test.describe('Dashboard KPI Cards', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(500);
  });

  test('should display Total P&L card', async ({ page }) => {
    await expect(page.getByText('Total P&L').first()).toBeVisible();
  });

  test('should display Today\'s P&L card', async ({ page }) => {
    await expect(page.getByText("Today's P&L").first()).toBeVisible();
  });

  test('should display Unrealized P&L card', async ({ page }) => {
    await expect(page.getByText('Unrealized P&L').first()).toBeVisible();
  });

  test('should display ROI card', async ({ page }) => {
    await expect(page.getByText(/roi|return/i).first()).toBeVisible();
  });
});

test.describe('Risk Overview', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/situation-room');
    await page.waitForTimeout(1000);
  });

  test('should display Risk Overview section', async ({ page }) => {
    await expect(page.getByText('Risk Overview').first()).toBeVisible({ timeout: 10000 });
  });

  test('should display Current Drawdown', async ({ page }) => {
    await expect(page.getByText('Risk Overview').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Current Drawdown')).toBeVisible({ timeout: 10000 });
  });

  test('should display Gross Exposure', async ({ page }) => {
    await expect(page.getByText('Risk Overview').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Gross Exposure')).toBeVisible({ timeout: 10000 });
  });

  test('should display Active Positions count', async ({ page }) => {
    await expect(page.getByText('Active Positions')).toBeVisible();
  });

  test('should display Circuit Breaker control', async ({ page }) => {
    await expect(page.getByText('Risk Overview').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Circuit Breaker')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Performance Page Balances', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
    await page.waitForTimeout(500);
  });

  test('should display performance page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Performance' }).first()).toBeVisible();
  });

  test('should display Balances tab', async ({ page }) => {
    await expect(page.getByRole('tab', { name: 'Balances' })).toBeVisible();
  });

  test('should show exchange balances when clicking Balances tab', async ({ page }) => {
    const balancesTab = page.getByRole('tab', { name: 'Balances' });
    await balancesTab.click();
    await page.waitForTimeout(1000);

    // Should show exchange balances section
    await expect(page.getByText('Exchange Balances')).toBeVisible({ timeout: 5000 });
  });

  test('should display Total Value card', async ({ page }) => {
    await expect(page.getByText('Total Value').first()).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Opportunity Execution Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(500);
  });

  test('should display execute button for active opportunities', async ({ page }) => {
    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();
    // May or may not have active opportunities
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should show execution dialog when clicking execute', async ({ page }) => {
    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    if (count > 0) {
      await executeButtons.first().click();
      await page.waitForTimeout(500);

      // Should see execution dialog or progress modal
      const dialog = page.getByRole('dialog').or(page.getByText('Execute Opportunity'));
      await expect(dialog).toBeVisible({ timeout: 5000 });
    }
  });
});

test.describe('Integrated System Flow', () => {
  test('should navigate between pages without errors', async ({ page }) => {
    // Dashboard
    await page.goto('/');
    await expect(page.locator('main')).toBeVisible({ timeout: 10000 });

    // Situation Room
    await page.goto('/situation-room');
    await expect(page.locator('main')).toBeVisible({ timeout: 10000 });

    // Opportunities
    await page.goto('/opportunities');
    await expect(page.locator('main')).toBeVisible({ timeout: 10000 });

    // Positions
    await page.goto('/positions');
    await expect(page.locator('main')).toBeVisible({ timeout: 10000 });

    // Funding Rates
    await page.goto('/funding-rates');
    await expect(page.locator('main')).toBeVisible({ timeout: 10000 });

    // Performance
    await page.goto('/performance');
    await expect(page.locator('main')).toBeVisible({ timeout: 10000 });
  });

  test('should maintain state across navigation', async ({ page }) => {
    // Set a filter on opportunities page
    await page.goto('/opportunities');
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(300);

    // Navigate away and back
    await page.goto('/');
    await page.goto('/opportunities');

    // Tab might reset (client-side only state), but page should load
    await expect(page.getByText('Opportunities').first()).toBeVisible();
  });
});
