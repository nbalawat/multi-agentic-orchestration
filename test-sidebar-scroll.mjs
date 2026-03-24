import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

await page.screenshot({ path: '/tmp/sidebar-scroll-1.png', fullPage: false });

// Deep dive into AgentList internals
const agentListInfo = await page.evaluate(() => {
  const agentList = document.querySelector('.agent-list');
  const content = document.querySelector('.agent-list-content');
  const items = document.querySelector('.agent-items');
  const cards = document.querySelectorAll('.agent-card');
  const header = document.querySelector('.agent-list-header');

  return {
    agentList: agentList ? {
      height: agentList.clientHeight,
      scrollHeight: agentList.scrollHeight,
      overflow: window.getComputedStyle(agentList).overflow,
      display: window.getComputedStyle(agentList).display,
      flexDirection: window.getComputedStyle(agentList).flexDirection,
    } : null,
    header: header ? { height: header.clientHeight } : null,
    content: content ? {
      height: content.clientHeight,
      scrollHeight: content.scrollHeight,
      overflow: window.getComputedStyle(content).overflowY,
      canScroll: content.scrollHeight > content.clientHeight,
      flex: window.getComputedStyle(content).flex,
    } : null,
    items: items ? {
      height: items.clientHeight,
      scrollHeight: items.scrollHeight,
      childCount: items.children.length,
    } : null,
    cardCount: cards.length,
    cardHeights: Array.from(cards).map(c => c.clientHeight),
  };
});

console.log('AgentList internals:', JSON.stringify(agentListInfo, null, 2));

await browser.close();
