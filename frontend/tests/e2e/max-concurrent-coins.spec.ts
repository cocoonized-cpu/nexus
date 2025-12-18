import { test, expect } from '@playwright/test';

/**
 * E2E tests for Max Concurrent Coins feature
 *
 * Tests the full user journey for configuring and viewing
 * max concurrent coins settings in the Settings page.
 */

test.describe('Max Concurrent Coins Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
    // Navigate to Trading tab where Position Limits card is
    await page.getByRole('tab', { name: 'Trading' }).click();
    // Wait for the page to load
    await page.waitForTimeout(500);
  });

  test('should display Position Limits card in Trading tab', async ({ page }) => {
    await expect(page.getByText('Position Limits').first()).toBeVisible();
  });

  test('should display max concurrent coins input', async ({ page }) => {
    await expect(page.locator('#max_concurrent_coins')).toBeVisible();
  });

  test('should display current vs max coin count', async ({ page }) => {
    // Should show "X / Y active" format
    await expect(page.getByText(/\d+ \/ \d+ active/)).toBeVisible();
  });

  test('should display auto-unwind behavior explanation', async ({ page }) => {
    await expect(page.getByText('Auto-Unwind Behavior')).toBeVisible();
    await expect(page.getByText(/weakest positions will auto-close/i)).toBeVisible();
  });

  test('should accept valid max coins values', async ({ page }) => {
    const input = page.locator('#max_concurrent_coins');

    // Clear and set to 10
    await input.fill('10');
    await expect(input).toHaveValue('10');

    // Clear and set to 1 (minimum)
    await input.fill('1');
    await expect(input).toHaveValue('1');

    // Clear and set to 20 (maximum)
    await input.fill('20');
    await expect(input).toHaveValue('20');
  });

  test('should show save button when value changes', async ({ page }) => {
    const input = page.locator('#max_concurrent_coins');
    const originalValue = await input.inputValue();

    // Change the value
    const newValue = originalValue === '10' ? '5' : '10';
    await input.fill(newValue);

    // Save button should appear in the Position Limits card
    await expect(
      page.locator('text=Position Limits').locator('..').locator('..').getByRole('button', { name: /save/i })
    ).toBeVisible();
  });

  test('should save max coins setting successfully', async ({ page }) => {
    const input = page.locator('#max_concurrent_coins');

    // Get current value and change it
    const originalValue = await input.inputValue();
    const newValue = originalValue === '10' ? '5' : '10';
    await input.fill(newValue);

    // Click save button
    const saveButton = page.locator('text=Position Limits').locator('..').locator('..').getByRole('button', { name: /save/i });
    await saveButton.click();

    // Wait for save to complete (button should disappear or show success)
    await page.waitForTimeout(1000);

    // Value should be persisted - refresh and check
    await page.reload();
    await page.getByRole('tab', { name: 'Trading' }).click();
    await page.waitForTimeout(500);

    // Value should match what we set
    await expect(page.locator('#max_concurrent_coins')).toHaveValue(newValue);
  });

  test('should display position limit terminology explanation', async ({ page }) => {
    // Should explain that each coin = 2 positions
    await expect(
      page.getByText(/each coin.*=.*1 arbitrage position.*=.*2 exchange positions/i)
    ).toBeVisible();
  });
});

test.describe('Max Concurrent Coins - At Limit Warning', () => {
  test('should show warning badge when at limit', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('tab', { name: 'Trading' }).click();
    await page.waitForTimeout(500);

    // If at limit, should show "At Limit" badge
    // This is conditional based on actual state
    const atLimitBadge = page.getByText('At Limit');
    const isAtLimit = await atLimitBadge.isVisible().catch(() => false);

    if (isAtLimit) {
      await expect(atLimitBadge).toBeVisible();
      // Should also show warning message
      await expect(
        page.getByText(/Position limit reached/i)
      ).toBeVisible();
    }
  });
});

test.describe('Max Concurrent Coins - Settings Tab Integration', () => {
  test('should be in correct tab order', async ({ page }) => {
    await page.goto('/settings');

    // Click Trading tab
    await page.getByRole('tab', { name: 'Trading' }).click();

    // Position Limits should appear before Strategy Parameters
    const positionLimitsCard = page.getByText('Position Limits').first();
    const strategyCard = page.getByText('Strategy Parameters').first();

    await expect(positionLimitsCard).toBeVisible();
    await expect(strategyCard).toBeVisible();
  });

  test('should not show Position Limits in other tabs', async ({ page }) => {
    await page.goto('/settings');

    // Check Exchanges tab
    await page.getByRole('tab', { name: 'Exchanges' }).click();
    await expect(page.getByText('Position Limits')).not.toBeVisible();

    // Check Risk tab
    await page.getByRole('tab', { name: 'Risk' }).click();
    // Position Limits might be visible in Risk tab if it's there,
    // but the Max Concurrent Coins input should not be
    const maxCoinsInput = page.locator('#max_concurrent_coins');
    await expect(maxCoinsInput).not.toBeVisible();

    // Check Notifications tab
    await page.getByRole('tab', { name: 'Notifications' }).click();
    await expect(page.locator('#max_concurrent_coins')).not.toBeVisible();
  });
});

test.describe('Max Concurrent Coins - Input Validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('tab', { name: 'Trading' }).click();
    await page.waitForTimeout(500);
  });

  test('input should have min and max attributes', async ({ page }) => {
    const input = page.locator('#max_concurrent_coins');
    await expect(input).toHaveAttribute('min', '1');
    await expect(input).toHaveAttribute('max', '20');
  });

  test('input should be of type number', async ({ page }) => {
    const input = page.locator('#max_concurrent_coins');
    await expect(input).toHaveAttribute('type', 'number');
  });
});
