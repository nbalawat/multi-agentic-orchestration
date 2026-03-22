<template>
  <div v-if="activeProject" class="project-context-bar">
    <div class="context-workspace" v-if="activeWorkspace">
      <span class="ctx-label">Workspace:</span>
      <span class="ctx-value">{{ activeWorkspace.name }}</span>
    </div>
    <div class="context-separator">/</div>
    <div class="context-project">
      <span class="ctx-label">Project:</span>
      <span class="ctx-value ctx-project-name">{{ activeProject.name }}</span>
    </div>
    <div class="context-phase">
      <span class="phase-badge" :class="phaseClass">
        {{ activeProject.current_phase?.toUpperCase() }}
      </span>
    </div>
    <div class="context-archetype" v-if="activeProject.archetype">
      <span class="archetype-badge">{{ activeProject.archetype }}</span>
    </div>
  </div>
  <div v-else class="project-context-bar empty">
    <span class="ctx-empty">No active project — use the orchestrator to switch to a project</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useOrchestratorStore } from '../stores/orchestratorStore'

const store = useOrchestratorStore()

const activeProject = ref<any>(null)
const activeWorkspace = ref<any>(null)

const phaseClass = computed(() => {
  const phase = activeProject.value?.current_phase?.toLowerCase()
  if (!phase) return ''
  const rapPhases = ['research', 'analysis', 'plan']
  const idsPhases = ['implement', 'deploy', 'sustain']
  if (rapPhases.includes(phase)) return `phase-rap phase-${phase}`
  if (idsPhases.includes(phase)) return `phase-ids phase-${phase}`
  return ''
})

async function fetchContext() {
  try {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:9403'
    const resp = await fetch(`${apiBase}/get_headers`)
    const data = await resp.json()
    activeProject.value = data.active_project
    activeWorkspace.value = data.active_workspace
  } catch (e) {
    console.error('Failed to fetch project context:', e)
  }
}

// Poll every 10s and on mount
onMounted(() => {
  fetchContext()
  setInterval(fetchContext, 10000)
})

// Also refresh when store events suggest a project switch
// (WebSocket orchestrator_updated events)
</script>

<style scoped>
.project-context-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background: var(--bg-tertiary, #1a1d23);
  border-bottom: 1px solid var(--border-color, #2d3748);
  font-size: 12px;
  min-height: 28px;
}

.project-context-bar.empty {
  justify-content: center;
}

.ctx-label {
  color: #64748b;
  margin-right: 4px;
}

.ctx-value {
  color: #e2e8f0;
  font-weight: 500;
}

.ctx-project-name {
  color: #22d3ee;
  font-weight: 600;
}

.ctx-empty {
  color: #64748b;
  font-style: italic;
}

.context-separator {
  color: #475569;
  font-weight: 300;
}

.phase-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.phase-rap {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.phase-ids {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.phase-research { background: rgba(168, 85, 247, 0.15); color: #a855f7; border-color: rgba(168, 85, 247, 0.3); }
.phase-analysis { background: rgba(59, 130, 246, 0.15); color: #3b82f6; border-color: rgba(59, 130, 246, 0.3); }
.phase-plan { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3); }
.phase-implement { background: rgba(34, 197, 94, 0.15); color: #22c55e; border-color: rgba(34, 197, 94, 0.3); }
.phase-deploy { background: rgba(6, 182, 212, 0.15); color: #06b6d4; border-color: rgba(6, 182, 212, 0.3); }
.phase-sustain { background: rgba(236, 72, 153, 0.15); color: #ec4899; border-color: rgba(236, 72, 153, 0.3); }

.archetype-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
}
</style>
