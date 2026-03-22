<template>
  <div class="phase-timeline">
    <div class="timeline-track">
      <div
        v-for="(phase, index) in phaseEntries"
        :key="phase.key"
        class="phase-node"
        :class="{
          active: phase.status === 'in_progress',
          complete: phase.status === 'completed',
          blocked: phase.status === 'blocked',
          pending: phase.status === 'not_started' || phase.status === 'pending',
          clickable: true
        }"
        @click="$emit('select-phase', phase.key)"
      >
        <!-- Connector line (not before the first node) -->
        <div v-if="index > 0" class="connector-line" :class="connectorClass(index)">
          <!-- Convergence gate marker between Plan and Implement -->
          <div
            v-if="isConvergenceGate(index)"
            class="convergence-gate"
            title="Convergence Gate"
          >
            <span class="gate-icon">||</span>
          </div>
        </div>

        <!-- Phase indicator circle -->
        <div class="phase-indicator" :class="phase.status">
          <span v-if="phase.status === 'completed'" class="indicator-icon">&#10003;</span>
          <span v-else-if="phase.status === 'blocked'" class="indicator-icon">!</span>
          <span v-else-if="phase.status === 'in_progress'" class="indicator-icon pulse-dot"></span>
          <span v-else class="indicator-icon dim-dot"></span>
        </div>

        <!-- Phase label -->
        <div class="phase-label">{{ phase.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useProjectStore, type Phase } from '../stores/projectStore'

const projectStore = useProjectStore()

defineEmits<{
  'select-phase': [phaseKey: string]
}>()

/** The canonical RAPIDS phase order */
const RAPIDS_PHASES = [
  { key: 'research', label: 'Research' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'plan', label: 'Plan' },
  { key: 'implement', label: 'Implement' },
  { key: 'deploy', label: 'Deploy' },
  { key: 'sustain', label: 'Sustain' }
]

/** Merge store phases with canonical order */
const phaseEntries = computed(() => {
  return RAPIDS_PHASES.map(rp => {
    const storePhase: Phase | undefined = projectStore.phases.find(
      p => p.phase === rp.key
    )
    return {
      key: rp.key,
      label: rp.label,
      status: storePhase?.status ?? 'not_started',
      started_at: storePhase?.started_at ?? null,
      completed_at: storePhase?.completed_at ?? null
    }
  })
})

function connectorClass(index: number): string {
  const prev = phaseEntries.value[index - 1]
  if (prev && prev.status === 'completed') return 'connector-done'
  return 'connector-pending'
}

/** The convergence gate sits between Plan (index 2) and Implement (index 3) */
function isConvergenceGate(index: number): boolean {
  return index === 3
}
</script>

<style scoped>
.phase-timeline {
  width: 100%;
  padding: 16px 12px;
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 8px;
}

.timeline-track {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  position: relative;
}

/* Phase Node */
.phase-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
  cursor: pointer;
}

.phase-node:hover .phase-indicator {
  transform: scale(1.15);
}

/* Connector line */
.connector-line {
  position: absolute;
  top: 14px;
  right: 50%;
  width: 100%;
  height: 2px;
  z-index: 0;
}

.connector-done {
  background: #56d364;
}

.connector-pending {
  background: #30363d;
}

/* Convergence Gate */
.convergence-gate {
  position: absolute;
  top: -8px;
  left: 50%;
  transform: translateX(-50%);
  background: #161b22;
  border: 1px solid #f0883e;
  border-radius: 4px;
  padding: 0 4px;
  z-index: 2;
}

.gate-icon {
  font-size: 10px;
  font-weight: 700;
  color: #f0883e;
  letter-spacing: 1px;
}

/* Phase Indicator */
.phase-indicator {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  transition: transform 0.15s, box-shadow 0.15s;
  font-size: 13px;
}

.phase-indicator.not_started,
.phase-indicator.pending {
  background: #21262d;
  border: 2px solid #30363d;
}

.phase-indicator.in_progress {
  background: #1f3a5f;
  border: 2px solid #58a6ff;
  box-shadow: 0 0 8px rgba(88, 166, 255, 0.4);
}

.phase-indicator.completed {
  background: #1a3a2a;
  border: 2px solid #56d364;
}

.phase-indicator.blocked {
  background: #3f1f1f;
  border: 2px solid #f85149;
}

/* Indicator Icons */
.indicator-icon {
  font-size: 12px;
  line-height: 1;
}

.phase-indicator.completed .indicator-icon {
  color: #56d364;
  font-weight: 700;
}

.phase-indicator.blocked .indicator-icon {
  color: #f85149;
  font-weight: 700;
}

.pulse-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #58a6ff;
  animation: pulse-glow 1.5s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px rgba(88, 166, 255, 0.6); }
  50% { opacity: 0.5; box-shadow: 0 0 12px rgba(88, 166, 255, 0.3); }
}

.dim-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #484f58;
}

/* Phase Label */
.phase-label {
  margin-top: 6px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.5px;
  color: #8b949e;
  text-align: center;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.phase-node.active .phase-label {
  color: #58a6ff;
  font-weight: 600;
}

.phase-node.complete .phase-label {
  color: #56d364;
}

.phase-node.blocked .phase-label {
  color: #f85149;
}
</style>
