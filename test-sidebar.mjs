import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

// Screenshot 1: Initial expanded state
await page.screenshot({ path: '/tmp/sidebar-1-expanded.png', fullPage: false });
console.log('Screenshot 1: Initial state saved to /tmp/sidebar-1-expanded.png');

// Find and click the collapse button (‹ icon in AgentList header)
const collapseBtn = page.locator('.collapse-btn').first();
if (await collapseBtn.isVisible()) {
  await collapseBtn.click();
  await page.waitForTimeout(500);

  // Screenshot 2: Collapsed state
  await page.screenshot({ path: '/tmp/sidebar-2-collapsed.png', fullPage: false });
  console.log('Screenshot 2: Collapsed state saved to /tmp/sidebar-2-collapsed.png');

  // Click expand button
  await collapseBtn.click();
  await page.waitForTimeout(500);

  // Screenshot 3: Re-expanded
  await page.screenshot({ path: '/tmp/sidebar-3-reexpanded.png', fullPage: false });
  console.log('Screenshot 3: Re-expanded state saved to /tmp/sidebar-3-reexpanded.png');
} else {
  console.log('Collapse button not found - checking sidebar structure...');
  const html = await page.locator('.app-sidebar.left').innerHTML();
  console.log('Left sidebar HTML (first 500 chars):', html.substring(0, 500));
}

// Check sidebar widths
const leftSidebar = page.locator('.app-sidebar.left').first();
const box = await leftSidebar.boundingBox();
console.log('Left sidebar bounding box:', JSON.stringify(box));

await browser.close();
