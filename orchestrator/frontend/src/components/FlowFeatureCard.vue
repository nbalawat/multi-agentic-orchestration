<template>
  <div class="flow-card" :class="[`stage-${run.status}`]">
    <div class="card-header">
      <span class="feature-name" :title="run.feature_name">{{ run.feature_name }}</span>
      <span class="wave-badge">W{{ run.wave_number }}</span>
    </div>

    <div class="card-meta" v-if="run.agent_name">
      <span class="agent-badge" :class="{ pulsing: run.status === 'building' }">
        <span class="agent-dot"></span>
        {{ run.agent_name }}
      </span>
    </div>

    <div class="card-footer">
      <span class="cost-badge" v-if="run.cost > 0">${{ run.cost.toFixed(3) }}</span>
      <span class="test-badge" v-if="hasTestResults" :class="testClass">
        {{ testLabel }}
      </span>
      <span class="elapsed" v-if="run.started_at && !run.completed_at">{{ elapsed }}</span>
      <span class="elapsed" v-if="run.completed_at">{{ duration }}</span>
    </div>

    <div v-if="run.error_message" class="error-line" :title="run.error_message">{{ run.error_message.substring(0, 60) }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { ExecutionRun } from '../stores/implementFlowStore'

const props = defineProps<{ run: ExecutionRun }>()

// Elapsed time ticker
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => { if (timer) clearInterval(timer) })

const elapsed = computed(() => {
  if (!props.run.started_at) return ''
  const ms = now.value - new Date(props.run.started_at).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
})

const duration = computed(() => {
  if (!props.run.started_at || !props.run.completed_at) return ''
  const ms = new Date(props.run.completed_at).getTime() - new Date(props.run.started_at).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
})

const hasTestResults = computed(() => {
  const t = props.run.test_results
  return t && (t.passed || t.failed || t.errors?.length)
})

const testClass = computed(() => {
  const t = props.run.test_results
  if (t?.failed && t.failed > 0) return 'test-fail'
  if (t?.passed && t.passed > 0) return 'test-pass'
  if (t?.errors?.length) return 'test-fail'
  return 'test-none'
})

const testLabel = computed(() => {
  const t = props.run.test_results
  if (t?.failed && t.failed > 0) return `${t.passed || 0}/${(t.passed || 0) + t.failed} passed`
  if (t?.passed && t.passed > 0) return `${t.passed} passed`
  if (t?.errors?.length) return `${t.errors.length} errors`
  return ''
})
</script>

<style scoped>
.flow-card {
  padding: 8px 10px;
  border-radius: 6px;
  background: #161b22;
  border: 1px solid #21262d;
  border-left: 3px solid #8b949e;
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.3s, background 0.3s;
}
.flow-card:hover { background: #1c2333; border-color: #30363d; }

.stage-queued { border-left-color: #8b949e; }
.stage-ready { border-left-color: #e3b341; }
.stage-building { border-left-color: #58a6ff; }
.stage-testing { border-left-color: #bc8cff; }
.stage-complete { border-left-color: #86BC24; opacity: 0.85; }
.stage-failed { border-left-color: #f85149; }

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
  margin-bottom: 4px;
}

.agent-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: #58a6ff;
  max-width: 100%;
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

.card-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.cost-badge {
  font-size: 9px;
  color: #e3b341;
  font-variant-numeric: tabular-nums;
}

.test-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
}
.test-pass { background: rgba(134, 188, 36, 0.15); color: #86BC24; }
.test-fail { background: rgba(248, 81, 73, 0.15); color: #f85149; }
.test-none { background: rgba(139, 148, 158, 0.15); color: #8b949e; }

.elapsed {
  font-size: 9px;
  color: #8b949e;
  font-variant-numeric: tabular-nums;
  margin-left: auto;
}

.error-line {
  margin-top: 4px;
  font-size: 9px;
  color: #f85149;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
