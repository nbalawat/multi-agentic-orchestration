<template>
  <div class="feature-dag-view">
    <!-- Header with stats -->
    <div class="dag-header">
      <h3 class="dag-title">Feature Dependencies</h3>
      <div class="dag-stats" v-if="projectStore.dagStatus">
        <span class="stat-item">
          <span class="stat-value">{{ projectStore.dagStatus.total }}</span>
          <span class="stat-label">Total</span>
        </span>
        <span class="stat-item stat-complete">
          <span class="stat-value">{{ projectStore.dagStatus.completed }}</span>
          <span class="stat-label">Done</span>
        </span>
        <span class="stat-item stat-progress">
          <span class="stat-value">{{ projectStore.dagStatus.in_progress }}</span>
          <span class="stat-label">Active</span>
        </span>
        <span class="stat-item stat-ready">
          <span class="stat-value">{{ projectStore.dagStatus.ready }}</span>
          <span class="stat-label">Ready</span>
        </span>
        <span class="stat-item stat-blocked">
          <span class="stat-value">{{ projectStore.dagStatus.blocked }}</span>
          <span class="stat-label">Blocked</span>
        </span>
      </div>
    </div>

    <!-- Completion bar -->
    <div class="completion-section">
      <div class="completion-bar-track">
        <div
          class="completion-bar-fill"
          :style="{ width: projectStore.dagCompletionPct + '%' }"
        ></div>
      </div>
      <span class="completion-text">{{ projectStore.dagCompletionPct }}% complete</span>
    </div>

    <!-- DAG list with indentation -->
    <div class="dag-list">
      <div
        v-for="node in dagNodes"
        :key="node.feature.id"
        class="dag-node"
        :class="{
          'on-critical-path': node.isOnCriticalPath,
          'dag-root': node.depth === 0
        }"
        :style="{ paddingLeft: (12 + node.depth * 20) + 'px' }"
      >
        <!-- Indent guide lines -->
        <span v-if="node.depth > 0" class="indent-connector">
          {{ node.isLast ? '\\u2514' : '\\u251C' }}\\u2500
        </span>

        <!-- Status badge -->
        <span class="node-status-badge" :class="'status-' + node.feature.status">
          <span v-if="node.feature.status === 'completed'">&#10003;</span>
          <span v-else-if="node.feature.status === 'in_progress'" class="badge-pulse"></span>
          <span v-else-if="node.feature.status === 'blocked'">&#10007;</span>
          <span v-else>&#9675;</span>
        </span>

        <!-- Feature name -->
        <span class="node-name" :class="{ 'critical-text': node.isOnCriticalPath }">
          {{ node.feature.name }}
        </span>

        <!-- Priority -->
        <span class="node-priority">P{{ node.feature.priority }}</span>

        <!-- Dependency count -->
        <span v-if="node.feature.depends_on.length > 0" class="node-dep-count">
          {{ node.feature.depends_on.length }} dep{{ node.feature.depends_on.length !== 1 ? 's' : '' }}
        </span>

        <!-- Critical path marker -->
        <span v-if="node.isOnCriticalPath" class="critical-marker" title="Critical path">
          CP
        </span>
      </div>

      <div v-if="dagNodes.length === 0" class="empty-state">
        No features defined
      </div>
    </div>

    <!-- Validation warnings -->
    <div
      v-if="projectStore.dagValidation && !projectStore.dagValidation.valid"
      class="dag-validation-errors"
    >
      <div class="validation-header">DAG Validation Issues</div>
      <div
        v-for="(err, i) in projectStore.dagValidation.errors"
        :key="'err-' + i"
        class="validation-item error"
      >
        {{ err }}
      </div>
      <div
        v-for="(warn, i) in projectStore.dagValidation.warnings"
        :key="'warn-' + i"
        class="validation-item warning"
      >
        {{ warn }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useProjectStore, type Feature } from '../stores/projectStore'

interface DagNode {
  feature: Feature
  depth: number
  isOnCriticalPath: boolean
  isLast: boolean
}

const projectStore = useProjectStore()

/** Build a flat list with depth for indentation, showing dependency relationships */
const dagNodes = computed((): DagNode[] => {
  const features = projectStore.features
  if (features.length === 0) return []

  const criticalPath = new Set(projectStore.dagStatus?.critical_path ?? [])
  const featureMap = new Map(features.map(f => [f.id, f]))

  // Find root features (no dependencies or deps not in current feature set)
  const roots = features.filter(f =>
    f.depends_on.length === 0 ||
    f.depends_on.every(depId => !featureMap.has(depId))
  )

  // Build reverse mapping: feature -> features that depend on it
  const dependents = new Map<string, string[]>()
  for (const f of features) {
    for (const depId of f.depends_on) {
      if (!dependents.has(depId)) dependents.set(depId, [])
      dependents.get(depId)!.push(f.id)
    }
  }

  const result: DagNode[] = []
  const visited = new Set<string>()

  function walk(featureId: string, depth: number, isLast: boolean) {
    if (visited.has(featureId)) return
    visited.add(featureId)

    const feature = featureMap.get(featureId)
    if (!feature) return

    result.push({
      feature,
      depth,
      isOnCriticalPath: criticalPath.has(featureId),
      isLast
    })

    const children = (dependents.get(featureId) ?? [])
      .filter(id => featureMap.has(id) && !visited.has(id))
      .sort((a, b) => {
        const fa = featureMap.get(a)!
        const fb = featureMap.get(b)!
        return fa.priority - fb.priority
      })

    children.forEach((childId, i) => {
      walk(childId, depth + 1, i === children.length - 1)
    })
  }

  // Sort roots by priority
  const sortedRoots = [...roots].sort((a, b) => a.priority - b.priority)
  sortedRoots.forEach((root, i) => {
    walk(root.id, 0, i === sortedRoots.length - 1)
  })

  // Add any unvisited features (isolated or in cycles)
  for (const f of features) {
    if (!visited.has(f.id)) {
      result.push({
        feature: f,
        depth: 0,
        isOnCriticalPath: criticalPath.has(f.id),
        isLast: true
      })
    }
  }

  return result
})
</script>

<style scoped>
.feature-dag-view {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 8px;
  color: #c9d1d9;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  overflow: hidden;
}

/* Header */
.dag-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid #21262d;
  flex-wrap: wrap;
  gap: 8px;
}

.dag-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
}

.dag-stats {
  display: flex;
  gap: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}

.stat-value {
  font-size: 13px;
  font-weight: 700;
  color: #e6edf3;
}

.stat-label {
  font-size: 9px;
  color: #484f58;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-complete .stat-value { color: #56d364; }
.stat-progress .stat-value { color: #58a6ff; }
.stat-ready .stat-value { color: #e3b341; }
.stat-blocked .stat-value { color: #f85149; }

/* Completion Bar */
.completion-section {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid #21262d;
}

.completion-bar-track {
  flex: 1;
  height: 4px;
  background: #21262d;
  border-radius: 2px;
  overflow: hidden;
}

.completion-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #58a6ff, #56d364);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.completion-text {
  font-size: 10px;
  color: #8b949e;
  white-space: nowrap;
}

/* DAG Node List */
.dag-list {
  padding: 8px 0;
  max-height: 400px;
  overflow-y: auto;
}

.dag-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  transition: background 0.1s;
}

.dag-node:hover {
  background: #161b22;
}

.dag-node.on-critical-path {
  background: rgba(88, 166, 255, 0.05);
}

.indent-connector {
  font-size: 11px;
  color: #30363d;
  white-space: pre;
  flex-shrink: 0;
}

/* Status Badge */
.node-status-badge {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  flex-shrink: 0;
}

.status-completed { background: #1a3a2a; color: #56d364; border: 1px solid #56d364; }
.status-in_progress { background: #1f3a5f; color: #58a6ff; border: 1px solid #58a6ff; }
.status-blocked { background: #3f1f1f; color: #f85149; border: 1px solid #f85149; }
.status-planned,
.status-ready,
.status-pending,
.status-not_started { background: #21262d; color: #484f58; border: 1px solid #30363d; }

.badge-pulse {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #58a6ff;
  animation: dag-pulse 1.5s ease-in-out infinite;
}

@keyframes dag-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Feature Name */
.node-name {
  flex: 1;
  font-size: 11px;
  color: #c9d1d9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-name.critical-text {
  color: #58a6ff;
  font-weight: 600;
}

/* Priority & Deps */
.node-priority {
  font-size: 9px;
  color: #484f58;
  font-weight: 600;
}

.node-dep-count {
  font-size: 9px;
  color: #484f58;
}

.critical-marker {
  font-size: 8px;
  font-weight: 700;
  color: #58a6ff;
  background: #1f3a5f;
  padding: 1px 4px;
  border-radius: 3px;
  letter-spacing: 0.5px;
}

/* Empty State */
.empty-state {
  padding: 24px;
  text-align: center;
  color: #484f58;
  font-style: italic;
}

/* Validation */
.dag-validation-errors {
  margin: 8px 14px 12px;
  border: 1px solid #f85149;
  border-radius: 6px;
  overflow: hidden;
}

.validation-header {
  padding: 6px 10px;
  background: #3f1f1f;
  font-size: 10px;
  font-weight: 600;
  color: #f85149;
  letter-spacing: 0.5px;
}

.validation-item {
  padding: 4px 10px;
  font-size: 10px;
  border-top: 1px solid #21262d;
}

.validation-item.error { color: #f85149; }
.validation-item.warning { color: #e3b341; }
</style>
