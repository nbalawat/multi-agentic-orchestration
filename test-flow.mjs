import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

// Check if ImplementationFlow component exists in DOM
const flowPanel = page.locator('.implementation-flow');
const flowExists = await flowPanel.count() > 0;
console.log('ImplementationFlow exists in DOM:', flowExists);

// Check for center tabs
const centerTabs = page.locator('.center-tabs');
const tabsExist = await centerTabs.count() > 0;
console.log('Center tabs visible:', tabsExist);

// Check for the RAPIDS logo (should be visible in event stream)
const rapidsText = page.locator('text=RAPIDS');
console.log('RAPIDS logo text found:', await rapidsText.count() > 0);

// Take screenshot
await page.screenshot({ path: '/tmp/flow-panel-1.png', fullPage: false });
console.log('Screenshot saved to /tmp/flow-panel-1.png');

// If the project is in implement phase, check for the flow tab
if (tabsExist) {
  const flowTab = page.locator('.center-tab:has-text("Implementation Flow")');
  if (await flowTab.count() > 0) {
    await flowTab.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: '/tmp/flow-panel-2.png', fullPage: false });
    console.log('Flow panel screenshot saved to /tmp/flow-panel-2.png');
  }
}

await browser.close();
