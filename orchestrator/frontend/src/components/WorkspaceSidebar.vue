<template>
  <div class="workspace-sidebar">
    <!-- Workspace Selector -->
    <div class="sidebar-section workspace-selector">
      <label class="section-label">WORKSPACE</label>
      <select
        class="workspace-dropdown"
        :value="workspaceStore.activeWorkspaceId"
        @change="onWorkspaceChange"
        :disabled="workspaceStore.isLoading"
      >
        <option value="" disabled>Select workspace...</option>
        <option
          v-for="ws in workspaceStore.workspaces"
          :key="ws.id"
          :value="ws.id"
        >
          {{ ws.name }}
        </option>
      </select>
    </div>

    <!-- Projects Section -->
    <div class="sidebar-section projects-section">
      <div class="section-header">
        <span class="section-label">PROJECTS</span>
        <span class="section-count">{{ workspaceStore.projectCount }}</span>
      </div>

      <div class="project-list">
        <div
          v-for="project in workspaceStore.projects"
          :key="project.id"
          class="project-item"
          :class="{ active: project.id === workspaceStore.activeProjectId }"
          @click="onSelectProject(project.id)"
        >
          <div class="project-item-header">
            <span class="project-name">{{ project.name }}</span>
            <span class="archetype-badge" :class="archetypeClass(project.archetype)">
              {{ project.archetype }}
            </span>
          </div>
          <div class="project-item-meta">
            <span class="phase-indicator" :class="phaseStatusClass(project.phase_status)">
              {{ formatPhase(project.current_phase) }}
            </span>
            <span class="priority-label" v-if="project.priority">
              P{{ project.priority }}
            </span>
          </div>
        </div>

        <div v-if="workspaceStore.projects.length === 0" class="empty-state">
          No projects in this workspace
        </div>
      </div>

      <button class="btn-onboard" @click="$emit('onboard-project')">
        + Onboard Project
      </button>
    </div>

    <!-- Agents Section (collapsible, wraps AgentList) -->
    <div class="sidebar-section agents-section">
      <div class="section-header clickable" @click="toggleAgents">
        <span class="section-label">AGENTS</span>
        <span class="collapse-chevron">{{ isAgentsExpanded ? '▾' : '▸' }}</span>
      </div>
      <div v-show="isAgentsExpanded" class="agents-wrapper">
        <slot name="agent-list">
          <!-- Parent should pass AgentList here -->
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspaceStore'

const workspaceStore = useWorkspaceStore()

const emit = defineEmits<{
  'onboard-project': []
  'select-project': [projectId: string]
}>()

const isAgentsExpanded = ref(true)

function toggleAgents() {
  isAgentsExpanded.value = !isAgentsExpanded.value
}

function onWorkspaceChange(event: Event) {
  const target = event.target as HTMLSelectElement
  if (target.value) {
    workspaceStore.setActiveWorkspace(target.value)
  }
}

function onSelectProject(projectId: string) {
  workspaceStore.switchProject(projectId)
  emit('select-project', projectId)
}

function archetypeClass(archetype: string): string {
  const normalized = (archetype || '').toLowerCase().replace(/[^a-z0-9]/g, '-')
  return `archetype-${normalized}`
}

function phaseStatusClass(status: string): string {
  switch (status) {
    case 'in_progress': return 'status-active'
    case 'completed': return 'status-complete'
    case 'blocked': return 'status-blocked'
    default: return 'status-pending'
  }
}

function formatPhase(phase: string): string {
  if (!phase) return 'Not Started'
  return phase.charAt(0).toUpperCase() + phase.slice(1).replace(/_/g, ' ')
}
</script>

<style scoped>
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0d1117;
  border-right: 1px solid #21262d;
  overflow-y: auto;
  color: #c9d1d9;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
}

/* Sections */
.sidebar-section {
  padding: 12px;
  border-bottom: 1px solid #21262d;
}

.section-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.2px;
  color: #8b949e;
  text-transform: uppercase;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.section-header.clickable {
  cursor: pointer;
  user-select: none;
}

.section-header.clickable:hover .section-label {
  color: #c9d1d9;
}

.section-count {
  font-size: 10px;
  color: #8b949e;
  background: #21262d;
  padding: 1px 6px;
  border-radius: 8px;
}

.collapse-chevron {
  font-size: 11px;
  color: #8b949e;
}

/* Workspace Dropdown */
.workspace-dropdown {
  width: 100%;
  margin-top: 6px;
  padding: 6px 8px;
  background: #161b22;
  color: #c9d1d9;
  border: 1px solid #30363d;
  border-radius: 6px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  outline: none;
}

.workspace-dropdown:hover {
  border-color: #58a6ff;
}

.workspace-dropdown:focus {
  border-color: #58a6ff;
  box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.15);
}

/* Project List */
.project-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.project-item {
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.project-item:hover {
  background: #161b22;
  border-color: #30363d;
}

.project-item.active {
  background: #1c2333;
  border-color: #58a6ff;
}

.project-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.project-name {
  font-size: 12px;
  font-weight: 500;
  color: #e6edf3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

/* Archetype Badges */
.archetype-badge {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.5px;
  padding: 1px 5px;
  border-radius: 4px;
  text-transform: uppercase;
  white-space: nowrap;
  flex-shrink: 0;
}

.archetype-web-app,
.archetype-webapp { background: #1f3a5f; color: #58a6ff; }

.archetype-api,
.archetype-rest-api { background: #2a1f3f; color: #bc8cff; }

.archetype-cli { background: #1f3f2a; color: #56d364; }

.archetype-library,
.archetype-lib { background: #3f3a1f; color: #e3b341; }

.archetype-data-pipeline,
.archetype-pipeline { background: #3f1f2a; color: #f78166; }

/* Fallback */
.archetype-badge:not([class*="archetype-"]) {
  background: #21262d;
  color: #8b949e;
}

/* Phase Indicator */
.phase-indicator {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
}

.status-pending { color: #8b949e; }
.status-active { color: #58a6ff; }
.status-complete { color: #56d364; }
.status-blocked { color: #f85149; }

.priority-label {
  font-size: 9px;
  color: #8b949e;
  font-weight: 600;
}

/* Empty State */
.empty-state {
  padding: 16px 8px;
  text-align: center;
  color: #484f58;
  font-style: italic;
}

/* Onboard Button */
.btn-onboard {
  width: 100%;
  margin-top: 8px;
  padding: 6px 10px;
  background: transparent;
  color: #58a6ff;
  border: 1px dashed #30363d;
  border-radius: 6px;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn-onboard:hover {
  background: #161b22;
  border-color: #58a6ff;
}

/* Agents Wrapper */
.agents-wrapper {
  margin-top: 4px;
}

.agents-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
