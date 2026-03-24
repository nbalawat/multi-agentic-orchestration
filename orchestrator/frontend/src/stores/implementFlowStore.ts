/**
 * Implementation Flow Store — v2 (Polling Only)
 *
 * Polls GET /api/projects/{id}/execution-status every 3 seconds.
 * No WebSocket dependency for execution state. Simple, reliable.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type RunStatus = 'queued' | 'ready' | 'building' | 'testing' | 'complete' | 'failed'

export interface ExecutionRun {
  id: string | null
  feature_id: string
  feature_name: string
  agent_name: string | null
  status: RunStatus
  agent_status: string | null
  started_at: string | null
  completed_at: string | null
  cost: number
  input_tokens: number
  output_tokens: number
  test_results: { passed?: number; failed?: number; skipped?: number; errors?: string[]; output?: string }
  files_changed: { path: string; action: string }[]
  error_message: string | null
  wave_number: number
  priority?: number
  depends_on?: string[]
}

export interface DagSummary {
  total: number
  complete: number
  in_progress: number
  blocked: number
  planned: number
  completion_pct: number
}

export const STAGE_COLUMNS = [
  { key: 'queued' as RunStatus, label: 'Queued', color: '#8b949e' },
  { key: 'ready' as RunStatus, label: 'Ready', color: '#e3b341' },
  { key: 'building' as RunStatus, label: 'Building', color: '#58a6ff' },
  { key: 'testing' as RunStatus, label: 'Testing', color: '#bc8cff' },
  { key: 'complete' as RunStatus, label: 'Done', color: '#86BC24' },
  { key: 'failed' as RunStatus, label: 'Failed', color: '#f85149' },
]

export const useImplementFlowStore = defineStore('implementFlow', () => {
  const runs = ref<ExecutionRun[]>([])
  const dag = ref<DagSummary>({ total: 0, complete: 0, in_progress: 0, blocked: 0, planned: 0, completion_pct: 0 })
  const totalCost = ref(0)
  const isActive = ref(false)
  const lastError = ref<string | null>(null)

  // Group runs by status for Kanban columns
  const runsByStatus = computed(() => {
    const groups: Record<RunStatus, ExecutionRun[]> = {
      queued: [], ready: [], building: [], testing: [], complete: [], failed: [],
    }
    for (const run of runs.value) {
      const status = run.status as RunStatus
      if (groups[status]) {
        groups[status].push(run)
      }
    }
    // Sort each group by wave then priority
    for (const key of Object.keys(groups) as RunStatus[]) {
      groups[key].sort((a, b) => (a.wave_number - b.wave_number) || ((a.priority || 999) - (b.priority || 999)))
    }
    return groups
  })

  const dagComplete = computed(() => dag.value.complete === dag.value.total && dag.value.total > 0)

  // Fetch from the single endpoint
  async function fetchStatus(projectId: string) {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:9403'
    try {
      const resp = await fetch(`${apiBase}/api/projects/${projectId}/execution-status`)
      if (!resp.ok) {
        lastError.value = `HTTP ${resp.status}`
        return
      }
      const data = await resp.json()

      runs.value = data.runs || []
      dag.value = data.dag || dag.value
      totalCost.value = data.total_cost || 0
      isActive.value = true
      lastError.value = null
    } catch (e: any) {
      lastError.value = e.message || 'Fetch failed'
      console.debug('[ImplementFlowStore] Fetch error:', e)
    }
  }

  function reset() {
    runs.value = []
    dag.value = { total: 0, complete: 0, in_progress: 0, blocked: 0, planned: 0, completion_pct: 0 }
    totalCost.value = 0
    isActive.value = false
    lastError.value = null
  }

  // Keep the old handlers as no-ops so WebSocket routing doesn't crash
  function handleFeatureStarted(_data: any) {}
  function handleFeatureMerged(_data: any) {}
  function handleFeatureMergeFailed(_data: any) {}
  function handleDagProgress(_data: any) {}
  function handleWaveTransition(_data: any) {}
  function handleDagComplete(_data: any) {}

  return {
    runs,
    dag,
    totalCost,
    isActive,
    lastError,
    runsByStatus,
    dagComplete,
    fetchStatus,
    reset,
    // Keep these so existing WebSocket routing doesn't break
    handleFeatureStarted,
    handleFeatureMerged,
    handleFeatureMergeFailed,
    handleDagProgress,
    handleWaveTransition,
    handleDagComplete,
  }
})
