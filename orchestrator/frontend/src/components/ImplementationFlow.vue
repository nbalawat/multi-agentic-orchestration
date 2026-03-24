<template>
  <div class="implementation-flow">
    <FlowProgressHeader
      :progress="flowStore.dag"
      :dag-complete="flowStore.dagComplete"
      :project-name="workspaceStore.activeProject?.name"
      :total-cost="flowStore.totalCost"
    />

    <div class="flow-columns">
      <div
        v-for="col in columns"
        :key="col.key"
        class="flow-column"
      >
        <div class="column-header">
          <span class="column-label">{{ col.label }}</span>
          <span class="column-count" :style="{ background: col.color + '22', color: col.color }">
            {{ columnRuns(col.key).length }}
          </span>
        </div>

        <div class="column-body">
          <div class="card-list">
            <FlowFeatureCard
              v-for="run in columnRuns(col.key)"
              :key="run.feature_id"
              :run="run"
              @click="onFeatureClick(run)"
            />
          </div>

          <div v-if="columnRuns(col.key).length === 0" class="column-empty">
            --
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch, ref } from 'vue'
import { useImplementFlowStore, STAGE_COLUMNS } from '../stores/implementFlowStore'
import type { RunStatus, ExecutionRun } from '../stores/implementFlowStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import FlowFeatureCard from './FlowFeatureCard.vue'
import FlowProgressHeader from './FlowProgressHeader.vue'

const props = defineProps<{ visible?: boolean }>()
const emit = defineEmits<{ 'select-feature': [run: ExecutionRun] }>()

const flowStore = useImplementFlowStore()
const workspaceStore = useWorkspaceStore()
const columns = STAGE_COLUMNS
const pollInterval = ref<ReturnType<typeof setInterval> | null>(null)

function columnRuns(status: RunStatus) {
  return flowStore.runsByStatus[status] || []
}

function onFeatureClick(run: ExecutionRun) {
  emit('select-feature', run)
}

async function poll() {
  const projectId = workspaceStore.activeProjectId
  if (projectId && props.visible !== false) {
    await flowStore.fetchStatus(projectId)
  }
}

onMounted(() => {
  poll()
  pollInterval.value = setInterval(poll, 3000)
})

onUnmounted(() => {
  if (pollInterval.value) clearInterval(pollInterval.value)
})

watch(() => props.visible, (v) => { if (v) poll() })
</script>

<style scoped>
.implementation-flow {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0d1117;
  overflow: hidden;
}

.flow-columns {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1px;
  background: #21262d;
  overflow-y: auto;
  min-height: 0;
}

.flow-column {
  display: flex;
  flex-direction: column;
  background: #0d1117;
  min-width: 0;
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid #21262d;
  position: sticky;
  top: 0;
  background: #0d1117;
  z-index: 1;
}

.column-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1px;
  color: #8b949e;
  text-transform: uppercase;
}

.column-count {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 8px;
}

.column-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.column-empty {
  text-align: center;
  color: #484f58;
  font-size: 11px;
  padding: 20px 0;
}
</style>
