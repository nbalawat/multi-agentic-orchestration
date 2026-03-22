"""
Comprehensive tests for the ProjectState module.

All tests use real implementations -- no mocks.
Uses pytest tmp_path for filesystem operations.
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.project_state import ProjectState, PHASE_DIRS


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def state(tmp_path):
    """A ProjectState instance backed by a temp directory."""
    return ProjectState(
        repo_path=str(tmp_path),
        project_id="proj-001",
        archetype="greenfield",
        plugin="greenfield",
    )


@pytest.fixture
def initialized_state(state):
    """A ProjectState that has been initialized."""
    state.init_rapids_dir()
    return state


# ======================================================================
# init_rapids_dir
# ======================================================================


class TestInitRapidsDir:
    def test_creates_rapids_directory(self, state):
        state.init_rapids_dir()
        assert state.rapids_dir.exists()
        assert state.rapids_dir.is_dir()

    def test_creates_all_phase_subdirectories(self, state):
        state.init_rapids_dir()
        for dir_name in PHASE_DIRS:
            assert (state.rapids_dir / dir_name).exists()
            assert (state.rapids_dir / dir_name).is_dir()

    def test_creates_state_json(self, state):
        state.init_rapids_dir()
        state_path = state.rapids_dir / "state.json"
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data["project_id"] == "proj-001"
        assert data["archetype"] == "greenfield"
        assert data["plugin"] == "greenfield"
        assert data["current_phase"] == "research"

    def test_creates_config_json(self, state):
        state.init_rapids_dir()
        config_path = state.rapids_dir / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["project_id"] == "proj-001"
        assert data["archetype"] == "greenfield"
        assert "created_at" in data

    def test_state_json_has_all_phases(self, state):
        state.init_rapids_dir()
        data = json.loads((state.rapids_dir / "state.json").read_text())
        phases = data["phases"]
        for phase in ["research", "analysis", "plan", "implement", "deploy", "sustain"]:
            assert phase in phases
            assert phases[phase]["status"] == "not_started"

    def test_idempotent_init(self, state):
        state.init_rapids_dir()
        # Write some data
        state.save_phase_artifact("research", "note.md", "my note")
        # Init again should not overwrite existing files
        state.init_rapids_dir()
        assert state.read_phase_artifact("research", "note.md") == "my note"

    def test_is_initialized(self, state):
        assert state.is_initialized is False
        state.init_rapids_dir()
        assert state.is_initialized is True


# ======================================================================
# read/write state.json
# ======================================================================


class TestStateJSON:
    def test_read_state_empty_when_not_initialized(self, state):
        assert state.read_state() == {}

    def test_write_and_read_state(self, initialized_state):
        custom_state = {"current_phase": "plan", "custom_key": "value"}
        initialized_state.write_state(custom_state)
        read_back = initialized_state.read_state()
        assert read_back["current_phase"] == "plan"
        assert read_back["custom_key"] == "value"

    def test_write_state_creates_dir(self, state):
        state.write_state({"test": True})
        assert state.rapids_dir.exists()
        assert state.read_state()["test"] is True

    def test_read_state_corrupt_file(self, initialized_state):
        (initialized_state.rapids_dir / "state.json").write_text("{not valid json")
        assert initialized_state.read_state() == {}


# ======================================================================
# read/write config.json
# ======================================================================


class TestConfigJSON:
    def test_read_config_empty_when_not_initialized(self, state):
        assert state.read_config() == {}

    def test_write_and_read_config(self, initialized_state):
        config = {"project_id": "proj-001", "setting": "value"}
        initialized_state.write_config(config)
        read_back = initialized_state.read_config()
        assert read_back["setting"] == "value"

    def test_write_config_creates_dir(self, state):
        state.write_config({"key": "val"})
        assert state.rapids_dir.exists()

    def test_read_config_corrupt_file(self, initialized_state):
        (initialized_state.rapids_dir / "config.json").write_text("corrupt")
        assert initialized_state.read_config() == {}


# ======================================================================
# Phase artifacts
# ======================================================================


class TestPhaseArtifacts:
    def test_save_and_read_artifact(self, initialized_state):
        path = initialized_state.save_phase_artifact("research", "findings.md", "# Findings\nGood stuff")
        assert path.exists()
        content = initialized_state.read_phase_artifact("research", "findings.md")
        assert content == "# Findings\nGood stuff"

    def test_save_artifact_with_subdirectory(self, initialized_state):
        path = initialized_state.save_phase_artifact("research", "sub/deep/file.md", "nested content")
        assert path.exists()
        content = initialized_state.read_phase_artifact("research", "sub/deep/file.md")
        assert content == "nested content"

    def test_read_missing_artifact_returns_none(self, initialized_state):
        assert initialized_state.read_phase_artifact("research", "missing.md") is None

    def test_get_phase_artifacts_lists_files(self, initialized_state):
        initialized_state.save_phase_artifact("research", "a.md", "aaa")
        initialized_state.save_phase_artifact("research", "b.md", "bbb")
        files = initialized_state.get_phase_artifacts("research")
        names = [f.name for f in files]
        assert "a.md" in names
        assert "b.md" in names

    def test_get_phase_artifacts_empty(self, initialized_state):
        files = initialized_state.get_phase_artifacts("research")
        assert files == []

    def test_get_phase_artifacts_nonexistent_phase_dir(self, state):
        # Not initialized -- directories don't exist
        files = state.get_phase_artifacts("research")
        assert files == []

    def test_implement_phase_uses_features_dir(self, initialized_state):
        """The 'implement' phase maps to the 'features' directory."""
        path = initialized_state.save_phase_artifact("implement", "code.py", "print('hello')")
        assert "features" in str(path)
        content = initialized_state.read_phase_artifact("implement", "code.py")
        assert content == "print('hello')"

    def test_delete_phase_artifact(self, initialized_state):
        initialized_state.save_phase_artifact("research", "temp.md", "temp")
        assert initialized_state.delete_phase_artifact("research", "temp.md") is True
        assert initialized_state.read_phase_artifact("research", "temp.md") is None

    def test_delete_nonexistent_artifact(self, initialized_state):
        assert initialized_state.delete_phase_artifact("research", "nope.md") is False

    def test_overwrite_artifact(self, initialized_state):
        initialized_state.save_phase_artifact("research", "file.md", "v1")
        initialized_state.save_phase_artifact("research", "file.md", "v2")
        assert initialized_state.read_phase_artifact("research", "file.md") == "v2"


# ======================================================================
# Feature specs
# ======================================================================


class TestFeatureSpecs:
    def test_save_and_read_feature_spec(self, initialized_state):
        path = initialized_state.save_feature_spec("auth", "spec.md", "# Auth Spec")
        assert path.exists()
        content = initialized_state.read_feature_spec("auth", "spec.md")
        assert content == "# Auth Spec"

    def test_read_missing_feature_spec(self, initialized_state):
        assert initialized_state.read_feature_spec("nonexistent", "spec.md") is None

    def test_get_feature_specs_lists_files(self, initialized_state):
        initialized_state.save_feature_spec("auth", "spec.md", "auth spec")
        initialized_state.save_feature_spec("auth", "tests.md", "auth tests")
        initialized_state.save_feature_spec("api", "spec.md", "api spec")
        files = initialized_state.get_feature_specs()
        names = [f.name for f in files]
        assert "spec.md" in names

    def test_get_feature_specs_empty(self, initialized_state):
        assert initialized_state.get_feature_specs() == []

    def test_feature_spec_in_correct_directory(self, initialized_state):
        path = initialized_state.save_feature_spec("auth", "spec.md", "content")
        assert path.parent.name == "auth"
        assert path.parent.parent.name == "features"

    def test_multiple_features(self, initialized_state):
        initialized_state.save_feature_spec("f1", "spec.md", "f1 spec")
        initialized_state.save_feature_spec("f2", "spec.md", "f2 spec")
        initialized_state.save_feature_spec("f3", "spec.md", "f3 spec")
        assert initialized_state.read_feature_spec("f1", "spec.md") == "f1 spec"
        assert initialized_state.read_feature_spec("f2", "spec.md") == "f2 spec"
        assert initialized_state.read_feature_spec("f3", "spec.md") == "f3 spec"


# ======================================================================
# Spec management
# ======================================================================


class TestSpecManagement:
    def test_save_and_read_spec(self, initialized_state):
        path = initialized_state.save_spec("# Project Specification\nDetails here")
        assert path.exists()
        content = initialized_state.read_spec()
        assert "Project Specification" in content

    def test_read_spec_missing(self, initialized_state):
        assert initialized_state.read_spec() is None

    def test_get_spec_path(self, initialized_state):
        path = initialized_state.get_spec_path()
        assert path.name == "spec.md"
        assert path.parent.name == "plan"

    def test_get_feature_dag_path(self, initialized_state):
        path = initialized_state.get_feature_dag_path()
        assert path.name == "feature_dag.json"
        assert path.parent.name == "plan"

    def test_overwrite_spec(self, initialized_state):
        initialized_state.save_spec("version 1")
        initialized_state.save_spec("version 2")
        assert initialized_state.read_spec() == "version 2"

    def test_save_spec_creates_plan_dir(self, state):
        """save_spec should create the plan directory if needed."""
        state.init_rapids_dir()
        path = state.save_spec("spec content")
        assert path.exists()
        assert path.parent.name == "plan"


# ======================================================================
# Handling of missing files
# ======================================================================


class TestMissingFiles:
    def test_read_state_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.read_state() == {}

    def test_read_config_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.read_config() == {}

    def test_read_spec_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.read_spec() is None

    def test_read_phase_artifact_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.read_phase_artifact("research", "file.md") is None

    def test_read_feature_spec_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.read_feature_spec("auth", "spec.md") is None

    def test_get_phase_artifacts_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.get_phase_artifacts("research") == []

    def test_get_feature_specs_no_dir(self, tmp_path):
        ps = ProjectState(str(tmp_path / "nonexistent"), "p", "a", "pl")
        assert ps.get_feature_specs() == []


# ======================================================================
# rapids_dir property
# ======================================================================


class TestRapidsDir:
    def test_rapids_dir_path(self, tmp_path):
        ps = ProjectState(str(tmp_path), "p", "a", "pl")
        assert ps.rapids_dir == tmp_path / ".rapids"

    def test_rapids_dir_is_path_object(self, tmp_path):
        ps = ProjectState(str(tmp_path), "p", "a", "pl")
        assert isinstance(ps.rapids_dir, Path)
