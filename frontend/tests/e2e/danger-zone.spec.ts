import { test, expect } from '@playwright/test';

test.describe('Danger Zone', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
    // Click on System tab to see Danger Zone
    await page.getByRole('tab', { name: /system/i }).click();
    await page.waitForTimeout(500);
  });

  test('should display Danger Zone section', async ({ page }) => {
    await expect(page.getByText('Danger Zone')).toBeVisible();
    await expect(page.getByText('Irreversible actions - use with caution')).toBeVisible();
  });

  test('should display Reset Positions button', async ({ page }) => {
    const resetButton = page.getByRole('button', { name: /reset positions/i });
    await expect(resetButton).toBeVisible();
    await expect(resetButton).toBeEnabled();
  });

  test('should display Clear Blacklist button', async ({ page }) => {
    const clearButton = page.getByRole('button', { name: /clear blacklist/i });
    await expect(clearButton).toBeVisible();
    await expect(clearButton).toBeEnabled();
  });

  test('should display Factory Reset button', async ({ page }) => {
    const factoryButton = page.getByRole('button', { name: /factory reset/i });
    await expect(factoryButton).toBeVisible();
    await expect(factoryButton).toBeEnabled();
  });

  test('should show confirmation dialog when clicking Reset Positions', async ({ page }) => {
    await page.getByRole('button', { name: /reset positions/i }).click();
    await page.waitForTimeout(300);

    // Confirmation dialog should appear
    await expect(page.getByRole('heading', { name: 'Reset All Positions' })).toBeVisible();
    await expect(page.getByText(/does NOT close positions on exchanges/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /cancel/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /yes, reset all positions/i })).toBeVisible();
  });

  test('should close Reset Positions dialog on cancel', async ({ page }) => {
    await page.getByRole('button', { name: /reset positions/i }).click();
    await page.waitForTimeout(300);

    await page.getByRole('button', { name: /cancel/i }).click();
    await page.waitForTimeout(300);

    // Dialog should close
    await expect(page.getByRole('heading', { name: 'Reset All Positions' })).not.toBeVisible();
  });

  test('should show confirmation dialog when clicking Clear Blacklist', async ({ page }) => {
    await page.getByRole('button', { name: /clear blacklist/i }).click();
    await page.waitForTimeout(300);

    // Confirmation dialog should appear
    await expect(page.getByRole('heading', { name: 'Clear Symbol Blacklist' })).toBeVisible();
    await expect(page.getByText(/able to open positions on all symbols/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /cancel/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /yes, clear blacklist/i })).toBeVisible();
  });

  test('should close Clear Blacklist dialog on cancel', async ({ page }) => {
    await page.getByRole('button', { name: /clear blacklist/i }).click();
    await page.waitForTimeout(300);

    await page.getByRole('button', { name: /cancel/i }).click();
    await page.waitForTimeout(300);

    // Dialog should close
    await expect(page.getByRole('heading', { name: 'Clear Symbol Blacklist' })).not.toBeVisible();
  });

  test('should show confirmation dialog when clicking Factory Reset', async ({ page }) => {
    await page.getByRole('button', { name: /factory reset/i }).click();
    await page.waitForTimeout(300);

    // Confirmation dialog should appear
    await expect(page.getByRole('heading', { name: 'Factory Reset' })).toBeVisible();
    await expect(page.getByText(/credentials will be preserved/i)).toBeVisible();
    await expect(page.getByText(/strategy parameters/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /cancel/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /yes, factory reset/i })).toBeVisible();
  });

  test('should close Factory Reset dialog on cancel', async ({ page }) => {
    await page.getByRole('button', { name: /factory reset/i }).click();
    await page.waitForTimeout(300);

    await page.getByRole('button', { name: /cancel/i }).click();
    await page.waitForTimeout(300);

    // Dialog should close
    await expect(page.getByRole('heading', { name: 'Factory Reset' })).not.toBeVisible();
  });

  test('should execute Clear Blacklist successfully', async ({ page }) => {
    await page.getByRole('button', { name: /clear blacklist/i }).click();
    await page.waitForTimeout(300);

    // Click confirm button
    await page.getByRole('button', { name: /yes, clear blacklist/i }).click();

    // Wait for dialog to close (with longer timeout for API call)
    await expect(page.getByRole('heading', { name: 'Clear Symbol Blacklist' })).not.toBeVisible({ timeout: 10000 });

    // Check for success toast - use first() as there may be multiple matches
    await expect(page.getByText('Blacklist Cleared', { exact: true }).first()).toBeVisible({ timeout: 5000 });
  });

  test('should execute Factory Reset successfully', async ({ page }) => {
    await page.getByRole('button', { name: /factory reset/i }).click();
    await page.waitForTimeout(300);

    // Click confirm button
    await page.getByRole('button', { name: /yes, factory reset/i }).click();

    // Wait for dialog to close (with longer timeout for API call)
    await expect(page.getByRole('heading', { name: 'Factory Reset' })).not.toBeVisible({ timeout: 10000 });

    // Check for success toast - use first() as there may be multiple matches
    await expect(page.getByText('Factory Reset Complete', { exact: true }).first()).toBeVisible({ timeout: 5000 });
  });
});
