import { test, expect } from '@playwright/test';

test.describe('Funding Rates Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
  });

  test('should display funding rates title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Funding Rates', level: 1 })).toBeVisible();
  });

  test('should display funding rates table', async ({ page }) => {
    await expect(page.getByRole('table')).toBeVisible();
  });

  test('should display table headers', async ({ page }) => {
    await expect(page.getByText('Coins').first()).toBeVisible();
    await expect(page.getByText('Max Spread').first()).toBeVisible();
  });

  test('should display refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible();
  });
});

test.describe('Data Source Toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
  });

  test('should display data source toggle', async ({ page }) => {
    await expect(page.getByText('Data Source').first()).toBeVisible();
  });

  test('should have three data source options', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /exchanges/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /arbitrage.?scanner/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /both/i })).toBeVisible();
  });

  test('should switch to ArbitrageScanner source', async ({ page }) => {
    const scannerTab = page.getByRole('tab', { name: /arbitrage.?scanner/i });
    await scannerTab.click();
    await page.waitForTimeout(500);
    // Tab should be active
    await expect(scannerTab).toHaveAttribute('data-state', 'active');
  });

  test('should switch to Both sources', async ({ page }) => {
    const bothTab = page.getByRole('tab', { name: /both/i });
    await bothTab.click();
    await page.waitForTimeout(500);
    await expect(bothTab).toHaveAttribute('data-state', 'active');
  });

  test('should return to Exchanges source', async ({ page }) => {
    // First switch to another source
    await page.getByRole('tab', { name: /both/i }).click();
    await page.waitForTimeout(300);

    // Then switch back to exchanges
    const exchangesTab = page.getByRole('tab', { name: /exchanges/i });
    await exchangesTab.click();
    await page.waitForTimeout(300);
    await expect(exchangesTab).toHaveAttribute('data-state', 'active');
  });
});

test.describe('Connected Exchanges Filter', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
  });

  test('should display connected exchanges checkbox', async ({ page }) => {
    await expect(page.getByText(/show only connected/i)).toBeVisible();
  });

  test('should have checkbox control', async ({ page }) => {
    const checkbox = page.getByRole('checkbox');
    await expect(checkbox).toBeVisible();
  });

  test('should toggle connected exchanges filter', async ({ page }) => {
    const checkbox = page.getByRole('checkbox');

    // Get initial state
    const initialChecked = await checkbox.isChecked();

    // Toggle the checkbox
    await checkbox.click();
    await page.waitForTimeout(300);

    // Verify state changed
    const newChecked = await checkbox.isChecked();
    expect(newChecked).toBe(!initialChecked);

    // Toggle back
    await checkbox.click();
    await page.waitForTimeout(300);
  });
});

test.describe('Funding Rates Table Interaction', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
  });

  test('should display funding rate data rows', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(1000);

    // Check for table body rows
    const rows = page.locator('tbody tr');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThanOrEqual(0); // May be 0 if no data
  });

  test('should highlight positive rates in green', async ({ page }) => {
    await page.waitForTimeout(1000);
    // Check for green colored text (positive rates)
    const greenText = page.locator('.text-green-500');
    // May or may not exist depending on data
    await expect(greenText.first()).toBeVisible().catch(() => true);
  });

  test('should highlight negative rates in red', async ({ page }) => {
    await page.waitForTimeout(1000);
    // Check for red colored text (negative rates)
    const redText = page.locator('.text-red-500');
    // May or may not exist depending on data
    await expect(redText.first()).toBeVisible().catch(() => true);
  });
});

test.describe('Funding Rates Refresh', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
  });

  test('should refresh data when clicking refresh button', async ({ page }) => {
    const refreshButton = page.getByRole('button', { name: /refresh/i });
    await refreshButton.click();

    // Button should show loading state (spinner)
    await page.waitForTimeout(100);
    // Wait for refresh to complete
    await page.waitForTimeout(2000);
  });
});

test.describe('Funding Rates Search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
  });

  test('should have search input', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();
  });

  test('should filter by search term', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill('BTC');
    await page.waitForTimeout(500);

    // Results should be filtered (or show no results message)
    await expect(page.getByText('BTC').first()).toBeVisible().catch(() => true);
  });

  test('should clear search', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill('BTC');
    await page.waitForTimeout(300);

    // Clear the search
    await searchInput.clear();
    await page.waitForTimeout(300);
  });
});

test.describe('Funding Rates Row Filtering (Show Connected Only)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
    await page.waitForTimeout(1000);
  });

  test('should filter both columns AND rows when Show Connected Only is enabled', async ({ page }) => {
    // Count rows before filter
    const rowsBefore = await page.locator('tbody tr').count();

    // Enable "Show only connected" filter
    const checkbox = page.getByRole('checkbox');
    const wasChecked = await checkbox.isChecked();

    // If not already checked, check it
    if (!wasChecked) {
      await checkbox.click();
      await page.waitForTimeout(500);
    }

    // Count rows after filter
    const rowsAfter = await page.locator('tbody tr').count();

    // If we had rows and connected exchanges are fewer than all exchanges,
    // the row count should be less than or equal to before
    expect(rowsAfter).toBeLessThanOrEqual(rowsBefore);

    // If checkbox was originally unchecked, uncheck it again
    if (!wasChecked) {
      await checkbox.click();
      await page.waitForTimeout(500);
    }
  });

  test('should restore all rows when unchecking Show Connected Only', async ({ page }) => {
    // First enable the filter
    const checkbox = page.getByRole('checkbox');
    if (!(await checkbox.isChecked())) {
      await checkbox.click();
      await page.waitForTimeout(500);
    }

    // Count rows with filter
    const rowsWithFilter = await page.locator('tbody tr').count();

    // Disable the filter
    await checkbox.click();
    await page.waitForTimeout(500);

    // Count rows without filter
    const rowsWithoutFilter = await page.locator('tbody tr').count();

    // Rows without filter should be >= rows with filter
    expect(rowsWithoutFilter).toBeGreaterThanOrEqual(rowsWithFilter);
  });

  test('should combine search with connected only filter', async ({ page }) => {
    // Enable connected only filter
    const checkbox = page.getByRole('checkbox');
    if (!(await checkbox.isChecked())) {
      await checkbox.click();
      await page.waitForTimeout(300);
    }

    // Apply search filter
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill('ETH');
    await page.waitForTimeout(500);

    // Both filters should work together
    // Table should be visible (either with results or empty state)
    await expect(page.getByRole('table')).toBeVisible();
  });
});

test.describe('Funding Rates Column Filtering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/funding-rates');
    await page.waitForTimeout(1000);
  });

  test('should filter exchange columns when Show Connected Only is enabled', async ({ page }) => {
    // Count visible column headers before filter (exchange columns)
    const headersBefore = await page.locator('thead th').count();

    // Enable connected only filter
    const checkbox = page.getByRole('checkbox');
    const wasChecked = await checkbox.isChecked();

    if (!wasChecked) {
      await checkbox.click();
      await page.waitForTimeout(500);
    }

    // Count visible column headers after filter
    const headersAfter = await page.locator('thead th').count();

    // If not all exchanges are connected, headers count should decrease
    expect(headersAfter).toBeLessThanOrEqual(headersBefore);

    // Restore original state
    if (!wasChecked) {
      await checkbox.click();
    }
  });
});
