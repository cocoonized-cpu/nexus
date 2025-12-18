import { chromium } from 'playwright';

async function debug() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Listen for all network requests
  page.on('request', request => {
    if (request.url().includes('/api/')) {
      console.log('REQUEST:', request.method(), request.url());
    }
  });

  page.on('response', response => {
    if (response.url().includes('/api/')) {
      console.log('RESPONSE:', response.status(), response.url());
    }
  });

  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('CONSOLE ERROR:', msg.text());
    }
  });

  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' });

  console.log('\nWaiting 5 seconds for data...');
  await page.waitForTimeout(5000);

  // Take screenshot
  await page.screenshot({ path: '/tmp/dashboard-debug.png', fullPage: true });
  console.log('\nScreenshot saved to /tmp/dashboard-debug.png');

  // Check for KPI cards content
  const kpiCards = await page.locator('.grid.gap-4.md\\:grid-cols-4 .rounded-lg').count();
  console.log(`\nFound ${kpiCards} KPI cards`);

  // Get text content of first card
  const firstCard = page.locator('.grid.gap-4.md\\:grid-cols-4 .rounded-lg').first();
  const cardText = await firstCard.textContent();
  console.log('First card text:', cardText);

  // Check if still loading
  const loaders = await page.locator('.animate-spin').count();
  console.log(`\nLoading spinners visible: ${loaders}`);

  await browser.close();
}

debug().catch(console.error);
