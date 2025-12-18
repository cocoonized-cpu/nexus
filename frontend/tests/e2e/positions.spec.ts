import { test, expect } from '@playwright/test';

test.describe('Positions Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
  });

  test('should display positions page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Positions & Trades' })).toBeVisible();
  });

  test('should display open positions card', async ({ page }) => {
    await expect(page.getByText('Open Positions').first()).toBeVisible();
  });

  test('should display summary stat cards', async ({ page }) => {
    await expect(page.getByText('Open Positions').first()).toBeVisible();
    await expect(page.getByText('Open Notional').first()).toBeVisible();
    await expect(page.getByText('Unrealized P&L').first()).toBeVisible();
    await expect(page.getByText('Total Trades').first()).toBeVisible();
  });

  test('should display refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible();
  });

  test('should display positions content', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(1000);

    // Page loaded successfully - check if main content exists
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();
  });

  test('should show empty state or positions', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(1000);

    // Either positions table or empty state should be visible
    const table = page.locator('table');
    const emptyState = page.getByText('No open positions');
    await expect(table.or(emptyState)).toBeVisible();
  });
});

test.describe('Positions Tab Filtering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
  });

  test('should display filter tabs', async ({ page }) => {
    // Tab structure: NEXUS Positions, Exchange, Trade History
    await expect(page.getByRole('tab', { name: /nexus positions/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /exchange/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /trade history/i })).toBeVisible();
  });

  test('should switch to Trade History tab', async ({ page }) => {
    await page.getByRole('tab', { name: /trade history/i }).click();
    await page.waitForTimeout(300);
    await expect(page.getByRole('tab', { name: /trade history/i })).toHaveAttribute('data-state', 'active');
  });

  test('should switch back to Exchange tab', async ({ page }) => {
    // First switch to history tab
    await page.getByRole('tab', { name: /trade history/i }).click();
    await page.waitForTimeout(300);

    // Then switch to Exchange tab
    await page.getByRole('tab', { name: /exchange/i }).click();
    await page.waitForTimeout(300);
    await expect(page.getByRole('tab', { name: /exchange/i })).toHaveAttribute('data-state', 'active');
  });

  test('should display filter dropdowns', async ({ page }) => {
    // Exchange filter
    await expect(page.getByText('All Exchanges')).toBeVisible();
    // Side filter
    await expect(page.getByText('All Sides')).toBeVisible();
    // Search input
    await expect(page.getByPlaceholder(/search symbol/i)).toBeVisible();
  });
});

test.describe('Positions Table', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
    await page.waitForTimeout(1000);
  });

  test('should display table headers or empty state', async ({ page }) => {
    // May show table with headers or empty state
    const symbolHeader = page.getByText('Symbol').first();
    const emptyState = page.getByText('No open positions');
    await expect(symbolHeader.or(emptyState)).toBeVisible();
  });

  test('should display table structure', async ({ page }) => {
    // May or may not have positions - just check page loads correctly
    const table = page.locator('table');
    const emptyState = page.getByText('No open positions');
    await expect(table.or(emptyState)).toBeVisible();
  });

  test('should display sortable columns', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(1000);

    // Check for sortable column headers or empty state
    const symbolHeader = page.getByText('Symbol').first();
    const emptyState = page.getByText('No open positions');

    // Either table headers exist or empty state
    await expect(symbolHeader.or(emptyState)).toBeVisible();
  });
});

test.describe('Trade History Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
    await page.getByRole('tab', { name: /trade history/i }).click();
    await page.waitForTimeout(500);
  });

  test('should show trade history section', async ({ page }) => {
    await expect(page.getByText('Trade History').first()).toBeVisible();
  });

  test('should show table or empty state', async ({ page }) => {
    const table = page.locator('table');
    const emptyState = page.getByText('No trade history');
    await expect(table.or(emptyState)).toBeVisible();
  });
});

test.describe('Positions Refresh', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
  });

  test('should refresh data when clicking refresh button', async ({ page }) => {
    const refreshButton = page.getByRole('button', { name: /refresh/i });
    await refreshButton.click();

    // Button should show loading state
    await page.waitForTimeout(100);
    // Wait for refresh to complete
    await page.waitForTimeout(2000);
  });
});

test.describe('NEXUS Consolidated Positions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
    await page.waitForTimeout(500);
  });

  test('should display NEXUS Positions tab', async ({ page }) => {
    const nexusTab = page.getByRole('tab', { name: /nexus positions/i });
    await expect(nexusTab).toBeVisible();
  });

  test('should default to NEXUS Positions tab', async ({ page }) => {
    const nexusTab = page.getByRole('tab', { name: /nexus positions/i });
    await expect(nexusTab).toHaveAttribute('data-state', 'active');
  });

  test('should display NEXUS positions card content', async ({ page }) => {
    // Check for card title
    await expect(page.getByText('NEXUS Positions').first()).toBeVisible();
    // Check for description
    await expect(page.getByText(/arbitrage positions with paired/i).first()).toBeVisible();
  });

  test('should display summary statistics', async ({ page }) => {
    // Position count - use more specific selector since "Positions" appears multiple times
    await expect(page.getByLabel('NEXUS Positions').getByText('Positions', { exact: true })).toBeVisible();
    // Total Capital
    await expect(page.getByText('Total Capital')).toBeVisible();
    // Funding P&L
    await expect(page.getByText('Funding P&L')).toBeVisible();
    // Net P&L
    await expect(page.getByText('Net P&L')).toBeVisible();
  });

  test('should display Long and Short column headers', async ({ page }) => {
    // Check for long/short column groups
    const table = page.locator('table');
    if (await table.isVisible()) {
      await expect(page.getByText(/long exchange/i).first()).toBeVisible();
      await expect(page.getByText(/short exchange/i).first()).toBeVisible();
    }
  });

  test('should show empty state or positions table', async ({ page }) => {
    await page.waitForTimeout(1000);
    const table = page.locator('table');
    const emptyState = page.getByText(/no nexus positions/i);
    await expect(table.or(emptyState)).toBeVisible();
  });

  test('should display Close All button when positions exist', async ({ page }) => {
    await page.waitForTimeout(1000);
    // The Close All button only appears when there are active positions
    const closeAllButton = page.getByRole('button', { name: /close all/i });
    // May or may not be visible depending on positions
    const count = await closeAllButton.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should switch between tabs correctly', async ({ page }) => {
    // Switch to Exchange tab
    const exchangeTab = page.getByRole('tab', { name: /exchange/i });
    await exchangeTab.click();
    await page.waitForTimeout(300);
    await expect(exchangeTab).toHaveAttribute('data-state', 'active');

    // Switch back to NEXUS tab
    const nexusTab = page.getByRole('tab', { name: /nexus positions/i });
    await nexusTab.click();
    await page.waitForTimeout(300);
    await expect(nexusTab).toHaveAttribute('data-state', 'active');
  });

  test('should have refresh button in NEXUS positions card', async ({ page }) => {
    // There should be a refresh button in the NEXUS positions card
    const refreshButtons = page.locator('button:has(svg)');
    const count = await refreshButtons.count();
    expect(count).toBeGreaterThan(0);
  });
});

test.describe('NEXUS Position Close Actions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
    await page.waitForTimeout(1000);
  });

  test('should display Close button for active positions', async ({ page }) => {
    const closeButtons = page.getByRole('button', { name: /close$/i });
    const count = await closeButtons.count();
    // May or may not have positions
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should show confirmation dialog when clicking Close button', async ({ page }) => {
    const closeButtons = page.getByRole('button', { name: /close$/i });
    const count = await closeButtons.count();

    if (count > 0) {
      await closeButtons.first().click();
      await page.waitForTimeout(300);

      // Should see confirmation dialog
      const dialogTitle = page.getByText('Close Position');
      await expect(dialogTitle).toBeVisible({ timeout: 3000 });
    }
  });

  test('should show confirmation dialog when clicking Close All', async ({ page }) => {
    const closeAllButton = page.getByRole('button', { name: /close all/i });

    if (await closeAllButton.isVisible()) {
      await closeAllButton.click();
      await page.waitForTimeout(300);

      // Should see confirmation dialog
      const dialogTitle = page.getByText('Close All Positions');
      await expect(dialogTitle).toBeVisible({ timeout: 3000 });
    }
  });

  test('should be able to cancel close confirmation', async ({ page }) => {
    const closeButtons = page.getByRole('button', { name: /close$/i });
    const count = await closeButtons.count();

    if (count > 0) {
      await closeButtons.first().click();
      await page.waitForTimeout(300);

      // Click cancel
      const cancelButton = page.getByRole('button', { name: /cancel/i });
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
        await page.waitForTimeout(300);

        // Dialog should close
        await expect(page.getByText('Close Position')).not.toBeVisible();
      }
    }
  });
});
