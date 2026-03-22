"""
RAPIDS Database Operations

Database operations for the RAPIDS meta-orchestrator providing CRUD for:
- Workspaces (top-level containers)
- Projects (software projects within workspaces)
- ProjectPhases (phase lifecycle tracking)
- Features (feature-level work items with dependencies)

Uses the shared asyncpg connection pool from the database module.

Reference:
- orchestrator/backend/modules/database.py (connection pool, query patterns)
- orchestrator/db/rapids_models.py (Pydantic models)
"""

import uuid
import json
from typing import Optional, List, Dict, Any

from .database import get_pool, get_connection
from orchestrator.db.rapids_models import Workspace, Project, ProjectPhase, Feature


# ═══════════════════════════════════════════════════════════
# WORKSPACE CRUD
# ═══════════════════════════════════════════════════════════


async def create_workspace(
    name: str,
    description: str = None,
    root_path: str = None,
    metadata: Dict[str, Any] = None,
) -> Workspace:
    """
    Create a new workspace.

    Args:
        name: Workspace name (must be unique)
        description: Optional description
        root_path: Optional filesystem root path
        metadata: Optional JSONB metadata

    Returns:
        Workspace model instance
    """
    async with get_connection() as conn:
        workspace_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO workspaces (
                id, name, description, root_path, status,
                metadata, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW(), NOW())
            """,
            workspace_id,
            name,
            description,
            root_path,
            "active",
            json.dumps(metadata or {}),
        )

        row = await conn.fetchrow(
            "SELECT * FROM workspaces WHERE id = $1", workspace_id
        )
        return Workspace(**dict(row))


async def get_workspace(workspace_id: uuid.UUID) -> Optional[Workspace]:
    """
    Get a workspace by ID.

    Args:
        workspace_id: UUID of the workspace

    Returns:
        Workspace model instance or None if not found
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM workspaces WHERE id = $1", workspace_id
        )
        if row:
            return Workspace(**dict(row))
        return None


async def get_workspace_by_name(name: str) -> Optional[Workspace]:
    """
    Get a workspace by name.

    Args:
        name: Workspace name

    Returns:
        Workspace model instance or None if not found
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM workspaces WHERE name = $1", name
        )
        if row:
            return Workspace(**dict(row))
        return None


async def list_workspaces(status: str = None) -> List[Workspace]:
    """
    List workspaces, optionally filtered by status.

    Args:
        status: Optional status filter ('active', 'archived', 'paused')

    Returns:
        List of Workspace model instances
    """
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM workspaces WHERE status = $1 ORDER BY created_at DESC",
                status,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM workspaces ORDER BY created_at DESC"
            )
        return [Workspace(**dict(row)) for row in rows]


async def update_workspace(
    workspace_id: uuid.UUID, **kwargs
) -> Optional[Workspace]:
    """
    Update workspace fields.

    Args:
        workspace_id: UUID of the workspace
        **kwargs: Fields to update (name, description, root_path, status, metadata)

    Returns:
        Updated Workspace model instance or None if not found
    """
    if not kwargs:
        return await get_workspace(workspace_id)

    set_clauses = []
    values = []
    idx = 1

    for key, value in kwargs.items():
        if key == "metadata":
            set_clauses.append(f"{key} = ${idx}::jsonb")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
        idx += 1

    set_clauses.append(f"updated_at = NOW()")
    values.append(workspace_id)

    query = f"""
        UPDATE workspaces
        SET {', '.join(set_clauses)}
        WHERE id = ${idx}
    """

    async with get_connection() as conn:
        await conn.execute(query, *values)
        row = await conn.fetchrow(
            "SELECT * FROM workspaces WHERE id = $1", workspace_id
        )
        if row:
            return Workspace(**dict(row))
        return None


async def archive_workspace(workspace_id: uuid.UUID) -> Optional[Workspace]:
    """
    Archive a workspace by setting its status to 'archived'.

    Args:
        workspace_id: UUID of the workspace

    Returns:
        Updated Workspace model instance or None if not found
    """
    return await update_workspace(workspace_id, status="archived")


# ═══════════════════════════════════════════════════════════
# PROJECT CRUD
# ═══════════════════════════════════════════════════════════


async def create_project(
    workspace_id: uuid.UUID,
    name: str,
    repo_path: str,
    archetype: str,
    repo_url: str = None,
    plugin_id: str = None,
    priority: int = 0,
    metadata: Dict[str, Any] = None,
) -> Project:
    """
    Create a new project within a workspace.

    Args:
        workspace_id: UUID of the parent workspace
        name: Project name
        repo_path: Filesystem path to the repository
        archetype: Project archetype (greenfield, brownfield, enhancement, etc.)
        repo_url: Optional remote repository URL
        plugin_id: Optional plugin identifier
        priority: Priority level (default 0)
        metadata: Optional JSONB metadata

    Returns:
        Project model instance
    """
    async with get_connection() as conn:
        project_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO projects (
                id, workspace_id, name, repo_path, repo_url, archetype,
                current_phase, phase_status, plugin_id, priority,
                metadata, archived, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, NOW(), NOW())
            """,
            project_id,
            workspace_id,
            name,
            repo_path,
            repo_url,
            archetype,
            "research",
            "not_started",
            plugin_id,
            priority,
            json.dumps(metadata or {}),
            False,
        )

        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1", project_id
        )
        return Project(**dict(row))


async def get_project(project_id: uuid.UUID) -> Optional[Project]:
    """
    Get a project by ID.

    Args:
        project_id: UUID of the project

    Returns:
        Project model instance or None if not found
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1 AND archived = false",
            project_id,
        )
        if row:
            return Project(**dict(row))
        return None


async def get_project_by_name(
    workspace_id: uuid.UUID, name: str
) -> Optional[Project]:
    """
    Get a project by name within a workspace.

    Args:
        workspace_id: UUID of the parent workspace
        name: Project name

    Returns:
        Project model instance or None if not found
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM projects
            WHERE workspace_id = $1 AND name = $2 AND archived = false
            """,
            workspace_id,
            name,
        )
        if row:
            return Project(**dict(row))
        return None


async def list_projects(
    workspace_id: uuid.UUID, archived: bool = False
) -> List[Project]:
    """
    List projects in a workspace.

    Args:
        workspace_id: UUID of the parent workspace
        archived: If True, include archived projects

    Returns:
        List of Project model instances
    """
    async with get_connection() as conn:
        if archived:
            rows = await conn.fetch(
                """
                SELECT * FROM projects
                WHERE workspace_id = $1
                ORDER BY priority DESC, created_at DESC
                """,
                workspace_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM projects
                WHERE workspace_id = $1 AND archived = false
                ORDER BY priority DESC, created_at DESC
                """,
                workspace_id,
            )
        return [Project(**dict(row)) for row in rows]


async def update_project(
    project_id: uuid.UUID, **kwargs
) -> Optional[Project]:
    """
    Update project fields.

    Args:
        project_id: UUID of the project
        **kwargs: Fields to update

    Returns:
        Updated Project model instance or None if not found
    """
    if not kwargs:
        return await get_project(project_id)

    set_clauses = []
    values = []
    idx = 1

    for key, value in kwargs.items():
        if key == "metadata":
            set_clauses.append(f"{key} = ${idx}::jsonb")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
        idx += 1

    set_clauses.append(f"updated_at = NOW()")
    values.append(project_id)

    query = f"""
        UPDATE projects
        SET {', '.join(set_clauses)}
        WHERE id = ${idx}
    """

    async with get_connection() as conn:
        await conn.execute(query, *values)
        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1", project_id
        )
        if row:
            return Project(**dict(row))
        return None


async def update_project_phase(
    project_id: uuid.UUID, current_phase: str, phase_status: str
) -> Optional[Project]:
    """
    Update a project's current phase and phase status.

    Args:
        project_id: UUID of the project
        current_phase: New phase value
        phase_status: New phase status value

    Returns:
        Updated Project model instance or None if not found
    """
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET current_phase = $1, phase_status = $2, updated_at = NOW()
            WHERE id = $3
            """,
            current_phase,
            phase_status,
            project_id,
        )

        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1", project_id
        )
        if row:
            return Project(**dict(row))
        return None


async def archive_project(project_id: uuid.UUID) -> Optional[Project]:
    """
    Archive a project by setting archived=true.

    Args:
        project_id: UUID of the project

    Returns:
        Updated Project model instance or None if not found
    """
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET archived = true, updated_at = NOW()
            WHERE id = $1
            """,
            project_id,
        )

        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1", project_id
        )
        if row:
            return Project(**dict(row))
        return None


# ═══════════════════════════════════════════════════════════
# PROJECT PHASE CRUD
# ═══════════════════════════════════════════════════════════

# The six RAPIDS phases in order
RAPIDS_PHASES = ["research", "analysis", "plan", "implement", "deploy", "sustain"]


async def create_project_phase(
    project_id: uuid.UUID, phase: str
) -> ProjectPhase:
    """
    Create a single project phase record.

    Args:
        project_id: UUID of the parent project
        phase: Phase name (research, analysis, plan, implement, deploy, sustain)

    Returns:
        ProjectPhase model instance
    """
    async with get_connection() as conn:
        phase_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO project_phases (
                id, project_id, phase, status,
                entry_criteria_met, exit_criteria_met,
                artifacts, metadata, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, NOW(), NOW())
            """,
            phase_id,
            project_id,
            phase,
            "not_started",
            False,
            False,
            json.dumps({}),
            json.dumps({}),
        )

        row = await conn.fetchrow(
            "SELECT * FROM project_phases WHERE id = $1", phase_id
        )
        return ProjectPhase(**dict(row))


async def get_project_phase(
    project_id: uuid.UUID, phase: str
) -> Optional[ProjectPhase]:
    """
    Get a specific phase for a project.

    Args:
        project_id: UUID of the project
        phase: Phase name

    Returns:
        ProjectPhase model instance or None if not found
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM project_phases
            WHERE project_id = $1 AND phase = $2
            """,
            project_id,
            phase,
        )
        if row:
            return ProjectPhase(**dict(row))
        return None


async def list_project_phases(
    project_id: uuid.UUID,
) -> List[ProjectPhase]:
    """
    List all phases for a project in order.

    Args:
        project_id: UUID of the project

    Returns:
        List of ProjectPhase model instances ordered by phase sequence
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM project_phases
            WHERE project_id = $1
            ORDER BY CASE phase
                WHEN 'research' THEN 1
                WHEN 'analysis' THEN 2
                WHEN 'plan' THEN 3
                WHEN 'implement' THEN 4
                WHEN 'deploy' THEN 5
                WHEN 'sustain' THEN 6
            END
            """,
            project_id,
        )
        return [ProjectPhase(**dict(row)) for row in rows]


async def update_project_phase_status(
    project_id: uuid.UUID, phase: str, status: str, **kwargs
) -> Optional[ProjectPhase]:
    """
    Update a project phase's status and optional fields.

    Automatically sets started_at when status changes to 'in_progress'
    and completed_at when status changes to 'complete'.

    Args:
        project_id: UUID of the project
        phase: Phase name
        status: New status value
        **kwargs: Additional fields to update (entry_criteria_met, exit_criteria_met,
                  artifacts, notes, metadata)

    Returns:
        Updated ProjectPhase model instance or None if not found
    """
    set_clauses = ["status = $1", "updated_at = NOW()"]
    values: list = [status]
    idx = 2

    # Auto-set timestamps based on status transitions
    if status == "in_progress":
        set_clauses.append(f"started_at = COALESCE(started_at, NOW())")
    elif status == "complete":
        set_clauses.append(f"completed_at = NOW()")

    for key, value in kwargs.items():
        if key in ("artifacts", "metadata"):
            set_clauses.append(f"{key} = ${idx}::jsonb")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
        idx += 1

    values.append(project_id)
    values.append(phase)

    query = f"""
        UPDATE project_phases
        SET {', '.join(set_clauses)}
        WHERE project_id = ${idx} AND phase = ${idx + 1}
    """

    async with get_connection() as conn:
        await conn.execute(query, *values)
        row = await conn.fetchrow(
            """
            SELECT * FROM project_phases
            WHERE project_id = $1 AND phase = $2
            """,
            project_id,
            phase,
        )
        if row:
            return ProjectPhase(**dict(row))
        return None


async def init_project_phases(
    project_id: uuid.UUID,
) -> List[ProjectPhase]:
    """
    Initialize all 6 RAPIDS phases for a project.

    Creates phase records for: research, analysis, plan, implement, deploy, sustain.

    Args:
        project_id: UUID of the project

    Returns:
        List of created ProjectPhase model instances in phase order
    """
    phases = []
    for phase_name in RAPIDS_PHASES:
        phase = await create_project_phase(project_id, phase_name)
        phases.append(phase)
    return phases


# ═══════════════════════════════════════════════════════════
# FEATURE CRUD
# ═══════════════════════════════════════════════════════════


async def create_feature(
    project_id: uuid.UUID,
    name: str,
    description: str = None,
    depends_on: List[str] = None,
    acceptance_criteria: List[str] = None,
    priority: int = 0,
    estimated_complexity: str = None,
    spec_file: str = None,
    metadata: Dict[str, Any] = None,
) -> Feature:
    """
    Create a new feature within a project.

    Args:
        project_id: UUID of the parent project
        name: Feature name
        description: Optional description
        depends_on: Optional list of feature IDs this feature depends on
        acceptance_criteria: Optional list of acceptance criteria strings
        priority: Priority level (default 0)
        estimated_complexity: Optional complexity estimate (low, medium, high)
        spec_file: Optional path to specification file
        metadata: Optional JSONB metadata

    Returns:
        Feature model instance
    """
    async with get_connection() as conn:
        feature_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO features (
                id, project_id, name, description, depends_on,
                acceptance_criteria, status, priority, estimated_complexity,
                spec_file, metadata, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11::jsonb,
                NOW(), NOW()
            )
            """,
            feature_id,
            project_id,
            name,
            description,
            json.dumps(depends_on or []),
            json.dumps(acceptance_criteria or []),
            "planned",
            priority,
            estimated_complexity,
            spec_file,
            json.dumps(metadata or {}),
        )

        row = await conn.fetchrow(
            "SELECT * FROM features WHERE id = $1", feature_id
        )
        return Feature(**dict(row))


async def get_feature(feature_id: uuid.UUID) -> Optional[Feature]:
    """
    Get a feature by ID.

    Args:
        feature_id: UUID of the feature

    Returns:
        Feature model instance or None if not found
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM features WHERE id = $1", feature_id
        )
        if row:
            return Feature(**dict(row))
        return None


async def list_features(
    project_id: uuid.UUID, status: str = None
) -> List[Feature]:
    """
    List features for a project, optionally filtered by status.

    Args:
        project_id: UUID of the parent project
        status: Optional status filter (planned, in_progress, complete, blocked, deferred)

    Returns:
        List of Feature model instances
    """
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT * FROM features
                WHERE project_id = $1 AND status = $2
                ORDER BY priority DESC, created_at ASC
                """,
                project_id,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM features
                WHERE project_id = $1
                ORDER BY priority DESC, created_at ASC
                """,
                project_id,
            )
        return [Feature(**dict(row)) for row in rows]


async def update_feature(
    feature_id: uuid.UUID, **kwargs
) -> Optional[Feature]:
    """
    Update feature fields.

    Args:
        feature_id: UUID of the feature
        **kwargs: Fields to update

    Returns:
        Updated Feature model instance or None if not found
    """
    if not kwargs:
        return await get_feature(feature_id)

    set_clauses = []
    values = []
    idx = 1

    for key, value in kwargs.items():
        if key in ("metadata",):
            set_clauses.append(f"{key} = ${idx}::jsonb")
            values.append(json.dumps(value))
        elif key in ("depends_on", "acceptance_criteria"):
            set_clauses.append(f"{key} = ${idx}::jsonb")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
        idx += 1

    set_clauses.append(f"updated_at = NOW()")
    values.append(feature_id)

    query = f"""
        UPDATE features
        SET {', '.join(set_clauses)}
        WHERE id = ${idx}
    """

    async with get_connection() as conn:
        await conn.execute(query, *values)
        row = await conn.fetchrow(
            "SELECT * FROM features WHERE id = $1", feature_id
        )
        if row:
            return Feature(**dict(row))
        return None


async def update_feature_status(
    feature_id: uuid.UUID,
    status: str,
    assigned_agent_id: uuid.UUID = None,
) -> Optional[Feature]:
    """
    Update a feature's status and optionally assign an agent.

    Args:
        feature_id: UUID of the feature
        status: New status value
        assigned_agent_id: Optional UUID of the agent to assign

    Returns:
        Updated Feature model instance or None if not found
    """
    async with get_connection() as conn:
        if assigned_agent_id is not None:
            await conn.execute(
                """
                UPDATE features
                SET status = $1, assigned_agent_id = $2, updated_at = NOW()
                WHERE id = $3
                """,
                status,
                assigned_agent_id,
                feature_id,
            )
        else:
            await conn.execute(
                """
                UPDATE features
                SET status = $1, updated_at = NOW()
                WHERE id = $2
                """,
                status,
                feature_id,
            )

        row = await conn.fetchrow(
            "SELECT * FROM features WHERE id = $1", feature_id
        )
        if row:
            return Feature(**dict(row))
        return None


async def get_ready_features(
    project_id: uuid.UUID,
) -> List[Feature]:
    """
    Get features that are ready to work on (all dependencies complete).

    A feature is ready if:
    - Its status is 'planned'
    - It has no dependencies, OR all of its dependencies have status 'complete'

    Args:
        project_id: UUID of the project

    Returns:
        List of Feature model instances that are ready for work
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT f.* FROM features f
            WHERE f.project_id = $1
              AND f.status = 'planned'
              AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements_text(f.depends_on) AS dep_id
                  WHERE NOT EXISTS (
                      SELECT 1 FROM features f2
                      WHERE f2.id = dep_id::uuid
                        AND f2.status = 'complete'
                  )
              )
            ORDER BY f.priority DESC, f.created_at ASC
            """,
            project_id,
        )
        return [Feature(**dict(row)) for row in rows]


async def bulk_create_features(
    project_id: uuid.UUID, features: List[Dict]
) -> List[Feature]:
    """
    Bulk create features for a project.

    Each feature dict should contain at minimum 'name', and optionally:
    description, depends_on, acceptance_criteria, priority,
    estimated_complexity, spec_file, metadata.

    Args:
        project_id: UUID of the parent project
        features: List of feature dictionaries

    Returns:
        List of created Feature model instances
    """
    created = []
    for feat_data in features:
        feature = await create_feature(
            project_id=project_id,
            name=feat_data["name"],
            description=feat_data.get("description"),
            depends_on=feat_data.get("depends_on"),
            acceptance_criteria=feat_data.get("acceptance_criteria"),
            priority=feat_data.get("priority", 0),
            estimated_complexity=feat_data.get("estimated_complexity"),
            spec_file=feat_data.get("spec_file"),
            metadata=feat_data.get("metadata"),
        )
        created.append(feature)
    return created
