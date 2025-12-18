import { test, expect } from '@playwright/test';

/**
 * This test uses mocked API data to verify the hover popup functionality
 * works correctly. This is necessary because real opportunities may not
 * always be available.
 */
test.describe('Hover Popup with Mocked Data', () => {
  test('should show hover popup on badge hover (mocked data)', async ({ page }) => {
    // Mock the opportunities API to return test data
    // The actual endpoint is /api/v1/opportunities/live
    await page.route('**/opportunities/live*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: [
            {
              id: 'test-opp-1',
              symbol: 'BTCUSDT',
              base_asset: 'BTC',
              opportunity_type: 'funding_rate',
              status: 'detected',
              primary_exchange: 'binance',
              primary_rate: 0.0005,
              primary_side: 'long',
              hedge_exchange: 'bybit',
              hedge_rate: -0.0002,
              hedge_side: 'short',
              funding_spread_pct: 0.0007,
              net_apr: 25.55,
              uos_score: 78,
              detected_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 3600000).toISOString(),
              long_leg: { exchange: 'binance', funding_rate: 0.0005 },
              short_leg: { exchange: 'bybit', funding_rate: -0.0002 },
              bot_action: {
                status: 'waiting',
                reason: 'Position limit reached for BTC',
                details: [
                  { rule: 'system_running', passed: true, current: null, threshold: null, message: 'System is operational' },
                  { rule: 'circuit_breaker', passed: true, current: null, threshold: null, message: 'Circuit breaker is not tripped' },
                  { rule: 'position_limit', passed: false, current: '3', threshold: '3', message: 'Maximum 3 positions allowed' },
                  { rule: 'min_spread', passed: true, current: '0.07%', threshold: '0.05%', message: 'Spread meets minimum threshold' },
                ],
                user_action: 'Close an existing position to open new trades',
                can_execute: false
              }
            },
            {
              id: 'test-opp-2',
              symbol: 'ETHUSDT',
              base_asset: 'ETH',
              opportunity_type: 'funding_rate',
              status: 'detected',
              primary_exchange: 'okx',
              primary_rate: 0.0003,
              primary_side: 'long',
              hedge_exchange: 'hyperliquid',
              hedge_rate: -0.0001,
              hedge_side: 'short',
              funding_spread_pct: 0.0004,
              net_apr: 14.6,
              uos_score: 65,
              detected_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 3600000).toISOString(),
              long_leg: { exchange: 'okx', funding_rate: 0.0003 },
              short_leg: { exchange: 'hyperliquid', funding_rate: -0.0001 },
              bot_action: {
                status: 'auto_trade',
                reason: 'All checks passed, ready to execute',
                details: [
                  { rule: 'system_running', passed: true, current: null, threshold: null, message: 'System is operational' },
                  { rule: 'circuit_breaker', passed: true, current: null, threshold: null, message: 'Circuit breaker is not tripped' },
                  { rule: 'position_limit', passed: true, current: '2', threshold: '3', message: 'Within position limits' },
                ],
                user_action: null,
                can_execute: true
              }
            }
          ]
        })
      });
    });

    // Navigate to opportunities page
    await page.goto('/opportunities');
    await page.waitForTimeout(1000);

    // Verify badges are visible
    const badges = page.locator('[data-testid="bot-action-badge"]');
    await expect(badges.first()).toBeVisible();
    const badgeCount = await badges.count();
    console.log(`Found ${badgeCount} bot action badges`);
    expect(badgeCount).toBe(2);

    // Take screenshot before hover
    await page.screenshot({ path: 'test-results/mocked-before-hover.png', fullPage: true });

    // Hover over the first badge
    const firstBadge = badges.first();
    await firstBadge.hover();
    await page.waitForTimeout(300);

    // Take screenshot after hover
    await page.screenshot({ path: 'test-results/mocked-after-hover.png', fullPage: true });

    // Verify the hover card appears
    const hoverCard = page.locator('[data-testid="bot-action-tooltip"]');
    await expect(hoverCard).toBeVisible({ timeout: 3000 });
    console.log('SUCCESS: Hover card is visible!');

    // Verify hover card content
    await expect(hoverCard.getByText('Waiting')).toBeVisible();
    await expect(hoverCard.getByText('Position limit reached for BTC')).toBeVisible();
    await expect(hoverCard.getByText('Blocking Rules')).toBeVisible();
    await expect(hoverCard.getByText('Maximum 3 positions allowed')).toBeVisible();

    // Take focused screenshot of hover card
    const hoverBox = await hoverCard.boundingBox();
    if (hoverBox) {
      await page.screenshot({
        path: 'test-results/mocked-hover-card-detail.png',
        clip: {
          x: Math.max(0, hoverBox.x - 20),
          y: Math.max(0, hoverBox.y - 20),
          width: hoverBox.width + 40,
          height: hoverBox.height + 40
        }
      });
    }

    // Move mouse away and verify hover card disappears
    await page.mouse.move(0, 0);
    await page.waitForTimeout(500);
    await expect(hoverCard).not.toBeVisible();
    console.log('SUCCESS: Hover card disappears when mouse leaves!');
  });

  test('should show auto-trade badge hover with passed checks', async ({ page }) => {
    // Mock the opportunities API
    await page.route('**/api/v1/opportunities*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: [
            {
              id: 'test-auto',
              symbol: 'SOLUSDT',
              base_asset: 'SOL',
              opportunity_type: 'funding_rate',
              status: 'detected',
              primary_exchange: 'binance',
              primary_rate: 0.001,
              primary_side: 'long',
              hedge_exchange: 'bybit',
              hedge_rate: -0.0005,
              hedge_side: 'short',
              funding_spread_pct: 0.0015,
              net_apr: 54.75,
              uos_score: 92,
              detected_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 3600000).toISOString(),
              long_leg: { exchange: 'binance', funding_rate: 0.001 },
              short_leg: { exchange: 'bybit', funding_rate: -0.0005 },
              bot_action: {
                status: 'auto_trade',
                reason: 'All 13 checks passed - ready for auto execution',
                details: [
                  { rule: 'system_running', passed: true, current: null, threshold: null, message: 'System is operational' },
                  { rule: 'auto_execute_enabled', passed: true, current: null, threshold: null, message: 'Auto-execution is enabled' },
                  { rule: 'circuit_breaker', passed: true, current: null, threshold: null, message: 'Circuit breaker is not tripped' },
                  { rule: 'position_limit', passed: true, current: '1', threshold: '5', message: 'Within position limits' },
                  { rule: 'capital_available', passed: true, current: '$500', threshold: '$100', message: 'Sufficient capital available' },
                  { rule: 'min_spread', passed: true, current: '0.15%', threshold: '0.05%', message: 'Spread meets threshold' },
                ],
                user_action: null,
                can_execute: true
              }
            }
          ]
        })
      });
    });

    await page.goto('/opportunities');
    await page.waitForTimeout(1000);

    // Verify auto-trade badge is visible
    const autoBadge = page.locator('[data-testid="bot-action-badge"]:has-text("Auto-trade")');
    await expect(autoBadge).toBeVisible();

    // Hover over the badge
    await autoBadge.hover();
    await page.waitForTimeout(300);

    // Verify hover card shows passed checks
    const hoverCard = page.locator('[data-testid="bot-action-tooltip"]');
    await expect(hoverCard).toBeVisible();
    await expect(hoverCard.getByText('Auto-trade')).toBeVisible();
    await expect(hoverCard.getByText('Passed Checks')).toBeVisible();
    await expect(hoverCard.getByText('System is operational')).toBeVisible();

    // Take screenshot
    await page.screenshot({ path: 'test-results/mocked-auto-trade-hover.png', fullPage: true });

    console.log('SUCCESS: Auto-trade hover card works correctly!');
  });
});
