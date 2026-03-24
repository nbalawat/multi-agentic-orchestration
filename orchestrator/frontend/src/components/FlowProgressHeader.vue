<template>
  <div class="flow-progress-header">
    <div class="progress-title">
      <span class="title-text">IMPLEMENTATION FLOW</span>
      <span v-if="projectName" class="project-name-badge">{{ projectName }}</span>
      <span v-if="dagComplete" class="complete-badge">ALL COMPLETE</span>
    </div>
    <div class="progress-stats">
      <span class="stat">{{ progress.complete }}/{{ progress.total }} features</span>
      <span class="stat-sep">|</span>
      <span class="stat">{{ progress.in_progress }} building</span>
      <span class="stat-sep" v-if="totalCost > 0">|</span>
      <span class="stat cost" v-if="totalCost > 0">${{ totalCost.toFixed(3) }}</span>
    </div>
    <div class="progress-bar-track">
      <div
        class="progress-bar-fill"
        :style="{ width: progress.completion_pct + '%' }"
        :class="{ complete: dagComplete }"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DagSummary } from '../stores/implementFlowStore'

defineProps<{
  progress: DagSummary
  dagComplete: boolean
  totalCost?: number
  projectName?: string
}>()
</script>

<style scoped>
.flow-progress-header {
  padding: 10px 14px;
  background: #0d1117;
  border-bottom: 1px solid #21262d;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.title-text {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #8b949e;
}

.project-name-badge {
  font-size: 11px;
  font-weight: 600;
  color: #22d3ee;
  background: rgba(34, 211, 238, 0.1);
  padding: 1px 8px;
  border-radius: 4px;
  border: 1px solid rgba(34, 211, 238, 0.2);
}

.complete-badge {
  font-size: 9px;
  font-weight: 700;
  color: #86BC24;
  background: rgba(134, 188, 36, 0.15);
  border: 1px solid rgba(134, 188, 36, 0.3);
  padding: 1px 8px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

.progress-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  color: #c9d1d9;
}

.stat-sep { color: #484f58; }
.stat.cost { color: #e3b341; }

.progress-bar-track {
  height: 4px;
  background: #21262d;
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #86BC24, #22c55e);
  border-radius: 2px;
  transition: width 0.5s ease;
}

.progress-bar-fill.complete {
  background: #86BC24;
}
</style>
