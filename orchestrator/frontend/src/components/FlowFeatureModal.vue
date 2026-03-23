<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="stage-dot" :class="`stage-${feature.stage}`"></span>
            <h3 class="modal-title">{{ feature.name }}</h3>
            <span class="stage-badge" :class="`stage-${feature.stage}`">{{ feature.stage.toUpperCase() }}</span>
          </div>
          <button class="modal-close" @click="$emit('close')">&times;</button>
        </div>

        <div class="modal-body">
          <!-- Status Row -->
          <div class="detail-section">
            <div class="detail-grid">
              <div class="detail-item">
                <span class="detail-label">Priority</span>
                <span class="detail-value priority" :class="`p${Math.min(feature.priority, 3)}`">P{{ feature.priority }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Wave</span>
                <span class="detail-value">{{ feature.waveNumber }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Dependencies</span>
                <span class="detail-value">{{ feature.satisfiedDeps }}/{{ feature.totalDeps }} satisfied</span>
              </div>
              <div class="detail-item" v-if="feature.assignedAgent">
                <span class="detail-label">Agent</span>
                <span class="detail-value agent">{{ feature.assignedAgent }}</span>
              </div>
            </div>
          </div>

          <!-- Dependencies -->
          <div class="detail-section" v-if="feature.dependsOn.length > 0">
            <h4 class="section-title">Dependencies</h4>
            <div class="dep-list">
              <div
                v-for="depId in feature.dependsOn"
                :key="depId"
                class="dep-item"
                :class="{ satisfied: isDependencySatisfied(depId) }"
              >
                <span class="dep-icon">{{ isDependencySatisfied(depId) ? '✓' : '○' }}</span>
                <span class="dep-name">{{ getDependencyName(depId) }}</span>
                <span class="dep-status">{{ getDependencyStatus(depId) }}</span>
              </div>
            </div>
          </div>

          <!-- Unlocks -->
          <div class="detail-section" v-if="dependents.length > 0">
            <h4 class="section-title">Unlocks</h4>
            <div class="dep-list">
              <div v-for="dep in dependents" :key="dep.id" class="dep-item">
                <span class="dep-icon">→</span>
                <span class="dep-name">{{ dep.name }}</span>
                <span class="dep-status">{{ dep.stage }}</span>
              </div>
            </div>
          </div>

          <!-- Timing -->
          <div class="detail-section" v-if="feature.startedAt || feature.completedAt">
            <h4 class="section-title">Timing</h4>
            <div class="detail-grid">
              <div class="detail-item" v-if="feature.startedAt">
                <span class="detail-label">Started</span>
                <span class="detail-value">{{ formatTime(feature.startedAt) }}</span>
              </div>
              <div class="detail-item" v-if="feature.completedAt">
                <span class="detail-label">Completed</span>
                <span class="detail-value">{{ formatTime(feature.completedAt) }}</span>
              </div>
              <div class="detail-item" v-if="feature.startedAt && feature.completedAt">
                <span class="detail-label">Duration</span>
                <span class="detail-value">{{ formatDuration(feature.startedAt, feature.completedAt) }}</span>
              </div>
            </div>
          </div>

          <!-- Merge Status -->
          <div class="detail-section" v-if="feature.mergeStatus">
            <h4 class="section-title">Merge</h4>
            <div class="merge-badge" :class="feature.mergeStatus">
              {{ feature.mergeStatus === 'success' ? '✓ Merged to main' : '✗ Merge failed' }}
            </div>
          </div>

          <!-- ID -->
          <div class="detail-section">
            <div class="detail-item">
              <span class="detail-label">Feature ID</span>
              <span class="detail-value mono">{{ feature.id }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FlowFeature } from '../stores/implementFlowStore'
import { useImplementFlowStore } from '../stores/implementFlowStore'

const props = defineProps<{
  feature: FlowFeature
  visible: boolean
}>()

defineEmits<{ close: [] }>()

const flowStore = useImplementFlowStore()

function isDependencySatisfied(depId: string): boolean {
  const dep = flowStore.features[depId]
  return dep?.stage === 'done'
}

function getDependencyName(depId: string): string {
  const dep = flowStore.features[depId]
  return dep?.name || depId.substring(0, 8)
}

function getDependencyStatus(depId: string): string {
  const dep = flowStore.features[depId]
  return dep?.stage || 'unknown'
}

const dependents = computed(() => {
  return Object.values(flowStore.features).filter(
    f => f.dependsOn.includes(props.feature.id)
  )
})

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  width: 480px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 20px;
  border-bottom: 1px solid #21262d;
}

.modal-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.stage-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.stage-dot.stage-queued { background: #8b949e; }
.stage-dot.stage-ready { background: #e3b341; }
.stage-dot.stage-building { background: #58a6ff; }
.stage-dot.stage-merging { background: #bc8cff; }
.stage-dot.stage-done { background: #86BC24; }
.stage-dot.stage-blocked { background: #f85149; }

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: #e6edf3;
  margin: 0;
}

.stage-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}
.stage-badge.stage-queued { background: rgba(139, 148, 158, 0.15); color: #8b949e; }
.stage-badge.stage-ready { background: rgba(227, 179, 65, 0.15); color: #e3b341; }
.stage-badge.stage-building { background: rgba(88, 166, 255, 0.15); color: #58a6ff; }
.stage-badge.stage-merging { background: rgba(188, 140, 255, 0.15); color: #bc8cff; }
.stage-badge.stage-done { background: rgba(134, 188, 36, 0.15); color: #86BC24; }
.stage-badge.stage-blocked { background: rgba(248, 81, 73, 0.15); color: #f85149; }

.modal-close {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 24px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.modal-close:hover { color: #e6edf3; }

.modal-body {
  padding: 16px 20px;
}

.detail-section {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #21262d;
}
.detail-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  color: #8b949e;
  text-transform: uppercase;
  margin: 0 0 8px 0;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 10px;
  color: #8b949e;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-value {
  font-size: 13px;
  color: #e6edf3;
}
.detail-value.agent { color: #58a6ff; }
.detail-value.mono {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
  color: #8b949e;
}

.priority.p1 { color: #f85149; }
.priority.p2 { color: #e3b341; }
.priority.p3 { color: #8b949e; }

.dep-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dep-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: #0d1117;
  font-size: 12px;
}
.dep-item.satisfied { opacity: 0.7; }

.dep-icon {
  font-size: 12px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}
.dep-item.satisfied .dep-icon { color: #86BC24; }

.dep-name {
  flex: 1;
  color: #c9d1d9;
}

.dep-status {
  font-size: 10px;
  color: #8b949e;
  text-transform: uppercase;
}

.merge-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
.merge-badge.success {
  background: rgba(134, 188, 36, 0.15);
  color: #86BC24;
  border: 1px solid rgba(134, 188, 36, 0.3);
}
.merge-badge.failed {
  background: rgba(248, 81, 73, 0.15);
  color: #f85149;
  border: 1px solid rgba(248, 81, 73, 0.3);
}
</style>
