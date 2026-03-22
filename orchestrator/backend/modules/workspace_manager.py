"""
Workspace Manager

Business logic for workspace/project lifecycle, context switching,
and project onboarding.
"""

import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone

from . import config
from .rapids_database import (
    create_workspace, get_workspace, get_workspace_by_name, list_workspaces,
    update_workspace, archive_workspace as db_archive_workspace,
    create_project, get_project, get_project_by_name, list_projects,
    update_project, archive_project as db_archive_project,
    init_project_phases,
)
from .project_state import ProjectState
from .phase_engine import PhaseEngine
from .plugin_loader import PluginLoader
from .git_worktree import GitWorktreeManager


class WorkspaceManager:
    """Manages workspace/project lifecycle and context switching."""

    def __init__(self, plugin_loader: Optional[PluginLoader] = None):
        self._plugin_loader = plugin_loader
        self._active_workspace_id: Optional[str] = None
        self._active_project_id: Optional[str] = None
        self._project_contexts: Dict[str, Dict] = {}  # project_id -> {repo_path, archetype, etc.}

    # =========================================================================
    # Workspace operations
    # =========================================================================

    async def create_workspace(self, name: str, description: str = None) -> Dict:
        """Create a new workspace. Returns workspace dict."""
        workspace_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        workspace = {
            "id": workspace_id,
            "name": name,
            "description": description or "",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }

        await create_workspace(workspace)

        # Set as active workspace if none is active
        if self._active_workspace_id is None:
            self._active_workspace_id = workspace_id

        return workspace

    async def list_workspaces(self) -> List[Dict]:
        """List all active workspaces."""
        workspaces = await list_workspaces()
        return [w for w in workspaces if w.get("status") != "archived"]

    async def get_workspace_details(self, workspace_id: str) -> Optional[Dict]:
        """Get workspace with project summary."""
        workspace = await get_workspace(workspace_id)
        if workspace is None:
            return None

        # Attach project summary
        projects = await list_projects(workspace_id)
        active_projects = [p for p in projects if p.get("status") != "archived"]

        workspace["projects"] = active_projects
        workspace["project_count"] = len(active_projects)
        return workspace

    async def archive_workspace(self, workspace_id: str) -> bool:
        """Archive a workspace. Returns True on success."""
        workspace = await get_workspace(workspace_id)
        if workspace is None:
            return False

        success = await db_archive_workspace(workspace_id)

        # Clear active workspace if it was the archived one
        if success and self._active_workspace_id == workspace_id:
            self._active_workspace_id = None
            self._active_project_id = None

        return success

    # =========================================================================
    # Project operations
    # =========================================================================

    async def onboard_project(
        self,
        workspace_id: str,
        name: str,
        repo_path: str,
        archetype: str,
        repo_url: str = None,
        plugin_id: str = None,
    ) -> Dict:
        """
        Onboard a new project into a workspace:
        1. Validate repo_path exists and is a git repo
        2. Create project in database
        3. Initialize all 6 project phases in database
        4. Initialize .rapids/ directory in the project repo
        5. Load plugin for the archetype
        6. Return project details
        """
        # 1. Validate repo_path and ensure git is initialized
        repo = Path(repo_path)
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        if not repo.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo_path}")

        # Initialize git if not already a git repo
        git_mgr = GitWorktreeManager(repo_path)
        if not git_mgr.is_git_repo():
            git_mgr.init_git_repo()

        # Verify the workspace exists
        workspace = await get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        # Check for duplicate project name within workspace
        existing = await get_project_by_name(workspace_id, name)
        if existing is not None:
            raise ValueError(
                f"A project named '{name}' already exists in this workspace"
            )

        # 2. Create project in database
        project_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        resolved_plugin = plugin_id or archetype

        project = {
            "id": project_id,
            "workspace_id": workspace_id,
            "name": name,
            "repo_path": str(repo.resolve()),
            "repo_url": repo_url or "",
            "archetype": archetype,
            "plugin_id": resolved_plugin,
            "status": "active",
            "current_phase": "research",
            "created_at": now,
            "updated_at": now,
        }

        await create_project(project)

        # 3. Initialize all 6 project phases in database
        await init_project_phases(project_id)

        # 4. Initialize .rapids/ directory in the project repo
        project_state = ProjectState(
            repo_path=str(repo.resolve()),
            project_id=project_id,
            archetype=archetype,
            plugin=resolved_plugin,
        )
        project_state.init_rapids_dir()

        # 5. Load plugin for the archetype
        plugin_info = None
        if self._plugin_loader is not None:
            try:
                plugin_info = self._plugin_loader.load_plugin(resolved_plugin)
            except Exception:
                # Plugin loading is non-fatal; project can still be used
                plugin_info = None

        # 6. Cache project context
        self._project_contexts[project_id] = {
            "name": name,
            "repo_path": str(repo.resolve()),
            "archetype": archetype,
            "plugin_id": resolved_plugin,
            "plugin_info": plugin_info,
        }

        # Set as active project
        self._active_workspace_id = workspace_id
        self._active_project_id = project_id

        project["plugin_info"] = plugin_info
        return project

    async def list_projects(self, workspace_id: str) -> List[Dict]:
        """List all projects in a workspace with phase summaries."""
        projects = await list_projects(workspace_id)
        result = []
        for project in projects:
            if project.get("status") == "archived":
                continue
            # Attach a lightweight phase summary
            repo_path = project.get("repo_path", "")
            rapids_dir = Path(repo_path) / ".rapids" if repo_path else None
            if rapids_dir and rapids_dir.exists():
                try:
                    engine = PhaseEngine(rapids_dir)
                    project["current_phase"] = engine.get_current_phase()
                    project["phases"] = engine.get_all_phases()
                except Exception:
                    pass
            result.append(project)
        return result

    async def get_project_details(self, project_id: str) -> Optional[Dict]:
        """Get project with full phase and feature info."""
        project = await get_project(project_id)
        if project is None:
            return None

        # Convert Pydantic model to dict if needed
        if hasattr(project, "model_dump"):
            project = project.model_dump()
        elif hasattr(project, "dict"):
            project = project.dict()
        elif not isinstance(project, dict):
            project = dict(project)

        repo_path = project.get("repo_path", "")
        rapids_dir = Path(repo_path) / ".rapids" if repo_path else None

        if rapids_dir and rapids_dir.exists():
            try:
                engine = PhaseEngine(rapids_dir)
                project["current_phase"] = engine.get_current_phase()
                project["phases"] = engine.get_all_phases()
            except Exception:
                pass

            # Attach feature info
            archetype = project.get("archetype", "")
            plugin_id = project.get("plugin_id", archetype)
            ps = ProjectState(repo_path, project_id, archetype, plugin_id)
            project["feature_specs"] = [
                str(f) for f in ps.get_feature_specs()
            ]
            spec_content = ps.read_spec()
            project["has_spec"] = spec_content is not None and len(spec_content) > 0

        return project

    async def archive_project(self, project_id: str) -> bool:
        """Archive a project. Returns True on success."""
        project = await get_project(project_id)
        if project is None:
            return False

        success = await db_archive_project(project_id)

        if success:
            # Clean up context cache
            self._project_contexts.pop(project_id, None)
            if self._active_project_id == project_id:
                self._active_project_id = None

        return success

    # =========================================================================
    # Context switching
    # =========================================================================

    async def switch_project(self, project_id: str) -> Dict:
        """
        Switch the active project context:
        1. Load project from DB
        2. Update config with project's repo_path as working dir
        3. Load project's plugin
        4. Return project info
        """
        # 1. Load project from DB
        project = await get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        # Convert Pydantic model to dict if needed
        if hasattr(project, "model_dump"):
            project = project.model_dump()
        elif hasattr(project, "dict"):
            project = project.dict()
        elif not isinstance(project, dict):
            project = dict(project)

        if project.get("status") == "archived":
            raise ValueError(f"Cannot switch to archived project: {project_id}")

        repo_path = project.get("repo_path", "")
        archetype = project.get("archetype", "")
        plugin_id = project.get("plugin_id", archetype)
        workspace_id = project.get("workspace_id", "")

        # 2. Update config with project's repo_path as working dir
        if repo_path:
            config.set_working_dir(repo_path)

        # 3. Load project's plugin
        plugin_info = None
        if self._plugin_loader is not None:
            try:
                plugin_info = self._plugin_loader.load_plugin(plugin_id)
            except Exception:
                plugin_info = None

        # Update context cache
        self._project_contexts[project_id] = {
            "name": project.get("name", "unknown"),
            "repo_path": repo_path,
            "archetype": archetype,
            "plugin_id": plugin_id,
            "plugin_info": plugin_info,
        }

        # 4. Set active IDs
        self._active_workspace_id = workspace_id
        self._active_project_id = project_id

        project["plugin_info"] = plugin_info
        return project

    def get_active_project_id(self) -> Optional[str]:
        """Get the currently active project ID."""
        return self._active_project_id

    def get_active_workspace_id(self) -> Optional[str]:
        """Get the currently active workspace ID."""
        return self._active_workspace_id

    async def get_active_project(self) -> Optional[Dict]:
        """Get the currently active project details."""
        if self._active_project_id is None:
            return None
        return await self.get_project_details(self._active_project_id)

    # =========================================================================
    # Project state helpers
    # =========================================================================

    def get_project_state(
        self, repo_path: str, project_id: str, archetype: str, plugin: str
    ) -> ProjectState:
        """Create a ProjectState instance for a project."""
        return ProjectState(
            repo_path=repo_path,
            project_id=project_id,
            archetype=archetype,
            plugin=plugin,
        )

    def get_phase_engine(
        self, repo_path: str, criteria_overrides: Dict = None
    ) -> PhaseEngine:
        """Create a PhaseEngine instance for a project."""
        rapids_dir = Path(repo_path) / ".rapids"
        return PhaseEngine(rapids_dir=rapids_dir, criteria_overrides=criteria_overrides)
