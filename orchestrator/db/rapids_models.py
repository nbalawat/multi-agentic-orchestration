"""
Pydantic Database Models for RAPIDS Meta-Orchestrator

These models map directly to the PostgreSQL tables for workspace, project,
project phase, and feature management. They provide:
- Automatic UUID handling (converts asyncpg UUID objects to Python UUID)
- Type safety and validation
- Automatic JSON serialization/deserialization
- Field validation and defaults

Usage:
    from rapids_models import Workspace, Project, ProjectPhase, Feature

    # Automatically handles UUID conversion from database
    workspace = Workspace(**row_dict)
    print(workspace.id)  # Works with both UUID objects and strings
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════
# WORKSPACE MODEL
# ═══════════════════════════════════════════════════════════


class Workspace(BaseModel):
    """
    Top-level workspace container for organizing projects.

    Maps to: workspaces table
    """
    id: UUID
    name: str
    description: Optional[str] = None
    root_path: Optional[str] = None
    status: Literal['active', 'archived', 'paused'] = 'active'
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        """Convert asyncpg UUID to Python UUID"""
        if isinstance(v, UUID):
            return v
        return UUID(str(v))

    @field_validator('metadata', mode='before')
    @classmethod
    def parse_metadata(cls, v):
        """Parse JSON string metadata to dict"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════
# PROJECT MODEL
# ═══════════════════════════════════════════════════════════


class Project(BaseModel):
    """
    A software project within a workspace, tracking its lifecycle phase.

    Maps to: projects table
    """
    id: UUID
    workspace_id: UUID
    name: str
    repo_path: str
    repo_url: Optional[str] = None
    archetype: str  # greenfield, brownfield, enhancement, bugfix, data-modernization, agentic-ai, reverse-engineering
    current_phase: Literal['research', 'analysis', 'plan', 'implement', 'deploy', 'sustain'] = 'research'
    phase_status: Literal['not_started', 'in_progress', 'blocked', 'review', 'complete'] = 'not_started'
    plugin_id: Optional[str] = None
    priority: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    archived: bool = False
    created_at: datetime
    updated_at: datetime

    @field_validator('id', 'workspace_id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        """Convert asyncpg UUID to Python UUID"""
        if isinstance(v, UUID):
            return v
        return UUID(str(v))

    @field_validator('metadata', mode='before')
    @classmethod
    def parse_metadata(cls, v):
        """Parse JSON string metadata to dict"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════
# PROJECT_PHASE MODEL
# ═══════════════════════════════════════════════════════════


class ProjectPhase(BaseModel):
    """
    Phase history and transition tracking for a project.

    Maps to: project_phases table
    """
    id: UUID
    project_id: UUID
    phase: Literal['research', 'analysis', 'plan', 'implement', 'deploy', 'sustain']
    status: Literal['not_started', 'in_progress', 'blocked', 'review', 'complete', 'skipped'] = 'not_started'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    entry_criteria_met: bool = False
    exit_criteria_met: bool = False
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator('id', 'project_id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        """Convert asyncpg UUID to Python UUID"""
        if isinstance(v, UUID):
            return v
        return UUID(str(v))

    @field_validator('artifacts', 'metadata', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """Parse JSON string to dict"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════
# FEATURE MODEL
# ═══════════════════════════════════════════════════════════


class Feature(BaseModel):
    """
    A feature within a project, with dependency tracking and agent assignment.

    Maps to: features table
    """
    id: UUID
    project_id: UUID
    name: str
    description: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)  # List of feature IDs
    acceptance_criteria: List[str] = Field(default_factory=list)
    status: Literal['planned', 'in_progress', 'complete', 'blocked', 'deferred'] = 'planned'
    priority: int = 0
    estimated_complexity: Optional[str] = None  # low, medium, high
    assigned_agent_id: Optional[UUID] = None
    spec_file: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator('id', 'project_id', 'assigned_agent_id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        """Convert asyncpg UUID to Python UUID"""
        if v is None:
            return None
        if isinstance(v, UUID):
            return v
        return UUID(str(v))

    @field_validator('depends_on', 'acceptance_criteria', mode='before')
    @classmethod
    def parse_json_list(cls, v):
        """Parse JSON string to list"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @field_validator('metadata', mode='before')
    @classmethod
    def parse_metadata(cls, v):
        """Parse JSON string metadata to dict"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "Workspace",
    "Project",
    "ProjectPhase",
    "Feature",
]
