<template>
  <div class="flow-progress-header">
    <div class="progress-title">
      <span class="title-text">IMPLEMENTATION FLOW</span>
      <span v-if="dagComplete" class="complete-badge">ALL COMPLETE</span>
    </div>
    <div class="progress-stats">
      <span class="stat">{{ progress.completed }}/{{ progress.total }} features</span>
      <span class="stat-sep">|</span>
      <span class="stat">Wave {{ progress.currentWave }}</span>
      <span class="stat-sep">|</span>
      <span class="stat">{{ progress.inProgress }} building</span>
    </div>
    <div class="progress-bar-track">
      <div
        class="progress-bar-fill"
        :style="{ width: progress.completionPct + '%' }"
        :class="{ complete: dagComplete }"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FlowProgress } from '../stores/implementFlowStore'

defineProps<{
  progress: FlowProgress
  dagComplete: boolean
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
