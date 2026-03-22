/**
 * Project Store
 *
 * Pinia store for managing the active project's phases, features, DAG, and workflow progress.
 * Works in tandem with the workspace store which handles project selection.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as projectService from '../services/projectService'

// ═══════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════

export interface Phase {
  phase: string
  status: string
  started_at?: string
  completed_at?: string
}

export interface Feature {
  id: string
  name: string
  description?: string
  depends_on: string[]
  acceptance_criteria: string[]
  status: string
  priority: number
  spec_file?: string
}

export interface DagStatus {
  total: number
  completed: number
  in_progress: number
  ready: number
  blocked: number
  completion_pct: number
  critical_path: string[]
}

export interface DagValidation {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export interface WorkflowProgress {
  project_id: string
  current_phase: string
  phase_progress: Record<string, number>
  overall_progress: number
  estimated_completion?: string
}

// ═══════════════════════════════════════════════════════════
// STORE
// ═══════════════════════════════════════════════════════════

export const useProjectStore = defineStore('project', () => {
  // ═══════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════

  const phases = ref<Phase[]>([])
  const features = ref<Feature[]>([])
  const dagStatus = ref<DagStatus | null>(null)
  const dagValidation = ref<DagValidation | null>(null)
  const workflowProgress = ref<WorkflowProgress | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ═══════════════════════════════════════════════════════════
  // GETTERS
  // ═══════════════════════════════════════════════════════════

  /** The currently active phase (status === 'in_progress') */
  const activePhase = computed(() =>
    phases.value.find(p => p.status === 'in_progress') ?? null
  )

  /** Phases that have been completed */
  const completedPhases = computed(() =>
    phases.value.filter(p => p.status === 'completed')
  )

  /** Phases still pending */
  const pendingPhases = computed(() =>
    phases.value.filter(p => p.status === 'pending')
  )

  /** Features grouped by status */
  const featuresByStatus = computed(() => {
    const grouped: Record<string, Feature[]> = {}
    for (const feature of features.value) {
      const status = feature.status || 'unknown'
      if (!grouped[status]) {
        grouped[status] = []
      }
      grouped[status].push(feature)
    }
    return grouped
  })

  /** Features sorted by priority (lower number = higher priority) */
  const featuresByPriority = computed(() =>
    [...features.value].sort((a, b) => a.priority - b.priority)
  )

  /** Features that are ready to work on (no blocked dependencies) */
  const readyFeatures = computed(() =>
    features.value.filter(f => f.status === 'ready')
  )

  /** DAG completion percentage */
  const dagCompletionPct = computed(() =>
    dagStatus.value?.completion_pct ?? 0
  )

  /** Overall workflow progress percentage */
  const overallProgress = computed(() =>
    workflowProgress.value?.overall_progress ?? 0
  )

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - PHASES
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch all phases for a project
   */
  async function fetchPhases(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.fetchPhases(projectId)
      phases.value = data.phases ?? data
      console.log(`Loaded ${phases.value.length} phases for project ${projectId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch phases'
      error.value = message
      console.error('Failed to fetch phases:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Start a specific phase
   */
  async function startPhase(projectId: string, phase: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.startPhase(projectId, phase)
      // Update the local phase status
      const index = phases.value.findIndex(p => p.phase === phase)
      if (index !== -1) {
        phases.value[index] = {
          ...phases.value[index],
          status: 'in_progress',
          started_at: data.started_at ?? new Date().toISOString()
        }
        // Force reactivity
        phases.value = [...phases.value]
      }
      console.log(`Started phase: ${phase} for project ${projectId}`)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start phase'
      error.value = message
      console.error('Failed to start phase:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Complete a specific phase
   */
  async function completePhase(projectId: string, phase: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.completePhase(projectId, phase)
      // Update the local phase status
      const index = phases.value.findIndex(p => p.phase === phase)
      if (index !== -1) {
        phases.value[index] = {
          ...phases.value[index],
          status: 'completed',
          completed_at: data.completed_at ?? new Date().toISOString()
        }
        // Force reactivity
        phases.value = [...phases.value]
      }
      console.log(`Completed phase: ${phase} for project ${projectId}`)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to complete phase'
      error.value = message
      console.error('Failed to complete phase:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Advance to the next phase automatically
   */
  async function advancePhase(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.advancePhase(projectId)
      // Reload phases to get the updated state
      await fetchPhases(projectId)
      console.log(`Advanced phase for project ${projectId}`)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to advance phase'
      error.value = message
      console.error('Failed to advance phase:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - FEATURES
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch all features for a project
   */
  async function fetchFeatures(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.fetchFeatures(projectId)
      features.value = data.features ?? data
      console.log(`Loaded ${features.value.length} features for project ${projectId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch features'
      error.value = message
      console.error('Failed to fetch features:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Create a new feature for a project
   */
  async function createFeature(
    projectId: string,
    data: {
      name: string
      description?: string
      depends_on?: string[]
      acceptance_criteria?: string[]
      priority?: number
      spec_file?: string
    }
  ) {
    isLoading.value = true
    error.value = null
    try {
      const result = await projectService.createFeature(projectId, data)
      const feature: Feature = result.feature ?? result
      features.value = [...features.value, feature]
      console.log(`Created feature: ${feature.name} (${feature.id})`)
      return feature
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create feature'
      error.value = message
      console.error('Failed to create feature:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Update a feature's status
   */
  async function updateFeatureStatus(projectId: string, featureId: string, status: string) {
    error.value = null
    try {
      await projectService.updateFeatureStatus(projectId, featureId, status)
      const index = features.value.findIndex(f => f.id === featureId)
      if (index !== -1) {
        features.value[index] = { ...features.value[index], status }
        features.value = [...features.value]
      }
      console.log(`Updated feature ${featureId} status to: ${status}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update feature status'
      error.value = message
      console.error('Failed to update feature status:', err)
      throw err
    }
  }

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - DAG
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch the current DAG status for a project
   */
  async function fetchDagStatus(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.fetchDagStatus(projectId)
      dagStatus.value = data.dag_status ?? data
      console.log(`Loaded DAG status for project ${projectId}: ${dagStatus.value?.completion_pct}% complete`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch DAG status'
      error.value = message
      console.error('Failed to fetch DAG status:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Validate the DAG for a project (check for cycles, missing dependencies, etc.)
   */
  async function validateDag(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.validateDag(projectId)
      dagValidation.value = data.validation ?? data
      console.log(`DAG validation for project ${projectId}: valid=${dagValidation.value?.valid}`)
      return dagValidation.value
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to validate DAG'
      error.value = message
      console.error('Failed to validate DAG:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - WORKFLOW PROGRESS
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch workflow progress for a project
   */
  async function fetchWorkflowProgress(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await projectService.fetchWorkflowProgress(projectId)
      workflowProgress.value = data.progress ?? data
      console.log(`Loaded workflow progress for project ${projectId}: ${workflowProgress.value?.overall_progress}%`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch workflow progress'
      error.value = message
      console.error('Failed to fetch workflow progress:', err)
    } finally {
      isLoading.value = false
    }
  }

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - LOAD ALL PROJECT DATA
  // ═══════════════════════════════════════════════════════════

  /**
   * Load all data for a project: phases, features, DAG status, and workflow progress
   */
  async function loadProjectData(projectId: string) {
    console.log(`Loading all data for project ${projectId}...`)
    isLoading.value = true
    error.value = null

    try {
      await Promise.all([
        fetchPhases(projectId),
        fetchFeatures(projectId),
        fetchDagStatus(projectId),
        fetchWorkflowProgress(projectId)
      ])
      console.log(`All data loaded for project ${projectId}`)
    } catch (err) {
      console.error('Failed to load some project data:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Clear all project-specific state (e.g., when switching projects)
   */
  function clearProjectData() {
    phases.value = []
    features.value = []
    dagStatus.value = null
    dagValidation.value = null
    workflowProgress.value = null
    error.value = null
  }

  // ═══════════════════════════════════════════════════════════
  // RETURN PUBLIC API
  // ═══════════════════════════════════════════════════════════

  return {
    // State
    phases,
    features,
    dagStatus,
    dagValidation,
    workflowProgress,
    isLoading,
    error,

    // Getters
    activePhase,
    completedPhases,
    pendingPhases,
    featuresByStatus,
    featuresByPriority,
    readyFeatures,
    dagCompletionPct,
    overallProgress,

    // Actions - Phases
    fetchPhases,
    startPhase,
    completePhase,
    advancePhase,

    // Actions - Features
    fetchFeatures,
    createFeature,
    updateFeatureStatus,

    // Actions - DAG
    fetchDagStatus,
    validateDag,

    // Actions - Workflow
    fetchWorkflowProgress,

    // Actions - Bulk
    loadProjectData,
    clearProjectData
  }
})
