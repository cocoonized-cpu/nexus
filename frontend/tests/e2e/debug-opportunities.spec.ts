import { test, expect } from '@playwright/test';

test('debug opportunities loading', async ({ page }) => {
  // Enable console logging
  page.on('console', msg => console.log('BROWSER:', msg.text()));
  
  await page.goto('/opportunities');
  await page.waitForTimeout(3000);
  
  // Take a full screenshot
  await page.screenshot({ path: 'test-results/opportunities-page.png', fullPage: true });
  
  // Check what's on the page
  const table = page.locator('table');
  const tableVisible = await table.isVisible();
  console.log('Table visible:', tableVisible);
  
  const emptyState = page.getByText(/no opportunities/i);
  const emptyVisible = await emptyState.count() > 0;
  console.log('Empty state visible:', emptyVisible);
  
  // Count table rows
  if (tableVisible) {
    const rows = page.locator('tbody tr');
    const rowCount = await rows.count();
    console.log('Table row count:', rowCount);
    
    // Get first row content
    if (rowCount > 0) {
      const firstRowText = await rows.first().textContent();
      console.log('First row content:', firstRowText?.substring(0, 200));
    }
  }
  
  // Check for badges
  const badges = page.locator('[data-testid="bot-action-badge"]');
  const badgeCount = await badges.count();
  console.log('Bot action badge count:', badgeCount);
  
  // Check for any badges at all (even without testid)
  const anyBadges = page.locator('span:has-text("Auto-trade"), span:has-text("Manual only"), span:has-text("Waiting"), span:has-text("Blocked")');
  const anyBadgeCount = await anyBadges.count();
  console.log('Any status badges:', anyBadgeCount);
  
  // Check loading state
  const loadingText = page.getByText('Loading');
  const loadingVisible = await loadingText.count() > 0;
  console.log('Loading state visible:', loadingVisible);
});
