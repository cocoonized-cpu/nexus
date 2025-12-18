import { chromium } from 'playwright';

async function debugAllPages() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const pages = [
    { name: 'Dashboard', url: '/' },
    { name: 'Situation Room', url: '/situation-room' },
    { name: 'Funding Rates', url: '/funding-rates' },
    { name: 'Opportunities', url: '/opportunities' },
    { name: 'Performance', url: '/performance' },
  ];

  for (const p of pages) {
    console.log(`\n=== ${p.name} ===`);
    await page.goto(`http://localhost:3000${p.url}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    await page.screenshot({
      path: `/tmp/nexus-${p.name.toLowerCase().replace(/ /g, '-')}.png`,
      fullPage: true
    });
    console.log(`Screenshot: /tmp/nexus-${p.name.toLowerCase().replace(/ /g, '-')}.png`);
  }

  await browser.close();
  console.log('\nDone! Check screenshots in /tmp/');
}

debugAllPages().catch(console.error);
