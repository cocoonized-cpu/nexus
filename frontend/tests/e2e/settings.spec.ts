import { test, expect } from '@playwright/test';

test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('should display settings title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  });

  test('should display settings tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: 'Exchanges' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Trading' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Risk' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Notifications' })).toBeVisible();
  });

  test('should display exchange connections card', async ({ page }) => {
    await expect(page.getByText('Exchange Connections').first()).toBeVisible();
  });

  test('should display trading behavior when trading tab clicked', async ({ page }) => {
    await page.getByRole('tab', { name: 'Trading' }).click();
    await expect(page.getByText('Trading Behavior').first()).toBeVisible();
  });

  test('should display trading toggles when trading tab clicked', async ({ page }) => {
    await page.getByRole('tab', { name: 'Trading' }).click();
    await expect(page.getByText('Auto-Execute Opportunities').first()).toBeVisible();
    await expect(page.getByText('Use ArbitrageScanner').first()).toBeVisible();
    await expect(page.getByText('Alerts Enabled').first()).toBeVisible();
  });

  test('should display strategy parameters when trading tab clicked', async ({ page }) => {
    await page.getByRole('tab', { name: 'Trading' }).click();
    await expect(page.getByText('Strategy Parameters').first()).toBeVisible();
  });

  test('should display exchange configurations', async ({ page }) => {
    await expect(page.getByText('Binance').first()).toBeVisible();
    await expect(page.getByText('Bybit').first()).toBeVisible();
  });

  test('should have configure buttons for exchanges', async ({ page }) => {
    // Wait for exchanges to load
    await page.waitForTimeout(1000);

    // Either Configure or Update button should be visible
    const configureButtons = page.getByRole('button', { name: 'Configure' });
    const updateButtons = page.getByRole('button', { name: 'Update' });
    const configCount = await configureButtons.count();
    const updateCount = await updateButtons.count();
    expect(configCount + updateCount).toBeGreaterThan(0);
  });
});
