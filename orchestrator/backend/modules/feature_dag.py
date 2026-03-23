"""Feature DAG engine module.

Manages the directed acyclic graph of features for a project.
Features have dependencies, and the DAG determines execution order
for the Implement phase.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FeatureNode(BaseModel):
    """A single feature in the DAG."""

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    priority: int = 0
    depends_on: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    estimated_complexity: Optional[str] = None
    spec_file: Optional[str] = None
    status: Literal["planned", "in_progress", "complete", "blocked", "deferred"] = (
        "planned"
    )
    assigned_agent: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class FeatureDAG:
    """Manages the directed acyclic graph of features for a project."""

    def __init__(self, dag_path: Optional[Path] = None):
        self._features: Dict[str, FeatureNode] = {}
        self._dag_path = dag_path

    # ------------------------------------------------------------------ #
    #  Loading / Saving
    # ------------------------------------------------------------------ #

    def load(self, path: Optional[Path] = None) -> None:
        """Load the DAG from a JSON file."""
        load_path = path or self._dag_path
        if load_path is None:
            raise ValueError("No path provided and no default dag_path set.")
        load_path = Path(load_path)
        if not load_path.exists():
            raise FileNotFoundError(f"DAG file not found: {load_path}")
        with open(load_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._features.clear()
        for feat_data in data.get("features", []):
            node = FeatureNode(**feat_data)
            self._features[node.id] = node
        if path is not None:
            self._dag_path = load_path

    def save(self, path: Optional[Path] = None) -> None:
        """Persist the DAG to a JSON file."""
        save_path = path or self._dag_path
        if save_path is None:
            raise ValueError("No path provided and no default dag_path set.")
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        if path is not None:
            self._dag_path = save_path

    def to_dict(self) -> Dict:
        """Serialise the DAG to a dictionary matching the spec format."""
        return {
            "spec_version": "1.0",
            "project_id": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "features": [feat.model_dump() for feat in self._features.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict, dag_path: Optional[Path] = None) -> "FeatureDAG":
        """Construct a FeatureDAG from a dictionary."""
        dag = cls(dag_path=dag_path)
        for feat_data in data.get("features", []):
            node = FeatureNode(**feat_data)
            dag._features[node.id] = node
        return dag

    # ------------------------------------------------------------------ #
    #  Database-primary loading / saving
    # ------------------------------------------------------------------ #

    @classmethod
    async def from_database(cls, project_id: str) -> "FeatureDAG":
        """Load DAG from the features database table (primary source of truth)."""
        import uuid as _uuid
        from .rapids_database import load_dag_features

        dag = cls()
        features = await load_dag_features(_uuid.UUID(str(project_id)))
        for f in features:
            node = FeatureNode(
                id=str(f.id),
                name=f.name,
                description=f.description,
                category=getattr(f, "category", None),
                priority=f.priority,
                depends_on=f.depends_on or [],
                acceptance_criteria=f.acceptance_criteria or [],
                estimated_complexity=f.estimated_complexity,
                spec_file=f.spec_file,
                status=f.status or "planned",
                assigned_agent=getattr(f, "assigned_agent", None),
                started_at=f.started_at.isoformat() if getattr(f, "started_at", None) else None,
                completed_at=f.completed_at.isoformat() if getattr(f, "completed_at", None) else None,
            )
            dag._features[node.id] = node
        return dag

    async def save_to_database(self, project_id: str) -> None:
        """Persist current in-memory DAG state back to the database."""
        from .rapids_database import update_feature_dag_status

        import uuid as _uuid
        pid = _uuid.UUID(str(project_id))
        for feat in self._features.values():
            await update_feature_dag_status(
                project_id=pid,
                feature_id=feat.id,
                status=feat.status,
                assigned_agent=feat.assigned_agent,
                started_at=feat.started_at,
                completed_at=feat.completed_at,
            )

    # ------------------------------------------------------------------ #
    #  Feature management
    # ------------------------------------------------------------------ #

    def add_feature(self, feature: FeatureNode) -> None:
        """Add a feature node to the DAG.

        Raises ValueError if a feature with the same id already exists.
        """
        if feature.id in self._features:
            raise ValueError(f"Feature '{feature.id}' already exists in the DAG.")
        self._features[feature.id] = feature

    def remove_feature(self, feat_id: str) -> None:
        """Remove a feature and clean up any references to it in depends_on lists.

        Raises KeyError if the feature does not exist.
        """
        if feat_id not in self._features:
            raise KeyError(f"Feature '{feat_id}' not found in the DAG.")
        del self._features[feat_id]
        # Remove from dependency lists of remaining features.
        for node in self._features.values():
            if feat_id in node.depends_on:
                node.depends_on.remove(feat_id)

    def get_feature(self, feat_id: str) -> Optional[FeatureNode]:
        """Return the FeatureNode for the given id, or None."""
        return self._features.get(feat_id)

    def list_features(self) -> List[FeatureNode]:
        """Return all features in insertion order."""
        return list(self._features.values())

    # ------------------------------------------------------------------ #
    #  DAG validation
    # ------------------------------------------------------------------ #

    def validate(self) -> List[str]:
        """Return a list of validation errors.  Empty list means valid.

        Checks performed:
        - No self-references in depends_on
        - No references to missing features
        - No dependency cycles
        """
        errors: List[str] = []

        for feat in self._features.values():
            # Self-reference check
            if feat.id in feat.depends_on:
                errors.append(
                    f"Feature '{feat.id}' lists itself as a dependency."
                )
            # Missing dependency check
            for dep_id in feat.depends_on:
                if dep_id not in self._features:
                    errors.append(
                        f"Feature '{feat.id}' depends on unknown feature '{dep_id}'."
                    )

        # Cycle check
        cycles = self._detect_cycles()
        for cycle in cycles:
            cycle_str = " -> ".join(cycle)
            errors.append(f"Dependency cycle detected: {cycle_str}")

        return errors

    def _detect_cycles(self) -> List[List[str]]:
        """Detect cycles using iterative DFS with coloring.

        Returns a list of cycles, where each cycle is a list of node IDs
        forming the loop (ending with the repeated start node).
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {fid: WHITE for fid in self._features}
        parent: Dict[str, Optional[str]] = {fid: None for fid in self._features}
        cycles: List[List[str]] = []

        for start in self._features:
            if color[start] != WHITE:
                continue
            stack: List[tuple] = [(start, 0)]  # (node, dep_index)
            color[start] = GRAY

            while stack:
                node, idx = stack[-1]
                deps = [
                    d
                    for d in self._features[node].depends_on
                    if d in self._features
                ]

                if idx < len(deps):
                    stack[-1] = (node, idx + 1)
                    dep = deps[idx]
                    if color[dep] == WHITE:
                        color[dep] = GRAY
                        parent[dep] = node
                        stack.append((dep, 0))
                    elif color[dep] == GRAY:
                        # Reconstruct cycle
                        cycle = [dep]
                        cur = node
                        while cur != dep:
                            cycle.append(cur)
                            cur = parent[cur]  # type: ignore[assignment]
                        cycle.append(dep)
                        cycle.reverse()
                        cycles.append(cycle)
                else:
                    color[node] = BLACK
                    stack.pop()

        return cycles

    # ------------------------------------------------------------------ #
    #  DAG queries
    # ------------------------------------------------------------------ #

    def topological_sort(self) -> List[str]:
        """Return feature IDs in valid execution order using Kahn's algorithm.

        Raises ValueError if the graph contains a cycle.
        Within the same topological level, features are ordered by priority
        (lower number = higher priority).
        """
        # Build in-degree map (only counting edges within the known feature set).
        in_degree: Dict[str, int] = {fid: 0 for fid in self._features}
        for feat in self._features.values():
            for dep_id in feat.depends_on:
                if dep_id in self._features:
                    in_degree[feat.id] += 1

        # Seed with zero in-degree nodes, sorted by priority for determinism.
        queue: deque[str] = deque(
            sorted(
                [fid for fid, deg in in_degree.items() if deg == 0],
                key=lambda fid: self._features[fid].priority,
            )
        )
        result: List[str] = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)

            # Find successors (features that list node_id as a dependency).
            successors: List[str] = []
            for feat in self._features.values():
                if node_id in feat.depends_on:
                    in_degree[feat.id] -= 1
                    if in_degree[feat.id] == 0:
                        successors.append(feat.id)

            # Sort successors by priority before enqueueing.
            successors.sort(key=lambda fid: self._features[fid].priority)
            queue.extend(successors)

        if len(result) != len(self._features):
            raise ValueError(
                "Cannot produce topological sort: the DAG contains a cycle."
            )
        return result

    def get_ready_features(self) -> List[str]:
        """Return IDs of features whose dependencies are all 'complete'
        and whose own status is 'planned'."""
        ready: List[str] = []
        for feat in self._features.values():
            if feat.status != "planned":
                continue
            all_deps_complete = all(
                self._features[dep_id].status == "complete"
                for dep_id in feat.depends_on
                if dep_id in self._features
            )
            if all_deps_complete:
                ready.append(feat.id)
        return ready

    def get_parallel_groups(self) -> List[List[str]]:
        """Return groups of features that can execute concurrently.

        Uses a level-based approach on the topological order: features at
        the same depth (longest incoming path length) can run in parallel.
        """
        if not self._features:
            return []

        # Build adjacency: dep -> list of dependents
        dependents: Dict[str, List[str]] = {fid: [] for fid in self._features}
        in_degree: Dict[str, int] = {fid: 0 for fid in self._features}
        for feat in self._features.values():
            for dep_id in feat.depends_on:
                if dep_id in self._features:
                    dependents[dep_id].append(feat.id)
                    in_degree[feat.id] += 1

        # BFS level assignment
        level: Dict[str, int] = {}
        queue: deque[str] = deque()
        for fid, deg in in_degree.items():
            if deg == 0:
                queue.append(fid)
                level[fid] = 0

        while queue:
            node_id = queue.popleft()
            for succ in dependents[node_id]:
                in_degree[succ] -= 1
                new_level = level[node_id] + 1
                level[succ] = max(level.get(succ, 0), new_level)
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(level) != len(self._features):
            return []  # cycle present, cannot group

        # Group by level
        max_level = max(level.values()) if level else 0
        groups: List[List[str]] = []
        for lvl in range(max_level + 1):
            group = sorted(
                [fid for fid, l in level.items() if l == lvl],
                key=lambda fid: self._features[fid].priority,
            )
            if group:
                groups.append(group)
        return groups

    def get_blocking_features(self, feat_id: str) -> List[str]:
        """Return IDs of incomplete features that block the given feature.

        Only direct dependencies whose status is not 'complete' are returned.
        """
        feat = self._features.get(feat_id)
        if feat is None:
            raise KeyError(f"Feature '{feat_id}' not found in the DAG.")
        blockers: List[str] = []
        for dep_id in feat.depends_on:
            dep = self._features.get(dep_id)
            if dep is not None and dep.status != "complete":
                blockers.append(dep_id)
        return blockers

    def get_dependent_features(self, feat_id: str) -> List[str]:
        """Return IDs of features that directly depend on the given feature."""
        if feat_id not in self._features:
            raise KeyError(f"Feature '{feat_id}' not found in the DAG.")
        return [
            f.id for f in self._features.values() if feat_id in f.depends_on
        ]

    def critical_path(self) -> List[str]:
        """Return the longest dependency chain (determines minimum sequential
        execution time).

        Uses dynamic programming on the topological order to find the longest
        path in the DAG.
        """
        if not self._features:
            return []

        try:
            topo_order = self.topological_sort()
        except ValueError:
            return []  # cycle present

        # dist[node] = length of longest path ending at node (in node count)
        dist: Dict[str, int] = {fid: 1 for fid in self._features}
        predecessor: Dict[str, Optional[str]] = {fid: None for fid in self._features}

        for node_id in topo_order:
            feat = self._features[node_id]
            for dep_id in feat.depends_on:
                if dep_id in self._features:
                    candidate = dist[dep_id] + 1
                    if candidate > dist[node_id]:
                        dist[node_id] = candidate
                        predecessor[node_id] = dep_id

        # Find the node with the maximum distance.
        end_node = max(dist, key=lambda fid: dist[fid])

        # Trace back through predecessors.
        path: List[str] = []
        cur: Optional[str] = end_node
        while cur is not None:
            path.append(cur)
            cur = predecessor[cur]
        path.reverse()
        return path

    # ------------------------------------------------------------------ #
    #  DAG mutations
    # ------------------------------------------------------------------ #

    def mark_in_progress(self, feat_id: str, agent_id: Optional[str] = None) -> None:
        """Mark a feature as in-progress, optionally assigning an agent.

        Raises KeyError if the feature does not exist.
        Raises ValueError if the feature is not in 'planned' status.
        """
        feat = self._features.get(feat_id)
        if feat is None:
            raise KeyError(f"Feature '{feat_id}' not found in the DAG.")
        if feat.status != "planned":
            raise ValueError(
                f"Feature '{feat_id}' cannot transition to 'in_progress' "
                f"from '{feat.status}' (must be 'planned')."
            )
        feat.status = "in_progress"
        feat.started_at = datetime.now(timezone.utc).isoformat()
        if agent_id is not None:
            feat.assigned_agent = agent_id

    def mark_complete(self, feat_id: str) -> List[str]:
        """Mark a feature as complete and return the list of newly-ready
        feature IDs (features that just became unblocked).

        Raises KeyError if the feature does not exist.
        Raises ValueError if the feature is not in 'in_progress' status.
        """
        feat = self._features.get(feat_id)
        if feat is None:
            raise KeyError(f"Feature '{feat_id}' not found in the DAG.")
        if feat.status != "in_progress":
            raise ValueError(
                f"Feature '{feat_id}' cannot transition to 'complete' "
                f"from '{feat.status}' (must be 'in_progress')."
            )
        feat.status = "complete"
        feat.completed_at = datetime.now(timezone.utc).isoformat()

        # Determine which features became newly ready.
        return self.get_ready_features()

    def mark_blocked(self, feat_id: str, reason: Optional[str] = None) -> None:
        """Mark a feature as blocked.

        Raises KeyError if the feature does not exist.
        """
        feat = self._features.get(feat_id)
        if feat is None:
            raise KeyError(f"Feature '{feat_id}' not found in the DAG.")
        feat.status = "blocked"
        if reason is not None:
            feat.description = f"{feat.description or ''} [BLOCKED: {reason}]".strip()

    # ------------------------------------------------------------------ #
    #  Statistics
    # ------------------------------------------------------------------ #

    def completion_percentage(self) -> float:
        """Return the percentage of features that are 'complete'."""
        if not self._features:
            return 0.0
        complete = sum(
            1 for f in self._features.values() if f.status == "complete"
        )
        return (complete / len(self._features)) * 100.0

    def status_summary(self) -> Dict[str, int]:
        """Return a count of features in each status."""
        summary: Dict[str, int] = {
            "planned": 0,
            "in_progress": 0,
            "complete": 0,
            "blocked": 0,
            "deferred": 0,
        }
        for feat in self._features.values():
            summary[feat.status] = summary.get(feat.status, 0) + 1
        return summary

    @property
    def feature_count(self) -> int:
        """Total number of features in the DAG."""
        return len(self._features)

    @property
    def is_complete(self) -> bool:
        """True if every feature in the DAG has status 'complete'."""
        if not self._features:
            return True
        return all(f.status == "complete" for f in self._features.values())
