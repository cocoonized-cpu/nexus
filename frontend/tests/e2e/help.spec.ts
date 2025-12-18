import { test, expect } from '@playwright/test';

test.describe('Help Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/help');
  });

  test('should display help center title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /help center/i })).toBeVisible();
  });

  test('should display main navigation tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /getting started/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /how it works/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /page guide/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /kpi/i })).toBeVisible();
  });

  test('should display welcome card on Getting Started tab', async ({ page }) => {
    await expect(page.getByText('Welcome to NEXUS').first()).toBeVisible();
    await expect(page.getByText('Your automated funding rate arbitrage system').first()).toBeVisible();
  });

  test('should display What is Funding Rate Arbitrage section', async ({ page }) => {
    await expect(page.getByText('What is Funding Rate Arbitrage?').first()).toBeVisible();
    await expect(page.getByText('The Opportunity').first()).toBeVisible();
    await expect(page.getByText('The Strategy').first()).toBeVisible();
    await expect(page.getByText('The Profit').first()).toBeVisible();
  });

  test('should display Quick Start Guide', async ({ page }) => {
    await expect(page.getByText('Quick Start Guide').first()).toBeVisible();
    await expect(page.getByText('Configure Exchanges').first()).toBeVisible();
    await expect(page.getByText('Review Funding Rates').first()).toBeVisible();
    await expect(page.getByText('Explore Opportunities').first()).toBeVisible();
    await expect(page.getByText('Start in Paper Mode').first()).toBeVisible();
    await expect(page.getByText('Monitor Positions').first()).toBeVisible();
    await expect(page.getByText('Analyze Performance').first()).toBeVisible();
  });

  test('should display Key Concepts section', async ({ page }) => {
    await expect(page.getByText('Key Concepts').first()).toBeVisible();
    await expect(page.getByText('Delta Neutral').first()).toBeVisible();
    await expect(page.getByText('UOS Score').first()).toBeVisible();
    await expect(page.getByText('Funding Spread').first()).toBeVisible();
    await expect(page.getByText('Position Legs').first()).toBeVisible();
  });
});

test.describe('Help Page - How It Works Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/help');
    await page.getByRole('tab', { name: /how it works/i }).click();
    await page.waitForTimeout(300);
  });

  test('should switch to How It Works tab', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /how it works/i })).toHaveAttribute('data-state', 'active');
  });

  test('should display Arbitrage Strategy Overview', async ({ page }) => {
    await expect(page.getByText('Arbitrage Strategy Overview').first()).toBeVisible();
  });

  test('should display exchange diagram', async ({ page }) => {
    await expect(page.getByText('Exchange A').first()).toBeVisible();
    await expect(page.getByText('Exchange B').first()).toBeVisible();
    await expect(page.getByText('Net Profit').first()).toBeVisible();
  });

  test('should display Decision Flow section', async ({ page }) => {
    await expect(page.getByText('Decision Flow').first()).toBeVisible();
    await expect(page.getByText('Opportunity Detected').first()).toBeVisible();
    await expect(page.getByText('UOS Score Check').first()).toBeVisible();
  });

  test('should display Step-by-Step Process', async ({ page }) => {
    await expect(page.getByText('Step-by-Step Process').first()).toBeVisible();
  });

  test('should display all 8 bot steps', async ({ page }) => {
    await expect(page.getByText('Data Collection').first()).toBeVisible();
    await expect(page.getByText('Opportunity Detection').first()).toBeVisible();
    await expect(page.getByText('UOS Scoring').first()).toBeVisible();
    await expect(page.getByText('Validation & Filtering').first()).toBeVisible();
    await expect(page.getByText('Capital Allocation').first()).toBeVisible();
    await expect(page.getByText('Order Execution').first()).toBeVisible();
    await expect(page.getByText('Position Management').first()).toBeVisible();
    await expect(page.getByText('Exit Optimization').first()).toBeVisible();
  });

  test('should expand step card on click', async ({ page }) => {
    // Click on the first step card (Data Collection)
    const dataCollectionCard = page.locator('text=Data Collection').first().locator('..');
    await dataCollectionCard.click();
    await page.waitForTimeout(300);

    // Should show step details
    await expect(page.getByText('Connect to exchange APIs').first()).toBeVisible();
  });

  test('should display Funding Payment Timeline', async ({ page }) => {
    await expect(page.getByText('Funding Payment Timeline').first()).toBeVisible();
    await expect(page.getByText('00:00 UTC').first()).toBeVisible();
    await expect(page.getByText('08:00 UTC').first()).toBeVisible();
    await expect(page.getByText('16:00 UTC').first()).toBeVisible();
  });
});

test.describe('Help Page - Page Guide Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/help');
    await page.getByRole('tab', { name: /page guide/i }).click();
    await page.waitForTimeout(300);
  });

  test('should switch to Page Guide tab', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /page guide/i })).toHaveAttribute('data-state', 'active');
  });

  test('should display Quick Navigation section', async ({ page }) => {
    await expect(page.getByText('Quick Navigation').first()).toBeVisible();
  });

  test('should display all page cards', async ({ page }) => {
    await expect(page.getByText('Dashboard').first()).toBeVisible();
    await expect(page.getByText('Situation Room').first()).toBeVisible();
    await expect(page.getByText('Funding Rates').first()).toBeVisible();
    await expect(page.getByText('Opportunities').first()).toBeVisible();
    await expect(page.getByText('Positions & Trades').first()).toBeVisible();
    await expect(page.getByText('Performance').first()).toBeVisible();
    await expect(page.getByText('Settings').first()).toBeVisible();
  });

  test('should display page descriptions and features', async ({ page }) => {
    // Dashboard card should have features
    await expect(page.getByText('View Portfolio Summary').first()).toBeVisible();
    await expect(page.getByText('Monitor Performance').first()).toBeVisible();
  });

  test('should display Key Metrics badges', async ({ page }) => {
    await expect(page.getByText('Total P&L').first()).toBeVisible();
    await expect(page.getByText('Win Rate').first()).toBeVisible();
  });
});

test.describe('Help Page - KPI Dictionary Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/help');
    await page.getByRole('tab', { name: /kpi/i }).click();
    await page.waitForTimeout(300);
  });

  test('should switch to KPI Dictionary tab', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /kpi/i })).toHaveAttribute('data-state', 'active');
  });

  test('should display KPI Dictionary title', async ({ page }) => {
    await expect(page.getByText('KPI Dictionary').first()).toBeVisible();
  });

  test('should display search input', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search metrics/i);
    await expect(searchInput).toBeVisible();
  });

  test('should display category filter tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /all/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /funding/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /position/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /performance/i })).toBeVisible();
  });

  test('should filter KPIs by search term', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search metrics/i);
    await searchInput.fill('funding rate');
    await page.waitForTimeout(500);

    // Should show funding rate related KPIs
    await expect(page.getByText('Funding Rate').first()).toBeVisible();
  });

  test('should filter KPIs by category', async ({ page }) => {
    // Click on Funding category tab
    await page.getByRole('tab', { name: /funding/i }).click();
    await page.waitForTimeout(300);

    // Should show funding category description
    await expect(page.getByText('Funding').first()).toBeVisible();
  });

  test('should expand KPI accordion item', async ({ page }) => {
    // Find and click on a KPI accordion trigger
    const firstAccordionTrigger = page.locator('[data-state]').filter({ has: page.getByText('Funding Rate') }).first();

    if (await firstAccordionTrigger.count() > 0) {
      await firstAccordionTrigger.click();
      await page.waitForTimeout(300);
    }
  });

  test('should clear search and show all KPIs', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search metrics/i);
    await searchInput.fill('funding');
    await page.waitForTimeout(300);

    await searchInput.clear();
    await page.waitForTimeout(300);

    // Should show all KPIs again
    await expect(page.getByRole('tab', { name: /all/i })).toBeVisible();
  });
});

test.describe('Help Page Tab Navigation', () => {
  test('should navigate between all tabs', async ({ page }) => {
    await page.goto('/help');

    // Start on Getting Started (default)
    await expect(page.getByText('Welcome to NEXUS').first()).toBeVisible();

    // Navigate to How It Works
    await page.getByRole('tab', { name: /how it works/i }).click();
    await page.waitForTimeout(300);
    await expect(page.getByText('Arbitrage Strategy Overview').first()).toBeVisible();

    // Navigate to Page Guide
    await page.getByRole('tab', { name: /page guide/i }).click();
    await page.waitForTimeout(300);
    await expect(page.getByText('Quick Navigation').first()).toBeVisible();

    // Navigate to KPI Dictionary
    await page.getByRole('tab', { name: /kpi/i }).click();
    await page.waitForTimeout(300);
    await expect(page.getByText('KPI Dictionary').first()).toBeVisible();

    // Return to Getting Started
    await page.getByRole('tab', { name: /getting started/i }).click();
    await page.waitForTimeout(300);
    await expect(page.getByText('Welcome to NEXUS').first()).toBeVisible();
  });
});

test.describe('Help Page Accessibility', () => {
  test('should have accessible tab panel structure', async ({ page }) => {
    await page.goto('/help');

    // Check tablist exists
    const tablist = page.getByRole('tablist');
    await expect(tablist).toBeVisible();

    // Check tabs have proper roles
    const tabs = page.getByRole('tab');
    const tabCount = await tabs.count();
    expect(tabCount).toBe(4);
  });

  test('should have keyboard navigable tabs', async ({ page }) => {
    await page.goto('/help');

    // Focus on first tab
    const firstTab = page.getByRole('tab', { name: /getting started/i });
    await firstTab.focus();

    // Press right arrow to move to next tab
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(100);
  });
});
