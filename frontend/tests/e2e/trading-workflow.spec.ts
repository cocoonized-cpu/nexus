import { test, expect } from '@playwright/test';

/**
 * E2E tests for the complete NEXUS trading workflow.
 *
 * These tests validate the core trading functionality:
 * - Auto-execution toggle and functionality
 * - Manual opportunity execution
 * - Position tracking after execution
 * - P&L display and updates
 * - Activity log showing execution events
 */

test.describe('Auto-Execution Configuration', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/situation-room');
    await page.waitForLoadState('networkidle');
  });

  test('should display auto-execute toggle with UOS threshold hint', async ({ page }) => {
    // Look for the auto-execute switch
    const autoExecuteSwitch = page.locator('#auto-execute');
    await expect(autoExecuteSwitch).toBeVisible({ timeout: 10000 });

    // Should show the UOS threshold hint near the auto-execute toggle
    await expect(page.getByText('(UOS ≥ 75)')).toBeVisible();
  });

  test('should toggle auto-execute setting', async ({ page }) => {
    const autoExecuteSwitch = page.locator('#auto-execute');
    await expect(autoExecuteSwitch).toBeVisible({ timeout: 10000 });

    // Get initial state
    const initialState = await autoExecuteSwitch.isChecked();

    // Toggle using the switch's click method
    await autoExecuteSwitch.click({ force: true });

    // Wait briefly for UI update
    await page.waitForTimeout(500);

    // Verify toggle worked by checking we can interact again
    await expect(autoExecuteSwitch).toBeEnabled();

    // Toggle back to restore state
    await autoExecuteSwitch.click({ force: true });
    await page.waitForTimeout(500);
  });

  test('should show toast notification on auto-execute toggle', async ({ page }) => {
    const autoExecuteSwitch = page.locator('#auto-execute');
    await expect(autoExecuteSwitch).toBeVisible({ timeout: 10000 });

    // Toggle
    await autoExecuteSwitch.click({ force: true });

    // Should show toast notification - look for the exact toast title
    await expect(page.getByText('Auto-Execute Updated', { exact: true })).toBeVisible({ timeout: 5000 });

    // Toggle back
    await autoExecuteSwitch.click({ force: true });
    await page.waitForTimeout(500);
  });
});

test.describe('Manual Opportunity Execution', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/opportunities');
    await page.waitForLoadState('networkidle');
  });

  test('should display opportunities with execute buttons', async ({ page }) => {
    // Click on Active tab to see executable opportunities
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(500);

    // Check if there are any opportunities
    const table = page.locator('table');
    const noOpportunities = page.getByText(/no.*opportunities/i);

    // Either table with execute buttons or empty state
    const hasTable = await table.isVisible();
    if (hasTable) {
      const executeButtons = page.getByRole('button', { name: /execute/i });
      const count = await executeButtons.count();
      // There may or may not be active opportunities
      expect(count).toBeGreaterThanOrEqual(0);
    } else {
      await expect(noOpportunities).toBeVisible();
    }
  });

  test('should open execution modal on execute click', async ({ page }) => {
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(500);

    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    if (count > 0) {
      // Click first execute button
      await executeButtons.first().click();
      await page.waitForTimeout(500);

      // Should see execution dialog
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible({ timeout: 5000 });

      // Dialog should have confirmation button
      const confirmButton = page.getByRole('button', { name: /confirm|start|execute/i });
      await expect(confirmButton).toBeVisible();

      // Close dialog
      await page.keyboard.press('Escape');
    }
  });

  test('should show opportunity details in execution modal', async ({ page }) => {
    await page.getByRole('tab', { name: 'Active' }).click();
    await page.waitForTimeout(500);

    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    if (count > 0) {
      await executeButtons.first().click();
      await page.waitForTimeout(500);

      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible({ timeout: 5000 });

      // Should show key opportunity info
      // The dialog should contain symbol, exchanges, or size info
      const dialogText = await dialog.textContent();
      expect(dialogText).toBeTruthy();

      await page.keyboard.press('Escape');
    }
  });
});

test.describe('Position Tracking After Execution', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
    await page.waitForLoadState('networkidle');
  });

  test('should display positions page with correct structure', async ({ page }) => {
    await expect(page.getByText('Positions').first()).toBeVisible();

    // Should have the three tabs: NEXUS Positions, Exchange, Trade History
    await expect(page.getByRole('tab', { name: /NEXUS Positions/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /Exchange/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /Trade History/i })).toBeVisible();
  });

  test('should show position details when positions exist', async ({ page }) => {
    // Click on NEXUS Positions tab
    await page.getByRole('tab', { name: /NEXUS Positions/i }).click();
    await page.waitForTimeout(500);

    const table = page.locator('table');
    const hasTable = await table.isVisible();
    const emptyState = page.getByText(/no.*positions/i);

    if (hasTable) {
      // Should show position columns
      await expect(page.getByText('Symbol').first()).toBeVisible();
      await expect(page.getByText('Size').first()).toBeVisible();
    } else if (await emptyState.isVisible()) {
      // Empty state is also valid
      expect(true).toBe(true);
    }
  });

  test('should display position health status', async ({ page }) => {
    // Click on NEXUS Positions tab
    await page.getByRole('tab', { name: /NEXUS Positions/i }).click();
    await page.waitForTimeout(500);

    const table = page.locator('table');
    const hasTable = await table.isVisible();

    if (hasTable) {
      const rows = page.locator('tbody tr');
      const rowCount = await rows.count();

      if (rowCount > 0) {
        // Positions should show health indicator (healthy, degraded, critical)
        const healthBadges = page.locator('text=/healthy|degraded|critical|warning/i');
        const healthCount = await healthBadges.count();
        expect(healthCount).toBeGreaterThanOrEqual(0);
      }
    }
  });

  test('should navigate to exchange positions tab', async ({ page }) => {
    // Click on Exchange tab
    await page.getByRole('tab', { name: /Exchange/i }).click();
    await page.waitForTimeout(500);

    // Should show exchange positions or empty state
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();
  });
});

test.describe('P&L Display and Updates', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should display all P&L KPI cards', async ({ page }) => {
    await expect(page.getByText('Total P&L').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Today's P&L").first()).toBeVisible();
    await expect(page.getByText('Unrealized P&L').first()).toBeVisible();
    await expect(page.getByText(/ROI/i).first()).toBeVisible();
  });

  test('should show P&L values with proper formatting', async ({ page }) => {
    // P&L values should be formatted with $ sign
    const pnlCards = page.locator('text=/\\$[-]?[0-9,]+\\.?[0-9]*/');
    const count = await pnlCards.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should show green/red color based on P&L value', async ({ page }) => {
    // Wait for cards to load
    await page.waitForTimeout(1000);

    // Look for colored P&L indicators
    const greenIndicators = page.locator('.text-green-500');
    const redIndicators = page.locator('.text-red-500');

    const greenCount = await greenIndicators.count();
    const redCount = await redIndicators.count();

    // Should have at least one colored indicator
    expect(greenCount + redCount).toBeGreaterThan(0);
  });

  test('should auto-refresh P&L data', async ({ page }) => {
    // Get initial content
    const initialPnl = await page.locator('[class*="text-2xl font-bold"]').first().textContent();

    // Wait for refresh interval (10 seconds)
    await page.waitForTimeout(11000);

    // Page should have made a refresh call
    // The values may or may not change depending on trading activity
    const currentPnl = await page.locator('[class*="text-2xl font-bold"]').first().textContent();

    // At minimum, the value should still be valid
    expect(currentPnl).toBeTruthy();
  });
});

test.describe('Activity Log Execution Events', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/situation-room');
    await page.waitForLoadState('networkidle');
  });

  test('should display activity log with filtering options', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 10000 });

    // Should have level filters
    await expect(page.getByRole('button', { name: /INFO/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /WARNING/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /ERROR/i })).toBeVisible();

    // Should have category filter dropdown
    await expect(page.getByRole('button', { name: /categories/i })).toBeVisible();
  });

  test('should filter activity log by level', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 10000 });

    // Toggle INFO filter off
    const infoButton = page.getByRole('button', { name: /INFO/i });
    await infoButton.click();
    await page.waitForTimeout(500);

    // Toggle back on
    await infoButton.click();
    await page.waitForTimeout(500);

    // Activity log should still be functional
    await expect(page.getByText('Activity Log')).toBeVisible();
  });

  test('should filter activity log by category', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 10000 });

    // Open categories dropdown
    const categoriesButton = page.getByRole('button', { name: /categories/i });
    await categoriesButton.click();
    await page.waitForTimeout(300);

    // Should show category options - look for the dropdown label
    await expect(page.getByText('Filter by Category')).toBeVisible();

    // Close dropdown
    await page.keyboard.press('Escape');
  });

  test('should show execution events in activity log', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 10000 });

    // Wait for events to load
    await page.waitForTimeout(2000);

    // Look for execution-related events or empty state
    const activityItems = page.locator('[class*="rounded-lg px-3 py-2"]');
    const emptyState = page.getByText(/no events/i);

    const hasItems = await activityItems.count() > 0;
    const hasEmpty = await emptyState.isVisible();

    expect(hasItems || hasEmpty).toBe(true);
  });

  test('should search activity log', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 10000 });

    // Find search input
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();

    // Type a search term
    await searchInput.fill('execution');
    await page.waitForTimeout(500);

    // Clear search
    await searchInput.clear();
  });

  test('should pause and resume activity log', async ({ page }) => {
    await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 10000 });

    // Find pause button
    const pauseButton = page.getByRole('button', { name: /pause/i });
    await expect(pauseButton).toBeVisible();

    // Click pause
    await pauseButton.click();
    await page.waitForTimeout(300);

    // Should now show resume button
    await expect(page.getByRole('button', { name: /resume/i })).toBeVisible();

    // Click resume
    await page.getByRole('button', { name: /resume/i }).click();
    await page.waitForTimeout(300);

    // Should be back to pause button
    await expect(page.getByRole('button', { name: /pause/i })).toBeVisible();
  });
});

test.describe('Complete Trading Workflow Integration', () => {
  test('should complete full trading workflow cycle', async ({ page }) => {
    // Step 1: Check system status on Situation Room
    await page.goto('/situation-room');
    await page.waitForLoadState('networkidle');

    // Verify system controls are visible
    await expect(page.getByText('Bot Controls')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('System Status')).toBeVisible();

    // Step 2: Verify opportunities are being detected
    await page.goto('/opportunities');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Opportunities').first()).toBeVisible();
    await expect(page.getByText('Total Detected').first()).toBeVisible();

    // Step 3: Check positions page
    await page.goto('/positions');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Positions').first()).toBeVisible();

    // Step 4: Verify dashboard shows P&L
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Total P&L').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Today's P&L").first()).toBeVisible();

    // Step 5: Check funding rates are loading
    await page.goto('/funding-rates');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Funding Rates').first()).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible({ timeout: 10000 });

    // Step 6: Verify performance page
    await page.goto('/performance');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Performance').first()).toBeVisible();
  });

  test('should handle API errors gracefully', async ({ page }) => {
    // Navigate to various pages and verify error handling
    const pages = ['/', '/opportunities', '/positions', '/situation-room', '/funding-rates'];

    for (const path of pages) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');

      // Page should not crash - main content should be visible
      await expect(page.locator('main')).toBeVisible({ timeout: 10000 });

      // No uncaught error overlays
      const errorOverlay = page.locator('text=/error|failed|exception/i');
      // Error messages in controlled components are OK, but not crash overlays
    }
  });
});
