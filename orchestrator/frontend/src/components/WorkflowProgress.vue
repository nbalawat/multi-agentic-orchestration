<template>
  <div class="workflow-progress">
    <!-- Header with overall progress -->
    <div class="progress-header">
      <h3 class="progress-title">Workflow Progress</h3>
      <div class="overall-progress">
        <div class="overall-bar-track">
          <div
            class="overall-bar-fill"
            :style="{ width: projectStore.overallProgress + '%' }"
          ></div>
        </div>
        <span class="overall-pct">{{ projectStore.overallProgress }}%</span>
      </div>
    </div>

    <!-- Phase / Section list -->
    <div class="section-list">
      <div
        v-for="section in sections"
        :key="section.phase"
        class="section-item"
        :class="{
          'section-current': section.isCurrent,
          'section-complete': section.status === 'completed',
          'section-pending': section.status === 'pending' || section.status === 'not_started'
        }"
      >
        <!-- Status indicator -->
        <div class="section-status-icon" :class="'icon-' + section.status">
          <span v-if="section.status === 'completed'">&#10003;</span>
          <span v-else-if="section.status === 'in_progress'" class="active-dot"></span>
          <span v-else>&#9675;</span>
        </div>

        <!-- Section content -->
        <div class="section-content">
          <div class="section-name-row">
            <span class="section-name">{{ section.label }}</span>
            <span class="section-progress-value" v-if="section.progressPct > 0">
              {{ section.progressPct }}%
            </span>
          </div>

          <!-- Per-section progress bar -->
          <div v-if="section.isCurrent || section.status === 'in_progress'" class="section-bar-track">
            <div
              class="section-bar-fill"
              :style="{ width: section.progressPct + '%' }"
            ></div>
          </div>

          <!-- Guide text for the current section -->
          <div v-if="section.isCurrent" class="section-guide">
            {{ section.guideText }}
          </div>
        </div>
      </div>
    </div>

    <!-- Estimated completion -->
    <div
      v-if="projectStore.workflowProgress?.estimated_completion"
      class="estimated-completion"
    >
      Estimated completion: {{ formatDate(projectStore.workflowProgress.estimated_completion) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useProjectStore } from '../stores/projectStore'
import { useWorkspaceStore } from '../stores/workspaceStore'

const projectStore = useProjectStore()
const workspaceStore = useWorkspaceStore()

interface SectionEntry {
  phase: string
  label: string
  status: string
  isCurrent: boolean
  progressPct: number
  guideText: string
}

const PHASE_GUIDES: Record<string, string> = {
  research: 'Analyze the codebase, dependencies, and existing patterns. Gather context for decision-making.',
  analysis: 'Identify requirements, constraints, and architectural decisions. Document findings.',
  plan: 'Create feature specifications, define the DAG, and establish implementation order.',
  implement: 'Execute feature implementations following the dependency DAG. Track progress per feature.',
  deploy: 'Run tests, build artifacts, and deploy to target environments.',
  sustain: 'Monitor, maintain, and iterate. Address technical debt and operational improvements.'
}

const RAPIDS_PHASES = [
  { key: 'research', label: 'Research' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'plan', label: 'Plan' },
  { key: 'implement', label: 'Implement' },
  { key: 'deploy', label: 'Deploy' },
  { key: 'sustain', label: 'Sustain' }
]

const sections = computed((): SectionEntry[] => {
  const currentPhase = workspaceStore.activeProject?.current_phase ?? ''
  const phaseProgress = projectStore.workflowProgress?.phase_progress ?? {}

  return RAPIDS_PHASES.map(rp => {
    const storePhase = projectStore.phases.find(p => p.phase === rp.key)
    const status = storePhase?.status ?? 'not_started'
    const isCurrent = rp.key === currentPhase

    return {
      phase: rp.key,
      label: rp.label,
      status,
      isCurrent,
      progressPct: Math.round(phaseProgress[rp.key] ?? 0),
      guideText: PHASE_GUIDES[rp.key] ?? ''
    }
  })
})

function formatDate(isoString: string): string {
  try {
    const d = new Date(isoString)
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    })
  } catch {
    return isoString
  }
}
</script>

<style scoped>
.workflow-progress {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 8px;
  color: #c9d1d9;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  overflow: hidden;
}

/* Header */
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid #21262d;
  gap: 12px;
}

.progress-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  white-space: nowrap;
}

.overall-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 200px;
}

.overall-bar-track {
  flex: 1;
  height: 6px;
  background: #21262d;
  border-radius: 3px;
  overflow: hidden;
}

.overall-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #58a6ff, #56d364);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.overall-pct {
  font-size: 12px;
  font-weight: 700;
  color: #58a6ff;
  min-width: 32px;
  text-align: right;
}

/* Section List */
.section-list {
  padding: 8px 0;
}

.section-item {
  display: flex;
  gap: 10px;
  padding: 8px 14px;
  transition: background 0.1s;
}

.section-item:hover {
  background: #161b22;
}

.section-item.section-current {
  background: #1c2333;
  border-left: 3px solid #58a6ff;
  padding-left: 11px;
}

/* Status Icon */
.section-status-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
  margin-top: 1px;
}

.icon-completed {
  background: #1a3a2a;
  color: #56d364;
  border: 1px solid #56d364;
  font-weight: 700;
}

.icon-in_progress {
  background: #1f3a5f;
  color: #58a6ff;
  border: 1px solid #58a6ff;
}

.icon-pending,
.icon-not_started {
  background: #21262d;
  color: #484f58;
  border: 1px solid #30363d;
}

.active-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #58a6ff;
  animation: wf-pulse 1.5s ease-in-out infinite;
}

@keyframes wf-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Section Content */
.section-content {
  flex: 1;
  min-width: 0;
}

.section-name-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
}

.section-name {
  font-size: 12px;
  font-weight: 500;
  color: #c9d1d9;
}

.section-current .section-name {
  color: #58a6ff;
  font-weight: 600;
}

.section-complete .section-name {
  color: #56d364;
}

.section-pending .section-name {
  color: #484f58;
}

.section-progress-value {
  font-size: 10px;
  color: #8b949e;
  font-weight: 600;
}

/* Section Bar */
.section-bar-track {
  width: 100%;
  height: 3px;
  background: #21262d;
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}

.section-bar-fill {
  height: 100%;
  background: #58a6ff;
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* Guide Text */
.section-guide {
  margin-top: 6px;
  font-size: 10px;
  color: #8b949e;
  line-height: 1.5;
  padding: 6px 8px;
  background: #161b22;
  border-radius: 4px;
  border-left: 2px solid #30363d;
}

/* Estimated Completion */
.estimated-completion {
  padding: 8px 14px;
  border-top: 1px solid #21262d;
  font-size: 10px;
  color: #8b949e;
  text-align: center;
}
</style>
