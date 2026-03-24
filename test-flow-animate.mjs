import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://127.0.0.1:5175', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

// Switch to task-api project (implement phase)
await fetch('http://127.0.0.1:9403/api/projects/2d6eed9a-b36d-45f9-b836-d8bcae9fef8e/switch', { method: 'POST' });
const taskApi = page.locator('.project-item:has-text("task-api")');
if (await taskApi.count() > 0) await taskApi.click();
await page.waitForTimeout(1500);

// Click Implementation Flow tab
const flowTab = page.locator('.center-tab:has-text("Implementation Flow")');
if (await flowTab.count() > 0) await flowTab.click();
await page.waitForTimeout(1000);

// Screenshot 1: All features in Ready
await page.screenshot({ path: '/tmp/flow-anim-1-ready.png' });
console.log('1. All 4 features in READY column');

// Simulate: feature "schemas" starts building (agent picks it up)
await page.evaluate(() => {
  const pinia = window.__pinia;
  if (!pinia) return;
  const store = pinia._s.get('implementFlow');
  if (!store) return;
  store.handleFeatureStarted({
    feature_id: Array.from(store.features.keys()).find(k => store.features.get(k)?.name?.includes('schema')),
    feature_name: 'schemas',
    agent_name: 'builder-schemas',
    project_id: '2d6eed9a-b36d-45f9-b836-d8bcae9fef8e'
  });
});
await page.waitForTimeout(800);
await page.screenshot({ path: '/tmp/flow-anim-2-building.png' });
console.log('2. "schemas" moved to BUILDING (agent assigned)');

// Simulate: second feature starts building too (parallel execution)
await page.evaluate(() => {
  const store = window.__pinia._s.get('implementFlow');
  if (!store) return;
  const dbModId = Array.from(store.features.keys()).find(k => store.features.get(k)?.name?.includes('db'));
  store.handleFeatureStarted({
    feature_id: dbModId,
    feature_name: 'db-models',
    agent_name: 'builder-db-models',
    project_id: '2d6eed9a-b36d-45f9-b836-d8bcae9fef8e'
  });
});
await page.waitForTimeout(800);
await page.screenshot({ path: '/tmp/flow-anim-3-parallel.png' });
console.log('3. "db-models" also BUILDING (parallel execution)');

// Simulate: "schemas" completes and merges
await page.evaluate(() => {
  const store = window.__pinia._s.get('implementFlow');
  if (!store) return;
  const schemaId = Array.from(store.features.keys()).find(k => store.features.get(k)?.name?.includes('schema'));
  store.handleFeatureMerged({
    feature_id: schemaId,
    feature_name: 'schemas',
    agent_name: 'builder-schemas',
    project_id: '2d6eed9a-b36d-45f9-b836-d8bcae9fef8e'
  });
  store.handleDagProgress({ total: 4, completed: 1, in_progress: 1, ready: 2 });
});
await page.waitForTimeout(800);
await page.screenshot({ path: '/tmp/flow-anim-4-first-done.png' });
console.log('4. "schemas" moved to DONE, progress updated');

// Simulate: "db-models" completes too
await page.evaluate(() => {
  const store = window.__pinia._s.get('implementFlow');
  if (!store) return;
  const dbId = Array.from(store.features.keys()).find(k => store.features.get(k)?.name?.includes('db'));
  store.handleFeatureMerged({
    feature_id: dbId,
    feature_name: 'db-models',
    agent_name: 'builder-db-models',
    project_id: '2d6eed9a-b36d-45f9-b836-d8bcae9fef8e'
  });
  store.handleDagProgress({ total: 4, completed: 2, in_progress: 0, ready: 2 });
});
await page.waitForTimeout(800);
await page.screenshot({ path: '/tmp/flow-anim-5-two-done.png' });
console.log('5. "db-models" also DONE, 2/4 complete');

// Simulate: next wave — remaining features start building
await page.evaluate(() => {
  const store = window.__pinia._s.get('implementFlow');
  if (!store) return;
  const remaining = Array.from(store.features.entries())
    .filter(([_, f]) => f.stage === 'ready')
    .map(([id, f]) => ({ id, name: f.name }));

  for (const feat of remaining) {
    store.handleFeatureStarted({
      feature_id: feat.id,
      feature_name: feat.name,
      agent_name: `builder-${feat.name}`,
      project_id: '2d6eed9a-b36d-45f9-b836-d8bcae9fef8e'
    });
  }
  store.handleDagProgress({ total: 4, completed: 2, in_progress: 2, ready: 0 });
});
await page.waitForTimeout(800);
await page.screenshot({ path: '/tmp/flow-anim-6-wave2.png' });
console.log('6. Wave 2: remaining features now BUILDING');

// Simulate: all complete
await page.evaluate(() => {
  const store = window.__pinia._s.get('implementFlow');
  if (!store) return;
  const building = Array.from(store.features.entries())
    .filter(([_, f]) => f.stage === 'building')
    .map(([id, f]) => ({ id, name: f.name }));

  for (const feat of building) {
    store.handleFeatureMerged({
      feature_id: feat.id,
      feature_name: feat.name,
      agent_name: `builder-${feat.name}`,
      project_id: '2d6eed9a-b36d-45f9-b836-d8bcae9fef8e'
    });
  }
  store.handleDagComplete({ total: 4, message: 'All features implemented!' });
});
await page.waitForTimeout(800);
await page.screenshot({ path: '/tmp/flow-anim-7-complete.png' });
console.log('7. ALL COMPLETE — all features in DONE column');

await browser.close();
console.log('\nDone! Screenshots saved to /tmp/flow-anim-*.png');
