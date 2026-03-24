import { chromium } from '@playwright/test';

const PROJECT_ID = '611eb355-e085-40e4-9c23-8581155fd6dc';
const API = 'http://127.0.0.1:9403';

// Step 1: Get orchestrator ID
const orchResp = await fetch(`${API}/api/orchestrator`);
let orchId;
try {
  const orchData = await orchResp.json();
  orchId = orchData.orchestrator?.id || orchData.data?.id;
} catch(e) {}

if (!orchId) {
  // Fetch from DB via API
  const headResp = await fetch(`${API}/get_headers`);
  const headData = await headResp.json();
  orchId = headData.orchestrator_id;
}

console.log('Orchestrator ID:', orchId || 'not found');

// Step 2: Get a ready feature
const dagResp = await fetch(`${API}/api/projects/${PROJECT_ID}/dag`);
const dagData = await dagResp.json();
const readyIds = dagData.ready_features;
const allFeatures = Object.fromEntries(dagData.dag.features.map(f => [f.id, f]));
const firstReady = allFeatures[readyIds[0]];
console.log(`\nFirst ready feature: ${firstReady.name} (${firstReady.id})`);
console.log(`DAG: ${dagData.summary.complete}/${dagData.feature_count} complete, ${readyIds.length} ready`);

// Step 3: Trigger execution via the chat endpoint (this is what the UI does)
console.log(`\n=== Sending execute_ready_features via chat ===`);

if (orchId) {
  const chatResp = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: `Use execute_ready_features for project ${PROJECT_ID} with max_parallel 1. Execute ONLY 1 feature.`,
      orchestrator_agent_id: orchId,
    }),
  });
  console.log('Chat response status:', chatResp.status);
} else {
  console.log('No orchestrator ID — cannot send chat message');
  console.log('Trying direct execute...');
}

// Step 4: Monitor for 2 minutes
console.log('\n=== Monitoring for 120 seconds ===');
for (let i = 0; i < 24; i++) {
  await new Promise(r => setTimeout(r, 5000));

  const dagCheck = await fetch(`${API}/api/projects/${PROJECT_ID}/dag`);
  const dagNow = await dagCheck.json();
  const s = dagNow.summary;

  const agentCheck = await fetch(`${API}/api/agents`);
  const agentData = await agentCheck.json();
  const agents = agentData.agents || agentData.data || [];
  const activeAgents = agents.filter(a => !a.archived && a.status !== 'completed');

  const elapsed = (i + 1) * 5;
  console.log(`[${elapsed}s] DAG: ${s.complete}/${dagNow.feature_count} complete, ${s.in_progress} building, ${dagNow.ready_features.length} ready | Agents: ${activeAgents.length} active`);

  for (const a of activeAgents) {
    console.log(`  → ${a.name} [${a.status}] cost=$${(a.total_cost || 0).toFixed(3)}`);
  }

  // If something completed, stop early
  if (s.complete > dagData.summary.complete) {
    console.log(`\n🎉 Feature completed! ${s.complete}/${dagNow.feature_count}`);
    break;
  }

  // If all agents gone and nothing progressed, flag it
  if (activeAgents.length === 0 && s.in_progress === 0 && elapsed > 30) {
    console.log('\n⚠️ No agents running and no features in progress — pipeline stalled');

    // Check if features moved to in_progress but agents are gone
    if (s.in_progress > 0 || s.complete > dagData.summary.complete) {
      console.log('Features did move — checking DB...');
    }
    break;
  }
}

// Final state
const dagFinal = await fetch(`${API}/api/projects/${PROJECT_ID}/dag`);
const dagFinalData = await dagFinal.json();
console.log(`\n=== Final state ===`);
console.log(`Complete: ${dagFinalData.summary.complete}/${dagFinalData.feature_count}`);
console.log(`In progress: ${dagFinalData.summary.in_progress}`);
console.log(`Planned: ${dagFinalData.summary.planned}`);
