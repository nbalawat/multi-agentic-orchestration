"""
Comprehensive tests for the FeatureDAG module.

All tests use real implementations -- no mocks.
Uses pytest tmp_path fixture for file operations.
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.feature_dag import FeatureDAG, FeatureNode


# ======================================================================
# Helpers
# ======================================================================

def _node(id: str, name: str = "", depends_on=None, priority: int = 0, status="planned", **kw):
    """Shorthand for creating a FeatureNode."""
    return FeatureNode(
        id=id,
        name=name or id,
        depends_on=depends_on or [],
        priority=priority,
        status=status,
        **kw,
    )


def _linear_dag(*ids):
    """Build a linear chain: ids[0] -> ids[1] -> ... (each depends on previous)."""
    dag = FeatureDAG()
    for i, fid in enumerate(ids):
        deps = [ids[i - 1]] if i > 0 else []
        dag.add_feature(_node(fid, depends_on=deps))
    return dag


# ======================================================================
# Creating a DAG, Adding Features
# ======================================================================


class TestDAGCreation:
    def test_create_empty_dag(self):
        dag = FeatureDAG()
        assert dag.feature_count == 0
        assert dag.list_features() == []

    def test_add_single_feature(self):
        dag = FeatureDAG()
        dag.add_feature(_node("f1"))
        assert dag.feature_count == 1
        assert dag.get_feature("f1") is not None
        assert dag.get_feature("f1").id == "f1"

    def test_add_multiple_features(self):
        dag = FeatureDAG()
        for i in range(5):
            dag.add_feature(_node(f"f{i}"))
        assert dag.feature_count == 5

    def test_add_duplicate_raises(self):
        dag = FeatureDAG()
        dag.add_feature(_node("f1"))
        with pytest.raises(ValueError, match="already exists"):
            dag.add_feature(_node("f1"))

    def test_remove_feature(self):
        dag = FeatureDAG()
        dag.add_feature(_node("f1"))
        dag.add_feature(_node("f2", depends_on=["f1"]))
        dag.remove_feature("f1")
        assert dag.feature_count == 1
        # Dependency on f1 should be cleaned up
        assert dag.get_feature("f2").depends_on == []

    def test_remove_missing_feature_raises(self):
        dag = FeatureDAG()
        with pytest.raises(KeyError, match="not found"):
            dag.remove_feature("nope")

    def test_get_feature_missing_returns_none(self):
        dag = FeatureDAG()
        assert dag.get_feature("nope") is None

    def test_feature_with_all_fields(self):
        dag = FeatureDAG()
        node = FeatureNode(
            id="auth",
            name="Authentication Module",
            description="Handles user auth",
            category="backend",
            priority=1,
            depends_on=[],
            acceptance_criteria=["Login works", "Logout works"],
            estimated_complexity="high",
            spec_file="auth-spec.md",
            status="planned",
        )
        dag.add_feature(node)
        retrieved = dag.get_feature("auth")
        assert retrieved.name == "Authentication Module"
        assert retrieved.description == "Handles user auth"
        assert retrieved.category == "backend"
        assert retrieved.priority == 1
        assert retrieved.acceptance_criteria == ["Login works", "Logout works"]
        assert retrieved.estimated_complexity == "high"


# ======================================================================
# Save / Load from file
# ======================================================================


class TestSaveLoad:
    def test_save_and_load_roundtrip(self, tmp_path):
        dag_path = tmp_path / "dag.json"
        dag = FeatureDAG(dag_path=dag_path)
        dag.add_feature(_node("f1"))
        dag.add_feature(_node("f2", depends_on=["f1"]))
        dag.save()

        dag2 = FeatureDAG(dag_path=dag_path)
        dag2.load()
        assert dag2.feature_count == 2
        assert dag2.get_feature("f2").depends_on == ["f1"]

    def test_save_to_explicit_path(self, tmp_path):
        dag = FeatureDAG()
        dag.add_feature(_node("x"))
        path = tmp_path / "sub" / "dag.json"
        dag.save(path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data["features"]) == 1

    def test_load_from_explicit_path(self, tmp_path):
        path = tmp_path / "dag.json"
        path.write_text(json.dumps({
            "features": [{"id": "a", "name": "A"}]
        }))
        dag = FeatureDAG()
        dag.load(path)
        assert dag.feature_count == 1
        assert dag.get_feature("a").name == "A"

    def test_save_no_path_raises(self):
        dag = FeatureDAG()
        with pytest.raises(ValueError, match="No path"):
            dag.save()

    def test_load_no_path_raises(self):
        dag = FeatureDAG()
        with pytest.raises(ValueError, match="No path"):
            dag.load()

    def test_load_missing_file_raises(self, tmp_path):
        dag = FeatureDAG()
        with pytest.raises(FileNotFoundError):
            dag.load(tmp_path / "nonexistent.json")

    def test_to_dict_structure(self):
        dag = FeatureDAG()
        dag.add_feature(_node("f1"))
        d = dag.to_dict()
        assert "spec_version" in d
        assert "features" in d
        assert len(d["features"]) == 1
        assert d["features"][0]["id"] == "f1"

    def test_from_dict(self):
        data = {
            "features": [
                {"id": "a", "name": "A", "depends_on": []},
                {"id": "b", "name": "B", "depends_on": ["a"]},
            ]
        }
        dag = FeatureDAG.from_dict(data)
        assert dag.feature_count == 2
        assert dag.get_feature("b").depends_on == ["a"]


# ======================================================================
# Topological Sort
# ======================================================================


class TestTopologicalSort:
    def test_empty_dag(self):
        dag = FeatureDAG()
        assert dag.topological_sort() == []

    def test_single_feature(self):
        dag = FeatureDAG()
        dag.add_feature(_node("f1"))
        assert dag.topological_sort() == ["f1"]

    def test_linear_chain(self):
        dag = _linear_dag("a", "b", "c", "d")
        order = dag.topological_sort()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")
        assert order.index("c") < order.index("d")

    def test_diamond_dependency(self):
        """
          a
         / \\
        b   c
         \\ /
          d
        """
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b", depends_on=["a"]))
        dag.add_feature(_node("c", depends_on=["a"]))
        dag.add_feature(_node("d", depends_on=["b", "c"]))
        order = dag.topological_sort()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_independent_features_sorted_by_priority(self):
        dag = FeatureDAG()
        dag.add_feature(_node("low", priority=10))
        dag.add_feature(_node("high", priority=1))
        dag.add_feature(_node("mid", priority=5))
        order = dag.topological_sort()
        # Lower priority number comes first
        assert order == ["high", "mid", "low"]

    def test_cycle_raises(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["b"]))
        dag.add_feature(_node("b", depends_on=["a"]))
        with pytest.raises(ValueError, match="cycle"):
            dag.topological_sort()

    def test_wide_dag(self):
        """Many independent features with one common root."""
        dag = FeatureDAG()
        dag.add_feature(_node("root"))
        for i in range(10):
            dag.add_feature(_node(f"leaf{i}", depends_on=["root"]))
        order = dag.topological_sort()
        assert order[0] == "root"
        assert set(order[1:]) == {f"leaf{i}" for i in range(10)}


# ======================================================================
# Cycle Detection
# ======================================================================


class TestCycleDetection:
    def test_no_cycle_valid(self):
        dag = _linear_dag("a", "b", "c")
        errors = dag.validate()
        assert len(errors) == 0

    def test_simple_cycle(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["b"]))
        dag.add_feature(_node("b", depends_on=["a"]))
        errors = dag.validate()
        cycle_errors = [e for e in errors if "cycle" in e.lower()]
        assert len(cycle_errors) > 0

    def test_three_node_cycle(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["c"]))
        dag.add_feature(_node("b", depends_on=["a"]))
        dag.add_feature(_node("c", depends_on=["b"]))
        errors = dag.validate()
        cycle_errors = [e for e in errors if "cycle" in e.lower()]
        assert len(cycle_errors) > 0

    def test_cycle_in_subgraph_detected(self):
        """Cycle exists in a subgraph while other parts are fine."""
        dag = FeatureDAG()
        dag.add_feature(_node("ok1"))
        dag.add_feature(_node("ok2", depends_on=["ok1"]))
        dag.add_feature(_node("cyc_a", depends_on=["cyc_b"]))
        dag.add_feature(_node("cyc_b", depends_on=["cyc_a"]))
        errors = dag.validate()
        cycle_errors = [e for e in errors if "cycle" in e.lower()]
        assert len(cycle_errors) > 0


# ======================================================================
# get_ready_features
# ======================================================================


class TestGetReadyFeatures:
    def test_no_deps_all_ready(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        ready = dag.get_ready_features()
        assert set(ready) == {"a", "b"}

    def test_deps_not_complete_not_ready(self):
        dag = _linear_dag("a", "b")
        ready = dag.get_ready_features()
        # Only "a" is ready since "b" depends on incomplete "a"
        assert ready == ["a"]

    def test_dep_complete_makes_dependent_ready(self):
        dag = _linear_dag("a", "b")
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        ready = dag.get_ready_features()
        assert "b" in ready

    def test_in_progress_not_in_ready(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_in_progress("a")
        ready = dag.get_ready_features()
        assert ready == []

    def test_blocked_not_in_ready(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_blocked("a")
        ready = dag.get_ready_features()
        assert ready == []

    def test_partial_deps_complete(self):
        """Feature with two deps, only one complete -- not ready."""
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        dag.add_feature(_node("c", depends_on=["a", "b"]))
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        ready = dag.get_ready_features()
        assert "c" not in ready
        assert "b" in ready


# ======================================================================
# get_parallel_groups
# ======================================================================


class TestGetParallelGroups:
    def test_empty_dag(self):
        dag = FeatureDAG()
        assert dag.get_parallel_groups() == []

    def test_single_feature(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        groups = dag.get_parallel_groups()
        assert groups == [["a"]]

    def test_all_independent(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        dag.add_feature(_node("c"))
        groups = dag.get_parallel_groups()
        assert len(groups) == 1
        assert set(groups[0]) == {"a", "b", "c"}

    def test_linear_chain_single_per_group(self):
        dag = _linear_dag("a", "b", "c")
        groups = dag.get_parallel_groups()
        assert len(groups) == 3
        assert groups[0] == ["a"]
        assert groups[1] == ["b"]
        assert groups[2] == ["c"]

    def test_diamond(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b", depends_on=["a"]))
        dag.add_feature(_node("c", depends_on=["a"]))
        dag.add_feature(_node("d", depends_on=["b", "c"]))
        groups = dag.get_parallel_groups()
        assert len(groups) == 3
        assert groups[0] == ["a"]
        assert set(groups[1]) == {"b", "c"}
        assert groups[2] == ["d"]

    def test_cycle_returns_empty(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["b"]))
        dag.add_feature(_node("b", depends_on=["a"]))
        assert dag.get_parallel_groups() == []


# ======================================================================
# mark_complete and newly-ready features
# ======================================================================


class TestMarkComplete:
    def test_mark_complete_returns_newly_ready(self):
        dag = _linear_dag("a", "b", "c")
        dag.mark_in_progress("a")
        newly_ready = dag.mark_complete("a")
        assert "b" in newly_ready

    def test_mark_complete_not_in_progress_raises(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        with pytest.raises(ValueError, match="in_progress"):
            dag.mark_complete("a")

    def test_mark_complete_missing_raises(self):
        dag = FeatureDAG()
        with pytest.raises(KeyError, match="not found"):
            dag.mark_complete("nope")

    def test_mark_complete_sets_timestamp(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        feat = dag.get_feature("a")
        assert feat.status == "complete"
        assert feat.completed_at is not None

    def test_mark_complete_chain(self):
        """Complete features one by one down a chain."""
        dag = _linear_dag("a", "b", "c")

        dag.mark_in_progress("a")
        newly = dag.mark_complete("a")
        assert "b" in newly

        dag.mark_in_progress("b")
        newly = dag.mark_complete("b")
        assert "c" in newly

        dag.mark_in_progress("c")
        newly = dag.mark_complete("c")
        assert newly == []  # nothing left


# ======================================================================
# mark_in_progress
# ======================================================================


class TestMarkInProgress:
    def test_mark_in_progress_basic(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_in_progress("a")
        feat = dag.get_feature("a")
        assert feat.status == "in_progress"
        assert feat.started_at is not None

    def test_mark_in_progress_with_agent(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_in_progress("a", agent_id="agent-1")
        assert dag.get_feature("a").assigned_agent == "agent-1"

    def test_mark_in_progress_not_planned_raises(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_in_progress("a")
        with pytest.raises(ValueError, match="planned"):
            dag.mark_in_progress("a")

    def test_mark_in_progress_missing_raises(self):
        dag = FeatureDAG()
        with pytest.raises(KeyError, match="not found"):
            dag.mark_in_progress("nope")


# ======================================================================
# mark_blocked
# ======================================================================


class TestMarkBlocked:
    def test_mark_blocked(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_blocked("a")
        assert dag.get_feature("a").status == "blocked"

    def test_mark_blocked_with_reason(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", description="some feature"))
        dag.mark_blocked("a", reason="external API down")
        desc = dag.get_feature("a").description
        assert "BLOCKED" in desc
        assert "external API down" in desc

    def test_mark_blocked_missing_raises(self):
        dag = FeatureDAG()
        with pytest.raises(KeyError, match="not found"):
            dag.mark_blocked("nope")


# ======================================================================
# critical_path
# ======================================================================


class TestCriticalPath:
    def test_empty_dag(self):
        dag = FeatureDAG()
        assert dag.critical_path() == []

    def test_single_feature(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        assert dag.critical_path() == ["a"]

    def test_linear_chain_is_critical_path(self):
        dag = _linear_dag("a", "b", "c", "d")
        path = dag.critical_path()
        assert path == ["a", "b", "c", "d"]

    def test_diamond_critical_path(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b", depends_on=["a"]))
        dag.add_feature(_node("c", depends_on=["a"]))
        dag.add_feature(_node("d", depends_on=["b", "c"]))
        path = dag.critical_path()
        # Should be length 3: a -> (b or c) -> d
        assert len(path) == 3
        assert path[0] == "a"
        assert path[-1] == "d"

    def test_independent_features_path_length_one(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        dag.add_feature(_node("c"))
        path = dag.critical_path()
        assert len(path) == 1

    def test_cycle_returns_empty(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["b"]))
        dag.add_feature(_node("b", depends_on=["a"]))
        assert dag.critical_path() == []

    def test_longer_branch_wins(self):
        """
        a -> b -> c -> d (length 4)
        a -> e (length 2)
        Critical path should be the longer branch.
        """
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b", depends_on=["a"]))
        dag.add_feature(_node("c", depends_on=["b"]))
        dag.add_feature(_node("d", depends_on=["c"]))
        dag.add_feature(_node("e", depends_on=["a"]))
        path = dag.critical_path()
        assert len(path) == 4
        assert path == ["a", "b", "c", "d"]


# ======================================================================
# completion_percentage
# ======================================================================


class TestCompletionPercentage:
    def test_empty_dag(self):
        dag = FeatureDAG()
        assert dag.completion_percentage() == 0.0

    def test_none_complete(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        assert dag.completion_percentage() == 0.0

    def test_half_complete(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        assert dag.completion_percentage() == 50.0

    def test_all_complete(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b"))
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        dag.mark_in_progress("b")
        dag.mark_complete("b")
        assert dag.completion_percentage() == 100.0


# ======================================================================
# Validation
# ======================================================================


class TestValidation:
    def test_valid_dag(self):
        dag = _linear_dag("a", "b", "c")
        assert dag.validate() == []

    def test_self_reference(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["a"]))
        errors = dag.validate()
        assert any("itself" in e for e in errors)

    def test_missing_dependency(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["nonexistent"]))
        errors = dag.validate()
        assert any("unknown" in e.lower() for e in errors)

    def test_multiple_errors(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a", depends_on=["a", "ghost"]))
        errors = dag.validate()
        assert len(errors) >= 2  # self-ref + missing dep


# ======================================================================
# Empty DAG edge cases
# ======================================================================


class TestEmptyDAG:
    def test_is_complete(self):
        dag = FeatureDAG()
        assert dag.is_complete is True

    def test_status_summary(self):
        dag = FeatureDAG()
        summary = dag.status_summary()
        assert all(v == 0 for v in summary.values())

    def test_topological_sort(self):
        dag = FeatureDAG()
        assert dag.topological_sort() == []

    def test_parallel_groups(self):
        dag = FeatureDAG()
        assert dag.get_parallel_groups() == []

    def test_critical_path(self):
        dag = FeatureDAG()
        assert dag.critical_path() == []


# ======================================================================
# Single Feature DAG
# ======================================================================


class TestSingleFeatureDAG:
    def test_topological_sort(self):
        dag = FeatureDAG()
        dag.add_feature(_node("only"))
        assert dag.topological_sort() == ["only"]

    def test_parallel_groups(self):
        dag = FeatureDAG()
        dag.add_feature(_node("only"))
        assert dag.get_parallel_groups() == [["only"]]

    def test_critical_path(self):
        dag = FeatureDAG()
        dag.add_feature(_node("only"))
        assert dag.critical_path() == ["only"]

    def test_lifecycle(self):
        dag = FeatureDAG()
        dag.add_feature(_node("only"))
        assert dag.completion_percentage() == 0.0
        dag.mark_in_progress("only")
        dag.mark_complete("only")
        assert dag.completion_percentage() == 100.0
        assert dag.is_complete is True


# ======================================================================
# Complex DAG (10+ features, multiple dependency chains)
# ======================================================================


class TestComplexDAG:
    """
    Complex project DAG:

    auth ─────────────────────┐
    db-schema ─────┐          │
    api-framework ─┤          │
                   ├─ crud-api┤
    logging ───────┘          ├─ user-dashboard
    caching ──────────────────┤
    search-index ─────────────┤
                              ├─ admin-panel
    notification-svc ─────────┘
    ci-cd (independent)
    monitoring (depends on ci-cd)
    """

    @pytest.fixture
    def complex_dag(self):
        dag = FeatureDAG()
        dag.add_feature(_node("auth", priority=0))
        dag.add_feature(_node("db-schema", priority=0))
        dag.add_feature(_node("api-framework", priority=1))
        dag.add_feature(_node("logging", priority=2))
        dag.add_feature(_node("crud-api", depends_on=["db-schema", "api-framework", "logging"], priority=1))
        dag.add_feature(_node("caching", priority=3))
        dag.add_feature(_node("search-index", priority=2))
        dag.add_feature(_node("notification-svc", priority=3))
        dag.add_feature(_node("user-dashboard", depends_on=["crud-api", "auth", "caching", "search-index"], priority=0))
        dag.add_feature(_node("admin-panel", depends_on=["crud-api", "auth", "notification-svc"], priority=1))
        dag.add_feature(_node("ci-cd", priority=5))
        dag.add_feature(_node("monitoring", depends_on=["ci-cd"], priority=5))
        return dag

    def test_feature_count(self, complex_dag):
        assert complex_dag.feature_count == 12

    def test_topological_sort_respects_deps(self, complex_dag):
        order = complex_dag.topological_sort()
        assert len(order) == 12
        idx = {fid: i for i, fid in enumerate(order)}
        # crud-api must come after its three deps
        assert idx["db-schema"] < idx["crud-api"]
        assert idx["api-framework"] < idx["crud-api"]
        assert idx["logging"] < idx["crud-api"]
        # user-dashboard after all its deps
        assert idx["crud-api"] < idx["user-dashboard"]
        assert idx["auth"] < idx["user-dashboard"]
        assert idx["caching"] < idx["user-dashboard"]
        # admin-panel after all its deps
        assert idx["crud-api"] < idx["admin-panel"]
        assert idx["notification-svc"] < idx["admin-panel"]
        # monitoring after ci-cd
        assert idx["ci-cd"] < idx["monitoring"]

    def test_parallel_groups(self, complex_dag):
        groups = complex_dag.get_parallel_groups()
        # First group should be all zero-indegree features
        first_group = set(groups[0])
        assert "auth" in first_group
        assert "db-schema" in first_group
        assert "api-framework" in first_group
        assert "ci-cd" in first_group
        assert "crud-api" not in first_group  # has deps

    def test_critical_path_length(self, complex_dag):
        path = complex_dag.critical_path()
        # Longest chain involves something like db-schema -> crud-api -> user-dashboard (length 3+)
        assert len(path) >= 3

    def test_ready_features_initial(self, complex_dag):
        ready = complex_dag.get_ready_features()
        # Only features with no deps should be ready
        assert "auth" in ready
        assert "db-schema" in ready
        assert "api-framework" in ready
        assert "ci-cd" in ready
        assert "crud-api" not in ready

    def test_incremental_completion(self, complex_dag):
        """Complete features incrementally and verify readiness updates."""
        # Complete the three deps of crud-api
        for fid in ["db-schema", "api-framework", "logging"]:
            complex_dag.mark_in_progress(fid)
            complex_dag.mark_complete(fid)

        ready = complex_dag.get_ready_features()
        assert "crud-api" in ready

    def test_validation_passes(self, complex_dag):
        assert complex_dag.validate() == []

    def test_status_summary(self, complex_dag):
        summary = complex_dag.status_summary()
        assert summary["planned"] == 12
        assert summary["complete"] == 0

    def test_save_load_preserves_complex(self, complex_dag, tmp_path):
        path = tmp_path / "complex_dag.json"
        complex_dag.save(path)
        loaded = FeatureDAG()
        loaded.load(path)
        assert loaded.feature_count == 12
        assert loaded.validate() == []


# ======================================================================
# Blocking / dependent features
# ======================================================================


class TestBlockingAndDependents:
    def test_get_blocking_features(self):
        dag = _linear_dag("a", "b", "c")
        blockers = dag.get_blocking_features("b")
        assert blockers == ["a"]

    def test_get_blocking_features_none_when_dep_complete(self):
        dag = _linear_dag("a", "b")
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        assert dag.get_blocking_features("b") == []

    def test_get_blocking_features_missing_raises(self):
        dag = FeatureDAG()
        with pytest.raises(KeyError, match="not found"):
            dag.get_blocking_features("nope")

    def test_get_dependent_features(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.add_feature(_node("b", depends_on=["a"]))
        dag.add_feature(_node("c", depends_on=["a"]))
        dependents = dag.get_dependent_features("a")
        assert set(dependents) == {"b", "c"}

    def test_get_dependent_features_missing_raises(self):
        dag = FeatureDAG()
        with pytest.raises(KeyError, match="not found"):
            dag.get_dependent_features("nope")


# ======================================================================
# is_complete property
# ======================================================================


class TestIsComplete:
    def test_empty_is_complete(self):
        dag = FeatureDAG()
        assert dag.is_complete is True

    def test_not_complete(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        assert dag.is_complete is False

    def test_becomes_complete(self):
        dag = FeatureDAG()
        dag.add_feature(_node("a"))
        dag.mark_in_progress("a")
        dag.mark_complete("a")
        assert dag.is_complete is True
