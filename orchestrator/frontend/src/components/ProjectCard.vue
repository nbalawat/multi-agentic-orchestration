<template>
  <div
    class="project-card"
    :class="{ selected: isSelected }"
    @click="$emit('select', project.id)"
  >
    <!-- Header row: name + archetype -->
    <div class="card-header">
      <h4 class="card-title">{{ project.name }}</h4>
      <span class="archetype-badge" :class="archetypeClass">
        {{ project.archetype }}
      </span>
    </div>

    <!-- Phase + status row -->
    <div class="card-phase">
      <span class="phase-name">{{ formatPhase(project.current_phase) }}</span>
      <span class="phase-status-dot" :class="statusClass"></span>
      <span class="phase-status-text" :class="statusClass">
        {{ formatStatus(project.phase_status) }}
      </span>
    </div>

    <!-- Repo path -->
    <div class="card-repo" :title="project.repo_path">
      {{ truncatedPath }}
    </div>

    <!-- Feature progress bar (only during implement phase) -->
    <div v-if="showFeatureProgress" class="feature-progress">
      <div class="progress-header">
        <span class="progress-label">Features</span>
        <span class="progress-value">{{ completedFeatures }}/{{ totalFeatures }}</span>
      </div>
      <div class="progress-bar-track">
        <div
          class="progress-bar-fill"
          :style="{ width: featureProgressPct + '%' }"
        ></div>
      </div>
    </div>

    <!-- Priority indicator -->
    <div v-if="project.priority" class="card-priority">
      P{{ project.priority }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { type Project } from '../stores/workspaceStore'
import { useProjectStore } from '../stores/projectStore'

const props = defineProps<{
  project: Project
  isSelected?: boolean
}>()

defineEmits<{
  select: [projectId: string]
}>()

const projectStore = useProjectStore()

const archetypeClass = computed(() => {
  const normalized = (props.project.archetype || '').toLowerCase().replace(/[^a-z0-9]/g, '-')
  return `archetype-${normalized}`
})

const statusClass = computed(() => {
  switch (props.project.phase_status) {
    case 'in_progress': return 'status-active'
    case 'completed': return 'status-complete'
    case 'blocked': return 'status-blocked'
    default: return 'status-pending'
  }
})

const truncatedPath = computed(() => {
  const path = props.project.repo_path || ''
  if (path.length <= 40) return path
  return '...' + path.slice(-37)
})

const showFeatureProgress = computed(() =>
  props.project.current_phase === 'implement'
)

const totalFeatures = computed(() => projectStore.features.length)
const completedFeatures = computed(() =>
  projectStore.features.filter(f => f.status === 'completed').length
)
const featureProgressPct = computed(() => {
  if (totalFeatures.value === 0) return 0
  return Math.round((completedFeatures.value / totalFeatures.value) * 100)
})

function formatPhase(phase: string): string {
  if (!phase) return 'Not Started'
  return phase.charAt(0).toUpperCase() + phase.slice(1).replace(/_/g, ' ')
}

function formatStatus(status: string): string {
  if (!status) return 'Pending'
  return status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
</script>

<style scoped>
.project-card {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: #c9d1d9;
  position: relative;
}

.project-card:hover {
  border-color: #30363d;
  background: #1c2128;
}

.project-card.selected {
  border-color: #58a6ff;
  background: #1c2333;
  box-shadow: 0 0 0 1px rgba(88, 166, 255, 0.15);
}

/* Header */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.card-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Archetype Badge */
.archetype-badge {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.5px;
  padding: 2px 6px;
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

/* Phase Row */
.card-phase {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.phase-name {
  font-size: 11px;
  font-weight: 500;
  color: #c9d1d9;
}

.phase-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.phase-status-dot.status-pending { background: #484f58; }
.phase-status-dot.status-active { background: #58a6ff; }
.phase-status-dot.status-complete { background: #56d364; }
.phase-status-dot.status-blocked { background: #f85149; }

.phase-status-text {
  font-size: 10px;
}

.phase-status-text.status-pending { color: #484f58; }
.phase-status-text.status-active { color: #58a6ff; }
.phase-status-text.status-complete { color: #56d364; }
.phase-status-text.status-blocked { color: #f85149; }

/* Repo Path */
.card-repo {
  font-size: 10px;
  color: #484f58;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Feature Progress */
.feature-progress {
  margin-top: 4px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}

.progress-label {
  font-size: 10px;
  color: #8b949e;
}

.progress-value {
  font-size: 10px;
  color: #8b949e;
  font-weight: 600;
}

.progress-bar-track {
  width: 100%;
  height: 4px;
  background: #21262d;
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: #58a6ff;
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* Priority */
.card-priority {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 9px;
  font-weight: 700;
  color: #8b949e;
  background: #21262d;
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
