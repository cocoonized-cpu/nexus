import { test, expect } from '@playwright/test';

test.describe('Verify Hover Popup', () => {
  test('verify hover popup actually shows', async ({ page }) => {
    // Enable console logging
    page.on('console', msg => console.log('BROWSER:', msg.type(), msg.text()));

    // Go to opportunities page
    await page.goto('/opportunities');
    await page.waitForTimeout(3000);

    // Check for badges
    const badges = page.locator('[data-testid="bot-action-badge"]');
    const count = await badges.count();
    console.log('Badge count:', count);

    if (count === 0) {
      console.log('No opportunities available - skipping test');
      return;
    }

    // Take screenshot of page with opportunities
    await page.screenshot({ path: 'test-results/with-opportunities.png', fullPage: true });

    // Get the first badge
    const badge = badges.first();

    // Get badge position
    const boundingBox = await badge.boundingBox();
    console.log('Badge bounding box:', boundingBox);

    // Standard hover
    console.log('Attempting hover...');
    await badge.hover();
    await page.waitForTimeout(500);

    // Check for hover card
    const hoverCard = page.locator('[data-testid="bot-action-tooltip"]');
    const visible = await hoverCard.isVisible();
    console.log('HoverCard visible:', visible);

    // Take screenshot after hover
    await page.screenshot({ path: 'test-results/after-hover.png', fullPage: true });

    // Check Radix portals
    const portals = page.locator('[data-radix-popper-content-wrapper]');
    const portalCount = await portals.count();
    console.log('Radix portal count:', portalCount);

    // Verify hover card
    await expect(hoverCard).toBeVisible({ timeout: 3000 });
    console.log('SUCCESS: HoverCard is visible!');
  });
});
