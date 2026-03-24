import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

// Step 1: Switch to task-api project (in implement phase) via API
const apiBase = 'http://127.0.0.1:9403';
await fetch(`${apiBase}/api/projects/2d6eed9a-b36d-45f9-b836-d8bcae9fef8e/switch`, { method: 'POST' });
await page.waitForTimeout(1000);

// Step 2: Click task-api in the sidebar to trigger frontend switch
const taskApiItem = page.locator('.project-item:has-text("task-api")');
if (await taskApiItem.count() > 0) {
  await taskApiItem.click();
  console.log('Clicked task-api project');
  await page.waitForTimeout(1500);
}

// Step 3: Screenshot - should show the Implementation Flow tab
await page.screenshot({ path: '/tmp/flow-test-1.png', fullPage: false });
console.log('Screenshot 1: After selecting task-api');

// Step 4: Check if the flow tab appeared
const flowTab = page.locator('.center-tab:has-text("Implementation Flow")');
const flowTabExists = await flowTab.count() > 0;
console.log('Flow tab visible:', flowTabExists);

if (flowTabExists) {
  // Click the flow tab
  await flowTab.click();
  await page.waitForTimeout(1000);

  await page.screenshot({ path: '/tmp/flow-test-2.png', fullPage: false });
  console.log('Screenshot 2: Implementation Flow panel');

  // Check column structure
  const columns = page.locator('.flow-column');
  const columnCount = await columns.count();
  console.log('Flow columns found:', columnCount);

  // Check for feature cards
  const cards = page.locator('.flow-card');
  const cardCount = await cards.count();
  console.log('Feature cards found:', cardCount);

  // Check column headers
  const headers = page.locator('.column-label');
  for (let i = 0; i < await headers.count(); i++) {
    const text = await headers.nth(i).textContent();
    const count = await page.locator('.column-count').nth(i).textContent();
    console.log(`  Column ${i}: ${text} (${count})`);
  }

  // Check progress header
  const progressHeader = page.locator('.flow-progress-header');
  if (await progressHeader.count() > 0) {
    const headerText = await progressHeader.textContent();
    console.log('Progress header:', headerText?.trim().replace(/\s+/g, ' '));
  }
} else {
  console.log('Flow tab not visible - checking project phase...');
  // Check what phase the active project is in
  const contextBar = page.locator('.project-context-bar');
  if (await contextBar.count() > 0) {
    const barText = await contextBar.textContent();
    console.log('Context bar:', barText?.trim());
  }
}

// Also check event stream tab toggling
const eventTab = page.locator('.center-tab:has-text("Event Stream")');
if (await eventTab.count() > 0) {
  await eventTab.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: '/tmp/flow-test-3.png', fullPage: false });
  console.log('Screenshot 3: Switched back to Event Stream');
}

await browser.close();
