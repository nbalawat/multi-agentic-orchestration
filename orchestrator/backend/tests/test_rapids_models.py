"""
Comprehensive tests for the RAPIDS Pydantic models.

All tests use real implementations -- no mocks, no database.
Tests validate model creation, field validation, type coercion, and rejection
of invalid data.
"""

import json
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.rapids_models import Workspace, Project, ProjectPhase, Feature


# ======================================================================
# Helpers
# ======================================================================


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return uuid4()


# ======================================================================
# Workspace Model
# ======================================================================


class TestWorkspace:
    def test_create_workspace(self):
        ws = Workspace(
            id=_uuid(),
            name="My Workspace",
            description="A workspace for testing",
            root_path="/tmp/workspace",
            status="active",
            metadata={},
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.name == "My Workspace"
        assert ws.status == "active"
        assert isinstance(ws.id, UUID)

    def test_workspace_defaults(self):
        ws = Workspace(
            id=_uuid(),
            name="Minimal",
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.description is None
        assert ws.root_path is None
        assert ws.status == "active"
        assert ws.metadata == {}

    def test_workspace_uuid_from_string(self):
        uid = str(_uuid())
        ws = Workspace(
            id=uid,
            name="Test",
            created_at=_now(),
            updated_at=_now(),
        )
        assert isinstance(ws.id, UUID)
        assert str(ws.id) == uid

    def test_workspace_metadata_from_json_string(self):
        ws = Workspace(
            id=_uuid(),
            name="Test",
            metadata='{"key": "value", "count": 42}',
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.metadata == {"key": "value", "count": 42}

    def test_workspace_metadata_dict(self):
        ws = Workspace(
            id=_uuid(),
            name="Test",
            metadata={"direct": True},
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.metadata["direct"] is True

    def test_workspace_invalid_status(self):
        with pytest.raises(Exception):  # ValidationError
            Workspace(
                id=_uuid(),
                name="Test",
                status="invalid_status",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_workspace_valid_statuses(self):
        for status in ["active", "archived", "paused"]:
            ws = Workspace(
                id=_uuid(),
                name="Test",
                status=status,
                created_at=_now(),
                updated_at=_now(),
            )
            assert ws.status == status

    def test_workspace_serialization(self):
        ws = Workspace(
            id=_uuid(),
            name="Test",
            created_at=_now(),
            updated_at=_now(),
        )
        d = ws.model_dump()
        assert "id" in d
        assert "name" in d
        assert d["name"] == "Test"


# ======================================================================
# Project Model
# ======================================================================


class TestProject:
    def test_create_project_all_fields(self):
        ws_id = _uuid()
        proj = Project(
            id=_uuid(),
            workspace_id=ws_id,
            name="My Project",
            repo_path="/tmp/repo",
            repo_url="https://github.com/test/repo",
            archetype="greenfield",
            current_phase="research",
            phase_status="not_started",
            plugin_id="greenfield",
            priority=1,
            metadata={"team": "backend"},
            archived=False,
            created_at=_now(),
            updated_at=_now(),
        )
        assert proj.name == "My Project"
        assert proj.archetype == "greenfield"
        assert isinstance(proj.workspace_id, UUID)
        assert proj.workspace_id == ws_id
        assert proj.priority == 1
        assert proj.metadata["team"] == "backend"

    def test_project_defaults(self):
        proj = Project(
            id=_uuid(),
            workspace_id=_uuid(),
            name="Minimal",
            repo_path="/tmp/repo",
            archetype="greenfield",
            created_at=_now(),
            updated_at=_now(),
        )
        assert proj.current_phase == "research"
        assert proj.phase_status == "not_started"
        assert proj.plugin_id is None
        assert proj.priority == 0
        assert proj.metadata == {}
        assert proj.archived is False
        assert proj.repo_url is None

    def test_project_uuid_conversion(self):
        id_str = str(_uuid())
        ws_str = str(_uuid())
        proj = Project(
            id=id_str,
            workspace_id=ws_str,
            name="Test",
            repo_path="/tmp",
            archetype="greenfield",
            created_at=_now(),
            updated_at=_now(),
        )
        assert isinstance(proj.id, UUID)
        assert isinstance(proj.workspace_id, UUID)

    def test_project_invalid_phase(self):
        with pytest.raises(Exception):
            Project(
                id=_uuid(),
                workspace_id=_uuid(),
                name="Test",
                repo_path="/tmp",
                archetype="greenfield",
                current_phase="invalid_phase",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_project_valid_phases(self):
        for phase in ["research", "analysis", "plan", "implement", "deploy", "sustain"]:
            proj = Project(
                id=_uuid(),
                workspace_id=_uuid(),
                name="Test",
                repo_path="/tmp",
                archetype="greenfield",
                current_phase=phase,
                created_at=_now(),
                updated_at=_now(),
            )
            assert proj.current_phase == phase

    def test_project_invalid_phase_status(self):
        with pytest.raises(Exception):
            Project(
                id=_uuid(),
                workspace_id=_uuid(),
                name="Test",
                repo_path="/tmp",
                archetype="greenfield",
                phase_status="invalid",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_project_valid_phase_statuses(self):
        for status in ["not_started", "in_progress", "blocked", "review", "complete"]:
            proj = Project(
                id=_uuid(),
                workspace_id=_uuid(),
                name="Test",
                repo_path="/tmp",
                archetype="greenfield",
                phase_status=status,
                created_at=_now(),
                updated_at=_now(),
            )
            assert proj.phase_status == status

    def test_project_metadata_from_json_string(self):
        proj = Project(
            id=_uuid(),
            workspace_id=_uuid(),
            name="Test",
            repo_path="/tmp",
            archetype="greenfield",
            metadata='{"tags": ["python", "api"]}',
            created_at=_now(),
            updated_at=_now(),
        )
        assert proj.metadata["tags"] == ["python", "api"]


# ======================================================================
# ProjectPhase Model
# ======================================================================


class TestProjectPhase:
    def test_create_project_phase(self):
        pp = ProjectPhase(
            id=_uuid(),
            project_id=_uuid(),
            phase="research",
            status="in_progress",
            started_at=_now(),
            completed_at=None,
            entry_criteria_met=True,
            exit_criteria_met=False,
            artifacts={"files": ["findings.md"]},
            notes="Starting research",
            metadata={},
            created_at=_now(),
            updated_at=_now(),
        )
        assert pp.phase == "research"
        assert pp.status == "in_progress"
        assert pp.entry_criteria_met is True
        assert pp.exit_criteria_met is False

    def test_project_phase_defaults(self):
        pp = ProjectPhase(
            id=_uuid(),
            project_id=_uuid(),
            phase="plan",
            created_at=_now(),
            updated_at=_now(),
        )
        assert pp.status == "not_started"
        assert pp.started_at is None
        assert pp.completed_at is None
        assert pp.entry_criteria_met is False
        assert pp.exit_criteria_met is False
        assert pp.artifacts == {}
        assert pp.notes is None
        assert pp.metadata == {}

    def test_project_phase_valid_phases(self):
        for phase in ["research", "analysis", "plan", "implement", "deploy", "sustain"]:
            pp = ProjectPhase(
                id=_uuid(),
                project_id=_uuid(),
                phase=phase,
                created_at=_now(),
                updated_at=_now(),
            )
            assert pp.phase == phase

    def test_project_phase_invalid_phase(self):
        with pytest.raises(Exception):
            ProjectPhase(
                id=_uuid(),
                project_id=_uuid(),
                phase="invalid",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_project_phase_valid_statuses(self):
        for status in ["not_started", "in_progress", "blocked", "review", "complete", "skipped"]:
            pp = ProjectPhase(
                id=_uuid(),
                project_id=_uuid(),
                phase="research",
                status=status,
                created_at=_now(),
                updated_at=_now(),
            )
            assert pp.status == status

    def test_project_phase_invalid_status(self):
        with pytest.raises(Exception):
            ProjectPhase(
                id=_uuid(),
                project_id=_uuid(),
                phase="research",
                status="bad_status",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_project_phase_uuid_conversion(self):
        id_str = str(_uuid())
        proj_str = str(_uuid())
        pp = ProjectPhase(
            id=id_str,
            project_id=proj_str,
            phase="research",
            created_at=_now(),
            updated_at=_now(),
        )
        assert isinstance(pp.id, UUID)
        assert isinstance(pp.project_id, UUID)

    def test_project_phase_artifacts_from_json_string(self):
        pp = ProjectPhase(
            id=_uuid(),
            project_id=_uuid(),
            phase="research",
            artifacts='{"files": ["a.md", "b.md"]}',
            created_at=_now(),
            updated_at=_now(),
        )
        assert pp.artifacts["files"] == ["a.md", "b.md"]

    def test_project_phase_metadata_from_json_string(self):
        pp = ProjectPhase(
            id=_uuid(),
            project_id=_uuid(),
            phase="research",
            metadata='{"reviewer": "alice"}',
            created_at=_now(),
            updated_at=_now(),
        )
        assert pp.metadata["reviewer"] == "alice"


# ======================================================================
# Feature Model
# ======================================================================


class TestFeature:
    def test_create_feature(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Authentication Module",
            description="Handles user authentication",
            depends_on=["auth-db", "user-model"],
            acceptance_criteria=["Login works", "Logout works", "Password reset"],
            status="planned",
            priority=1,
            estimated_complexity="high",
            assigned_agent_id=_uuid(),
            spec_file="auth-spec.md",
            metadata={"component": "backend"},
            created_at=_now(),
            updated_at=_now(),
        )
        assert feat.name == "Authentication Module"
        assert feat.depends_on == ["auth-db", "user-model"]
        assert len(feat.acceptance_criteria) == 3
        assert feat.estimated_complexity == "high"
        assert feat.priority == 1
        assert isinstance(feat.assigned_agent_id, UUID)

    def test_feature_defaults(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Minimal Feature",
            created_at=_now(),
            updated_at=_now(),
        )
        assert feat.description is None
        assert feat.depends_on == []
        assert feat.acceptance_criteria == []
        assert feat.status == "planned"
        assert feat.priority == 0
        assert feat.estimated_complexity is None
        assert feat.assigned_agent_id is None
        assert feat.spec_file is None
        assert feat.metadata == {}

    def test_feature_valid_statuses(self):
        for status in ["planned", "in_progress", "complete", "blocked", "deferred"]:
            feat = Feature(
                id=_uuid(),
                project_id=_uuid(),
                name="Test",
                status=status,
                created_at=_now(),
                updated_at=_now(),
            )
            assert feat.status == status

    def test_feature_invalid_status(self):
        with pytest.raises(Exception):
            Feature(
                id=_uuid(),
                project_id=_uuid(),
                name="Test",
                status="invalid_status",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_feature_uuid_conversion(self):
        id_str = str(_uuid())
        proj_str = str(_uuid())
        agent_str = str(_uuid())
        feat = Feature(
            id=id_str,
            project_id=proj_str,
            name="Test",
            assigned_agent_id=agent_str,
            created_at=_now(),
            updated_at=_now(),
        )
        assert isinstance(feat.id, UUID)
        assert isinstance(feat.project_id, UUID)
        assert isinstance(feat.assigned_agent_id, UUID)

    def test_feature_uuid_none_agent(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Test",
            assigned_agent_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        assert feat.assigned_agent_id is None

    def test_feature_depends_on_from_json_string(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Test",
            depends_on='["feat-1", "feat-2"]',
            created_at=_now(),
            updated_at=_now(),
        )
        assert feat.depends_on == ["feat-1", "feat-2"]

    def test_feature_acceptance_criteria_from_json_string(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Test",
            acceptance_criteria='["AC1", "AC2", "AC3"]',
            created_at=_now(),
            updated_at=_now(),
        )
        assert feat.acceptance_criteria == ["AC1", "AC2", "AC3"]

    def test_feature_metadata_from_json_string(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Test",
            metadata='{"effort": 5, "team": "alpha"}',
            created_at=_now(),
            updated_at=_now(),
        )
        assert feat.metadata["effort"] == 5
        assert feat.metadata["team"] == "alpha"

    def test_feature_serialization(self):
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Test Feature",
            depends_on=["a", "b"],
            acceptance_criteria=["Works"],
            created_at=_now(),
            updated_at=_now(),
        )
        d = feat.model_dump()
        assert d["name"] == "Test Feature"
        assert d["depends_on"] == ["a", "b"]
        assert d["acceptance_criteria"] == ["Works"]


# ======================================================================
# UUID Conversion Edge Cases
# ======================================================================


class TestUUIDConversion:
    def test_uuid_object_passthrough(self):
        uid = _uuid()
        ws = Workspace(
            id=uid,
            name="Test",
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.id == uid

    def test_uuid_from_string(self):
        uid_str = "12345678-1234-5678-1234-567812345678"
        ws = Workspace(
            id=uid_str,
            name="Test",
            created_at=_now(),
            updated_at=_now(),
        )
        assert str(ws.id) == uid_str

    def test_invalid_uuid_string_raises(self):
        with pytest.raises(Exception):
            Workspace(
                id="not-a-uuid",
                name="Test",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_multiple_uuid_fields_converted(self):
        """Project has both id and workspace_id as UUID fields."""
        id_str = str(_uuid())
        ws_str = str(_uuid())
        proj = Project(
            id=id_str,
            workspace_id=ws_str,
            name="Test",
            repo_path="/tmp",
            archetype="greenfield",
            created_at=_now(),
            updated_at=_now(),
        )
        assert isinstance(proj.id, UUID)
        assert isinstance(proj.workspace_id, UUID)
        assert str(proj.id) == id_str
        assert str(proj.workspace_id) == ws_str


# ======================================================================
# Metadata JSON Parsing
# ======================================================================


class TestMetadataJSONParsing:
    def test_empty_json_string(self):
        ws = Workspace(
            id=_uuid(),
            name="Test",
            metadata="{}",
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.metadata == {}

    def test_nested_json_metadata(self):
        meta = {"config": {"db": {"host": "localhost", "port": 5432}}, "tags": ["a", "b"]}
        ws = Workspace(
            id=_uuid(),
            name="Test",
            metadata=json.dumps(meta),
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.metadata["config"]["db"]["port"] == 5432

    def test_dict_passthrough(self):
        meta = {"key": "value"}
        ws = Workspace(
            id=_uuid(),
            name="Test",
            metadata=meta,
            created_at=_now(),
            updated_at=_now(),
        )
        assert ws.metadata == meta

    def test_feature_list_fields_from_json(self):
        """depends_on and acceptance_criteria should parse JSON strings."""
        feat = Feature(
            id=_uuid(),
            project_id=_uuid(),
            name="Test",
            depends_on='["dep-1"]',
            acceptance_criteria='["AC-1", "AC-2"]',
            created_at=_now(),
            updated_at=_now(),
        )
        assert isinstance(feat.depends_on, list)
        assert isinstance(feat.acceptance_criteria, list)
        assert feat.depends_on[0] == "dep-1"

    def test_project_phase_artifacts_from_json(self):
        pp = ProjectPhase(
            id=_uuid(),
            project_id=_uuid(),
            phase="research",
            artifacts='{"output": ["file1.md"]}',
            metadata='{"reviewer": "bob"}',
            created_at=_now(),
            updated_at=_now(),
        )
        assert pp.artifacts["output"] == ["file1.md"]
        assert pp.metadata["reviewer"] == "bob"


# ======================================================================
# from_attributes Config
# ======================================================================


class TestFromAttributes:
    def test_workspace_from_attributes(self):
        """Config.from_attributes should allow creating from ORM-like objects."""

        class Row:
            id = _uuid()
            name = "Test"
            description = None
            root_path = None
            status = "active"
            metadata = {}
            created_at = _now()
            updated_at = _now()

        ws = Workspace.model_validate(Row())
        assert ws.name == "Test"

    def test_project_from_attributes(self):
        class Row:
            id = _uuid()
            workspace_id = _uuid()
            name = "Proj"
            repo_path = "/tmp"
            repo_url = None
            archetype = "greenfield"
            current_phase = "research"
            phase_status = "not_started"
            plugin_id = None
            priority = 0
            metadata = {}
            archived = False
            created_at = _now()
            updated_at = _now()

        proj = Project.model_validate(Row())
        assert proj.name == "Proj"
        assert proj.archetype == "greenfield"
