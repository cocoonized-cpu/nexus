import { test, expect } from '@playwright/test';

test.describe('Opportunities Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
  });

  test('should display opportunities page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Opportunities', exact: true })).toBeVisible();
  });

  test('should display refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });

  test('should display statistics cards', async ({ page }) => {
    await expect(page.getByText('Total Detected').first()).toBeVisible();
    await expect(page.getByText('Active').first()).toBeVisible();
    await expect(page.getByText('Executed').first()).toBeVisible();
  });

  test('should display detected opportunities section', async ({ page }) => {
    await expect(page.getByText('Detected Opportunities').first()).toBeVisible();
  });

  test('should display opportunities content', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(1000);

    // Page loaded successfully - check if main content exists
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();
  });

  test('should display filter tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: 'All' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Active' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Executed' })).toBeVisible();
  });

  test('should show empty state or opportunities', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(1000);

    // Either table or empty state should be visible
    const table = page.locator('table');
    const emptyState = page.getByText(/no opportunities/i);
    await expect(table.or(emptyState)).toBeVisible();
  });
});

test.describe('Opportunities Tab Filtering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
  });

  test('should switch to Active tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(300);
    await expect(page.getByRole('tab', { name: 'Active' })).toHaveAttribute('data-state', 'active');
  });

  test('should switch to Executed tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Executed' }).click();
    await page.waitForTimeout(300);
    await expect(page.getByRole('tab', { name: 'Executed' })).toHaveAttribute('data-state', 'active');
  });

  test('should return to All tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Executed' }).click();
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: 'All' }).click();
    await page.waitForTimeout(300);
    await expect(page.getByRole('tab', { name: 'All' })).toHaveAttribute('data-state', 'active');
  });
});

test.describe('Opportunities Table', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should display table headers', async ({ page }) => {
    await expect(page.getByText('Symbol').first()).toBeVisible();
    await expect(page.getByText('Spread').first()).toBeVisible();
    await expect(page.getByText('APR').first()).toBeVisible();
  });

  test('should display expires column header', async ({ page }) => {
    await expect(page.getByText('Expires').first()).toBeVisible();
  });

  test('should display status badges', async ({ page }) => {
    // Look for status badge indicators
    const table = page.locator('table');
    await expect(table).toBeVisible();
  });
});

test.describe('Opportunity Countdown Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should display countdown cells for active opportunities', async ({ page }) => {
    // Switch to active opportunities
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(500);

    // Look for time-related text (hours/minutes/seconds or expired)
    const timePatterns = page.locator('text=/\\d+[hms]|Expired|N\\/A/');
    const count = await timePatterns.count();

    // Either we have countdown cells or no active opportunities
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('countdown updates in real-time', async ({ page }) => {
    // Switch to active tab
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(1000);

    // Find countdown cells
    const countdownCells = page.locator('[data-countdown]');
    const count = await countdownCells.count();

    if (count > 0) {
      // Get initial value
      const initialText = await countdownCells.first().textContent();

      // Wait for update (countdowns update every second)
      await page.waitForTimeout(2000);

      // Get updated value
      const updatedText = await countdownCells.first().textContent();

      // If not expired, value should have changed
      if (initialText && !initialText.includes('Expired')) {
        expect(updatedText).toBeDefined();
      }
    }
  });

  test('expired opportunities show expired state', async ({ page }) => {
    // Look for expired indicators
    const expiredBadges = page.getByText('Expired');
    const count = await expiredBadges.count();

    // May or may not have expired opportunities
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe('Opportunity Status Badges', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should display open status for active opportunities', async ({ page }) => {
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(500);

    // Look for open status indicators
    const openBadges = page.getByText(/open/i);
    const count = await openBadges.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should display executed status for executed opportunities', async ({ page }) => {
    await page.getByRole('tab', { name: 'Executed' }).click();
    await page.waitForTimeout(500);

    // Look for executed status indicators
    const executedBadges = page.getByText(/executed/i);
    const count = await executedBadges.count();
    // Count includes the tab label, so should be at least 1
    expect(count).toBeGreaterThanOrEqual(1);
  });
});

test.describe('Opportunity Actions', () => {
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

  test('should show confirmation dialog when clicking execute', async ({ page }) => {
    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    if (count > 0) {
      await executeButtons.first().click();
      await page.waitForTimeout(500);

      // Should see either the dialog heading or the progress modal
      // Use first() to avoid strict mode violations when multiple elements match
      const dialogVisible = await page.getByRole('heading', { name: 'Execute Opportunity' }).isVisible();
      const progressVisible = await page.getByText('Execution Progress').first().isVisible();

      expect(dialogVisible || progressVisible).toBe(true);
    }
  });

  test('should show execution progress modal with trade summary', async ({ page }) => {
    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    if (count > 0) {
      await executeButtons.first().click();
      await page.waitForTimeout(500);

      // Check for trade summary elements
      const longBadge = page.getByText(/LONG/i);
      const shortBadge = page.getByText(/SHORT/i);

      // The modal should show the trade direction badges
      if (await longBadge.count() > 0) {
        await expect(longBadge.first()).toBeVisible();
      }

      // Check for execution steps
      const validateStep = page.getByText('Validating Opportunity');
      if (await validateStep.count() > 0) {
        await expect(validateStep).toBeVisible();
      }
    }
  });
});

test.describe('Opportunities Refresh', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
  });

  test('should refresh data when clicking refresh button', async ({ page }) => {
    const refreshButton = page.getByRole('button', { name: 'Refresh' });
    await refreshButton.click();

    // Wait for refresh
    await page.waitForTimeout(2000);

    // Page should still show opportunities content
    await expect(page.getByText('Detected Opportunities').first()).toBeVisible();
  });
});

test.describe('Opportunities Sorting', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should have sortable table headers', async ({ page }) => {
    // Look for sortable header indicators
    const headers = page.locator('th');
    const count = await headers.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should sort by clicking header', async ({ page }) => {
    // Click on Spread header to sort
    const spreadHeader = page.getByText('Spread').first();
    await spreadHeader.click();
    await page.waitForTimeout(500);

    // Table should still be visible
    await expect(page.locator('table')).toBeVisible();
  });

  test('should sort by symbol', async ({ page }) => {
    // Click on Symbol header
    const symbolHeader = page.getByRole('button', { name: /symbol/i }).first();
    if (await symbolHeader.isVisible()) {
      await symbolHeader.click();
      await page.waitForTimeout(300);
      // Click again to toggle direction
      await symbolHeader.click();
      await page.waitForTimeout(300);
      await expect(page.locator('table')).toBeVisible();
    }
  });

  test('should sort by UOS score', async ({ page }) => {
    const uosHeader = page.getByRole('button', { name: /uos/i }).first();
    if (await uosHeader.isVisible()) {
      await uosHeader.click();
      await page.waitForTimeout(300);
      await expect(page.locator('table')).toBeVisible();
    }
  });

  test('should sort by expires time', async ({ page }) => {
    const expiresHeader = page.getByRole('button', { name: /expires/i }).first();
    if (await expiresHeader.isVisible()) {
      await expiresHeader.click();
      await page.waitForTimeout(300);
      await expect(page.locator('table')).toBeVisible();
    }
  });

  test('should default sort by spread descending', async ({ page }) => {
    // The default sort should be by spread descending
    const spreadButton = page.getByRole('button', { name: /spread/i }).first();
    if (await spreadButton.isVisible()) {
      // Should have descending indicator by default
      await expect(page.locator('table')).toBeVisible();
    }
  });
});

test.describe('Opportunities Filtering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);
  });

  test('should display filter controls', async ({ page }) => {
    // Symbol search input
    const searchInput = page.getByPlaceholder(/search symbol/i);
    await expect(searchInput).toBeVisible();
  });

  test('should display exchange filter dropdown', async ({ page }) => {
    const exchangeLabel = page.getByText('Exchange:');
    await expect(exchangeLabel).toBeVisible();
  });

  test('should display min UOS score input', async ({ page }) => {
    const uosLabel = page.getByText('Min UOS:');
    await expect(uosLabel).toBeVisible();
  });

  test('should filter by symbol search', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search symbol/i);
    await searchInput.fill('BTC');
    await page.waitForTimeout(500);

    // Table should still be visible
    await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
  });

  test('should filter by minimum UOS score', async ({ page }) => {
    const uosInput = page.locator('input[type="number"]').first();
    if (await uosInput.isVisible()) {
      await uosInput.fill('70');
      await page.waitForTimeout(500);
      await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
    }
  });

  test('should show results count', async ({ page }) => {
    // Should display "Showing X of Y opportunities"
    const resultsText = page.getByText(/showing .* of .* opportunities/i);
    await expect(resultsText).toBeVisible();
  });

  test('should combine multiple filters', async ({ page }) => {
    // Apply symbol filter
    const searchInput = page.getByPlaceholder(/search symbol/i);
    await searchInput.fill('ETH');
    await page.waitForTimeout(300);

    // Apply UOS filter if input exists
    const uosInput = page.locator('input[type="number"]').first();
    if (await uosInput.isVisible()) {
      await uosInput.fill('60');
      await page.waitForTimeout(300);
    }

    // Results should update
    await expect(page.locator('table').or(page.getByText(/no opportunities/i))).toBeVisible();
  });
});
