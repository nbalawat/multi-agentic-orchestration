<template>
  <div class="flow-card" :class="[`stage-${feature.stage}`, { 'on-critical-path': feature.isOnCriticalPath }]">
    <div class="card-header">
      <span class="feature-name" :title="feature.name">{{ feature.name }}</span>
      <span class="wave-badge">W{{ feature.waveNumber }}</span>
    </div>

    <div class="card-meta">
      <span v-if="feature.assignedAgent" class="agent-badge" :class="{ pulsing: feature.stage === 'building' }">
        <span class="agent-dot"></span>
        {{ feature.assignedAgent }}
      </span>
      <span class="priority-badge" :class="`p${Math.min(feature.priority, 3)}`">P{{ feature.priority }}</span>
    </div>

    <div class="card-footer">
      <span class="dep-indicator" v-if="feature.totalDeps > 0">
        <span class="dep-fill" :style="{ width: depPct + '%' }"></span>
        {{ feature.satisfiedDeps }}/{{ feature.totalDeps }} deps
      </span>
      <span v-else class="dep-indicator no-deps">no deps</span>
      <span class="elapsed" v-if="elapsed">{{ elapsed }}</span>
    </div>

    <div v-if="feature.mergeStatus === 'failed'" class="merge-error">merge conflict</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FlowFeature } from '../stores/implementFlowStore'
import { useElapsedTime } from '../composables/useElapsedTime'

const props = defineProps<{ feature: FlowFeature }>()
const { formatElapsed } = useElapsedTime()

const elapsed = computed(() => {
  if (props.feature.stage === 'done' || props.feature.stage === 'queued') return ''
  return formatElapsed(props.feature.stageEnteredAt)
})

const depPct = computed(() =>
  props.feature.totalDeps > 0
    ? Math.round((props.feature.satisfiedDeps / props.feature.totalDeps) * 100)
    : 0
)
</script>

<style scoped>
.flow-card {
  padding: 8px 10px;
  border-radius: 6px;
  background: #161b22;
  border: 1px solid #21262d;
  border-left: 3px solid #8b949e;
  font-size: 11px;
  transition: border-color 0.3s, background 0.3s;
}
.flow-card:hover { background: #1c2333; }

.stage-queued { border-left-color: #8b949e; }
.stage-ready { border-left-color: #e3b341; }
.stage-building { border-left-color: #58a6ff; }
.stage-merging { border-left-color: #bc8cff; }
.stage-done { border-left-color: #86BC24; opacity: 0.8; }
.stage-blocked { border-left-color: #f85149; }
.on-critical-path { box-shadow: 0 0 0 1px rgba(134, 188, 36, 0.3); }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.feature-name {
  font-weight: 500;
  color: #e6edf3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.wave-badge {
  font-size: 9px;
  font-weight: 700;
  color: #8b949e;
  background: #21262d;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.agent-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: #58a6ff;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #58a6ff;
  flex-shrink: 0;
}

.pulsing .agent-dot {
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.4); }
}

.priority-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
}
.p1 { background: rgba(248, 81, 73, 0.2); color: #f85149; }
.p2 { background: rgba(227, 179, 65, 0.2); color: #e3b341; }
.p3 { background: rgba(139, 148, 158, 0.2); color: #8b949e; }

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dep-indicator {
  position: relative;
  font-size: 9px;
  color: #8b949e;
  background: #21262d;
  padding: 1px 6px;
  border-radius: 3px;
  overflow: hidden;
}

.dep-fill {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  background: rgba(134, 188, 36, 0.15);
  border-radius: 3px;
  transition: width 0.3s;
}

.no-deps { color: #484f58; }

.elapsed {
  font-size: 9px;
  color: #8b949e;
  font-variant-numeric: tabular-nums;
}

.merge-error {
  margin-top: 4px;
  font-size: 9px;
  color: #f85149;
  font-weight: 600;
}
</style>
