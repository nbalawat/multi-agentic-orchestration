import { chromium } from '@playwright/test';

const PROJECT_ID = '611eb355-e085-40e4-9c23-8581155fd6dc';
const API = 'http://127.0.0.1:9403';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

// Select agent-memory project
const projectItem = page.locator('.project-item:has-text("agent-memory")');
if (await projectItem.count() > 0) await projectItem.click();
await page.waitForTimeout(2000);

// Switch to Implementation Flow
const flowTab = page.locator('.center-tab:has-text("Implementation Flow")');
if (await flowTab.count() > 0) await flowTab.click();
await page.waitForTimeout(2000);

console.log('=== MONITORING E2E FLOW ===');
console.log('6 features, 3 waves. Checking every 15 seconds.\n');

let lastComplete = 0;
let screenshots = 0;

for (let i = 0; i < 40; i++) {  // Up to 10 minutes
  await page.waitForTimeout(15000);

  const elapsed = (i + 1) * 15;

  // Get status from API
  try {
    const resp = await fetch(`${API}/api/projects/${PROJECT_ID}/execution-status`);
    const data = await resp.json();
    const dag = data.dag;

    const runs = data.runs || [];
    const byStatus = {};
    for (const r of runs) {
      byStatus[r.status] = (byStatus[r.status] || 0) + 1;
    }

    const building = runs.filter(r => r.status === 'building').map(r => r.feature_name);
    const complete = runs.filter(r => r.status === 'complete').map(r => `${r.feature_name}($${r.cost.toFixed(2)})`);
    const failed = runs.filter(r => r.status === 'failed').map(r => r.feature_name);

    console.log(`[${elapsed}s] DAG: ${dag.complete}/${dag.total} | Runs: ${JSON.stringify(byStatus)}`);
    if (building.length) console.log(`  Building: ${building.join(', ')}`);
    if (complete.length > lastComplete) {
      console.log(`  ✅ Complete: ${complete.join(', ')}`);
      lastComplete = complete.length;
    }
    if (failed.length) console.log(`  ❌ Failed: ${failed.join(', ')}`);

    // Screenshot at key moments
    if (dag.complete > screenshots * 2 || building.length > 0 && screenshots === 0) {
      screenshots++;
      await page.screenshot({ path: `/tmp/e2e-flow-${screenshots}.png` });
      console.log(`  📸 Screenshot saved: /tmp/e2e-flow-${screenshots}.png`);
    }

    // All done?
    if (dag.complete === dag.total && dag.total > 0) {
      console.log(`\n🎉 ALL ${dag.total} FEATURES COMPLETE! Total cost: $${data.total_cost.toFixed(3)}`);
      await page.screenshot({ path: '/tmp/e2e-flow-final.png' });
      console.log('📸 Final screenshot saved');
      break;
    }

    // All failed?
    if (failed.length === runs.length && runs.length > 0) {
      console.log('\n❌ ALL RUNS FAILED');
      break;
    }
  } catch (e) {
    console.log(`[${elapsed}s] Error: ${e.message}`);
  }
}

// Final check
const finalResp = await fetch(`${API}/api/projects/${PROJECT_ID}/execution-status`);
const finalData = await finalResp.json();
console.log('\n=== FINAL STATE ===');
console.log(`DAG: ${finalData.dag.complete}/${finalData.dag.total} (${finalData.dag.completion_pct}%)`);
console.log(`Cost: $${finalData.total_cost.toFixed(3)}`);
for (const r of finalData.runs.filter(r => r.id)) {
  const test = r.test_results?.passed ? `tests: ${r.test_results.passed}p/${r.test_results.failed}f` : '';
  console.log(`  ${r.feature_name}: ${r.status} $${r.cost.toFixed(3)} ${test}`);
}

await browser.close();
