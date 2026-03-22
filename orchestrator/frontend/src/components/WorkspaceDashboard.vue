<template>
  <div class="workspace-dashboard">
    <!-- Dashboard Header -->
    <div class="dashboard-header">
      <div class="header-left">
        <h2 class="dashboard-title">
          {{ workspaceStore.activeWorkspace?.name ?? 'Workspace' }}
        </h2>
        <span class="dashboard-subtitle" v-if="workspaceStore.activeWorkspace?.description">
          {{ workspaceStore.activeWorkspace.description }}
        </span>
      </div>
      <div class="header-actions">
        <button class="btn-action" @click="$emit('onboard-project')">
          + New Project
        </button>
        <button class="btn-action btn-secondary" @click="$emit('refresh')">
          Refresh
        </button>
      </div>
    </div>

    <!-- Summary Stats -->
    <div class="stats-row">
      <div class="stat-card">
        <span class="stat-number">{{ workspaceStore.projectCount }}</span>
        <span class="stat-desc">Total Projects</span>
      </div>
      <div class="stat-card" v-for="(count, phase) in phaseStats" :key="phase">
        <span class="stat-number" :class="'phase-num-' + phase">{{ count }}</span>
        <span class="stat-desc">{{ formatPhase(phase as string) }}</span>
      </div>
    </div>

    <!-- Archetype breakdown -->
    <div class="archetype-row" v-if="Object.keys(archetypeStats).length > 0">
      <span
        v-for="(count, archetype) in archetypeStats"
        :key="archetype"
        class="archetype-chip"
        :class="archetypeClass(archetype as string)"
      >
        {{ archetype }}: {{ count }}
      </span>
    </div>

    <!-- Project Grid -->
    <div class="project-grid">
      <ProjectCard
        v-for="project in workspaceStore.projects"
        :key="project.id"
        :project="project"
        :is-selected="project.id === workspaceStore.activeProjectId"
        @select="onSelectProject"
      />

      <div v-if="workspaceStore.projects.length === 0" class="empty-state">
        <div class="empty-icon">&#9744;</div>
        <div class="empty-text">No projects yet</div>
        <button class="btn-action" @click="$emit('onboard-project')">
          Onboard your first project
        </button>
      </div>
    </div>

    <!-- Loading overlay -->
    <div v-if="workspaceStore.isLoading" class="loading-overlay">
      <span class="loading-spinner"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '../stores/workspaceStore'
import ProjectCard from './ProjectCard.vue'

const workspaceStore = useWorkspaceStore()

const emit = defineEmits<{
  'onboard-project': []
  'refresh': []
  'select-project': [projectId: string]
}>()

/** Count projects by current_phase */
const phaseStats = computed(() => {
  const counts: Record<string, number> = {}
  for (const p of workspaceStore.projects) {
    const phase = p.current_phase || 'not_started'
    counts[phase] = (counts[phase] || 0) + 1
  }
  return counts
})

/** Count projects by archetype */
const archetypeStats = computed(() => {
  const counts: Record<string, number> = {}
  for (const p of workspaceStore.projects) {
    const arch = p.archetype || 'unknown'
    counts[arch] = (counts[arch] || 0) + 1
  }
  return counts
})

function onSelectProject(projectId: string) {
  workspaceStore.switchProject(projectId)
  emit('select-project', projectId)
}

function formatPhase(phase: string): string {
  if (!phase) return 'Unknown'
  return phase.charAt(0).toUpperCase() + phase.slice(1).replace(/_/g, ' ')
}

function archetypeClass(archetype: string): string {
  const normalized = (archetype || '').toLowerCase().replace(/[^a-z0-9]/g, '-')
  return `chip-${normalized}`
}
</script>

<style scoped>
.workspace-dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0d1117;
  color: #c9d1d9;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  overflow-y: auto;
  position: relative;
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 20px;
  border-bottom: 1px solid #21262d;
  gap: 12px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dashboard-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #e6edf3;
}

.dashboard-subtitle {
  font-size: 11px;
  color: #8b949e;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn-action {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #30363d;
  background: #21262d;
  color: #c9d1d9;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn-action:hover {
  background: #30363d;
  border-color: #58a6ff;
  color: #e6edf3;
}

.btn-secondary {
  background: transparent;
  border-color: #21262d;
  color: #8b949e;
}

.btn-secondary:hover {
  background: #161b22;
  color: #c9d1d9;
}

/* Stats Row */
.stats-row {
  display: flex;
  gap: 10px;
  padding: 14px 20px;
  border-bottom: 1px solid #21262d;
  overflow-x: auto;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 14px;
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  min-width: 70px;
}

.stat-number {
  font-size: 18px;
  font-weight: 700;
  color: #e6edf3;
}

.stat-desc {
  font-size: 9px;
  color: #8b949e;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.phase-num-research { color: #bc8cff; }
.phase-num-analysis { color: #79c0ff; }
.phase-num-plan { color: #e3b341; }
.phase-num-implement { color: #58a6ff; }
.phase-num-deploy { color: #f78166; }
.phase-num-sustain { color: #56d364; }

/* Archetype Row */
.archetype-row {
  display: flex;
  gap: 6px;
  padding: 8px 20px;
  border-bottom: 1px solid #21262d;
  flex-wrap: wrap;
}

.archetype-chip {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.chip-web-app,
.chip-webapp { background: #1f3a5f; color: #58a6ff; }

.chip-api,
.chip-rest-api { background: #2a1f3f; color: #bc8cff; }

.chip-cli { background: #1f3f2a; color: #56d364; }

.chip-library,
.chip-lib { background: #3f3a1f; color: #e3b341; }

.chip-data-pipeline,
.chip-pipeline { background: #3f1f2a; color: #f78166; }

/* Project Grid */
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  padding: 16px 20px;
}

/* Empty State */
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 40px 20px;
  color: #484f58;
}

.empty-icon {
  font-size: 32px;
  opacity: 0.4;
}

.empty-text {
  font-size: 13px;
  font-style: italic;
}

/* Loading Overlay */
.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(13, 17, 23, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #30363d;
  border-top-color: #58a6ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
