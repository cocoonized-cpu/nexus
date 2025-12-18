import { test, expect } from '@playwright/test';

test.describe('Performance Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
  });

  test('should display performance title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Performance', level: 1 })).toBeVisible();
  });

  test('should display summary cards', async ({ page }) => {
    await expect(page.getByText('Total Value').first()).toBeVisible();
    await expect(page.getByText('Net P&L').first()).toBeVisible();
    await expect(page.getByText('Return').first()).toBeVisible();
  });

  test('should display performance chart', async ({ page }) => {
    // Performance chart card has title "Performance" (in h3)
    const performanceCard = page.locator('h3', { hasText: 'Performance' }).first();
    await expect(performanceCard).toBeVisible();
  });

  test('should display tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Balances' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Trading' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Funding' })).toBeVisible();
  });
});

test.describe('Performance Chart Time Range', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
  });

  test('should display time range selector', async ({ page }) => {
    // Time range uses TabsTrigger components (role=tab)
    await expect(page.getByRole('tab', { name: '7D' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '30D' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '90D' })).toBeVisible();
  });

  test('should switch time range', async ({ page }) => {
    // Click 30D
    await page.getByRole('tab', { name: '30D' }).click();
    await page.waitForTimeout(300);

    // Click 90D
    await page.getByRole('tab', { name: '90D' }).click();
    await page.waitForTimeout(300);

    // Return to 7D
    await page.getByRole('tab', { name: '7D' }).click();
    await page.waitForTimeout(300);
  });
});

test.describe('Performance Tab Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
  });

  test('should switch to Balances tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Balances' }).click();
    await expect(page.getByText('Exchange Balances').first()).toBeVisible();
  });

  test('should display exchange balance table in Balances tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Balances' }).click();
    await expect(page.getByText('Exchange').first()).toBeVisible();
    await expect(page.getByText('Balance').first()).toBeVisible();
  });

  test('should switch to Trading tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Trading' }).click();
    // Trading tab shows "Trading History" card title
    await expect(page.getByText('Trading History').first()).toBeVisible();
  });

  test('should display trading metrics in Trading tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Trading' }).click();
    // Trading tab shows Win Rate and other metric cards
    await expect(page.getByText('Win Rate').first()).toBeVisible();
    await expect(page.getByText('Total Realized P&L').first()).toBeVisible();
  });

  test('should switch to Funding tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Funding' }).click();
    await expect(page.getByText('Funding Breakdown').first()).toBeVisible();
  });

  test('should return to Overview tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'Funding' }).click();
    await page.waitForTimeout(300);
    await page.getByRole('tab', { name: 'Overview' }).click();
    // Overview shows P&L Breakdown and Key Metrics
    await expect(page.getByText('P&L Breakdown').first()).toBeVisible();
  });
});

test.describe('Funding Breakdown View Toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
    await page.getByRole('tab', { name: 'Funding' }).click();
  });

  test('should display view toggle options', async ({ page }) => {
    // Funding breakdown uses TabsTrigger components (role=tab)
    await expect(page.getByRole('tab', { name: /per position/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /daily/i })).toBeVisible();
  });

  test('should switch between per-position and daily views', async ({ page }) => {
    // Click daily view
    await page.getByRole('tab', { name: /daily/i }).click();
    await page.waitForTimeout(300);

    // Click per-position view
    await page.getByRole('tab', { name: /per position/i }).click();
    await page.waitForTimeout(300);
  });

  test('should display funding data table or empty state', async ({ page }) => {
    // May show a table or "No positions with funding data" message
    const table = page.locator('table');
    const emptyMessage = page.getByText(/no (positions|daily funding)/i);
    await expect(table.or(emptyMessage)).toBeVisible();
  });
});

test.describe('Overview Tab Content', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
  });

  test('should display key metrics section', async ({ page }) => {
    // Overview tab shows "Key Metrics" card
    await expect(page.getByText('Key Metrics').first()).toBeVisible();
  });

  test('should display key metrics values', async ({ page }) => {
    // Key Metrics shows Total Trades and other metrics
    await expect(page.getByText('Total Trades').first()).toBeVisible();
    await expect(page.getByText('Sharpe Ratio').first()).toBeVisible();
  });

  test('should display P&L breakdown', async ({ page }) => {
    await expect(page.getByText('P&L Breakdown').first()).toBeVisible();
  });
});

test.describe('Balances Tab Content', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
    await page.getByRole('tab', { name: 'Balances' }).click();
  });

  test('should display exchange balances section', async ({ page }) => {
    await expect(page.getByText('Exchange Balances').first()).toBeVisible();
  });

  test('should display balance summary cards', async ({ page }) => {
    await expect(page.getByText('Total Value').first()).toBeVisible();
    await expect(page.getByText('Deployed').first()).toBeVisible();
    await expect(page.getByText('Available').first()).toBeVisible();
  });
});
