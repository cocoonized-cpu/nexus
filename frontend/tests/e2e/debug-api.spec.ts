import { test, expect } from '@playwright/test';

test('debug API call', async ({ page }) => {
  // Listen for API responses
  page.on('response', async response => {
    if (response.url().includes('/opportunities')) {
      console.log('API Response URL:', response.url());
      console.log('API Response Status:', response.status());
      try {
        const json = await response.json();
        console.log('API Response success:', json.success);
        console.log('API Response data length:', json.data?.length || 0);
        if (json.data?.[0]) {
          console.log('First item has bot_action:', !!json.data[0].bot_action);
        }
      } catch (e) {
        console.log('Could not parse response');
      }
    }
  });
  
  await page.goto('/opportunities');
  await page.waitForTimeout(5000);
  
  await page.screenshot({ path: 'test-results/api-debug.png', fullPage: true });
});
