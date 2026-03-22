/**
 * Workspace Service
 *
 * Handles HTTP communication for workspace and project management operations.
 */

import { apiClient } from './api'

/**
 * List all workspaces
 */
export async function listWorkspaces() {
  const response = await apiClient.get('/api/workspaces')
  return response.data
}

/**
 * Create a new workspace
 */
export async function createWorkspace(data: { name: string; description?: string }) {
  const response = await apiClient.post('/api/workspaces', data)
  return response.data
}

/**
 * Get a single workspace by ID
 */
export async function getWorkspace(id: string) {
  const response = await apiClient.get(`/api/workspaces/${id}`)
  return response.data
}

/**
 * List all projects in a workspace
 */
export async function listProjects(workspaceId: string) {
  const response = await apiClient.get(`/api/workspaces/${workspaceId}/projects`)
  return response.data
}

/**
 * Onboard (create) a new project within a workspace
 */
export async function onboardProject(
  workspaceId: string,
  data: {
    name: string
    repo_path: string
    archetype: string
    plugin_id?: string
    priority?: number
  }
) {
  const response = await apiClient.post(`/api/workspaces/${workspaceId}/projects`, data)
  return response.data
}

/**
 * Get a single project by ID
 */
export async function getProject(id: string) {
  const response = await apiClient.get(`/api/projects/${id}`)
  return response.data
}

/**
 * Switch active project context
 */
export async function switchProject(id: string) {
  const response = await apiClient.post(`/api/projects/${id}/switch`)
  return response.data
}

/**
 * List available plugins
 */
export async function listPlugins() {
  const response = await apiClient.get('/api/plugins')
  return response.data
}
