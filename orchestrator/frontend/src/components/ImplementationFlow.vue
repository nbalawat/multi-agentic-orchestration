<template>
  <div class="implementation-flow">
    <FlowProgressHeader
      :progress="flowStore.progress"
      :dag-complete="flowStore.dagComplete"
      :project-name="workspaceStore.activeProject?.name"
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
            {{ stageFeatures(col.key).length }}
          </span>
        </div>

        <div class="column-body">
          <TransitionGroup name="flow-card" tag="div" class="card-list">
            <FlowFeatureCard
              v-for="feature in stageFeatures(col.key)"
              :key="feature.id"
              :feature="feature"
              @click="onFeatureClick(feature.id)"
            />
          </TransitionGroup>

          <div v-if="stageFeatures(col.key).length === 0" class="column-empty">
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
import type { FlowStage } from '../stores/implementFlowStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import FlowFeatureCard from './FlowFeatureCard.vue'
import FlowProgressHeader from './FlowProgressHeader.vue'

const props = defineProps<{
  visible?: boolean
}>()

const flowStore = useImplementFlowStore()
const workspaceStore = useWorkspaceStore()

const columns = STAGE_COLUMNS

const emit = defineEmits<{
  'select-feature': [featureId: string]
}>()

function stageFeatures(stage: FlowStage) {
  return flowStore.featuresByStage[stage] || []
}

function onFeatureClick(featureId: string) {
  emit('select-feature', featureId)
}

async function loadData() {
  const projectId = workspaceStore.activeProjectId
  if (projectId) {
    await flowStore.initializeFromDag(projectId)
  }
}

// Load on mount + auto-refresh every 5 seconds while visible
const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)

onMounted(() => {
  loadData()
  refreshInterval.value = setInterval(() => {
    if (props.visible !== false) {
      loadData()
    }
  }, 5000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})

// Also re-load when panel becomes visible
watch(() => props.visible, (isVisible) => {
  if (isVisible) { loadData() }
})
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
  position: relative;
}

.column-empty {
  text-align: center;
  color: #484f58;
  font-size: 11px;
  padding: 20px 0;
}

/* TransitionGroup animations */
.flow-card-enter-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.flow-card-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.flow-card-enter-from {
  opacity: 0;
  transform: translateY(-10px) scale(0.95);
}
.flow-card-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.95);
}
.flow-card-move {
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
