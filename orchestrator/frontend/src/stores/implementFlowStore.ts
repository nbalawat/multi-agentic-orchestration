import { defineStore } from 'pinia'
import { ref, computed, reactive } from 'vue'

export type FlowStage = 'queued' | 'ready' | 'building' | 'merging' | 'done' | 'blocked'

export interface FlowFeature {
  id: string
  name: string
  stage: FlowStage
  priority: number
  dependsOn: string[]
  assignedAgent: string | null
  waveNumber: number
  startedAt: string | null
  completedAt: string | null
  stageEnteredAt: string
  satisfiedDeps: number
  totalDeps: number
  isOnCriticalPath: boolean
  mergeStatus: 'pending' | 'success' | 'failed' | null
}

export interface FlowProgress {
  total: number
  completed: number
  inProgress: number
  ready: number
  blocked: number
  completionPct: number
  currentWave: number
}

export const STAGE_COLUMNS = [
  { key: 'queued' as FlowStage, label: 'Queued', color: '#8b949e' },
  { key: 'ready' as FlowStage, label: 'Ready', color: '#e3b341' },
  { key: 'building' as FlowStage, label: 'Building', color: '#58a6ff' },
  { key: 'merging' as FlowStage, label: 'Merging', color: '#bc8cff' },
  { key: 'done' as FlowStage, label: 'Done', color: '#86BC24' },
  { key: 'blocked' as FlowStage, label: 'Blocked', color: '#f85149' },
]

export const useImplementFlowStore = defineStore('implementFlow', () => {
  const features = reactive<Map<string, FlowFeature>>(new Map())
  const progress = ref<FlowProgress>({
    total: 0, completed: 0, inProgress: 0, ready: 0, blocked: 0,
    completionPct: 0, currentWave: 0,
  })
  const isActive = ref(false)
  const dagComplete = ref(false)

  // Computed: features grouped by stage
  const featuresByStage = computed(() => {
    const groups: Record<FlowStage, FlowFeature[]> = {
      queued: [], ready: [], building: [], merging: [], done: [], blocked: [],
    }
    for (const feat of features.values()) {
      groups[feat.stage].push(feat)
    }
    // Sort each group by priority (lower = higher priority)
    for (const stage of Object.keys(groups) as FlowStage[]) {
      groups[stage].sort((a, b) => a.priority - b.priority)
    }
    return groups
  })

  const totalFeatures = computed(() => features.size)

  // Compute wave numbers via BFS levels over dependency graph
  function computeWaveNumbers(featureList: any[]): Map<string, number> {
    const waves = new Map<string, number>()
    const featureMap = new Map(featureList.map(f => [f.id, f]))

    // Features with no dependencies are wave 0
    for (const f of featureList) {
      const deps = f.depends_on || f.dependsOn || []
      if (deps.length === 0) {
        waves.set(f.id, 0)
      }
    }

    // BFS: wave number = max(wave of deps) + 1
    let changed = true
    while (changed) {
      changed = false
      for (const f of featureList) {
        if (waves.has(f.id)) continue
        const deps = f.depends_on || f.dependsOn || []
        const depWaves = deps.map((d: string) => waves.get(d))
        if (depWaves.every((w: number | undefined) => w !== undefined)) {
          waves.set(f.id, Math.max(...(depWaves as number[])) + 1)
          changed = true
        }
      }
    }

    // Assign remaining (circular or broken deps) to wave 999
    for (const f of featureList) {
      if (!waves.has(f.id)) waves.set(f.id, 999)
    }

    return waves
  }

  function mapStatusToStage(status: string, deps: string[], allFeatures: Map<string, FlowFeature>): FlowStage {
    switch (status) {
      case 'complete':
      case 'completed':
        return 'done'
      case 'in_progress':
        return 'building'
      case 'blocked':
        return 'blocked'
      case 'deferred':
        return 'blocked'
      case 'planned':
      default: {
        // Check if all dependencies are complete
        if (deps.length === 0) return 'ready'
        const allDepsComplete = deps.every(d => {
          const dep = allFeatures.get(d)
          return dep && dep.stage === 'done'
        })
        return allDepsComplete ? 'ready' : 'queued'
      }
    }
  }

  // Initialize from backend DAG data
  async function initializeFromDag(projectId: string) {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:9403'

    try {
      // Fetch features and DAG
      const [featResp, dagResp] = await Promise.all([
        fetch(`${apiBase}/api/projects/${projectId}/features`),
        fetch(`${apiBase}/api/projects/${projectId}/dag`),
      ])

      const featData = await featResp.json()
      const dagData = await dagResp.json()

      const featureList = featData.features || []
      const dagSummary = dagData.summary || dagData.dag_status || {}
      const criticalPath: string[] = dagData.critical_path || []

      // Compute wave numbers
      const waveNumbers = computeWaveNumbers(featureList)

      // Build FlowFeature map
      features.clear()
      const now = new Date().toISOString()

      for (const f of featureList) {
        const deps = f.depends_on || []
        const satisfiedDeps = deps.filter((d: string) =>
          featureList.find((x: any) => x.id === d && (x.status === 'complete' || x.status === 'completed'))
        ).length

        const flowFeat: FlowFeature = {
          id: f.id,
          name: f.name,
          stage: 'queued', // will be recomputed below
          priority: f.priority || 999,
          dependsOn: deps,
          assignedAgent: f.assigned_agent || null,
          waveNumber: waveNumbers.get(f.id) || 0,
          startedAt: f.started_at || null,
          completedAt: f.completed_at || null,
          stageEnteredAt: now,
          satisfiedDeps,
          totalDeps: deps.length,
          isOnCriticalPath: criticalPath.includes(f.id),
          mergeStatus: null,
        }

        features.set(f.id, flowFeat)
      }

      // Now compute stages (needs all features in map for dep checking)
      for (const f of featureList) {
        const flowFeat = features.get(f.id)
        if (flowFeat) {
          flowFeat.stage = mapStatusToStage(f.status, f.depends_on || [], features)
        }
      }

      // Update progress
      progress.value = {
        total: dagSummary.total || featureList.length,
        completed: dagSummary.completed || 0,
        inProgress: dagSummary.in_progress || 0,
        ready: dagSummary.ready || 0,
        blocked: dagSummary.blocked || 0,
        completionPct: dagSummary.completion_percentage || 0,
        currentWave: Math.min(...Array.from(features.values())
          .filter(f => f.stage === 'building' || f.stage === 'ready')
          .map(f => f.waveNumber)
          .concat([0])
        ),
      }

      isActive.value = true
      dagComplete.value = progress.value.completed === progress.value.total && progress.value.total > 0

    } catch (e) {
      console.error('[ImplementFlowStore] Failed to initialize:', e)
    }
  }

  // WebSocket event handlers
  function handleFeatureStarted(data: any) {
    const feat = features.get(data.feature_id)
    if (feat) {
      feat.stage = 'building'
      feat.assignedAgent = data.agent_name || null
      feat.startedAt = new Date().toISOString()
      feat.stageEnteredAt = new Date().toISOString()
    }
    progress.value.inProgress = (progress.value.inProgress || 0) + 1
  }

  function handleFeatureMerged(data: any) {
    const feat = features.get(data.feature_id)
    if (feat) {
      feat.stage = 'done'
      feat.mergeStatus = 'success'
      feat.completedAt = new Date().toISOString()
      feat.stageEnteredAt = new Date().toISOString()
    }

    // Update satisfied deps on dependent features
    for (const f of features.values()) {
      if (f.dependsOn.includes(data.feature_id)) {
        f.satisfiedDeps = f.dependsOn.filter(d => {
          const dep = features.get(d)
          return dep && dep.stage === 'done'
        }).length
      }
    }
  }

  function handleFeatureMergeFailed(data: any) {
    const feat = features.get(data.feature_id)
    if (feat) {
      feat.stage = 'blocked'
      feat.mergeStatus = 'failed'
      feat.stageEnteredAt = new Date().toISOString()
    }
  }

  function handleDagProgress(data: any) {
    progress.value = {
      ...progress.value,
      total: data.total ?? progress.value.total,
      completed: data.completed ?? progress.value.completed,
      inProgress: data.in_progress ?? progress.value.inProgress,
      ready: data.ready ?? progress.value.ready,
      completionPct: data.total ? Math.round((data.completed / data.total) * 100) : 0,
    }
  }

  function handleWaveTransition(data: any) {
    const nextFeatures: string[] = data.next_features || []
    for (const fId of nextFeatures) {
      const feat = features.get(fId)
      if (feat && feat.stage === 'queued') {
        feat.stage = 'ready'
        feat.stageEnteredAt = new Date().toISOString()
      }
    }
    progress.value.currentWave += 1
  }

  function handleDagComplete(data: any) {
    dagComplete.value = true
    progress.value.completionPct = 100
    progress.value.completed = data.total || progress.value.total
  }

  function reset() {
    features.clear()
    isActive.value = false
    dagComplete.value = false
    progress.value = {
      total: 0, completed: 0, inProgress: 0, ready: 0, blocked: 0,
      completionPct: 0, currentWave: 0,
    }
  }

  return {
    features,
    progress,
    isActive,
    dagComplete,
    featuresByStage,
    totalFeatures,
    initializeFromDag,
    handleFeatureStarted,
    handleFeatureMerged,
    handleFeatureMergeFailed,
    handleDagProgress,
    handleWaveTransition,
    handleDagComplete,
    reset,
  }
})
