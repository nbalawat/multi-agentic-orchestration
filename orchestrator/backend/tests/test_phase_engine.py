"""
Comprehensive tests for the PhaseEngine module.

All tests use real implementations -- no mocks.
Uses pytest tmp_path fixture to create .rapids/ directory structures.
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.phase_engine import PhaseEngine, PHASE_ORDER, PHASE_TRANSITIONS, DEFAULT_CRITERIA


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def rapids_dir(tmp_path):
    """Create a minimal .rapids/ directory."""
    d = tmp_path / ".rapids"
    d.mkdir()
    return d


@pytest.fixture
def engine(rapids_dir):
    """PhaseEngine backed by a temp .rapids/ dir."""
    return PhaseEngine(rapids_dir)


def _write_state(rapids_dir, state):
    """Helper to write state.json."""
    rapids_dir.mkdir(parents=True, exist_ok=True)
    (rapids_dir / "state.json").write_text(json.dumps(state, indent=2))


def _read_state(rapids_dir):
    """Helper to read state.json."""
    return json.loads((rapids_dir / "state.json").read_text())


# ======================================================================
# Initial state
# ======================================================================


class TestInitialState:
    def test_default_current_phase(self, engine):
        assert engine.get_current_phase() == "research"

    def test_all_phases_not_started(self, engine):
        all_phases = engine.get_all_phases()
        assert len(all_phases) == 6
        for phase_name, info in all_phases.items():
            assert info["status"] == "not_started"
            assert info["started_at"] is None
            assert info["completed_at"] is None

    def test_phase_status_not_started(self, engine):
        for phase in PHASE_ORDER:
            assert engine.get_phase_status(phase) == "not_started"

    def test_no_state_file_uses_defaults(self, rapids_dir):
        engine = PhaseEngine(rapids_dir)
        assert engine.get_current_phase() == "research"


# ======================================================================
# start_phase
# ======================================================================


class TestStartPhase:
    def test_start_research_phase(self, engine, rapids_dir):
        # Research has no entry criteria, so should start without force
        result = engine.start_phase("research")
        assert result["status"] == "in_progress"
        assert result["started_at"] is not None

    def test_start_phase_updates_current(self, engine, rapids_dir):
        engine.start_phase("research")
        assert engine.get_current_phase() == "research"

    def test_start_phase_persists(self, engine, rapids_dir):
        engine.start_phase("research")
        state = _read_state(rapids_dir)
        assert state["current_phase"] == "research"
        assert state["phases"]["research"]["status"] == "in_progress"

    def test_start_phase_with_force(self, engine, rapids_dir):
        # analysis has entry criteria (research_complete) which isn't met
        result = engine.start_phase("analysis", force=True)
        assert result["status"] == "in_progress"

    def test_start_phase_without_entry_criteria_fails(self, engine):
        # analysis requires research_complete
        with pytest.raises(ValueError, match="unmet entry criteria"):
            engine.start_phase("analysis")

    def test_start_invalid_phase_raises(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.start_phase("invalid_phase")


# ======================================================================
# complete_phase
# ======================================================================


class TestCompletePhase:
    def test_complete_research_with_artifacts(self, engine, rapids_dir):
        # Create research artifacts to satisfy exit criteria
        research_dir = rapids_dir / "research"
        research_dir.mkdir(exist_ok=True)
        (research_dir / "findings.md").write_text("findings here")

        engine.start_phase("research")
        result = engine.complete_phase("research")
        assert result["status"] == "completed"
        assert result["completed_at"] is not None

    def test_complete_phase_without_exit_criteria_fails(self, engine, rapids_dir):
        engine.start_phase("research")
        # No research artifacts exist
        with pytest.raises(ValueError, match="unmet exit criteria"):
            engine.complete_phase("research")

    def test_complete_phase_with_force(self, engine, rapids_dir):
        engine.start_phase("research")
        result = engine.complete_phase("research", force=True)
        assert result["status"] == "completed"

    def test_complete_invalid_phase_raises(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.complete_phase("bogus")


# ======================================================================
# advance_phase
# ======================================================================


class TestAdvancePhase:
    def test_advance_research_to_analysis(self, engine, rapids_dir):
        engine.start_phase("research")
        # Use force to bypass criteria
        result = engine.advance_phase(force=True)
        assert result["status"] == "in_progress"
        assert engine.get_current_phase() == "analysis"

    def test_advance_completes_current(self, engine, rapids_dir):
        engine.start_phase("research")
        engine.advance_phase(force=True)
        assert engine.get_phase_status("research") == "completed"

    def test_advance_last_phase_raises(self, engine, rapids_dir):
        # Force through to sustain
        for phase in PHASE_ORDER:
            engine.start_phase(phase, force=True)
            if phase != "sustain":
                engine.complete_phase(phase, force=True)

        with pytest.raises(ValueError, match="last phase"):
            engine.advance_phase(force=True)

    def test_advance_without_force_checks_criteria(self, engine, rapids_dir):
        engine.start_phase("research")
        # No artifacts, so exit criteria fail
        with pytest.raises(ValueError, match="unmet"):
            engine.advance_phase()


# ======================================================================
# Entry / exit criteria checking
# ======================================================================


class TestEntryCriteria:
    def test_research_has_no_entry_criteria(self, engine):
        can_start, unmet = engine.can_start_phase("research")
        assert can_start is True
        assert unmet == []

    def test_analysis_requires_research_complete(self, engine):
        can_start, unmet = engine.can_start_phase("analysis")
        assert can_start is False
        assert "research_complete" in unmet

    def test_analysis_entry_met_after_research_completed(self, engine, rapids_dir):
        engine.start_phase("research")
        engine.complete_phase("research", force=True)
        can_start, unmet = engine.can_start_phase("analysis")
        assert can_start is True
        assert unmet == []

    def test_plan_requires_analysis_complete(self, engine):
        can_start, unmet = engine.can_start_phase("plan")
        assert can_start is False
        assert "analysis_complete" in unmet

    def test_implement_requires_plan_and_dag(self, engine):
        can_start, unmet = engine.can_start_phase("implement")
        assert can_start is False
        assert "plan_complete" in unmet
        assert "feature_dag_valid" in unmet


class TestExitCriteria:
    def test_research_exit_requires_artifacts(self, engine, rapids_dir):
        can_complete, unmet = engine.can_complete_phase("research")
        assert can_complete is False
        assert "research_artifacts_exist" in unmet

    def test_research_exit_met_with_files(self, engine, rapids_dir):
        research_dir = rapids_dir / "research"
        research_dir.mkdir(exist_ok=True)
        (research_dir / "findings.md").write_text("content")
        can_complete, unmet = engine.can_complete_phase("research")
        assert can_complete is True

    def test_plan_exit_requires_spec_and_dag_and_features(self, engine, rapids_dir):
        can_complete, unmet = engine.can_complete_phase("plan")
        assert "spec_exists" in unmet
        assert "feature_dag_valid" in unmet
        assert "feature_specs_exist" in unmet

    def test_plan_exit_spec_exists(self, engine, rapids_dir):
        plan_dir = rapids_dir / "plan"
        plan_dir.mkdir(exist_ok=True)
        (plan_dir / "spec.md").write_text("# Spec\nContent here")
        can_complete, unmet = engine.can_complete_phase("plan")
        assert "spec_exists" not in unmet

    def test_sustain_has_no_exit_criteria(self, engine):
        can_complete, unmet = engine.can_complete_phase("sustain")
        assert can_complete is True
        assert unmet == []

    def test_deploy_exit_requires_artifacts(self, engine, rapids_dir):
        can_complete, unmet = engine.can_complete_phase("deploy")
        assert "deployment_artifacts_exist" in unmet

    def test_deploy_exit_met_with_files(self, engine, rapids_dir):
        deploy_dir = rapids_dir / "deploy"
        deploy_dir.mkdir(exist_ok=True)
        (deploy_dir / "deploy.yaml").write_text("deploy config")
        can_complete, unmet = engine.can_complete_phase("deploy")
        assert "deployment_artifacts_exist" not in unmet


# ======================================================================
# Phase ordering
# ======================================================================


class TestPhaseOrdering:
    def test_phase_order(self):
        assert PHASE_ORDER == ['research', 'analysis', 'plan', 'implement', 'deploy', 'sustain']

    def test_get_next_phase(self, engine):
        assert engine.get_next_phase("research") == "analysis"
        assert engine.get_next_phase("analysis") == "plan"
        assert engine.get_next_phase("plan") == "implement"
        assert engine.get_next_phase("implement") == "deploy"
        assert engine.get_next_phase("deploy") == "sustain"
        assert engine.get_next_phase("sustain") is None

    def test_get_phase_index(self, engine):
        for i, phase in enumerate(PHASE_ORDER):
            assert engine.get_phase_index(phase) == i

    def test_get_next_phase_invalid_raises(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.get_next_phase("bogus")

    def test_get_phase_index_invalid_raises(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.get_phase_index("bogus")

    def test_transitions(self):
        assert PHASE_TRANSITIONS["research"]["prev"] is None
        assert PHASE_TRANSITIONS["sustain"]["next"] is None
        # Each phase's next matches the following one in PHASE_ORDER
        for i in range(len(PHASE_ORDER) - 1):
            assert PHASE_TRANSITIONS[PHASE_ORDER[i]]["next"] == PHASE_ORDER[i + 1]


# ======================================================================
# Convergence / execution phases
# ======================================================================


class TestPhaseTypes:
    def test_convergence_phases(self, engine):
        assert engine.is_convergence_phase("research") is True
        assert engine.is_convergence_phase("analysis") is True
        assert engine.is_convergence_phase("plan") is True
        assert engine.is_convergence_phase("implement") is False
        assert engine.is_convergence_phase("deploy") is False
        assert engine.is_convergence_phase("sustain") is False

    def test_execution_phases(self, engine):
        assert engine.is_execution_phase("research") is False
        assert engine.is_execution_phase("analysis") is False
        assert engine.is_execution_phase("plan") is False
        assert engine.is_execution_phase("implement") is True
        assert engine.is_execution_phase("deploy") is True
        assert engine.is_execution_phase("sustain") is True


# ======================================================================
# Force flag
# ======================================================================


class TestForceFlag:
    def test_force_bypasses_entry_criteria(self, engine, rapids_dir):
        # implement has entry criteria that aren't met
        result = engine.start_phase("implement", force=True)
        assert result["status"] == "in_progress"

    def test_force_bypasses_exit_criteria(self, engine, rapids_dir):
        engine.start_phase("research")
        result = engine.complete_phase("research", force=True)
        assert result["status"] == "completed"

    def test_force_advance(self, engine, rapids_dir):
        engine.start_phase("research")
        result = engine.advance_phase(force=True)
        assert result["status"] == "in_progress"
        assert engine.get_current_phase() == "analysis"


# ======================================================================
# Invalid phase names
# ======================================================================


class TestInvalidPhaseNames:
    def test_get_phase_status_invalid(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.get_phase_status("nope")

    def test_can_start_phase_invalid(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.can_start_phase("nope")

    def test_can_complete_phase_invalid(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.can_complete_phase("nope")

    def test_start_phase_invalid(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.start_phase("nope")

    def test_complete_phase_invalid(self, engine):
        with pytest.raises(ValueError, match="Invalid phase"):
            engine.complete_phase("nope")


# ======================================================================
# Criteria overrides
# ======================================================================


class TestCriteriaOverrides:
    def test_override_entry_criteria(self, rapids_dir):
        overrides = {
            "research": {"entry": ["custom_criterion"]},
        }
        engine = PhaseEngine(rapids_dir, criteria_overrides=overrides)
        can_start, unmet = engine.can_start_phase("research")
        assert can_start is False
        assert "custom_criterion" in unmet

    def test_override_exit_criteria(self, rapids_dir):
        overrides = {
            "sustain": {"exit": ["custom_exit"]},
        }
        engine = PhaseEngine(rapids_dir, criteria_overrides=overrides)
        can_complete, unmet = engine.can_complete_phase("sustain")
        assert can_complete is False
        assert "custom_exit" in unmet

    def test_override_does_not_affect_other_phases(self, rapids_dir):
        overrides = {
            "research": {"entry": ["custom"]},
        }
        engine = PhaseEngine(rapids_dir, criteria_overrides=overrides)
        # analysis should still require research_complete
        can_start, unmet = engine.can_start_phase("analysis")
        assert "research_complete" in unmet


# ======================================================================
# State file I/O edge cases
# ======================================================================


class TestStateIO:
    def test_corrupt_state_file(self, rapids_dir):
        (rapids_dir / "state.json").write_text("not json{{{")
        engine = PhaseEngine(rapids_dir)
        # Should fall back to default
        assert engine.get_current_phase() == "research"

    def test_state_persists_across_engine_instances(self, rapids_dir):
        engine1 = PhaseEngine(rapids_dir)
        engine1.start_phase("research")
        engine1.complete_phase("research", force=True)

        engine2 = PhaseEngine(rapids_dir)
        assert engine2.get_phase_status("research") == "completed"

    def test_rapids_dir_created_on_write(self, tmp_path):
        new_dir = tmp_path / "new" / ".rapids"
        engine = PhaseEngine(new_dir)
        engine.start_phase("research")
        assert new_dir.exists()
        assert (new_dir / "state.json").exists()


# ======================================================================
# Feature DAG criteria
# ======================================================================


class TestFeatureDAGCriteria:
    def test_feature_dag_valid_missing_file(self, engine, rapids_dir):
        can_complete, unmet = engine.can_complete_phase("plan")
        assert "feature_dag_valid" in unmet

    def test_feature_dag_valid_empty_json(self, engine, rapids_dir):
        plan_dir = rapids_dir / "plan"
        plan_dir.mkdir(exist_ok=True)
        (plan_dir / "feature_dag.json").write_text("{}")
        can_complete, unmet = engine.can_complete_phase("plan")
        # Empty features means not valid
        assert "feature_dag_valid" in unmet

    def test_feature_specs_exist(self, engine, rapids_dir):
        features_dir = rapids_dir / "features"
        features_dir.mkdir(exist_ok=True)
        (features_dir / "auth" / "spec.md").parent.mkdir(parents=True, exist_ok=True)
        (features_dir / "auth" / "spec.md").write_text("spec")
        can_complete, unmet = engine.can_complete_phase("plan")
        assert "feature_specs_exist" not in unmet

    def test_all_features_complete_check(self, engine, rapids_dir):
        plan_dir = rapids_dir / "plan"
        plan_dir.mkdir(exist_ok=True)
        dag_data = {
            "features": [
                {"id": "f1", "name": "F1", "status": "completed"},
                {"id": "f2", "name": "F2", "status": "completed"},
            ]
        }
        (plan_dir / "feature_dag.json").write_text(json.dumps(dag_data))

        can_complete, unmet = engine.can_complete_phase("implement")
        assert "all_features_complete" not in unmet

    def test_all_features_not_complete(self, engine, rapids_dir):
        plan_dir = rapids_dir / "plan"
        plan_dir.mkdir(exist_ok=True)
        dag_data = {
            "features": [
                {"id": "f1", "name": "F1", "status": "completed"},
                {"id": "f2", "name": "F2", "status": "in_progress"},
            ]
        }
        (plan_dir / "feature_dag.json").write_text(json.dumps(dag_data))

        can_complete, unmet = engine.can_complete_phase("implement")
        assert "all_features_complete" in unmet
