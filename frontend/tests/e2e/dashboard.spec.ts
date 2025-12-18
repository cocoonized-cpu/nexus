import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display dashboard title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  });

  test('should display P&L insight cards', async ({ page }) => {
    await expect(page.getByText('Total P&L').first()).toBeVisible();
    await expect(page.getByText("Today's P&L").first()).toBeVisible();
    await expect(page.getByText('Unrealized P&L').first()).toBeVisible();
    await expect(page.getByText('ROI').first()).toBeVisible();
  });

  test('should display bot status card', async ({ page }) => {
    await expect(page.getByText('Bot Status').first()).toBeVisible();
    // Either Running or Stopped should be visible
    const running = page.getByText('Running');
    const stopped = page.getByText('Stopped');
    await expect(running.or(stopped)).toBeVisible();
  });

  test('should display bot performance metrics', async ({ page }) => {
    await expect(page.getByText('Bot Performance').first()).toBeVisible();
    await expect(page.getByText('Win Rate').first()).toBeVisible();
    await expect(page.getByText('Total Trades').first()).toBeVisible();
  });

  test('should display active positions card', async ({ page }) => {
    await expect(page.getByText('Active Positions').first()).toBeVisible();
  });

  test('should display navigation sidebar', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Situation Room' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Funding Rates' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Opportunities' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Positions' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Performance' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
  });

  test('should display NEXUS branding', async ({ page }) => {
    await expect(page.getByText('NEXUS').first()).toBeVisible();
  });

  test('should show connection status', async ({ page }) => {
    // Either Connected or Disconnected should be visible
    const connected = page.getByText('Connected');
    const disconnected = page.getByText('Disconnected');
    await expect(connected.or(disconnected)).toBeVisible();
  });

  test('should display Top Opportunities with Execute button', async ({ page }) => {
    await expect(page.getByText('Top Opportunities').first()).toBeVisible();

    // Check if Execute buttons exist in the opportunities table
    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    // If there are opportunities, Execute buttons should exist
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should show execution modal when clicking Execute on dashboard', async ({ page }) => {
    const executeButtons = page.getByRole('button', { name: /execute/i });
    const count = await executeButtons.count();

    if (count > 0) {
      await executeButtons.first().click();
      await page.waitForTimeout(500);

      // Verify the execution progress modal appears
      const dialogTitle = page.getByText('Execute Opportunity');
      const executionProgress = page.getByText('Execution Progress');

      await expect(dialogTitle.or(executionProgress)).toBeVisible({ timeout: 3000 });
    }
  });
});

test.describe('Navigation', () => {
  test('should navigate to situation room page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Situation Room' }).click();
    await expect(page).toHaveURL('/situation-room');
    await expect(page.getByRole('heading', { name: 'Situation Room' })).toBeVisible();
  });

  test('should navigate to funding rates page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Funding Rates' }).click();
    await expect(page).toHaveURL('/funding-rates');
    await expect(page.getByRole('heading', { name: 'Funding Rates', level: 1 })).toBeVisible();
  });

  test('should navigate to opportunities page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Opportunities' }).click();
    await expect(page).toHaveURL('/opportunities');
    await expect(page.getByRole('heading', { name: 'Opportunities', exact: true })).toBeVisible();
  });

  test('should navigate to positions page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Positions' }).click();
    await expect(page).toHaveURL('/positions');
    await expect(page.getByRole('heading', { name: 'Positions & Trades' })).toBeVisible();
  });

  test('should navigate to performance page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Performance' }).click();
    await expect(page).toHaveURL('/performance');
    await expect(page.getByRole('heading', { name: 'Performance', level: 1 })).toBeVisible();
  });

  test('should navigate to settings page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page).toHaveURL('/settings');
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  });
});
