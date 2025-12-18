import { test, expect } from '@playwright/test';

test('screenshot hover card verification', async ({ page }) => {
  await page.goto('/opportunities');
  await page.waitForTimeout(2000);
  
  // Find a bot action badge
  const badge = page.locator('[data-testid="bot-action-badge"]').first();
  
  if (await badge.isVisible()) {
    // Take screenshot before hover
    await page.screenshot({ path: 'test-results/before-hover.png', fullPage: true });
    console.log('Screenshot saved: before-hover.png');
    
    // Hover over the badge
    await badge.hover();
    await page.waitForTimeout(500);
    
    // Take screenshot after hover - showing the popup
    await page.screenshot({ path: 'test-results/after-hover.png', fullPage: true });
    console.log('Screenshot saved: after-hover.png');
    
    // Check hover card is visible
    const hoverCard = page.locator('[data-testid="bot-action-tooltip"]');
    await expect(hoverCard).toBeVisible({ timeout: 2000 });
    
    // Take a focused screenshot of just the hover card area
    const boundingBox = await hoverCard.boundingBox();
    if (boundingBox) {
      await page.screenshot({ 
        path: 'test-results/hover-card-only.png',
        clip: {
          x: Math.max(0, boundingBox.x - 20),
          y: Math.max(0, boundingBox.y - 20),
          width: boundingBox.width + 40,
          height: boundingBox.height + 40
        }
      });
      console.log('Screenshot saved: hover-card-only.png');
    }
    
    console.log('SUCCESS: Hover card IS visible!');
  } else {
    console.log('No badge found - no opportunities available');
  }
});
