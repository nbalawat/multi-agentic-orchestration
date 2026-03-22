/**
 * Project Service
 *
 * Handles HTTP communication for project phase, feature, and DAG operations.
 */

import { apiClient } from './api'

// ═══════════════════════════════════════════════════════════
// PHASE OPERATIONS
// ═══════════════════════════════════════════════════════════

/**
 * Fetch all phases for a project
 */
export async function fetchPhases(projectId: string) {
  const response = await apiClient.get(`/api/projects/${projectId}/phases`)
  return response.data
}

/**
 * Start a specific phase for a project
 */
export async function startPhase(projectId: string, phase: string) {
  const response = await apiClient.post(`/api/projects/${projectId}/phases/${phase}/start`)
  return response.data
}

/**
 * Complete a specific phase for a project
 */
export async function completePhase(projectId: string, phase: string) {
  const response = await apiClient.post(`/api/projects/${projectId}/phases/${phase}/complete`)
  return response.data
}

/**
 * Advance to the next phase automatically
 */
export async function advancePhase(projectId: string) {
  const response = await apiClient.post(`/api/projects/${projectId}/phases/advance`)
  return response.data
}

// ═══════════════════════════════════════════════════════════
// FEATURE OPERATIONS
// ═══════════════════════════════════════════════════════════

/**
 * Fetch all features for a project
 */
export async function fetchFeatures(projectId: string) {
  const response = await apiClient.get(`/api/projects/${projectId}/features`)
  return response.data
}

/**
 * Create a new feature for a project
 */
export async function createFeature(
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
  const response = await apiClient.post(`/api/projects/${projectId}/features`, data)
  return response.data
}

/**
 * Update a feature's status
 */
export async function updateFeatureStatus(projectId: string, featureId: string, status: string) {
  const response = await apiClient.patch(`/api/projects/${projectId}/features/${featureId}`, { status })
  return response.data
}

// ═══════════════════════════════════════════════════════════
// DAG OPERATIONS
// ═══════════════════════════════════════════════════════════

/**
 * Fetch the current DAG status for a project
 */
export async function fetchDagStatus(projectId: string) {
  const response = await apiClient.get(`/api/projects/${projectId}/dag/status`)
  return response.data
}

/**
 * Validate the DAG for a project (check for cycles, missing dependencies, etc.)
 */
export async function validateDag(projectId: string) {
  const response = await apiClient.post(`/api/projects/${projectId}/dag/validate`)
  return response.data
}

// ═══════════════════════════════════════════════════════════
// WORKFLOW PROGRESS
// ═══════════════════════════════════════════════════════════

/**
 * Fetch workflow progress for a project
 */
export async function fetchWorkflowProgress(projectId: string) {
  const response = await apiClient.get(`/api/projects/${projectId}/workflow/progress`)
  return response.data
}
