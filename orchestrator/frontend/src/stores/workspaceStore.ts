/**
 * Workspace Store
 *
 * Pinia store for managing workspaces, projects, and plugins.
 * Provides state management and API integration for the workspace/project hierarchy.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as workspaceService from '../services/workspaceService'

// ═══════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════

export interface Workspace {
  id: string
  name: string
  description?: string
  status: string
  created_at: string
}

export interface Project {
  id: string
  workspace_id: string
  name: string
  repo_path: string
  archetype: string
  current_phase: string
  phase_status: string
  plugin_id?: string
  priority: number
}

export interface Plugin {
  name: string
  archetype: string
  description: string
  version: string
}

// ═══════════════════════════════════════════════════════════
// STORE
// ═══════════════════════════════════════════════════════════

export const useWorkspaceStore = defineStore('workspace', () => {
  // ═══════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════

  const workspaces = ref<Workspace[]>([])
  const activeWorkspaceId = ref<string | null>(null)
  const projects = ref<Project[]>([])
  const activeProjectId = ref<string | null>(null)
  const plugins = ref<Plugin[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ═══════════════════════════════════════════════════════════
  // GETTERS
  // ═══════════════════════════════════════════════════════════

  /** The currently active workspace object */
  const activeWorkspace = computed(() =>
    activeWorkspaceId.value
      ? workspaces.value.find(w => w.id === activeWorkspaceId.value) ?? null
      : null
  )

  /** The currently active project object */
  const activeProject = computed(() =>
    activeProjectId.value
      ? projects.value.find(p => p.id === activeProjectId.value) ?? null
      : null
  )

  /** Projects grouped by their current_phase */
  const projectsByPhase = computed(() => {
    const grouped: Record<string, Project[]> = {}
    for (const project of projects.value) {
      const phase = project.current_phase || 'unknown'
      if (!grouped[phase]) {
        grouped[phase] = []
      }
      grouped[phase].push(project)
    }
    return grouped
  })

  /** Number of projects in the active workspace */
  const projectCount = computed(() => projects.value.length)

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - WORKSPACES
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch all workspaces from the backend
   */
  async function fetchWorkspaces() {
    isLoading.value = true
    error.value = null
    try {
      const data = await workspaceService.listWorkspaces()
      workspaces.value = data.workspaces ?? data
      console.log(`Loaded ${workspaces.value.length} workspaces`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch workspaces'
      error.value = message
      console.error('Failed to fetch workspaces:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Create a new workspace
   */
  async function createWorkspace(name: string, description?: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await workspaceService.createWorkspace({ name, description })
      const workspace: Workspace = data.workspace ?? data
      workspaces.value = [...workspaces.value, workspace]
      console.log(`Created workspace: ${workspace.name} (${workspace.id})`)
      return workspace
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create workspace'
      error.value = message
      console.error('Failed to create workspace:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Set the active workspace and load its projects
   */
  async function setActiveWorkspace(workspaceId: string) {
    activeWorkspaceId.value = workspaceId
    // Persist selection
    try {
      localStorage.setItem('active_workspace_id', workspaceId)
    } catch (err) {
      console.warn('Failed to persist active workspace:', err)
    }
    // Load projects for the newly selected workspace
    await fetchProjects(workspaceId)
  }

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - PROJECTS
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch all projects for a given workspace
   */
  async function fetchProjects(workspaceId: string) {
    isLoading.value = true
    error.value = null
    try {
      const data = await workspaceService.listProjects(workspaceId)
      projects.value = data.projects ?? data
      console.log(`Loaded ${projects.value.length} projects for workspace ${workspaceId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch projects'
      error.value = message
      console.error('Failed to fetch projects:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Onboard (create) a new project in the active workspace
   */
  async function onboardProject(
    workspaceId: string,
    data: {
      name: string
      repo_path: string
      archetype: string
      plugin_id?: string
      priority?: number
    }
  ) {
    isLoading.value = true
    error.value = null
    try {
      const result = await workspaceService.onboardProject(workspaceId, data)
      const project: Project = result.project ?? result
      projects.value = [...projects.value, project]
      console.log(`Onboarded project: ${project.name} (${project.id})`)
      return project
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to onboard project'
      error.value = message
      console.error('Failed to onboard project:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Switch the active project context
   */
  async function switchProject(projectId: string) {
    isLoading.value = true
    error.value = null
    try {
      await workspaceService.switchProject(projectId)
      activeProjectId.value = projectId
      // Persist selection
      try {
        localStorage.setItem('active_project_id', projectId)
      } catch (err) {
        console.warn('Failed to persist active project:', err)
      }
      console.log(`Switched to project: ${projectId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to switch project'
      error.value = message
      console.error('Failed to switch project:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // ═══════════════════════════════════════════════════════════
  // ACTIONS - PLUGINS
  // ═══════════════════════════════════════════════════════════

  /**
   * Fetch available plugins from the backend
   */
  async function fetchPlugins() {
    isLoading.value = true
    error.value = null
    try {
      const data = await workspaceService.listPlugins()
      plugins.value = data.plugins ?? data
      console.log(`Loaded ${plugins.value.length} plugins`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch plugins'
      error.value = message
      console.error('Failed to fetch plugins:', err)
    } finally {
      isLoading.value = false
    }
  }

  // ═══════════════════════════════════════════════════════════
  // INITIALIZATION
  // ═══════════════════════════════════════════════════════════

  /**
   * Initialize the workspace store: load workspaces, restore persisted selections
   */
  async function initialize() {
    console.log('Initializing workspace store...')

    await fetchWorkspaces()

    // Restore persisted active workspace
    try {
      const savedWorkspaceId = localStorage.getItem('active_workspace_id')
      if (savedWorkspaceId && workspaces.value.some(w => w.id === savedWorkspaceId)) {
        await setActiveWorkspace(savedWorkspaceId)
      } else if (workspaces.value.length > 0) {
        // Default to first workspace
        await setActiveWorkspace(workspaces.value[0].id)
      }
    } catch (err) {
      console.warn('Failed to restore workspace selection:', err)
    }

    // Restore persisted active project
    try {
      const savedProjectId = localStorage.getItem('active_project_id')
      if (savedProjectId && projects.value.some(p => p.id === savedProjectId)) {
        activeProjectId.value = savedProjectId
      }
    } catch (err) {
      console.warn('Failed to restore project selection:', err)
    }

    // Load plugins
    await fetchPlugins()

    console.log('Workspace store initialized')
  }

  // ═══════════════════════════════════════════════════════════
  // RETURN PUBLIC API
  // ═══════════════════════════════════════════════════════════

  return {
    // State
    workspaces,
    activeWorkspaceId,
    projects,
    activeProjectId,
    plugins,
    isLoading,
    error,

    // Getters
    activeWorkspace,
    activeProject,
    projectsByPhase,
    projectCount,

    // Actions
    fetchWorkspaces,
    createWorkspace,
    setActiveWorkspace,
    fetchProjects,
    onboardProject,
    switchProject,
    fetchPlugins,
    initialize
  }
})
