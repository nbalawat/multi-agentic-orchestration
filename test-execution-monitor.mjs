import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: false });  // Visible browser
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

const PROJECT_ID = '611eb355-e085-40e4-9c23-8581155fd6dc';
const API = 'http://127.0.0.1:9403';

// Step 1: Open the app and switch to the project
console.log('=== Opening app ===');
await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

// Click agent-memory project
const projectItem = page.locator('.project-item:has-text("agent-memory")');
if (await projectItem.count() > 0) {
  await projectItem.click();
  console.log('Clicked agent-memory project');
  await page.waitForTimeout(2000);
}

// Switch to Implementation Flow tab
const flowTab = page.locator('.center-tab:has-text("Implementation Flow")');
if (await flowTab.count() > 0) {
  await flowTab.click();
  console.log('Switched to Implementation Flow');
  await page.waitForTimeout(1000);
}

await page.screenshot({ path: '/tmp/exec-monitor-1-before.png' });
console.log('Screenshot 1: Before execution');

// Step 2: Trigger execute_ready_features with max_parallel=1 (just ONE feature)
console.log('\n=== Triggering 1 feature execution ===');
const dagBefore = await (await fetch(`${API}/api/projects/${PROJECT_ID}/dag`)).json();
const readyFeatures = dagBefore.ready_features;
console.log(`Ready features: ${readyFeatures.length}`);

// Get orchestrator ID
const orchResp = await fetch(`${API}/api/orchestrator`);
const orchData = await orchResp.json();
const orchId = orchData.orchestrator?.id || orchData.id;
console.log(`Orchestrator ID: ${orchId}`);

// Execute via direct API - trigger the MCP tool
const execResp = await fetch(`${API}/api/projects/${PROJECT_ID}/dag/features/${readyFeatures[0]}/status`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ status: 'in_progress', agent_name: 'test-monitor' }),
});
const execResult = await execResp.json();
console.log('Marked in_progress:', JSON.stringify(execResult));

await page.waitForTimeout(2000);
await page.screenshot({ path: '/tmp/exec-monitor-2-in-progress.png' });
console.log('Screenshot 2: Feature in progress');

// Step 3: Check agents
const agentsResp = await fetch(`${API}/api/agents`);
const agentsData = await agentsResp.json();
console.log(`\nAgents: ${JSON.stringify(agentsData.agents?.length || 0)}`);

// Step 4: Now complete the feature
console.log('\n=== Marking feature complete ===');
const completeResp = await fetch(`${API}/api/projects/${PROJECT_ID}/dag/features/${readyFeatures[0]}/status`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ status: 'complete' }),
});
const completeResult = await completeResp.json();
console.log('Marked complete:', JSON.stringify(completeResult.status));
console.log('Newly ready:', completeResult.newly_ready?.length || 0);

await page.waitForTimeout(3000);
await page.screenshot({ path: '/tmp/exec-monitor-3-complete.png' });
console.log('Screenshot 3: After completion');

// Step 5: Check final DAG state
const dagAfter = await (await fetch(`${API}/api/projects/${PROJECT_ID}/dag`)).json();
console.log(`\nDAG after: complete=${dagAfter.summary.complete}, planned=${dagAfter.summary.planned}, ready=${dagAfter.ready_features.length}`);

console.log('\n=== Test complete — browser stays open for inspection ===');
await page.waitForTimeout(60000);  // Keep browser open for 60s
await browser.close();
