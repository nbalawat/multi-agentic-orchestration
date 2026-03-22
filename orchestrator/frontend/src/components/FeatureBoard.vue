<template>
  <div class="feature-board">
    <!-- DAG completion header -->
    <div class="board-header">
      <h3 class="board-title">Feature Board</h3>
      <div class="dag-completion">
        <span class="dag-label">DAG Completion</span>
        <div class="dag-bar-track">
          <div
            class="dag-bar-fill"
            :style="{ width: projectStore.dagCompletionPct + '%' }"
          ></div>
        </div>
        <span class="dag-pct">{{ projectStore.dagCompletionPct }}%</span>
      </div>
    </div>

    <!-- Kanban columns -->
    <div class="board-columns">
      <div
        v-for="column in columns"
        :key="column.key"
        class="board-column"
      >
        <div class="column-header">
          <span class="column-title">{{ column.label }}</span>
          <span class="column-count">{{ getColumnFeatures(column.key).length }}</span>
        </div>
        <div class="column-body">
          <div
            v-for="feature in getColumnFeatures(column.key)"
            :key="feature.id"
            class="feature-card"
            :class="'feature-' + column.key"
            @click="$emit('select-feature', feature.id)"
          >
            <div class="feature-name">{{ feature.name }}</div>
            <div class="feature-meta">
              <span class="feature-priority" :class="priorityClass(feature.priority)">
                P{{ feature.priority }}
              </span>
              <span
                v-if="feature.depends_on.length > 0"
                class="feature-deps"
                :title="feature.depends_on.join(', ')"
              >
                {{ feature.depends_on.length }} dep{{ feature.depends_on.length !== 1 ? 's' : '' }}
              </span>
            </div>
          </div>
          <div v-if="getColumnFeatures(column.key).length === 0" class="column-empty">
            No features
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useProjectStore, type Feature } from '../stores/projectStore'

const projectStore = useProjectStore()

defineEmits<{
  'select-feature': [featureId: string]
}>()

const columns = [
  { key: 'planned', label: 'Planned', statuses: ['planned', 'ready', 'pending', 'not_started'] },
  { key: 'in_progress', label: 'In Progress', statuses: ['in_progress'] },
  { key: 'completed', label: 'Complete', statuses: ['completed', 'done'] },
  { key: 'blocked', label: 'Blocked', statuses: ['blocked'] }
]

function getColumnFeatures(columnKey: string): Feature[] {
  const column = columns.find(c => c.key === columnKey)
  if (!column) return []
  return projectStore.features.filter(f =>
    column.statuses.includes(f.status)
  ).sort((a, b) => a.priority - b.priority)
}

function priorityClass(priority: number): string {
  if (priority <= 1) return 'priority-high'
  if (priority <= 3) return 'priority-medium'
  return 'priority-low'
}
</script>

<style scoped>
.feature-board {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0d1117;
  color: #c9d1d9;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
}

/* Board Header */
.board-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #21262d;
}

.board-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: 0.5px;
}

.dag-completion {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dag-label {
  font-size: 10px;
  color: #8b949e;
}

.dag-bar-track {
  width: 100px;
  height: 4px;
  background: #21262d;
  border-radius: 2px;
  overflow: hidden;
}

.dag-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #58a6ff, #56d364);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.dag-pct {
  font-size: 11px;
  font-weight: 600;
  color: #58a6ff;
  min-width: 32px;
  text-align: right;
}

/* Board Columns */
.board-columns {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding: 12px;
  flex: 1;
  min-height: 0;
  overflow-x: auto;
}

.board-column {
  display: flex;
  flex-direction: column;
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 8px;
  min-height: 120px;
  overflow: hidden;
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid #21262d;
}

.column-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #8b949e;
}

.column-count {
  font-size: 10px;
  color: #484f58;
  background: #21262d;
  padding: 1px 6px;
  border-radius: 8px;
}

.column-body {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  flex: 1;
}

.column-empty {
  padding: 12px 8px;
  text-align: center;
  color: #30363d;
  font-style: italic;
  font-size: 11px;
}

/* Feature Cards */
.feature-card {
  padding: 8px 10px;
  border-radius: 6px;
  border-left: 3px solid transparent;
  background: #0d1117;
  cursor: pointer;
  transition: background 0.15s;
}

.feature-card:hover {
  background: #1c2128;
}

.feature-planned { border-left-color: #8b949e; }
.feature-in_progress { border-left-color: #58a6ff; }
.feature-completed { border-left-color: #56d364; }
.feature-blocked { border-left-color: #f85149; }

.feature-name {
  font-size: 11px;
  font-weight: 500;
  color: #e6edf3;
  margin-bottom: 4px;
  line-height: 1.3;
}

.feature-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.feature-priority {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
}

.priority-high { background: #3f1f1f; color: #f85149; }
.priority-medium { background: #3f3a1f; color: #e3b341; }
.priority-low { background: #21262d; color: #8b949e; }

.feature-deps {
  font-size: 9px;
  color: #484f58;
}
</style>
